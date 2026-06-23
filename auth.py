import os
import time
import asyncio
import threading
import re
import html as html_lib
import traceback
import json
import logging
from collections import defaultdict
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter

from config import (
    PAGE_ACCESS_TOKEN, VERIFY_TOKEN, OWNER_ID, RENDER_URL,
    FIREBASE_DATABASE_URL, CLOUTED_BASE_URL
)
from firebase_db import *
from auth import validate_and_save_cookie
from api_client import fetch_campaigns, fetch_clips, fetch_campaign_progress

load_dotenv()

# Patch 13: Suppress Flask request logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

session = requests.Session()
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
session.mount("https://", adapter)

HELP_TEXT = """✨ *Commands:*
/start
menu
/setcookie <cookie>
profile
stats
campaigns
videos
download
language
help"""

def call_send_api(payload):
    url = "https://graph.facebook.com/v25.0/me/messages"
    try:
        resp = session.post(url, params={"access_token": PAGE_ACCESS_TOKEN}, json=payload, timeout=10)
        return resp.json()
    except Exception as e:
        logging.error(f"Send API error: {e}")
        return None

def send_messenger_message(psid, text):
    clean_text = text.replace("<br>", "\n").replace("<b>", "").replace("</b>", "")
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
    payload = {"recipient": {"id": psid}, "message": {"text": clean_text}}
    return call_send_api(payload)

def send_image(psid, image_url, caption=None):
    payload = {
        "recipient": {"id": psid},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": True}
            }
        }
    }
    if caption:
        payload["message"]["attachment"]["payload"]["caption"] = caption
    return call_send_api(payload)

def send_button_template(psid, text, buttons):
    payload = {
        "recipient": {"id": psid},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text,
                    "buttons": buttons
                }
            }
        }
    }
    return call_send_api(payload)

def send_quick_replies(psid, text, quick_replies):
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text, "quick_replies": quick_replies}
    }
    return call_send_api(payload)

def send_text_file(psid, filename, content):
    url = "https://graph.facebook.com/v25.0/me/messages"
    data = {
        "recipient": json.dumps({"id": psid}),
        "message": json.dumps({
            "attachment": {
                "type": "file",
                "payload": {}
            }
        })
    }
    files = {"filedata": (filename, content, "text/plain")}
    try:
        resp = session.post(url, params={"access_token": PAGE_ACCESS_TOKEN}, data=data, files=files, timeout=30)
        print(f"[FILE SEND] {resp.status_code} {resp.text[:200]}")
        return resp.json()
    except Exception as e:
        logging.error(f"File send error: {e}")
        return None

def send_main_menu(psid):
    buttons1 = [
        {"type": "postback", "title": t('stats_button', psid), "payload": "STATS"},
        {"type": "postback", "title": t('campaigns_button', psid), "payload": "CAMPAIGNS"},
        {"type": "postback", "title": t('videos_button', psid), "payload": "VIDEOS"},
    ]
    buttons2 = [
        {"type": "postback", "title": t('profile_button', psid), "payload": "PROFILE"},
        {"type": "postback", "title": t('lang_button', psid), "payload": "LANG"},
        {"type": "postback", "title": t('help_button', psid), "payload": "HELP"},
    ]
    buttons3 = [
        {"type": "postback", "title": t('download_button', psid), "payload": "DOWNLOAD"}
    ]
    send_button_template(psid, "📋 Main Menu (1/3)", buttons1)
    send_button_template(psid, "📋 Main Menu (2/3)", buttons2)
    send_button_template(psid, "📋 Main Menu (3/3)", buttons3)

def send_message_then_menu(psid, text):
    send_messenger_message(psid, text)
    send_main_menu(psid)

def get_lang(psid):
    settings = get_user_settings_ref(psid).get() or {}
    return settings.get('lang', 'en') or 'en'

def set_lang(psid, lang):
    get_user_settings_ref(psid).update({'lang': lang})

