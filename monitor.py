from firebase_db import (
    get_user_state_ref, get_all_users,
    set_cookie_invalid_flag, get_cookie_invalid_flag
)
from api_client import fetch_campaigns, fetch_clips, fetch_campaign_progress
from bot import send_notification
from config import OWNER_ID

async def check_changes_for_user(chat_id: int):
    was_invalid = get_cookie_invalid_flag(chat_id)

    try:
        fresh_campaigns = fetch_campaigns(chat_id)
        fresh_clips = fetch_clips(chat_id)
    except Exception as e:
        error_msg = str(e)
        if '401' in error_msg or 'expired' in error_msg.lower() or 'cookie' in error_msg.lower():
            if not was_invalid:
                set_cookie_invalid_flag(chat_id, True)
                await send_notification(chat_id,
                    "⚠️ Your Clouted cookie is invalid or expired.\n"
                    "Please update it with /setcookie to resume monitoring."
                )
        return

    if was_invalid:
        set_cookie_invalid_flag(chat_id, False)
        await send_notification(chat_id, "✅ Your cookie is working again. Monitoring resumed.")

    if not isinstance(fresh_campaigns, list) or not isinstance(fresh_clips, list):
        return

    # Attach progress to campaigns (no notification)
    for camp in fresh_campaigns:
        uuid = camp.get('uuid')
        if uuid:
            progress = fetch_campaign_progress(chat_id, uuid)
            camp['progress'] = progress

    old_campaigns = get_user_state_ref(chat_id, 'campaigns').get() or {}
    old_clips = get_user_state_ref(chat_id, 'clips').get() or {}
    old_stats = get_user_state_ref(chat_id, 'stats').get() or {}
    first_poll_done_flag = get_user_state_ref(chat_id, 'first_poll_done').get() or False

    is_first_poll = not first_poll_done_flag and not old_campaigns and not old_clips

    new_camp_dict = {c['uuid']: c for c in fresh_campaigns}
    new_clip_dict = {str(c.get('id')): c for c in fresh_clips}

    campaigns_changed = False

    # ---- CAMPAIGN NOTIFICATIONS (status + progress + budget milestones) ----
    if not is_first_poll:
        for uuid, camp in new_camp_dict.items():
            old = old_campaigns.get(uuid)
            if old is None:
                # New campaign
                await send_notification(chat_id,
                    f"🆕 New Campaign\n"
                    f"Name: {camp['name']}\n"
                    f"Status: {camp['status']}\n"
                    f"CPM: {camp.get('cpm','?')}\n"
                    f"Participants: {camp.get('participantCount','?')}"
                )
                campaigns_changed = True
                # Initialize budget milestone tracking for the new campaign
                camp['last_budget_milestone'] = 0
            else:
                # Status change
                if camp['status'] != old['status']:
                    emoji = "▶️" if camp['status'] == 'active' else ("⏸️" if camp['status'] == 'paused' else "🔄")
                    await send_notification(chat_id,
                        f"{emoji} Campaign Status Changed\n"
                        f"Name: {camp['name']}\n"
                        f"Old: {old['status']} → New: {camp['status']}"
                    )
                    campaigns_changed = True

                # Progress change (from campaign.progress)
                old_progress = old.get('progress')
                new_progress = camp.get('progress')
                if old_progress and new_progress:
                    old_pct = old_progress.get('percentage') if isinstance(old_progress, dict) else old_progress
                    new_pct = new_progress.get('percentage') if isinstance(new_progress, dict) else new_progress
                    if old_pct != new_pct:
                        await send_notification(chat_id,
                            f"📊 Campaign Progress Updated\n"
                            f"Campaign: {camp['name']}\n"
                            f"Progress: {old_pct}% → {new_pct}%"
                        )
                        campaigns_changed = True

                # --- Budget Milestone Calculation ---
                budget = camp.get('budget')
                cpm = camp.get('cpm')
                views = camp.get('viewCount')
                if budget and cpm and views and budget > 0:
                    # Budget spent = (views * cpm) / 1000
                    budget_spent = (views * cpm) / 1000
                    budget_percent = (budget_spent / budget) * 100
                    current_milestone = int(budget_percent // 10) * 10  # 0,10,20,...
                    last_milestone = old.get('last_budget_milestone', 0)

                    if current_milestone > last_milestone:
                        await send_notification(chat_id,
                            f"💰 Budget Milestone Reached\n"
                            f"Campaign: {camp['name']}\n"
                            f"{current_milestone}% of budget used\n"
                            f"Spent: ${budget_spent:.2f} / ${budget}"
                        )
                        camp['last_budget_milestone'] = current_milestone
                        campaigns_changed = True
                else:
                    camp['last_budget_milestone'] = old.get('last_budget_milestone', 0)
    else:
        campaigns_changed = True
        # First poll – initialize budget milestone to 0
        for camp in new_camp_dict.values():
            camp['last_budget_milestone'] = 0

    # ---- CLIP NOTIFICATIONS (unchanged) ----
    clips_changed = False
    if not is_first_poll:
        for clip_id, clip in new_clip_dict.items():
            old = old_clips.get(clip_id)
            if old is None:
                status = clip.get('status', 'unknown')
                emoji, label = {
                    'healthy':  ('✅', 'Clip Approved'),
                    'flagged':  ('❌', 'Clip Rejected'),
                    'pending':  ('📝', 'Clip Pending Review'),
                    'rejected': ('❌', 'Clip Rejected'),
                }.get(status, ('❓', f'Clip Status: {status}'))
                text = (
                    f"{emoji} {label}\n"
                    f"Campaign: {clip['campaignName']}\n"
                    f"Video: {clip.get('url', 'No link')}\n"
                    f"Views: {clip.get('views', 0)}\n"
                    f"Earnings: {clip.get('earningsCents', 0)} cents"
                )
                if status == 'flagged':
                    text += f"\nReason: {clip.get('flagReason', 'No reason given')}"
                await send_notification(chat_id, text)
                clips_changed = True
            else:
                if clip['status'] != old['status']:
                    old_status = old.get('status', '?')
                    new_status = clip.get('status', '?')
                    if new_status == 'flagged':
                        await send_notification(chat_id,
                            f"❌ Clip Rejected (was {old_status})\n"
                            f"Campaign: {clip['campaignName']}\n"
                            f"Video: {clip.get('url', 'No link')}\n"
                            f"Reason: {clip.get('flagReason', 'No reason given')}"
                        )
                    elif new_status == 'healthy':
                        await send_notification(chat_id,
                            f"✅ Clip Approved (was {old_status})\n"
                            f"Campaign: {clip['campaignName']}\n"
                            f"Video: {clip.get('url', 'No link')}"
                        )
                    else:
                        await send_notification(chat_id,
                            f"🔄 Clip Status Changed\n"
                            f"Campaign: {clip['campaignName']}\n"
                            f"Video: {clip.get('url', 'No link')}\n"
                            f"Old: {old_status} → New: {new_status}"
                        )
                    clips_changed = True
                if clip.get('views', 0) != old.get('views', 0):
                    await send_notification(chat_id,
                        f"👀 Clip Views Updated\n"
                        f"Campaign: {clip['campaignName']}\n"
                        f"Video: {clip.get('url', 'No link')}\n"
                        f"Old: {old.get('views', 0)} → New: {clip.get('views', 0)}"
                    )
                    clips_changed = True
    else:
        clips_changed = True

    # ---- OVERALL STATS ----
    total_earnings = sum(c.get('earningsCents', 0) for c in fresh_clips)
    total_views = sum(c.get('views', 0) for c in fresh_clips)
    total_clips = len(fresh_clips)

    if not is_first_poll and (total_earnings != old_stats.get('totalEarningsCents') or
        total_views != old_stats.get('totalViews') or
        total_clips != old_stats.get('totalClips')):
        await send_notification(chat_id,
            f"💰 Earnings Updated\n"
            f"Old: {old_stats.get('totalEarningsCents', 0)} cents\n"
            f"New: {total_earnings} cents\n"
            f"Views: {old_stats.get('totalViews', 0)} → {total_views}\n"
            f"Clips: {old_stats.get('totalClips', 0)} → {total_clips}"
        )

    # ---- SAVE TO FIREBASE ----
    if campaigns_changed:
        get_user_state_ref(chat_id, 'campaigns').set(new_camp_dict)
    if clips_changed:
        get_user_state_ref(chat_id, 'clips').set(new_clip_dict)
    get_user_state_ref(chat_id, 'stats').set({
        'totalViews': total_views,
        'totalClips': total_clips,
        'totalEarningsCents': total_earnings
    })
    get_user_state_ref(chat_id, 'first_poll_done').set(True)

    print(f"[MONITOR] User {chat_id}: campaigns={len(fresh_campaigns)}, clips={len(fresh_clips)}")


async def check_all_users():
    users = get_all_users()
    print(f"[MONITOR] Checking {len(users)} user(s)...")
    for chat_id in users:
        await check_changes_for_user(chat_id)

    # ---- Send summary to owner ----
    try:
        if users:
            first_user = next(iter(users))
            camps = get_user_state_ref(first_user, 'campaigns').get() or {}
            clips = get_user_state_ref(first_user, 'clips').get() or {}
            msg = f"✅ Monitor check completed\nCampaigns: {len(camps)}\nClips: {len(clips)}"
        else:
            msg = "✅ Monitor check completed\nNo users linked."
        await send_notification(OWNER_ID, msg)
    except Exception as e:
        print(f"Failed to send monitor summary: {e}")
