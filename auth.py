import requests
from urllib.parse import unquote
from config import CLOUTED_BASE_URL
from firebase_db import get_user_settings_ref

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7,ru;q=0.6,vi;q=0.5',
    'Referer': 'https://app.clouted.com/profile',
}

COOKIE_NAME = "__Secure-better-auth.session_token="

def validate_and_save_cookie(chat_id: int, cookie_input: str):
    # Decode URL-encoded characters
    cookie_input = unquote(cookie_input.strip())

    # If the input doesn't contain ';' (so it's a single cookie) and
    # doesn't already start with the expected cookie name, prepend it.
    if ';' not in cookie_input and not cookie_input.startswith(COOKIE_NAME):
        cookie_header = COOKIE_NAME + cookie_input
    else:
        cookie_header = cookie_input

    headers = BROWSER_HEADERS.copy()
    headers['Cookie'] = cookie_header

    # Debug: show partial token
    token_part = cookie_header.split('=', 1)[-1][:10] + '...'
    print(f"[VALIDATE] Using cookie: __Secure-better-auth.session_token={token_part}")

    try:
        resp = requests.get(f'{CLOUTED_BASE_URL}/api/auth/get-session', headers=headers)

        print(f"[VALIDATE] Status: {resp.status_code}")
        print(f"[VALIDATE] Content-Type: {resp.headers.get('Content-Type','unknown')}")
        print(f"[VALIDATE] Body (first 300 chars): {resp.text[:300]}")

        if resp.status_code != 200:
            return False, f"❌ Server returned HTTP {resp.status_code}. Cookie may be invalid or expired."

        if 'application/json' not in resp.headers.get('Content-Type', ''):
            return False, f"❌ Response is not JSON. Content-Type: {resp.headers.get('Content-Type')}. Body: {resp.text[:200]}"

        data = resp.json()
        if not isinstance(data, dict):
            return False, f"❌ Response is not a JSON object."

        session = data.get('session')
        user = data.get('user')
        if not session or not user:
            return False, f"❌ Session/user missing."

        get_user_settings_ref(chat_id).set({
            'clouted_cookie': cookie_header,
            'userId': user['id'],
            'organizationId': session['activeOrganizationId'],
            'expiresAt': session.get('expiresAt', 'unknown'),
            'username': user.get('name', 'Unknown'),
            'cookie_invalid': False
        })
        return True, f"✅ Logged in as {user.get('name', 'Unknown')} (userId: {user['id']})"

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
