import asyncio
import os
import threading
import time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from bot import application
from monitor import check_all_users

POLL_INTERVAL_MINUTES = 5
PORT = int(os.environ.get("PORT", 10000))

# --- Periodic monitor function (called by JobQueue) ---
async def periodic_monitor(context):
    await check_all_users()

# --- Minimal HTTP handler for Render health checks ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server listening on port {PORT}")
    server.serve_forever()

# --- Keep‑alive pinger (replace with your actual Render URL) ---
RENDER_URL = "https://clouted-bot.onrender.com/"   # ← replace me!

def keep_alive():
    while True:
        try:
            response = requests.get(RENDER_URL, timeout=30)
            print(f"Self Ping: {response.status_code}")
        except Exception as e:
            print(f"Self Ping Error: {e}")
        time.sleep(49)

# --- Start everything ---
if __name__ == '__main__':
    # 1. Health server thread
    threading.Thread(target=run_health_server, daemon=True).start()

    # 2. Keep‑alive thread
    threading.Thread(target=keep_alive, daemon=True).start()

    # 3. Telegram bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application.job_queue.run_repeating(
        periodic_monitor,
        interval=POLL_INTERVAL_MINUTES * 60,
        first=0
    )
    print("Bot started. Polling every", POLL_INTERVAL_MINUTES, "minutes.")
    application.run_polling()
