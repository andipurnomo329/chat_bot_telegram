from config.settings import BASE_URL,PICT_DIR
from utils.http_utils import safe_post, safe_post_pict
import requests
from typing import Optional, Tuple, Dict, Any

class TelegramAPIError(Exception):
    pass

def send_document(chat_id, file):

    url = f"{BASE_URL}/sendDocument"

    data = {
        "chat_id": chat_id
    }

    files = {
        "document": file
    }

    response = requests.post(
        url,
        data=data,
        files=files
    )

    return response.json()

def send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None,
                 parse_mode: Optional[str] = "Markdown") -> Tuple[int, Dict[str, Any]]:
    """
    Kirim pesan dan return (message_id, full_message_object).
    Raise TelegramAPIError kalau API mengembalikan ok=False atau response tidak valid.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    resp = safe_post(f"{BASE_URL}/sendMessage", json_payload=payload)
    if not resp:
        raise TelegramAPIError("No response from safe_post")

    # Bisa gagal parse jika bukan JSON valid
    try:
        data = resp.json()
    except Exception as e:
        raise TelegramAPIError(f"Invalid JSON response: {e}")

    if not data.get("ok", False):
        # Ambil 'description' jika ada, untuk logging yang jelas
        desc = data.get("description", "unknown error")
        raise TelegramAPIError(f"Telegram API returned ok=False: {desc}")

    result = data.get("result")
    if not isinstance(result, dict):
        raise TelegramAPIError("Missing 'result' in response")

    msg_id = result.get("message_id")
    if msg_id is None:
        raise TelegramAPIError("Missing 'message_id' in result")

    return msg_id, result


def send_photo(chat_id, image_path, caption=None):
    url = f"{BASE_URL}/sendPhoto"

    with open(f"{PICT_DIR}/{image_path}", "rb") as f:
        files = {"photo": f}
        data = {
            "chat_id": chat_id,
        }

        if caption:
            data["caption"] = caption

        resp = safe_post_pict(url, data=data, files=files)

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


def delete_message(chat_id: int, message_id: int) -> None:
    """
    Delete message; raise exception kalau gagal supaya caller bisa handle.
    """
    resp = safe_post(
        f"{BASE_URL}/deleteMessage",
        json_payload={"chat_id": chat_id, "message_id": message_id}
    )
    if not resp:
        raise TelegramAPIError("No response from safe_post")

    try:
        data = resp.json()
    except Exception as e:
        raise TelegramAPIError(f"Invalid JSON response: {e}")

    if not data.get("ok", False):
        desc = data.get("description", "unknown error")
