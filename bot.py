import asyncio
import html
import json
import logging
import traceback
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from config import TELEGRAM_BOT_TOKEN, OWNER_ID
from firebase_db import (
    get_user_state_ref, get_user_settings_ref, get_cookie_invalid_flag,
    get_all_users
)
from auth import validate_and_save_cookie
from api_client import fetch_campaigns

application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ═══════════════════════════════════════════════
# GLOBAL ERROR HANDLER (unchanged)
# ═══════════════════════════════════════════════
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)[-3500:]
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    update_json = json.dumps(update_str, indent=2, ensure_ascii=False)[:1000]

    message = (
        f"🚨 <b>An exception was raised</b>\n\n"
        f"<b>Update:</b>\n<pre>{html.escape(update_json)}</pre>\n\n"
        f"<b>Traceback:</b>\n<pre>{html.escape(tb_string)}</pre>"
    )

    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=message, parse_mode='HTML')
    except Exception:
        safe_message = message.replace('<', '&lt;').replace('>', '&gt;')
        try:
            await context.bot.send_message(chat_id=OWNER_ID, text=safe_message)
        except:
            pass

# ═══════════════════════════════════════════════
# LANGUAGE HANDLING
# ═══════════════════════════════════════════════
def get_user_lang(chat_id) -> str:
    settings = get_user_settings_ref(chat_id).get() or {}
    return settings.get('lang', 'en') or 'en'

def set_user_lang(chat_id, lang: str):
    get_user_settings_ref(chat_id).update({'lang': lang})

