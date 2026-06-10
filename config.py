import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
FIREBASE_DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL')
CLOUTED_BASE_URL = os.getenv('CLOUTED_BASE_URL')