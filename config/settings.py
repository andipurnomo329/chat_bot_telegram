import os
import urllib3
import socket
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ES_HOST = "https://192.168.45.15:443" 
USERNAME = "app_super"
PASSWORD = "appsuperpassw0rd"

TELEGRAM_TOKEN = "8121093891:AAHUjXLArJ1QOuAQPHtuJtHNVaLMdM-XEJE"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
#JENKINS_BASE_URL = "http://10.70.12.34:8226"
JENKINS_BASE_URL = "https://192.168.62.119" 

# BOT_USERNAME = "Ultramen99_bot"
GROUP_ID = [-1003265313247, 538565365]
# -1003265313247
AUTHORIZED_USERS = [538565365]

MENU_TIMEOUT = 30
active_menu = {}

BASE_DIR = Path(__file__).resolve().parents[1]
PICT_DIR = BASE_DIR / "pict"
LOG_DIR = BASE_DIR / "log"
LOG_FILE = os.path.join(LOG_DIR, "jenkins_bot.log")

os.makedirs(LOG_DIR, exist_ok=True)

try:
    SERVER_IP = socket.gethostbyname(socket.gethostname())
except:
    SERVER_IP = "127.0.0.1"
