import json
import uuid
from config.settings import LOG_FILE
from utils.time_utils import iso_now
import socket

try:
    SERVER_IP = socket.gethostbyname(socket.gethostname())
except:
    SERVER_IP = "127.0.0.1"

def write_log(user, group_id=None, user_id=None, action=None, site=None,
              status=None, message_id=None, note=None, trace_id=None):
    try:
        if not trace_id:
            trace_id = str(uuid.uuid4())

        log_entry = {
            "timestamp": iso_now(),
            "trace_id": trace_id,
            "user": user,
            "user_id": user_id,
            "group_id": group_id,
            "site": site,
            "action": action.upper() if action else None,
            "status": status.upper() if status else None,
            "message_id": message_id,
            "note": note,
            "ip_address": SERVER_IP
        }

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False)
            f.write("\n")

        return trace_id

    except Exception:
        return trace_id or str(uuid.uuid4())
