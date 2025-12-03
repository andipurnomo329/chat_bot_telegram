import os
import urllib3
import socket
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = "8555958659:AAGn6GG1UffyNwL5OIPB9pLOA5kNsIRrExQ"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
#JENKINS_BASE_URL = "http://10.70.12.34:8226"
JENKINS_BASE_URL = "https://192.168.62.119"

# BOT_USERNAME = "Ultramen99_bot"
GROUP_ID = [-4933442695, -1003265313247]
# -1003265313247
AUTHORIZED_USERS = [1131769475]

MENU_TIMEOUT = 30
active_menu = {}

LOG_DIR = r"D:\Monitoring-Trail\telegram_bot\log"
LOG_FILE = os.path.join(LOG_DIR, "jenkins_bot.log")

os.makedirs(LOG_DIR, exist_ok=True)

try:
    SERVER_IP = socket.gethostbyname(socket.gethostname())
except:
    SERVER_IP = "127.0.0.1"
