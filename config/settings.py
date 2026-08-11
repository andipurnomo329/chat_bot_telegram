import os
import urllib3
import socket
from pathlib import Path

from utils.env_loader import load_env_file

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).resolve().parents[1]
load_env_file(BASE_DIR / ".env")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Environment variable '{name}' belum di-set. "
            f"Isi file .env di root project (contoh di .env.example) "
            f"atau set environment variable-nya di server."
        )
    return value


ES_HOST = _require_env("ES_HOST")
USERNAME = _require_env("ES_USERNAME")
PASSWORD = _require_env("ES_PASSWORD")

KBNHUB = _require_env("KBNHUB_URL")
USERKBNHUB = _require_env("KBNHUB_USERNAME")
PASSWORDKBNHUB = _require_env("KBNHUB_PASSWORD")

KIBANA_LOGIN_URL = os.environ.get("KIBANA_LOGIN_URL", "https://192.168.45.33/login")
KIBANA_USERNAME = _require_env("KIBANA_USERNAME")
KIBANA_PASSWORD = _require_env("KIBANA_PASSWORD")

TELEGRAM_TOKEN = _require_env("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

JENKINS_BASE_URL = os.environ.get("JENKINS_BASE_URL", "https://192.168.62.119")

GROUP_ID = [int(x) for x in os.environ.get("TELEGRAM_GROUP_IDS", "").split(",") if x.strip()]
AUTHORIZED_USERS = [int(x) for x in os.environ.get("TELEGRAM_AUTHORIZED_USERS", "").split(",") if x.strip()]

MENU_TIMEOUT = int(os.environ.get("MENU_TIMEOUT", "30"))
active_menu = {}

PICT_DIR = BASE_DIR / "pict"
LOG_DIR = BASE_DIR / "log"
LOG_FILE = os.path.join(LOG_DIR, "jenkins_bot.log")

os.makedirs(LOG_DIR, exist_ok=True)

try:
    SERVER_IP = socket.gethostbyname(socket.gethostname())
except Exception:
    SERVER_IP = "127.0.0.1"
