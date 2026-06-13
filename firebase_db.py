import firebase_admin
from firebase_admin import credentials, db
from config import FIREBASE_DATABASE_URL

cred = credentials.Certificate("firebase.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': FIREBASE_DATABASE_URL
})

def get_user_settings_ref(chat_id):
    return db.reference(f'users/{chat_id}/settings')

def get_user_state_ref(chat_id, state_type):
    return db.reference(f'users/{chat_id}/{state_type}')

def get_all_users():
    users = db.reference('users').get() or {}
    result = {}
    for uid, data in users.items():
        settings = data.get('settings', {})
        if settings and settings.get('clouted_cookie'):
            result[int(uid)] = settings
    return result

def set_cookie_invalid_flag(chat_id, is_invalid: bool):
    db.reference(f'users/{chat_id}/settings/cookie_invalid').set(is_invalid)

def db_get(path):
    return db.reference(path).get()

def db_set(path, data):
    db.reference(path).set(data)

def get_cookie_invalid_flag(chat_id) -> bool:
    return db.reference(f'users/{chat_id}/settings/cookie_invalid').get() or False
