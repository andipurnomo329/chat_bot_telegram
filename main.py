import time
import requests
from datetime import datetime

from bot.message_handler import handle_message
from bot.callback_handler import *

def main():
    print(f"{datetime.today()} 🤖 Ready to serve ...")
    offset = None
    site_selected = {}
    menu_message_id = {}

    while True:
        print(f"{datetime.today()} 🤖 waiting comand...")
        # Poll Telegram
        try:
            updates = requests.get(
                f"{BASE_URL}/getUpdates",
                params={"timeout": 20, "offset": offset},
                verify=False
            ).json()
        except:
            time.sleep(0.3)
            continue

        if "result" not in updates:
            continue
        # print(updates)
        for update in updates["result"]:
            offset = update["update_id"] + 1

            if "callback_query" in update:
                handle_callback(update, site_selected)

            else:
                handle_message(update, menu_message_id)

        time.sleep(0.4)

if __name__ == "__main__":
    main()
