import requests
from config.settings import BASE_URL

def safe_post(url, json_payload=None, params=None, timeout=10):
    try:
        return requests.post(url, json=json_payload, params=params,
                             timeout=timeout, verify=False)
    except:
        return None

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

    if reply_markup:
        data["reply_markup"] = reply_markup

    resp = safe_post(f"{BASE_URL}/sendMessage", json_payload=data)
    if resp:
        try:
            return resp.json()
        except:
            return None
    return None

def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        data["reply_markup"] = reply_markup

    safe_post(f"{BASE_URL}/editMessageText", json_payload=data)

def delete_message(chat_id, message_id):
    safe_post(
        f"{BASE_URL}/deleteMessage",
        json_payload={"chat_id": chat_id, "message_id": message_id}
    )