T = {
    'en': {
        'welcome': "👋 Welcome! I monitor your Clouted account.\nUse /setcookie <your_cookie> to link your account.",
        'help': HELP_TEXT,
        'lang_button': "🌐 Language", 'stats_button': "📊 Stats", 'campaigns_button': "📋 Campaigns",
        'videos_button': "🎬 My Videos", 'profile_button': "👤 Profile", 'help_button': "ℹ️ Help",
        'download_button': "📥 Download Links",
        'select_campaign': "📁 Select a campaign to view its videos:",
        'videos_empty': "You have no clips yet.",
        'download_empty': "No campaigns with videos found.",
        'download_success': "✅ File sent!",
        'stats_no_cookie': "You need to set your cookie first. Use /setcookie.",
        'profile_no_cookie': "You haven't linked an account. Use /setcookie.",
        'cookie_invalid_warn': "⚠️ Your cookie is invalid/expired. Please update it with /setcookie.",
        'total_earnings_campaign': "💰 Total earnings from this campaign",
        'earnings': "Earnings", 'video_status_title': "Clip Status",
        'campaign_card_status': "Status", 'stats_views': "Total Views",
        'campaign_card_budget': "Budget", 'campaign_card_cpm': "CPM", 'campaign_card_payout': "Payout",
        'campaign_card_participants': "Participants", 'campaign_card_views': "Views",
        'campaign_card_platforms': "Platforms", 'campaign_card_start': "Start", 'campaign_card_end': "End",
        'campaign_card_remarks': "Remarks", 'campaign_card_budget_used': "📊 Budget Used"
    },
    'bn': {
        'welcome': "👋 স্বাগতম! আমি আপনার Clouted অ্যাকাউন্ট মনিটর করি।",
        'help': HELP_TEXT,
        'lang_button': "🌐 ভাষা", 'stats_button': "📊 পরিসংখ্যান", 'campaigns_button': "📋 ক্যাম্পেইন",
        'videos_button': "🎬 আমার ভিডিও", 'profile_button': "👤 প্রোফাইল", 'help_button': "ℹ️ সাহায্য",
        'download_button': "📥 লিঙ্ক ডাউনলোড",
        'select_campaign': "📁 একটি ক্যাম্পেইন নির্বাচন করুন:", 'videos_empty': "আপনার কোনো ক্লিপ নেই।",
        'download_empty': "কোনো ক্যাম্পেইন পাওয়া যায়নি।",
        'download_success': "✅ ফাইল পাঠানো হয়েছে!",
        'stats_no_cookie': "আগে কুকি সেট করতে হবে। /setcookie ব্যবহার করুন।",
        'profile_no_cookie': "আপনি অ্যাকাউন্ট লিঙ্ক করেননি। /setcookie ব্যবহার করুন।",
        'cookie_invalid_warn': "⚠️ আপনার কুকি অবৈধ/মেয়াদোত্তীর্ণ। /setcookie দিয়ে আপডেট করুন।",
        'total_earnings_campaign': "💰 এই ক্যাম্পেইন থেকে মোট আয়",
        'earnings': "আয়", 'video_status_title': "ক্লিপ অবস্থা",
        'campaign_card_status': "অবস্থা", 'stats_views': "মোট ভিউ",
        'campaign_card_budget': "বাজেট", 'campaign_card_cpm': "CPM", 'campaign_card_payout': "পেআউট",
        'campaign_card_participants': "অংশগ্রহণকারী", 'campaign_card_views': "ভিউ",
        'campaign_card_platforms': "প্ল্যাটফর্ম", 'campaign_card_start': "শুরু", 'campaign_card_end': "শেষ",
        'campaign_card_remarks': "মন্তব্য", 'campaign_card_budget_used': "📊 বাজেট ব্যবহৃত"
    }
}

def t(key, psid):
    return T.get(get_lang(psid), T['en']).get(key, T['en'][key])

def cents_to_dollar(c):
    try: return f"${int(c)/100:.2f}"
    except: return "?"

