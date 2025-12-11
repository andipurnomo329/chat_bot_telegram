from config.settings import BASE_URL,PICT_DIR
from utils.http_utils import safe_post, safe_post_pict

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


def delete_message(chat_id, message_id):
    safe_post(
        f"{BASE_URL}/deleteMessage",
        json_payload={"chat_id": chat_id, "message_id": message_id}
    )
