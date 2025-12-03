from config.menu import MENU_STRUCTURE
from config.jenkins_services import JENKINS_SERVICES
from config.settings import JENKINS_BASE_URL, BASE_URL, AUTHORIZED_USERS, GROUP_ID

from utils.telegram_api import safe_post

def get_app_name(site):
    for app, items in MENU_STRUCTURE.items():
        if site in items:
            return app
    return "UNKNOWN"


def send_to_jenkins(site, action):
    if site not in JENKINS_SERVICES:
        return False, f"❌ Site `{site}` tidak ditemukan."

    token = JENKINS_SERVICES[site]["token"]
    url = f"{JENKINS_BASE_URL}/generic-webhook-trigger/invoke?token={token}"

    payload = {
        "ACTION": action,
        "SITE_NAME": site,
        "APP_POOL": ""
    }

    resp = safe_post(url, json_payload=payload)
    if resp is None:
        return False, "Network error"

    try:
        return True, resp.text
    except:
        return True, str(resp)