def format_campaign_card(camp, psid):
    emoji = "🟢" if camp.get('status') == 'active' else ("⏸️" if camp.get('status') == 'paused' else "🔄")
    name = camp.get('name', 'Unknown')
    status = camp.get('status', '?').capitalize()
    budget = cents_to_dollar(camp.get('budget', 0))
    buyer = cents_to_dollar(camp.get('buyerBudget', 0))
    cpm = cents_to_dollar(camp.get('cpm', 0))
    min_p = cents_to_dollar(camp.get('minPayout', 0))
    max_p = cents_to_dollar(camp.get('maxPayout', 0))
    participants = camp.get('participantCount', '?')
    views = camp.get('viewCount', '?')
    platforms = ', '.join(camp.get('platforms', [])) or 'N/A'
    start = camp.get('startAt', '?')
    end = camp.get('endAt', 'ongoing') or 'ongoing'
    remarks = camp.get('remarks', '')
    if len(remarks) > 200:
        remarks = remarks[:200] + "..."

    budget_val = camp.get('budget', 0)
    cpm_val = camp.get('cpm', 0)
    views_val = camp.get('viewCount', 0)
    if budget_val and cpm_val and views_val:
        spent = (views_val * cpm_val) / 1000
        percent = (spent / budget_val) * 100
        budget_used_str = f"{percent:.1f}%"
    else:
        budget_used_str = "N/A"

    return (
        f"{emoji} {name}\n"
        f"{t('campaign_card_status', psid)}: {status}\n"
        f"💰 {t('campaign_card_budget', psid)}: {budget} (buyer: {buyer})\n"
        f"{t('campaign_card_budget_used', psid)}: {budget_used_str}\n"
        f"💵 {t('campaign_card_cpm', psid)}: {cpm} | {t('campaign_card_payout', psid)}: {min_p}–{max_p}\n"
        f"👥 {t('campaign_card_participants', psid)}: {participants}\n"
        f"👀 {t('campaign_card_views', psid)}: {views}\n"
        f"📱 {t('campaign_card_platforms', psid)}: {platforms}\n"
        f"📅 {t('campaign_card_start', psid)}: {start}\n"
        f"🏁 {t('campaign_card_end', psid)}: {end}\n"
        f"📝 {t('campaign_card_remarks', psid)}: {remarks if remarks else 'None'}\n"
    )

# ─── Handlers ─────────────────────────────────
def handle_postback(psid, payload):
    if payload == "START":
        send_message_then_menu(psid, t('welcome', psid))
    elif payload == "MENU":
        send_main_menu(psid)
    elif payload == "LANG":
        send_quick_replies(psid, "Choose language:", [
            {"content_type": "text", "title": "English", "payload": "LANG_EN"},
            {"content_type": "text", "title": "বাংলা", "payload": "LANG_BN"}
        ])
    elif payload in ("LANG_EN", "LANG_BN"):
        set_lang(psid, 'en' if payload == "LANG_EN" else 'bn')
        send_message_then_menu(psid, "Language set.")
    elif payload == "STATS":
        show_stats(psid)
    elif payload == "CAMPAIGNS":
        show_campaigns(psid)
    elif payload == "VIDEOS":
        show_video_campaigns(psid)
    elif payload == "DOWNLOAD":
        show_download_campaigns(psid)
    elif payload == "PROFILE":
        show_profile(psid)
    elif payload == "HELP":
        send_message_then_menu(psid, t('help', psid))
    elif payload.startswith("VIDEO_CAMP_"):
        show_videos_for_campaign(psid, payload[11:])
    elif payload.startswith("VIDEOPAGE_"):
        parts = payload.split("_", 2)
        if len(parts) == 3:
            show_videos_for_campaign(psid, parts[1], int(parts[2]))
    elif payload.startswith("DOWNLOAD_CAMP_"):
        generate_download_file(psid, payload[14:])

def handle_message(psid, text):
    text = text.strip()
    cmd = text.lower()
    if cmd in ("/start", "start"):
        send_message_then_menu(psid, t('welcome', psid))
    elif text.startswith("/setcookie"):
        parts = text.split(" ", 1)
        if len(parts) == 2:
            ok, msg = validate_and_save_cookie(psid, parts[1].strip())
            send_message_then_menu(psid, msg)
        else:
            send_message_then_menu(psid, "Usage: /setcookie <cookie>")
    elif cmd == "menu":
        send_main_menu(psid)
    elif cmd == "profile":
        show_profile(psid)
    elif cmd == "stats":
        show_stats(psid)
    elif cmd == "campaigns":
        show_campaigns(psid)
    elif cmd == "videos":
        show_video_campaigns(psid)
    elif cmd == "download":
        show_download_campaigns(psid)
    elif cmd == "language":
        send_quick_replies(psid, "Choose language:", [
            {"content_type": "text", "title": "English", "payload": "LANG_EN"},
            {"content_type": "text", "title": "বাংলা", "payload": "LANG_BN"}
        ])
    elif cmd in ("/myid", "myid"):
        send_message_then_menu(psid, f"Your PSID: {psid}")
    else:
        send_message_then_menu(psid, "Unknown command. Type /start")

def show_stats(psid):
    s = get_user_state_ref(psid, 'stats').get() or {}
    text = f"📊 Stats\nViews: {s.get('totalViews',0)}\nClips: {s.get('totalClips',0)}\nEarnings: {cents_to_dollar(s.get('totalEarningsCents',0))}"
    send_message_then_menu(psid, text)

