
from config.settings import *
from config.jenkins_services import JENKINS_SERVICES
from utils.telegram import send_message, edit_message, delete_message, send_photo
from utils.helper import *
from utils.logger import write_log
from bot.callback_handler import *
from bot.menu_builder import build_dynamic_menu
from bot.menu_builder import build_dynamic_menu

def handle_callback(update, site_selected):
    cb = update["callback_query"]

    chat_id = cb["message"]["chat"]["id"]
    user_id = cb["from"]["id"]
    username = cb["from"].get("first_name", f"user_{user_id}")
    message_id = cb["message"]["message_id"]
    data = cb.get("data")

    # Authorization check
    if user_id not in AUTHORIZED_USERS:
        send_message(chat_id, f"🚫 @{username} tidak punya akses.")
        return

    # -------------------------
    # Navigation menu
    # -------------------------
    if data.startswith("go::"):
        path = data.split("::")[1:]
        title, kb = build_dynamic_menu(path)
        edit_message(chat_id, message_id, title, kb)
        return

    # -------------------------
    # Select site
    # -------------------------
    if data.startswith("site::"):
        site = data.split("::")[1]
        site_selected[chat_id] = site

        buttons = [
            [{"text": act, "callback_data": f"jenk::{site}::{act.lower()}"}]
            for act in ["START", "STOP", "RESTART", "STATUS"]
        ]
        buttons.append([{"text": "⬅️ Kembali", "callback_data": "go::"}])

        edit_message(
            chat_id, message_id,
            f"🛠 Pilih ACTION untuk `{site}`:",
            {"inline_keyboard": buttons}
        )
        return

    # -------------------------
    # Confirmation
    # -------------------------
    if data.startswith("jenk::"):
        _, site, action = data.split("::")
        app_name = get_app_name(site)

        confirm_buttons = {
            "inline_keyboard": [
                [{"text": "✅ YA", "callback_data": f"confirm::{site}::{action}"}],
                [{"text": "❌ BATAL", "callback_data": f"site::{site}"}]
            ]
        }

        edit_message(
            chat_id, message_id,
            f"⚠️ Konfirmasi ACTION\n\n"
            f"Aplikasi : *{app_name}*\n"
            f"Site     : `{site}`\n"
            f"Action   : *{action.upper()}*\n\n"
            f"Yakin ingin melanjutkan?",
            confirm_buttons
        )
        return

    # -------------------------
    # Execute Jenkins action
    # -------------------------
    if data.startswith("confirm::"):
        _, site, action = data.split("::")

        user = cb["from"].get("username", f"user_{user_id}")

        trace = write_log(
            user=user,
            user_id=user_id,
            group_id=chat_id,
            action=action,
            site=site,
            status="TRIGGERED",
            message_id=message_id
        )

        try:
            delete_message(chat_id, message_id)
        except:
            pass

        # STATUS MODE
        if action.lower() == "status":
            send_message(
                chat_id,
                f"✅ Job Status Dijalankan oleh @{user}\n"
                f"📦 Job: {JENKINS_SERVICES[site]['token']}\n"
                f"⚙️ Action: status\n"
                f"🔗 Lihat Log Jenkins:\n"
                f"{JENKINS_BASE_URL}"
            )
            running_msg_id = None

        else:
            resp = send_message(
                chat_id,
                f"🚀 @{user} Menjalankan *{action.upper()}* pada `{site}` ..."
            )
            running_msg_id = resp.get("result", {}).get("message_id")

        ok, result = send_to_jenkins(site, action)

        write_log(
            user=user,
            user_id=user_id,
            group_id=chat_id,
            action=action,
            site=site,
            status="SUCCESS" if ok else "FAILED",
            message_id=running_msg_id,
            note=(None if ok else str(result)),
            trace_id=trace
        )

        # send_message(
        #     chat_id,
        #     f"📡 *Response Jenkins:*\n```\n{result}\n```"
        # )
        return