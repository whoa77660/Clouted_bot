import asyncio
import time
import logging
from firebase_db import (
    get_user_state_ref, get_all_users,
    set_cookie_invalid_flag, get_cookie_invalid_flag,
    db_get, db_set
)
from api_client import fetch_campaigns, fetch_clips, fetch_campaign_progress
from config import OWNER_ID

CLIP_FETCH_LIMIT = 100

# ─── Global milestone deduplication ─────────────────
def _milestone_key(uuid, milestone):
    return f"{uuid}_{milestone}"
def _already_broadcasted(uuid, milestone):
    return db_get(f"broadcasted_milestones/{_milestone_key(uuid, milestone)}") == True
def _mark_broadcasted(uuid, milestone):
    db_set(f"broadcasted_milestones/{_milestone_key(uuid, milestone)}", True)

async def send_notification(psid, text):
    # Lazy import to avoid circular dependency (Critical Bug 1)
    from messenger_app import send_messenger_message
    await asyncio.to_thread(send_messenger_message, psid, text)

async def broadcast_to_all(users, text):
    for uid in users:
        try:
            await send_notification(uid, text)
        except Exception as e:
            logging.error(f"Broadcast error to {uid}: {e}")

async def check_changes_for_user(psid):
    was_invalid = get_cookie_invalid_flag(psid)
    try:
        camps = fetch_campaigns(psid)
        clips = fetch_clips(psid, page_size=CLIP_FETCH_LIMIT)
    except Exception as e:
        err = str(e)
        logging.error(f"Fetch failed for {psid}: {err}")
        if '401' in err or 'expired' in err.lower() or 'cookie' in err.lower():
            if not was_invalid:
                set_cookie_invalid_flag(psid, True)
                await send_notification(psid,
                    "⚠️ Your Clouted cookie is invalid or expired.\n"
                    "Please update it with /setcookie to resume monitoring."
                )
        return
    if was_invalid:
        set_cookie_invalid_flag(psid, False)
        await send_notification(psid, "✅ Your cookie is working again. Monitoring resumed.")
    if not isinstance(camps, list) or not isinstance(clips, list):
        return

    # Performance: fetch campaign progress concurrently (Critical Performance Issue)
    async def fetch_progress(camp):
        uuid = camp.get('uuid')
        if uuid:
            # run the synchronous call in a thread to avoid blocking
            return await asyncio.to_thread(fetch_campaign_progress, psid, uuid)
        return None

    progress_tasks = [fetch_progress(c) for c in camps]
    progress_results = await asyncio.gather(*progress_tasks, return_exceptions=True)
    for camp, progress in zip(camps, progress_results):
        if isinstance(progress, Exception):
            logging.error(f"Progress fetch error for campaign {camp.get('name')}: {progress}")
        else:
            camp['progress'] = progress

    old_camps = get_user_state_ref(psid, 'campaigns').get() or {}
    old_clips = get_user_state_ref(psid, 'clips').get() or {}
    old_stats = get_user_state_ref(psid, 'stats').get() or {}
    first_poll_done = get_user_state_ref(psid, 'first_poll_done').get() or False
    is_first = not first_poll_done and not old_camps and not old_clips

    new_camp_dict = {c['uuid']: c for c in camps}
    new_clip_dict = {str(c.get('id')): c for c in clips}
    all_users = get_all_users()
    camps_changed = False

    if not is_first:
        for uuid, camp in new_camp_dict.items():
            old = old_camps.get(uuid)
            name = camp.get('name', 'Unknown')
            status = camp.get('status', '?')
            if old is None:
                await broadcast_to_all(all_users,
                    f"🆕 New Campaign\nName: {name}\nStatus: {status}\nCPM: {camp.get('cpm','?')}\nParticipants: {camp.get('participantCount','?')}")
                camps_changed = True
                camp['last_budget_milestone'] = 0
            else:
                if camp['status'] != old['status']:
                    emoji = "▶️" if camp['status'] == 'active' else ("⏸️" if camp['status'] == 'paused' else "🔄")
                    await broadcast_to_all(all_users,
                        f"{emoji} Campaign Status Changed\nName: {name}\nOld: {old['status']} → New: {camp['status']}")
                    camps_changed = True
                op = old.get('progress')
                np = camp.get('progress')
                if op and np:
                    opct = op.get('percentage') if isinstance(op, dict) else op
                    npct = np.get('percentage') if isinstance(np, dict) else np
                    if opct != npct:
                        await broadcast_to_all(all_users,
                            f"📊 Campaign Progress Updated\nCampaign: {name}\nProgress: {opct}% → {npct}%")
                        camps_changed = True
                budget = camp.get('budget')
                cpm = camp.get('cpm')
                views = camp.get('viewCount')
                if budget and cpm and views and budget > 0:
                    spent = (views * cpm) / 1000
                    pct = (spent / budget) * 100
                    milestone = int(pct // 10) * 10
                    last_milestone = old.get('last_budget_milestone', 0)
                    if milestone > last_milestone and not _already_broadcasted(uuid, milestone):
                        _mark_broadcasted(uuid, milestone)
                        await broadcast_to_all(all_users,
                            f"💰 Budget Milestone Reached\nCampaign: {name}\n🎯 Crossed {milestone}% milestone\n📊 Current usage: {pct:.1f}%\n💸 Spent: ${spent/100:.2f} / ${budget/100:.2f}")
                        camps_changed = True
                    camp['last_budget_milestone'] = milestone
                else:
                    camp['last_budget_milestone'] = old.get('last_budget_milestone', 0)
    else:
        camps_changed = True
        for camp in new_camp_dict.values():
            camp['last_budget_milestone'] = 0

    clips_changed = False
    if not is_first:
        for clip_id, clip in new_clip_dict.items():
            old = old_clips.get(clip_id)
            status = clip.get('status', 'unknown')
            campaign_name = clip.get('campaignName', 'Unknown')
            if old is None:
                emoji, label = {
                    'healthy':('✅','Clip Approved'),'flagged':('❌','Clip Rejected'),
                    'pending':('📝','Clip Pending Review'),'rejected':('❌','Clip Rejected')
                }.get(status,('❓',f'Clip Status: {status}'))
                text = f"{emoji} {label}\nCampaign: {campaign_name}\nVideo: {clip.get('url','No link')}\nViews: {clip.get('views',0)}\nEarnings: ${clip.get('earningsCents',0)/100:.2f}"
                if status == 'flagged':
                    text += f"\nReason: {clip.get('flagReason','No reason given')}"
                await send_notification(psid, text)
                clips_changed = True
            else:
                if clip['status'] != old['status']:
                    old_s, new_s = old.get('status','?'), clip.get('status','?')
                    if new_s == 'flagged':
                        await send_notification(psid, f"❌ Clip Rejected (was {old_s})\nCampaign: {campaign_name}\nVideo: {clip.get('url','No link')}\nReason: {clip.get('flagReason','No reason given')}")
                    elif new_s == 'healthy':
                        await send_notification(psid, f"✅ Clip Approved (was {old_s})\nCampaign: {campaign_name}\nVideo: {clip.get('url','No link')}")
                    else:
                        await send_notification(psid, f"🔄 Clip Status Changed\nCampaign: {campaign_name}\nVideo: {clip.get('url','No link')}\nOld: {old_s} → New: {new_s}")
                    clips_changed = True
                # View spam reduction: only notify if change >= 500
                old_views = old.get("views", 0)
                new_views = clip.get("views", 0)
                if new_views - old_views >= 500:
                    emoji = {"healthy":"✅","flagged":"❌","pending":"🕒","rejected":"❌"}.get(status,"❓")
                    await send_notification(psid, f"👀 Clip Views Updated\nCampaign: {campaign_name}\nVideo: {clip.get('url','No link')}\nStatus: {emoji} {status}\nOld: {old_views} → New: {new_views}")
                    clips_changed = True
    else:
        clips_changed = True

    total_earn = sum(c.get('earningsCents',0) for c in clips)
    total_views = sum(c.get('views',0) for c in clips)
    total_clips = len(clips)

    if not is_first and (total_earn != old_stats.get('totalEarningsCents') or total_views != old_stats.get('totalViews') or total_clips != old_stats.get('totalClips')):
        await send_notification(psid, f"💰 Earnings Updated\nOld: ${old_stats.get('totalEarningsCents',0)/100:.2f}\nNew: ${total_earn/100:.2f}\nViews: {old_stats.get('totalViews',0)} → {total_views}\nClips: {old_stats.get('totalClips',0)} → {total_clips}")

    if camps_changed:
        get_user_state_ref(psid, 'campaigns').set(new_camp_dict)
    if clips_changed:
        get_user_state_ref(psid, 'clips').set(new_clip_dict)
    get_user_state_ref(psid, 'stats').set({
        'totalViews': total_views,
        'totalClips': total_clips,
        'totalEarningsCents': total_earn
    })
    get_user_state_ref(psid, 'first_poll_done').set(True)

    print(f"[MONITOR] User {psid}: campaigns={len(camps)}, clips={len(clips)}")


async def check_all_users():
    users = get_all_users()
    print(f"[MONITOR] Checking {len(users)} user(s)...")
    if not users:
        return

    # Run all users concurrently (Performance Patch)
    tasks = [check_changes_for_user(uid) for uid in users]
    await asyncio.gather(*tasks, return_exceptions=True)
