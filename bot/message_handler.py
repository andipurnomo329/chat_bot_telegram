from utils.helper import *
from bot.menu_builder import build_dynamic_menu
from bot.callback_handler import *
from bot.elk_getdata import *

def handle_message(update, menu_message_id):
    msg = update.get("message")
    if not msg:
        return
    
    # print(msg)

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("first_name", f"user_{user_id}")
    text = msg.get("text", "")
    text_lower = text.lower()
    # print(text_lower)
    # Hanya handle perintah tertentu
    if text_lower in ("/start", "/jenkins_bot"):
        # Cek user authorized
        if user_id not in AUTHORIZED_USERS:
            send_message(chat_id, f"🚫 @{username} tidak punya akses.")
            return

        # Cek group chat
        if chat_id not in GROUP_ID:
            return

        # Build dan kirim menu dinamis
        title, kb = build_dynamic_menu([])
        msg_out = send_message(chat_id, title, kb)

        if msg_out and "result" in msg_out:
            menu_message_id[chat_id] = msg_out["result"]["message_id"]

    elif text_lower == "/quegoaml":
        send_message(chat_id, f"sedang menarik data, mohon tunggu sebentar ...")
        data = get_elastic_data()
        send_message(chat_id, data)
        return

    elif text_lower == "/notifcc":
        send_message(chat_id, f"sedang menarik data, mohon tunggu sebentar ...")
        data = get_notifcc()
        send_message(chat_id, data)
        return

    else:
        # Perintah tidak dikenal, bisa dikosongkan atau kirim pesan
        pass
