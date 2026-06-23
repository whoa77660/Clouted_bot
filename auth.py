import requests
from urllib.parse import unquote
from config import CLOUTED_BASE_URL
from firebase_db import get_user_settings_ref

# Patch 14: Modern User-Agent
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7,ru;q=0.6,vi;q=0.5',
    'Referer': 'https://app.clouted.com/profile',
}

COOKIE_NAME = "__Secure-better-auth.session_token="

def validate_and_save_cookie(chat_id: int, cookie_input: str):
    if '=' not in cookie_input and ';' not in cookie_input:
        cookie_input = f"__Secure-better-auth.session_token={cookie_input.strip()}"
    cookie_header = unquote(cookie_input.strip())

    headers = BROWSER_HEADERS.copy()
    headers['Cookie'] = cookie_header

    # Patch 11: hide cookie details
    print(f"[VALIDATE] User {chat_id}")

    try:
        resp = requests.get(f'{CLOUTED_BASE_URL}/api/auth/get-session',
                            headers=headers, timeout=20)

        if resp.status_code != 200:
            return False, f"❌ Server returned HTTP {resp.status_code}. Cookie may be invalid or expired."

        if 'application/json' not in resp.headers.get('Content-Type', ''):
            return False, f"❌ Response is not JSON."

        data = resp.json()
        if not isinstance(data, dict):
            return False, f"❌ Response is not a JSON object."

        session = data.get('session')
        user = data.get('user')
        if not session or not user:
            return False, f"❌ Session/user missing."

        # Critical Bug 4: safe dict access
        get_user_settings_ref(chat_id).set({
            'clouted_cookie': cookie_header,
            'userId': user.get('id'),
            'organizationId': session.get('activeOrganizationId'),
            'expiresAt': session.get('expiresAt', 'unknown'),
            'username': user.get('name', 'Unknown'),
            'cookie_invalid': False
        })
        return True, f"✅ Logged in as {user.get('name', 'Unknown')} (userId: {user.get('id')})"

    except requests.exceptions.RequestException as e:
        return False, f"❌ Request failed: {str(e)}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def get_auth_headers(chat_id: int):
    settings = get_user_settings_ref(chat_id).get()
    if not settings or not settings.get('clouted_cookie'):
        return None
    headers = BROWSER_HEADERS.copy()
    headers['Cookie'] = settings['clouted_cookie']
    return headers