def show_campaigns(psid):
    camps = fetch_campaigns(psid)
    if not camps:
        send_message_then_menu(psid, "No campaigns available right now.")
        return
    # Newest first by startAt
    camps.sort(key=lambda c: c.get('startAt', '0'), reverse=True)
    for camp in camps:
        card = format_campaign_card(camp, psid)
        thumbnail = camp.get('thumbnail')
        if thumbnail and thumbnail.startswith('http'):
            send_image(psid, thumbnail)
            send_messenger_message(psid, card)
        else:
            send_messenger_message(psid, card)
    send_main_menu(psid)

def show_video_campaigns(psid):
    clips_dict = get_user_state_ref(psid, 'clips').get() or {}
    if not clips_dict:
        send_message_then_menu(psid, t('videos_empty', psid))
        return

    grouped = defaultdict(list)
    for clip in clips_dict.values():
        grouped[clip.get('campaignName', 'Unknown')].append(clip)

    # Sort campaigns by most recent clip
    def latest_clip_date(campaign_name):
        clips = grouped[campaign_name]
        newest = max(clips, key=lambda c: c.get('createdAt', '') or '')
        return newest.get('createdAt', '') or ''

    sorted_campaigns = sorted(grouped.keys(), key=latest_clip_date, reverse=True)

    buttons = []
    for name in sorted_campaigns:
        buttons.append({"type": "postback", "title": name, "payload": f"VIDEO_CAMP_{name}"})
    for i in range(0, len(buttons), 3):
        chunk = buttons[i:i+3]
        send_button_template(psid, t('select_campaign', psid) if i == 0 else "More campaigns", chunk)
    send_main_menu(psid)

def show_videos_for_campaign(psid, campaign_name, offset=0):
    clips_dict = get_user_state_ref(psid, 'clips').get() or {}
    campaigns_dict = get_user_state_ref(psid, 'campaigns').get() or {}

    campaign_clips = [c for c in clips_dict.values() if c.get('campaignName') == campaign_name]
    campaign_clips.sort(key=lambda c: c.get('createdAt', ''), reverse=True)

    if not campaign_clips:
        send_message_then_menu(psid, "No videos in this campaign.")
        return

    total_clips = len(campaign_clips)
    total_earnings_cents = sum(c.get('earningsCents', 0) for c in campaign_clips)
    total_earnings = f"${total_earnings_cents / 100:.2f}"

    campaign_info = next((cdata for cdata in campaigns_dict.values() if cdata.get('name') == campaign_name), None)

    header = f"📌 {campaign_name}\n{t('total_earnings_campaign', psid)}: {total_earnings}"
    if campaign_info and campaign_info.get('thumbnail'):
        send_image(psid, campaign_info['thumbnail'], caption=header)
    else:
        send_messenger_message(psid, header)

    PAGE_SIZE = 12
    start = offset
    end = min(start + PAGE_SIZE, total_clips)
    page_clips = campaign_clips[start:end]

    for clip in page_clips:
        status = clip.get('status', 'unknown')
        emoji = {"healthy":"✅", "flagged":"❌", "pending":"🕒", "rejected":"❌"}.get(status, "❓")
        views = clip.get('views', 0)
        earnings = cents_to_dollar(clip.get('earningsCents', 0))
        url = clip.get('url', '')
        text = (
            f"{emoji} {t('video_status_title', psid)}\n"
            f"{t('campaign_card_status', psid)}: {status}\n"
            f"{t('stats_views', psid)}: {views}\n"
            f"{t('earnings', psid)}: {earnings}"
        )
        if url:
            text += f"\n🔗 {url}"
        send_messenger_message(psid, text)

    if end < total_clips:
        remaining = total_clips - end
        button = {"type": "postback", "title": f"Show more ({remaining} left)", "payload": f"VIDEOPAGE_{campaign_name}_{end}"}
        send_button_template(psid, "More videos available", [button])
        print(f"[DEBUG] Sent 'Show more' button for campaign '{campaign_name}'")
    else:
        print(f"[DEBUG] No more pages for campaign '{campaign_name}'")

    send_main_menu(psid)

