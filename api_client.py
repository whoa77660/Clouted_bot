import requests
import json
from config import CLOUTED_BASE_URL
from auth import get_auth_headers
from firebase_db import get_user_settings_ref

def _trpc_batch_request(chat_id: int, path: str, input_data: dict, referer: str):
    headers = get_auth_headers(chat_id)
    if not headers:
        raise Exception(f"No cookie set for user {chat_id}")

    headers.update({
        'accept': '*/*',
        'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7,ru;q=0.6,vi;q=0.5',
        'content-type': 'application/json',
        'dnt': '1',
        'priority': 'u=1, i',
        'referer': referer,
        'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
    })

    input_json_str = json.dumps(input_data, separators=(',', ':'))
    params = {'batch': '1', 'input': input_json_str}
    resp = requests.get(f'{CLOUTED_BASE_URL}{path}', headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def _extract_list_from_response(response_json, index=0):
    if isinstance(response_json, list):
        if len(response_json) > index:
            return _extract_inner(response_json[index])
        return []

    if isinstance(response_json, dict):
        data = response_json.get('data')
        if isinstance(data, list):
            return data
        result = response_json.get('result', {})
        if isinstance(result, dict):
            inner = result.get('data', {})
            if isinstance(inner, dict):
                inner_json = inner.get('json')
                if isinstance(inner_json, list):
                    return inner_json
                if isinstance(inner_json, dict):
                    nested = inner_json.get('data')
                    if isinstance(nested, list):
                        return nested
                if isinstance(inner_json, str):
                    try:
                        parsed = json.loads(inner_json)
                        if isinstance(parsed, dict):
                            nested = parsed.get('data')
                            if isinstance(nested, list):
                                return nested
                        elif isinstance(parsed, list):
                            return parsed
                    except:
                        pass
        for v in response_json.values():
            if isinstance(v, list):
                return v
    return []


def _extract_inner(item):
    if isinstance(item, dict):
        result = item.get('result', {})
        if isinstance(result, dict):
            data = result.get('data', {})
            if isinstance(data, dict):
                inner = data.get('json')
                if isinstance(inner, list):
                    return inner
                if isinstance(inner, dict):
                    nested = inner.get('data')
                    if isinstance(nested, list):
                        return nested
                if isinstance(inner, str):
                    try:
                        parsed = json.loads(inner)
                        if isinstance(parsed, dict):
                            nested = parsed.get('data')
                            if isinstance(nested, list):
                                return nested
                        elif isinstance(parsed, list):
                            return parsed
                    except:
                        pass
    return []


def fetch_campaigns(chat_id: int, page_size: int = 12):
    input_data = {
        "0": {
            "json": {
                "filter": "browse",
                "pageSize": page_size,
                "direction": "forward"
            }
        }
    }
    raw = _trpc_batch_request(chat_id, '/api/trpc/campaign.list', input_data,
                              referer='https://app.clouted.com/campaigns')
    result = _extract_list_from_response(raw)
    if not isinstance(result, list):
        return []
    return result


def fetch_campaign_progress(chat_id: int, campaign_uuid: str):
    input_data = {
        "0": {
            "json": {
                "campaignId": campaign_uuid
            }
        }
    }
    try:
        raw = _trpc_batch_request(chat_id, '/api/trpc/campaign.progress', input_data,
                                  referer='https://app.clouted.com/campaigns')
        result = _extract_inner(raw)
        if isinstance(result, dict):
            return result
        return None
    except Exception:
        return None


def fetch_clips_and_stats(chat_id: int, page_size: int = 50):   # <--- default now 50
    settings = get_user_settings_ref(chat_id).get()
    user_id = settings.get('userId') if settings else None

    input_data = {
        "0": {"json": None, "meta": {"values": ["undefined"]}},
        "1": {
            "json": {
                "pageSize": page_size,
                "status": None,
                "direction": "forward"
            },
            "meta": {"values": {"status": ["undefined"]}}
        },
        "2": {"json": None, "meta": {"values": ["undefined"]}},
        "3": {"json": {"userId": user_id}}
    }

    batch_path = '/api/trpc/clip.stats,clip.list,social.list,accounts.loginProvider'
    raw = _trpc_batch_request(chat_id, batch_path, input_data,
                              referer='https://app.clouted.com/profile')

    stats = {}
    clips = []
    if isinstance(raw, list) and len(raw) >= 2:
        stats_raw = _extract_inner(raw[0])
        if isinstance(stats_raw, dict):
            stats = stats_raw
        clips = _extract_inner(raw[1]) or []
    elif isinstance(raw, dict):
        pass

    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(clips, list):
        clips = []
    return clips, stats


def fetch_clips(chat_id: int, page_size: int = 50):   # <--- default now 50
    clips, _ = fetch_clips_and_stats(chat_id, page_size)
    return clips