# ═══════════════════════════════════════════════
# TRANSLATIONS
# ═══════════════════════════════════════════════
T = {
    'en': {
        'welcome': "👋 Welcome! I monitor your Clouted account.\nUse /setcookie <your_full_cookie> to link your account.\nThen use the buttons below.",
        'help': "Commands:\n/start - Show main keyboard\n/setcookie <cookie> - Link Clouted account\n/profile - Your profile & session expiry\n/stats - Your total views/clips/earnings\n/campaigns - All campaigns (public)\n/videos - Your clips status\n\nAuto‑alerts for changes every few minutes.",
        'choose_language': "Please choose your language:",
        'language_set': "✅ Language set to English.",
        'setcookie_prompt': "Usage: /setcookie <your_full_cookie_value>",
        'profile_no_cookie': "You haven't linked an account. Use /setcookie.",
        'profile_title': "👤 <b>Profile</b>",
        'profile_username': "Username",
        'profile_user_id': "User ID",
        'profile_org': "Organization",
        'profile_expires': "Session expires",
        'cookie_invalid_warn': "\n\n⚠️ Your cookie is invalid/expired. Please update it with /setcookie.",
        'stats_no_cookie': "You need to set your cookie first. Use /setcookie.",
        'stats_title': "📊 <b>Your Stats</b>",
        'stats_views': "Total Views",
        'stats_clips': "Total Clips",
        'stats_earnings': "Total Earnings",
        'stats_earnings_unit': "dollars",
        'campaigns_fail': "Failed to fetch campaigns. Try again later.",
        'campaigns_empty': "No campaigns available right now.\nIf you haven't set a cookie, ask someone who has to set one first.",
        'videos_no_cookie': "You need to set your cookie first. Use /setcookie.",
        'videos_no_data': "No data yet. Please wait for the first poll.",
        'videos_empty': "You have no clips yet.",
        'video_status_title': "Clip Status",
        'campaign_card_status': "Status",
        'campaign_card_budget': "Budget",
        'campaign_card_cpm': "CPM",
        'campaign_card_payout': "Payout",
        'campaign_card_participants': "Participants",
        'campaign_card_views': "Views",
        'campaign_card_platforms': "Platforms",
        'campaign_card_start': "Start",
        'campaign_card_end': "End",
        'campaign_card_remarks': "Remarks",
        'campaign_card_progress': "Progress",
        'campaign_card_budget_used': "📊 Budget Used",
        'lang_button': "🌐 Language",
        'stats_button': "📊 Stats",
        'campaigns_button': "📋 Campaigns",
        'videos_button': "🎬 My Videos",
        'profile_button': "👤 Profile",
        'help_button': "ℹ️ Help",
        'show_more_button': "📄 Show more 12 ({remaining} remaining)",
        'earnings': "Earnings",
        'video_url': "🔗 Video",
    },
    'bn': {
        'welcome': "👋 স্বাগতম! আমি আপনার Clouted অ্যাকাউন্ট মনিটর করি।\nঅ্যাকাউন্ট লিঙ্ক করতে /setcookie <আপনার_পূর্ণ_কুকি> ব্যবহার করুন।\nতারপর নিচের বোতামগুলি ব্যবহার করুন।",
        'help': "কমান্ডসমূহ:\n/start - প্রধান কিবোর্ড দেখান\n/setcookie <কুকি> - Clouted অ্যাকাউন্ট লিঙ্ক করুন\n/profile - আপনার প্রোফাইল ও সেশন মেয়াদ\n/stats - আপনার মোট ভিউ/ক্লিপ/আয়\n/campaigns - সকল ক্যাম্পেইন (পাবলিক)\n/videos - আপনার ক্লিপের অবস্থা\n\nপ্রতি কয়েক মিনিটে পরিবর্তনের জন্য স্বয়ংক্রিয় সতর্কতা।",
        'choose_language': "অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন:",
        'language_set': "✅ ভাষা বাংলায় সেট করা হয়েছে।",
        'setcookie_prompt': "ব্যবহার: /setcookie <আপনার_পূর্ণ_কুকি_মান>",
        'profile_no_cookie': "আপনি অ্যাকাউন্ট লিঙ্ক করেননি। /setcookie ব্যবহার করুন।",
        'profile_title': "👤 <b>প্রোফাইল</b>",
        'profile_username': "ইউজারনেম",
        'profile_user_id': "ইউজার আইডি",
        'profile_org': "সংস্থা",
        'profile_expires': "সেশন মেয়াদ শেষ",
        'cookie_invalid_warn': "\n\n⚠️ আপনার কুকি অবৈধ/মেয়াদোত্তীর্ণ। অনুগ্রহ করে /setcookie দিয়ে আপডেট করুন।",
        'stats_no_cookie': "আগে কুকি সেট করতে হবে। /setcookie ব্যবহার করুন।",
        'stats_title': "📊 <b>আপনার পরিসংখ্যান</b>",
        'stats_views': "মোট ভিউ",
        'stats_clips': "মোট ক্লিপ",
        'stats_earnings': "মোট আয়",
        'stats_earnings_unit': "ডলার",
        'campaigns_fail': "ক্যাম্পেইন লোড করা যায়নি। পরে আবার চেষ্টা করুন।",
        'campaigns_empty': "এখনই কোনো ক্যাম্পেইন নেই।\nআপনি যদি কুকি সেট না করে থাকেন, তাহলে যার সেট করা আছে তাকে আগে সেট করতে বলুন।",
        'videos_no_cookie': "আগে কুকি সেট করতে হবে। /setcookie ব্যবহার করুন।",
        'videos_no_data': "এখনো ডেটা নেই। প্রথম পোলের জন্য অপেক্ষা করুন।",
        'videos_empty': "আপনার কোনো ক্লিপ নেই।",
        'video_status_title': "ক্লিপ অবস্থা",
        'campaign_card_status': "অবস্থা",
        'campaign_card_budget': "বাজেট",
        'campaign_card_cpm': "CPM",
        'campaign_card_payout': "পেআউট",
        'campaign_card_participants': "অংশগ্রহণকারী",
        'campaign_card_views': "ভিউ",
        'campaign_card_platforms': "প্ল্যাটফর্ম",
        'campaign_card_start': "শুরু",
        'campaign_card_end': "শেষ",
        'campaign_card_remarks': "মন্তব্য",
        'campaign_card_progress': "অগ্রগতি",
        'campaign_card_budget_used': "📊 বাজেট ব্যবহৃত",
        'lang_button': "🌐 ভাষা",
        'stats_button': "📊 পরিসংখ্যান",
        'campaigns_button': "📋 ক্যাম্পেইন",
        'videos_button': "🎬 আমার ভিডিও",
        'profile_button': "👤 প্রোফাইল",
        'help_button': "ℹ️ সাহায্য",
        'show_more_button': "📄 আরও ১২ দেখুন ({remaining} বাকি)",
        'earnings': "আয়",
        'video_url': "🔗 ভিডিও",
    }
}

