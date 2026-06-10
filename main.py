import asyncio
import threading
import time
import requests
from bot import application
from monitor import check_all_users

POLL_INTERVAL_MINUTES = 5   # change to 1 for fast testing

# --- Keep‑alive (pings itself every 49s) ---
RENDER_URL = "https://clouted-bot.onrender.com"   # <-- replace with your actual URL

def keep_alive():
    while True:
        try:
            response = requests.get(RENDER_URL, timeout=30)
            print(f"Self Ping: {response.status_code}")
        except Exception as e:
            print(f"Self Ping Error: {e}")
        time.sleep(49)

threading.Thread(target=keep_alive, daemon=True).start()
# -------------------------------------------

async def periodic_monitor(context):
    await check_all_users()

if __name__ == '__main__':
    application.job_queue.run_repeating(
        periodic_monitor,
        interval=POLL_INTERVAL_MINUTES * 60,
        first=0   # immediate first poll
    )
    print("Bot started. Polling every", POLL_INTERVAL_MINUTES, "minutes.")
    application.run_polling()