def show_profile(psid):
    settings = get_user_settings_ref(psid).get() or {}
    if not settings.get('userId'):
        send_message_then_menu(psid, t('profile_no_cookie', psid))
        return
    username = settings.get('username', 'Unknown')
    user_id = settings.get('userId', '?')
    org = settings.get('organizationId', '?')
    expires = settings.get('expiresAt', '?')
    text = (
        f"👤 Profile\n"
        f"Username: {username}\n"
        f"User ID: {user_id}\n"
        f"Organization: {org}\n"
        f"Session expires: {expires}"
    )
    send_message_then_menu(psid, text)

# ─── Download feature ────────────────────────
def show_download_campaigns(psid):
    clips_dict = get_user_state_ref(psid, 'clips').get() or {}
    if not clips_dict:
        send_message_then_menu(psid, t('download_empty', psid))
        return
    grouped = defaultdict(list)
    for clip in clips_dict.values():
        grouped[clip.get('campaignName', 'Unknown')].append(clip)
    buttons = []
    for name in grouped:
        buttons.append({"type": "postback", "title": name, "payload": f"DOWNLOAD_CAMP_{name}"})
    for i in range(0, len(buttons), 3):
        chunk = buttons[i:i+3]
        send_button_template(psid, t('select_campaign', psid) if i == 0 else "More campaigns", chunk)
    send_main_menu(psid)

def generate_download_file(psid, campaign_name):
    clips_dict = get_user_state_ref(psid, 'clips').get() or {}
    campaign_clips = [c for c in clips_dict.values() if c.get('campaignName') == campaign_name]
    if not campaign_clips:
        send_message_then_menu(psid, "No videos found in this campaign.")
        return
    campaign_clips.sort(key=lambda c: c.get('createdAt', ''), reverse=True)
    lines = [f"Campaign: {campaign_name}\n"]
    for idx, clip in enumerate(campaign_clips, 1):
        url = clip.get('url', '')
        if url:
            lines.append(f"{idx}. {url}")
        else:
            lines.append(f"{idx}. (no link)")
    content = "\n".join(lines)
    filename = f"{campaign_name.replace(' ', '_')}_links.txt"
    result = send_text_file(psid, filename, content)
    if result and result.get("message_id"):
        send_message_then_menu(psid, t('download_success', psid))
    else:
        send_message_then_menu(psid, "❌ Failed to send file. Please try again.")

# ─── Flask ───────────────────────────────────
@app.route("/")
def home():
    return {"status": "ok", "bot": "Clouted Messenger Bot"}

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            if not sender_id:
                continue
            if "postback" in event:
                handle_postback(sender_id, event["postback"]["payload"])
                continue
            if "message" in event:
                message = event["message"]
                if message.get("is_echo"):
                    continue
                if "quick_reply" in message:
                    handle_postback(sender_id, message["quick_reply"]["payload"])
                    continue
                text = message.get("text", "").strip()
                if text:
                    handle_message(sender_id, text)
    return "EVENT_RECEIVED", 200

# ─── Background ──────────────────────────────
POLL_INTERVAL_MINUTES = 5

def run_monitor_loop():
    # Critical Bug 1: import lazily to avoid circular dependency
    from monitor import check_all_users

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def monitor():
        while True:
            start = time.time()
            try:
                await check_all_users()
            except Exception as e:
                logging.error(f"Monitor error: {e}")
            elapsed = time.time() - start
            wait_time = max(0, POLL_INTERVAL_MINUTES * 60 - elapsed)
            await asyncio.sleep(wait_time)
    loop.run_until_complete(monitor())

if __name__ == "__main__":
    def setup():
        url = "https://graph.facebook.com/v25.0/me/messenger_profile"
        payload = {
            "get_started": {"payload": "START"},
            "persistent_menu": [{
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {"type": "postback", "title": "📋 Menu", "payload": "MENU"},
                    {"type": "postback", "title": "🌐 Language", "payload": "LANG"},
                    {"type": "postback", "title": "🆘 Help", "payload": "HELP"}
                ]
            }]
        }
        resp = requests.post(url, params={"access_token": PAGE_ACCESS_TOKEN}, json=payload, timeout=10)
        print("Profile setup:", resp.status_code, resp.text)
    try:
        setup()
        print("✅ Messenger profile configured")
    except Exception as e:
        print("❌ Profile setup error:", e)

    # Keep‑alive pinger removed (Bug 5) – Render paid plans don't need it
    # If you still need it, uncomment the thread below:
    # threading.Thread(target=keep_alive, daemon=True).start()

    threading.Thread(target=run_monitor_loop, daemon=True).start()

    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT, threaded=True)