def t(key: str, chat_id: int) -> str:
    lang = get_user_lang(chat_id)
    return T.get(lang, T['en']).get(key, T['en'][key])

def cents_to_dollar(cents) -> str:
    try:
        dollars = int(cents) / 100
        return f"${dollars:.2f}"
    except (ValueError, TypeError):
        return "?"

# ═══════════════════════════════════════════════
# STYLED KEYBOARD BUTTON
# ═══════════════════════════════════════════════
def _make_styled_button(text, style=None):
    if style:
        return KeyboardButton(text, api_kwargs={"style": style})
    return KeyboardButton(text)

def get_language_keyboard():
    keyboard = [
        [_make_styled_button("English", "primary"), _make_styled_button("বাংলা", "primary")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_main_keyboard(chat_id: int):
    keyboard = [
        [
            _make_styled_button(t("stats_button", chat_id), "success"),
            _make_styled_button(t("campaigns_button", chat_id), "success")
        ],
        [
            _make_styled_button(t("videos_button", chat_id), "danger"),
            _make_styled_button(t("profile_button", chat_id), "danger")
        ],
        [
            _make_styled_button(t("help_button", chat_id), "primary"),
            _make_styled_button(t("lang_button", chat_id), "primary")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def first_poll_done(chat_id):
    return get_user_state_ref(chat_id, 'first_poll_done').get() == True

async def send_notification(chat_id: int, text: str):
    await application.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

def format_campaign_card(camp: dict, chat_id: int) -> str:
    emoji = "🟢" if camp.get('status') == 'active' else ("⏸️" if camp.get('status') == 'paused' else "🔄")
    name = html.escape(camp.get('name', 'Unknown'))
    status_val = html.escape(str(camp.get('status', '?')).capitalize())
    budget = cents_to_dollar(camp.get('budget', 0))
    buyer_budget = cents_to_dollar(camp.get('buyerBudget', 0))
    cpm = cents_to_dollar(camp.get('cpm', 0))
    min_payout = cents_to_dollar(camp.get('minPayout', 0))
    max_payout = cents_to_dollar(camp.get('maxPayout', 0))

    budget_val = camp.get('budget', 0)
    cpm_val = camp.get('cpm', 0)
    views_val = camp.get('viewCount', 0)
    if budget_val and cpm_val and views_val:
        spent = (views_val * cpm_val) / 1000
        percent = (spent / budget_val) * 100
        budget_used_str = f"{percent:.1f}%"
    else:
        budget_used_str = "N/A"

    participants = html.escape(str(camp.get('participantCount', '?')))
    views = html.escape(str(camp.get('viewCount', '?')))
    platforms = html.escape(', '.join(camp.get('platforms', [])) or 'N/A')
    start = html.escape(str(camp.get('startAt', '?')))
    end = html.escape(str(camp.get('endAt', 'ongoing') or 'ongoing'))
    remarks = html.escape(str(camp.get('remarks', '')))
    if len(remarks) > 200:
        remarks = remarks[:200] + "..."

    progress = camp.get('progress')
    progress_text = ""
    if progress and isinstance(progress, dict):
        pct = progress.get('percentage')
        if pct is not None:
            progress_text = f"📊 {t('campaign_card_progress', chat_id)}: {html.escape(str(pct))}%\n"

    platforms_display = f"<b>{platforms}</b>"
    cpm_display = f"<b>{cpm}</b>"

    card = (
        f"{emoji} <b>{name}</b>\n"
        f"{t('campaign_card_status', chat_id)}: <code>{status_val}</code>\n"
        f"{progress_text}"
        f"💰 {t('campaign_card_budget', chat_id)}: {budget} (buyer: {buyer_budget})\n"
        f"{t('campaign_card_budget_used', chat_id)}: {budget_used_str}\n"
        f"💵 {t('campaign_card_cpm', chat_id)}: {cpm_display} | {t('campaign_card_payout', chat_id)}: {min_payout}–{max_payout}\n"
        f"👥 {t('campaign_card_participants', chat_id)}: {participants}\n"
        f"👀 {t('campaign_card_views', chat_id)}: {views}\n"
        f"📱 {t('campaign_card_platforms', chat_id)}: {platforms_display}\n"
        f"📅 {t('campaign_card_start', chat_id)}: {start}\n"
        f"🏁 {t('campaign_card_end', chat_id)}: {end}\n"
        f"📝 {t('campaign_card_remarks', chat_id)}: {remarks if remarks else 'None'}\n"
    )
    return card

# ═══════════════════════════════════════════════
# VIDEOS – OLD STYLE CARDS + PAGINATION
# ═══════════════════════════════════════════════
VIDEOS_PER_PAGE = 12

async def send_videos_page(update, context, chat_id: int, offset: int = 0):
    """
    Sends up to 12 separate clip cards, and if there are more, a final
    message with a 'Show More' inline button.
    """
    clips_dict = get_user_state_ref(chat_id, 'clips').get() or {}
    if not clips_dict:
        await update.message.reply_text(t('videos_empty', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return

    clips = list(clips_dict.values())
    total = len(clips)
    start = offset
    end = min(offset + VIDEOS_PER_PAGE, total)
    page_clips = clips[start:end]

    # Send each clip as a separate beautiful card
    for clip in page_clips:
        status = clip.get('status', 'unknown')
        if status == 'healthy':
            status_emoji = "✅"
        elif status in ('flagged', 'rejected'):
            status_emoji = "❌"
        elif status == 'pending':
            status_emoji = "🕒"
        else:
            status_emoji = "❓"

        campaign = html.escape(str(clip.get('campaignName', 'Unknown')))
        views = html.escape(str(clip.get('views', 0)))
        earnings = cents_to_dollar(clip.get('earningsCents', 0))
        url = clip.get('url', '')

        text = (
            f"{status_emoji} {t('video_status_title', chat_id)}\n"
            f"{t('campaign_card_status', chat_id)}: <code>{status}</code>\n"
            f"{t('stats_views', chat_id)}: <code>{views}</code>\n"
            f"{t('earnings', chat_id)}: <code>{earnings}</code>\n"
        )
        if url:
            text += f'🔗 <a href="{html.escape(url)}">Open Video</a>'
        await update.message.reply_text(text, parse_mode="HTML",
                                        disable_web_page_preview=True,
                                        reply_markup=get_main_keyboard(chat_id))
        await asyncio.sleep(0.3)

    # If there are more clips, send a final message with the "Show More" button
    if end < total:
        remaining = total - end
        keyboard = [[
            InlineKeyboardButton(
                t('show_more_button', chat_id).format(remaining=remaining),
                callback_data=f"videos_page_{end}",
                style="primary"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📄 More videos available:", reply_markup=reply_markup)

# ── Callback handler for pagination ──
async def video_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("videos_page_"):
        return
    offset = int(data.split("_")[-1])
    chat_id = query.message.chat_id
    # Remove the "More videos available" button message
    try:
        await query.message.delete()
    except:
        pass
    # Send the next batch
    await send_videos_page(update, context, chat_id, offset=offset)

# ── Updated videos command ──
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_user_settings_ref(chat_id).get() or {}
    if not settings.get('userId'):
        await update.message.reply_text(t('videos_no_cookie', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return

    if not first_poll_done(chat_id):
        await update.message.reply_text(t('videos_no_data', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return

    await send_videos_page(update, context, chat_id, offset=0)

# ═══════════════════════════════════════════════
# OTHER COMMAND HANDLERS (unchanged)
# ═══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_user_settings_ref(chat_id).get() or {}
    if not settings.get('lang'):
        await update.message.reply_text(
            "Please choose your language / অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন:",
            reply_markup=get_language_keyboard()
        )
    else:
        await update.message.reply_text(
            t('welcome', chat_id),
            reply_markup=get_main_keyboard(chat_id)
        )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        t('help', chat_id),
        reply_markup=get_main_keyboard(chat_id)
    )

async def set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(t('setcookie_prompt', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return
    cookie = ' '.join(context.args)
    success, message = validate_and_save_cookie(chat_id, cookie)
    await update.message.reply_text(message, reply_markup=get_main_keyboard(chat_id) if success else None)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_user_settings_ref(chat_id).get() or {}
    if not settings.get('userId'):
        await update.message.reply_text(t('profile_no_cookie', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return

    username = html.escape(str(settings.get('username', 'Unknown')))
    user_id = html.escape(str(settings['userId']))
    org_id = html.escape(str(settings.get('organizationId', 'N/A')))
    expires = html.escape(str(settings.get('expiresAt', 'Unknown')))
    cookie_bad = get_cookie_invalid_flag(chat_id)

    text = (
        f"{t('profile_title', chat_id)}\n"
        f"{t('profile_username', chat_id)}: <code>{username}</code>\n"
        f"{t('profile_user_id', chat_id)}: <code>{user_id}</code>\n"
        f"{t('profile_org', chat_id)}: <code>{org_id}</code>\n"
        f"{t('profile_expires', chat_id)}: <code>{expires}</code>"
    )
    if cookie_bad:
        text += t('cookie_invalid_warn', chat_id)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_main_keyboard(chat_id))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_user_settings_ref(chat_id).get() or {}
    if not settings.get('userId'):
        await update.message.reply_text(t('stats_no_cookie', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return

    s = get_user_state_ref(chat_id, 'stats').get() or {}
    cookie_bad = get_cookie_invalid_flag(chat_id)
    total_views = html.escape(str(s.get('totalViews', 0)))
    total_clips = html.escape(str(s.get('totalClips', 0)))
    total_earnings = cents_to_dollar(s.get('totalEarningsCents', 0))
    unit = t('stats_earnings_unit', chat_id)
    text = (
        f"{t('stats_title', chat_id)}\n"
        f"{t('stats_views', chat_id)}: <code>{total_views}</code>\n"
        f"{t('stats_clips', chat_id)}: <code>{total_clips}</code>\n"
        f"{t('stats_earnings', chat_id)}: <code>{total_earnings} {unit}</code>"
    )
    if cookie_bad:
        text += t('cookie_invalid_warn', chat_id)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_main_keyboard(chat_id))

async def campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    camps = None

    settings = get_user_settings_ref(chat_id).get() or {}
    if settings.get('clouted_cookie'):
        try:
            camps = fetch_campaigns(chat_id)
        except Exception:
            pass

    if not camps:
        all_users = get_all_users()
        for other_id, other_settings in all_users.items():
            if other_id == chat_id:
                continue
            try:
                camps = fetch_campaigns(other_id)
                break
            except Exception:
                continue

    if not camps:
        await update.message.reply_text(t('campaigns_empty', chat_id),
                                        reply_markup=get_main_keyboard(chat_id))
        return

    for camp in camps:
        card = format_campaign_card(camp, chat_id)
        await update.message.reply_text(card, parse_mode="HTML", reply_markup=get_main_keyboard(chat_id))
        await asyncio.sleep(0.3)

# ═══════════════════════════════════════════════
# BUTTON HANDLER (reply keyboard only)
# ═══════════════════════════════════════════════
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "English":
        set_user_lang(chat_id, 'en')
        await update.message.reply_text("✅ Language set to English.", reply_markup=get_main_keyboard(chat_id))
        return
    elif text == "বাংলা":
        set_user_lang(chat_id, 'bn')
        await update.message.reply_text("✅ ভাষা বাংলায় সেট করা হয়েছে।", reply_markup=get_main_keyboard(chat_id))
        return

    if text == t("lang_button", chat_id):
        await update.message.reply_text(
            "Choose language / ভাষা নির্বাচন করুন:",
            reply_markup=get_language_keyboard()
        )
        return

    if text == t("stats_button", chat_id):
        await stats(update, context)
    elif text == t("campaigns_button", chat_id):
        await campaigns(update, context)
    elif text == t("videos_button", chat_id):
        await videos(update, context)
    elif text == t("profile_button", chat_id):
        await profile(update, context)
    elif text == t("help_button", chat_id):
        await help_cmd(update, context)

# ═══════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════
application.add_error_handler(error_handler)

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("setcookie", set_cookie))
application.add_handler(CommandHandler("profile", profile))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CommandHandler("campaigns", campaigns))
application.add_handler(CommandHandler("videos", videos))

# Inline pagination callback for videos
application.add_handler(CallbackQueryHandler(video_pagination_callback, pattern="^videos_page_"))

# Reply keyboard handler
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
