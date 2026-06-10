from firebase_db import (
    get_user_state_ref, get_all_users,
    set_cookie_invalid_flag, get_cookie_invalid_flag
)
from api_client import fetch_campaigns, fetch_clips, fetch_campaign_progress
from bot import send_notification

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

    # ---- Attach progress to each campaign ----
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

    # ---- Campaign alerts (status + progress) ----
    if not is_first_poll:
        for uuid, camp in new_camp_dict.items():
            old = old_campaigns.get(uuid)
            if old is None:
                # New campaign – no explicit notification (you requested no “new campaign” spam)
                pass
            else:
                # 1. Status change (paused / resumed / etc.)
                if camp['status'] != old['status']:
                    emoji = "▶️" if camp['status'] == 'active' else ("⏸️" if camp['status'] == 'paused' else "🔄")
                    await send_notification(chat_id,
                        f"{emoji} Campaign Status Changed\n"
                        f"Campaign: {camp['name']}\n"
                        f"Old: {old['status']} → New: {camp['status']}"
                    )
                    campaigns_changed = True

                # 2. Progress change
                old_progress = old.get('progress') or {}
                new_progress = camp.get('progress') or {}
                old_pct = old_progress.get('percentage') if isinstance(old_progress, dict) else old_progress
                new_pct = new_progress.get('percentage') if isinstance(new_progress, dict) else new_progress

                if old_pct != new_pct and old_pct is not None and new_pct is not None:
                    # Fetch extra progress fields for detail
                    detail = ""
                    if isinstance(new_progress, dict):
                        # Add any other useful fields (example: completed steps)
                        steps = new_progress.get('completedSteps') or new_progress.get('steps')
                        if steps is not None:
                            detail += f"Steps: {steps}\n"
                    await send_notification(chat_id,
                        f"📊 Campaign Progress Updated\n"
                        f"Campaign: {camp['name']}\n"
                        f"Progress: {old_pct}% → {new_pct}%\n"
                        f"{detail}"
                    )
                    campaigns_changed = True
    else:
        campaigns_changed = True   # first poll – store everything silently

    # ---- Clip alerts (status + view count) ----
    clips_changed = False
    if not is_first_poll:
        for clip_id, clip in new_clip_dict.items():
            old = old_clips.get(clip_id)
            if old is None:
                # New clip
                if clip['status'] == 'healthy':
                    await send_notification(chat_id,
                        f"✅ Clip Approved\n"
                        f"Campaign: {clip['campaignName']}\n"
                        f"Video: {clip.get('url', 'No link')}\n"
                        f"Views: {clip['views']}\n"
                        f"Earnings: {clip['earningsCents']} cents"
                    )
                else:
                    await send_notification(chat_id,
                        f"❌ Clip Rejected\n"
                        f"Campaign: {clip['campaignName']}\n"
                        f"Video: {clip.get('url', 'No link')}\n"
                        f"Reason: {clip.get('flagReason', 'No reason given')}"
                    )
                clips_changed = True
            else:
                # Status change
                if clip['status'] != old['status']:
                    if clip['status'] == 'flagged':
                        await send_notification(chat_id,
                            f"❌ Clip Rejected (status change)\n"
                            f"Campaign: {clip['campaignName']}\n"
                            f"Video: {clip.get('url', 'No link')}\n"
                            f"Reason: {clip.get('flagReason', 'No reason given')}"
                        )
                    else:
                        await send_notification(chat_id,
                            f"✅ Clip Approved (was flagged)\n"
                            f"Campaign: {clip['campaignName']}\n"
                            f"Video: {clip.get('url', 'No link')}"
                        )
                    clips_changed = True

                # View count change (per clip)
                if clip.get('views', 0) != old.get('views', 0):
                    await send_notification(chat_id,
                        f"👀 Clip Views Updated\n"
                        f"Campaign: {clip['campaignName']}\n"
                        f"Video: {clip.get('url', 'No link')}\n"
                        f"Old: {old.get('views', 0)} → New: {clip.get('views', 0)}"
                    )
                    clips_changed = True
    else:
        clips_changed = True   # first poll – store silently

    # ---- Overall stats (earnings / total views) ----
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

    # ---- Write to Firebase ----
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


async def check_all_users():
    users = get_all_users()
    for chat_id in users:
        await check_changes_for_user(chat_id)