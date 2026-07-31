from utils.helper import *
from bot.menu_builder import build_dynamic_menu
from bot.callback_handler import *
from bot.elk_getdata import *
from utils.telegram import send_message, delete_message, send_document

WAITING_MSG = "🤖 Mohon ditunggu ..."
CAPTURE_DASHBOARD_MSG = "🤖 Sedang mengambil screenshot dashboard ..."

def cek_authorized(user_id: int, chat_id: int, username: str) -> bool:
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

def process_data_and_dashboard(chat_id: int, data_func, dashboard_name: str):
    mid, message = send_message(chat_id, WAITING_MSG)
    try:
        data = data_func()
        send_message(chat_id, data)
    except Exception as e:
        send_message(chat_id, f"❌ Terjadi kesalahan: {e}")
    delete_message(chat_id=message["chat"]["id"], message_id=mid)
    mid, message = send_message(chat_id, CAPTURE_DASHBOARD_MSG)
    try:
        filename = getDashboardScreenshot(dashboard_name)
        send_photo(chat_id, filename, caption=f"Dashboard {dashboard_name.capitalize()} Screenshot")
    except Exception as e:
        send_message(chat_id, f"❌ Gagal mengambil screenshot: {e}")
    finally:
        delete_message(chat_id=message["chat"]["id"], message_id=mid)

@require_auth
def cmd_mtel(chat_id, user_id, username):
    process_data_and_dashboard(chat_id, get_mtel, "mtel")

@require_auth
def cmd_quegoaml(chat_id, user_id, username):
    process_data_and_dashboard(chat_id, get_goaml_data, "goaml")

@require_auth
def cmd_ams(chat_id, user_id, username):
    mid, message = send_message(chat_id, WAITING_MSG)
    try:
        data = get_ams_data()
        send_message(chat_id, data)
    except Exception as e:
        send_message(chat_id, f"❌ Terjadi kesalahan: {e}")
    finally:
        delete_message(chat_id=message["chat"]["id"], message_id=mid)

@require_auth
def cmd_notifcc(chat_id, user_id, username):
    mid, message = send_message(chat_id, WAITING_MSG)
    try:
        data = get_notifcc()
        send_message(chat_id, data)
    except Exception as e:
        send_message(chat_id, f"❌ Terjadi kesalahan: {e}")
    finally:
        delete_message(chat_id=message["chat"]["id"], message_id=mid)

@require_auth
def cmd_wic(chat_id, user_id, username, cif):

    mid, message = send_message(chat_id, WAITING_MSG)
    try:
        result_text, file_name = get_wic_data(cif)
        if not file_name:
            send_message(chat_id, result_text)
            return 
        send_message(chat_id, result_text)
        with open(file_name, "rb") as f:
            send_document(chat_id, f)
    except Exception as e:
        send_message(chat_id, f"❌ ERROR: {str(e)}")
    finally:
        delete_message(
            chat_id=message["chat"]["id"],
            message_id=mid
        )

def handle_message(update, menu_message_id):
    msg = update.get("message")

    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("first_name", f"user_{user_id}")

    text = msg.get("text", "").lower().strip()

    # HANDLE DYNAMIC COMMAND
    if text.startswith("/wic_"):

        cif = text.split("_", 1)[1]

        return cmd_wic(
            chat_id,
            user_id,
            username,
            cif
        )

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
        return handler()
