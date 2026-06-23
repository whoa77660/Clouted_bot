import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # not used, kept for compatibility
FIREBASE_DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL')
CLOUTED_BASE_URL = os.getenv('CLOUTED_BASE_URL')

# Messenger‑specific
PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', 'rnrteam123')
RENDER_URL = os.getenv('RENDER_URL')

# Critical Bug 2 fix: OWNER_ID as int (default 0 if missing)
OWNER_ID = int(os.getenv('OWNER_ID', '0'))

# Critical validation
required = [
    PAGE_ACCESS_TOKEN,
    FIREBASE_DATABASE_URL,
    CLOUTED_BASE_URL
]
if not all(required):
    raise RuntimeError("Missing required environment variables (PAGE_ACCESS_TOKEN, FIREBASE_DATABASE_URL, CLOUTED_BASE_URL)")
