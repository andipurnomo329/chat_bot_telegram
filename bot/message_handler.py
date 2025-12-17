from utils.helper import *
from bot.menu_builder import build_dynamic_menu
from bot.callback_handler import *
from bot.elk_getdata import *

def cek_authorized(user_id, chat_id, username):
    if user_id not in AUTHORIZED_USERS:
        send_message(chat_id, f"🚫 @{username} tidak punya akses.")
        return False
    if chat_id not in GROUP_ID:
        return False
    return True

def require_auth(func):
    def wrapper(chat_id, user_id, username, *args, **kwargs):
        if not cek_authorized(user_id, chat_id, username):
            return
        return func(chat_id, user_id, username, *args, **kwargs)
    return wrapper

@require_auth
def cmd_start(chat_id, user_id, username, menu_message_id):
    title, kb = build_dynamic_menu([])
    msg_out = send_message(chat_id, title, kb)

    if msg_out and "result" in msg_out:
        menu_message_id[chat_id] = msg_out["result"]["message_id"]

@require_auth
def cmd_mtel(chat_id, user_id, username):
    send_message(chat_id, "sedang menarik data, mohon tunggu sebentar ...")
    data = get_mtel()
    # send_photo(chat_id, "kibana.png", caption="Grafik MTEL Terbaru")
    send_message(chat_id, data)

@require_auth
def cmd_quegoaml(chat_id, user_id, username):
    send_message(chat_id, "sedang menarik data, mohon tunggu sebentar ...")
    data = get_goaml_data()
    send_message(chat_id, data)

@require_auth
def cmd_ams(chat_id, user_id, username):
    send_message(chat_id, "sedang menarik data, mohon tunggu sebentar ...")
    data = get_ams_data()
    send_message(chat_id, data)

@require_auth
def cmd_notifcc(chat_id, user_id, username):
    send_message(chat_id, "sedang menarik data, mohon tunggu sebentar ...")
    data = get_notifcc()
    send_message(chat_id, data)

def handle_message(update, menu_message_id):

    msg = update.get("message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("first_name", f"user_{user_id}")
    text = msg.get("text", "").lower()

    COMMANDS = {
        "/start": lambda: cmd_start(chat_id, user_id, username, menu_message_id),
        "/jenkins_bot": lambda: cmd_start(chat_id, user_id, username, menu_message_id),
        "/goaml": lambda: cmd_quegoaml(chat_id, user_id, username),
        "/mtel": lambda: cmd_mtel(chat_id, user_id, username),
        "/ams": lambda: cmd_ams(chat_id, user_id, username),
        "/notifcc": lambda: cmd_notifcc(chat_id, user_id, username),
    }

    handler = COMMANDS.get(text)
    if handler:
        handler()
        return

    return