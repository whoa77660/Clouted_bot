import asyncio
import os
import threading
import time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from bot import application
from monitor import check_all_users

POLL_INTERVAL_MINUTES = 1   # 1 for testing, change to 5 later
PORT = int(os.environ.get("PORT", 10000))

# --- Health server for Render port binding ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server listening on port {PORT}")
    server.serve_forever()

# --- Keep‑alive pinger (uses external URL to prevent sleep) ---
RENDER_URL = "https://clouted-bot.onrender.com/"   # replace with your exact Render URL

def keep_alive():
    while True:
        try:
            response = requests.get(RENDER_URL, timeout=30)
            print(f"Self Ping: {response.status_code}")
        except Exception as e:
            print(f"Self Ping Error: {e}")
        time.sleep(49)

# --- Manual monitoring loop (runs every POLL_INTERVAL_MINUTES) ---
async def run_monitor_loop():
    while True:
        print("[MONITOR] Starting poll...")
        await check_all_users()
        await asyncio.sleep(POLL_INTERVAL_MINUTES * 60)

async def main():
    # 1. Start health server in daemon thread
    threading.Thread(target=run_health_server, daemon=True).start()

    # 2. Start keep‑alive pinger in daemon thread
    threading.Thread(target=keep_alive, daemon=True).start()

    # 3. Start manual monitor loop as background asyncio task
    asyncio.create_task(run_monitor_loop())

    # 4. Start Telegram bot (blocking)
    print("Bot started. Polling every", POLL_INTERVAL_MINUTES, "minutes.")
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
