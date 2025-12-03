import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

LOG_DIR = os.path.join(BASE_DIR, "log")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "jenkins_bot.log")
