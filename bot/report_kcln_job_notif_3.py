import base64
import json
import os
from datetime import datetime, time, timezone
from pathlib import Path

import pytz
import urllib3
from telegram import Bot, Update
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    Filters,
    MessageHandler,
    Updater,
)
from utils.env_loader import load_env_file

# Muat file .env dari folder root project
load_env_file(Path(__file__).resolve().parents[1] / ".env")

# ================================
# KONFIGURASI & KREDENSIAL
# ================================
ES_HOST = os.environ.get("ES_HOST", "")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_REPORTS", "")

# Parsing target chat / group ID dari ENV (format comma-separated)
RAW_TARGET_IDS = os.environ.get("TELEGRAM_GROUP_IDS", "")


def parse_target_chat_ids(raw_ids: str) -> list:
    targets = []
    if not raw_ids:
        return targets
    for item in raw_ids.split(","):
        cleaned = item.strip()
        if cleaned:
            try:
                targets.append(int(cleaned))
            except ValueError:
                print(f"[ENV WARNING] ID Telegram tidak valid: {cleaned}")
    return targets


TARGET_CHAT_IDS = parse_target_chat_ids(RAW_TARGET_IDS)

# --- KONFIGURASI JADWAL TARGET PER SERVER (WIB) ---
SCHEDULE_CONFIG = {
    "london_dc": {"hour": 8, "minute": 45},
    "newyork_dc": {"hour": 13, "minute": 45},
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http = urllib3.PoolManager(cert_reqs="CERT_NONE", assert_hostname=False)
bot = Bot(token=TELEGRAM_TOKEN)

ETL_INDEX_CONFIG = {
    "index": "reportingkcln-*",
    "date_field": "@timestamp",
    "status_field": "status.keyword",
    "error_msg_field": "error_message",
    "fail_value": "GAGAL",
}

SERVERS = ["london_dc", "newyork_dc"]

REQUIRED_JOBS = [
    "run_edw_dblink.sh",
    "get_dump_file.sh",
    "restore_dump_file.sh",
    "run_edw.sh",
    "get_ext_file.sh",
    "run_ext_file.sh",
    "get_f1_file.sh",
    "run_f1_file.sh",
    "Batch_edw.sh",
]


# ================================
# HELPER ELASTICSEARCH & TIMESTAMP
# ================================
def es_api_for_rqst(http, method, path, body=None):
    url = f"{ES_HOST}{path}"
    token = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
    }
    try:
        r = http.request(
            method.upper(),
            url,
            body=json.dumps(body) if body else None,
            headers=headers,
        )
        return json.loads(r.data.decode("utf-8")) if r.data else {}
    except Exception as e:
        return {"error": str(e)}


def parse_es_timestamp(ts_raw: str):
    if not ts_raw or ts_raw == "-":
        return None
    try:
        clean_ts = ts_raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        return dt.astimezone()
    except Exception:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%b-%d %H:%M:%S.%f",
        ):
            try:
                dt_naive = datetime.strptime(ts_raw.split("+")[0].strip(), fmt)
                return dt_naive.replace(tzinfo=timezone.utc).astimezone()
            except ValueError:
                continue
    return None


def detect_server_name(source: dict, source_str_lower: str) -> str:
    srv_from_doc = (
        source.get("server")
        or source.get("server_name")
        or source.get("datacenter")
        or source.get("host", {}).get("name")
        or ""
    ).lower()

    if "london" in srv_from_doc or "london_dc" in source_str_lower:
        return "london_dc"
    elif "newyork" in srv_from_doc or "newyork_dc" in source_str_lower:
        return "newyork_dc"

    return None


def is_in_target_window_by_es_timestamp(es_ts_str: str, server: str) -> bool:
    dt = parse_es_timestamp(es_ts_str)
    if not dt:
        return False

    now = datetime.now().astimezone()
    if dt.date() != now.date():
        return False

    t = dt.time()
    if server == "london_dc":
        return time(8, 0, 0) <= t <= time(9, 0, 59)
    elif server == "newyork_dc":
        return time(13, 15, 0) <= t <= time(23, 59, 59)

    return False


# ================================
# FUNGSI CORE EVALUASI JOB
# ================================
def fetch_and_evaluate_jobs(hours_back=24):
    cfg = ETL_INDEX_CONFIG
    query = {
        "size": 1000,
        "sort": [{cfg["date_field"]: {"order": "asc"}}],
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            cfg["date_field"]: {
                                "gte": f"now-{hours_back}h",
                                "lte": "now",
                            }
                        }
                    }
                ]
            }
        },
    }

    res = es_api_for_rqst(http, "GET", f"/{cfg['index']}/_search", query)
    hits = res.get("hits", {}).get("hits", [])

    server_job_map = {srv: {} for srv in SERVERS}

    for hit in hits:
        doc_id = hit.get("_id", "")
        source = hit.get("_source", {})
        source_str_lower = json.dumps(source).lower()

        server = detect_server_name(source, source_str_lower)
        if not server or server not in SERVERS:
            continue

        es_timestamp = (
            source.get(cfg["date_field"]) or source.get("@timestamp") or "-"
        )
        if not is_in_target_window_by_es_timestamp(es_timestamp, server):
            continue

        start_time = source.get("start_time") or source.get("START_TIME") or "-"
        end_time = source.get("end_time") or source.get("END_TIME") or "-"
        status = (
            source.get(cfg["status_field"])
            or source.get("status")
            or source.get("STATUS")
            or "UNKNOWN"
        )
        error_msg = (
            source.get(cfg["error_msg_field"])
            or source.get("ERROR_MESSAGE")
            or source.get("error_message")
        )

        is_success = str(status).upper() not in [
            cfg["fail_value"].upper(),
            "FAILED",
            "ERROR",
        ]

        for req_job in REQUIRED_JOBS:
            if req_job.lower() in source_str_lower:
                if req_job not in server_job_map[server]:
                    server_job_map[server][req_job] = {
                        "doc_id": doc_id,
                        "job_name": req_job,
                        "status": str(status).upper(),
                        "error_msg": error_msg,
                        "count": 1 if is_success else 0,
                        "runs_history": (
                            [{"start": start_time, "end": end_time}]
                            if is_success
                            else []
                        ),
                    }
                else:
                    if is_success:
                        server_job_map[server][req_job]["count"] += 1
                        server_job_map[server][req_job]["runs_history"].append(
                            {"start": start_time, "end": end_time}
                        )

                    if str(status).upper() == cfg["fail_value"].upper():
                        server_job_map[server][req_job]["status"] = cfg[
                            "fail_value"
                        ].upper()
                        if error_msg:
                            server_job_map[server][req_job]["error_msg"] = error_msg

    return server_job_map


# ================================
# FUNGSI BROADCAST & FORMAT LAPORAN
# ================================
def broadcast_telegram_message(text: str, chat_ids: list):
    """Kirim pesan ke seluruh Chat ID yang terdaftar."""
    for cid in chat_ids:
        try:
            bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
        except Exception as e:
            print(f"[TELEGRAM ERROR] Gagal mengirim pesan ke Chat ID {cid}: {e}")


def send_report_check_etl(
    target_chat_ids, server_job_map, target_servers=None, is_auto=False
):
    if target_servers is None:
        target_servers = SERVERS

    # Konversi ke list jika passing single integer chat_id
    if isinstance(target_chat_ids, (int, str)):
        target_chat_ids = [target_chat_ids]

    tag_title = "🤖 *[AUTOMATIC NOTIFICATION]*\n" if is_auto else ""
    msg = f"{tag_title}📊 *LAPORAN AUDIT BATCH ETL (HARI INI)*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for server in target_servers:
        job_map = server_job_map.get(server, {})
        srv_name = server.upper()
        window_info = (
            "Jam 08:00 - 09:00" if server == "london_dc" else "Jam 13:15 - 23:59"
        )

        failed_jobs = []
        missing_jobs = []
        successful_jobs = []

        for req_job in REQUIRED_JOBS:
            if req_job in job_map:
                job_info = job_map[req_job]
                if job_info["status"] == ETL_INDEX_CONFIG["fail_value"].upper():
                    failed_jobs.append(job_info)
                else:
                    successful_jobs.append(job_info)
            else:
                missing_jobs.append(req_job)

        total_req = len(REQUIRED_JOBS)
        total_ok = len(successful_jobs)

        msg += f"🖥️ *SERVER: {srv_name}*\n"
        msg += f"⏱️ *Jendela Waktu Target:* {window_info}\n"
        msg += f"📈 *Status:* `{total_ok}/{total_req}` Job Berhasil\n"

        if failed_jobs or missing_jobs:
            if failed_jobs:
                msg += f"⚠️ *Job Gagal ({len(failed_jobs)}):*\n"
                for f in failed_jobs:
                    msg += f" • `{f['job_name']}` ({f['count']}x Run)\n"
                    if f["error_msg"]:
                        msg += f"   💬 _Err:_ `{str(f['error_msg'])[:80]}`\n"

            if missing_jobs:
                msg += f"🚫 *Job Missing/Belum Jalan ({len(missing_jobs)}):*\n"
                for m in missing_jobs:
                    msg += f" • `{m}`\n"

        msg += "📋 *Detail Status Job:*\n"
        for req_job in REQUIRED_JOBS:
            if req_job in job_map:
                st = job_map[req_job]["status"]
                cnt = job_map[req_job]["count"]
                history = job_map[req_job]["runs_history"]
                icon = "✅" if st != "GAGAL" else "❌"

                msg += f"{icon} `{req_job}` (`{cnt}x`) → *{st}*\n"

                if history:
                    first_run = history[0]
                    msg += f" ├ 🕒 _Run 1:_ `{first_run['start']}` s/d `{first_run['end']}`\n"
                    if len(history) > 1:
                        last_run = history[-1]
                        msg += f" └ 🕒 _Run {len(history)}:_ `{last_run['start']}` s/d `{last_run['end']}`\n"
            else:
                msg += f"❓ `{req_job}` → *MISSING*\n"

        msg += "\n-----------------------------\n\n"

    broadcast_telegram_message(msg, target_chat_ids)


def send_report_notif_gagal(target_chat_ids, server_job_map):
    if isinstance(target_chat_ids, (int, str)):
        target_chat_ids = [target_chat_ids]

    has_issues = False
    msg = "🚨 *[ALERT] DETEKSI MASALAH JOB ETL!* 🚨\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for server in SERVERS:
        job_map = server_job_map.get(server, {})
        srv_name = server.upper()
        failed_jobs = []
        missing_jobs = []

        for req_job in REQUIRED_JOBS:
            if req_job in job_map:
                job_info = job_map[req_job]
                if job_info["status"] == ETL_INDEX_CONFIG["fail_value"].upper():
                    failed_jobs.append(job_info)
            else:
                missing_jobs.append(req_job)

        if failed_jobs or missing_jobs:
            has_issues = True
            msg += f"🖥️ *SERVER: {srv_name}*\n"

            if failed_jobs:
                msg += f"❌ *JOB GAGAL ({len(failed_jobs)}):*\n"
                for f in failed_jobs:
                    msg += f"⚙️ Job: `{f['job_name']}` ({f['count']}x Run)\n"
                    if f["error_msg"]:
                        msg += f"💬 Error: `{str(f['error_msg'])[:150]}`\n"
                    msg += "-----------------------------\n"

            if missing_jobs:
                msg += f"⚠️ *JOB MISSING ({len(missing_jobs)}):*\n"
                for m in missing_jobs:
                    msg += f" • `{m}` (Tidak ada log pada jam target)\n"
                msg += "\n"

    if not has_issues:
        msg = "✅ *[OK]* Semua Job ETL di London & NewYork DC berjalan sukses sesuai jadwal."

    broadcast_telegram_message(msg, target_chat_ids)


# ================================
# TRACKING CACHE HARIAN PER SERVER
# ================================
DAILY_RUN_TRACKER_FILE = "daily_run_tracker.json"


def load_daily_run_tracker() -> dict:
    if os.path.exists(DAILY_RUN_TRACKER_FILE):
        try:
            with open(DAILY_RUN_TRACKER_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_daily_run_tracker(tracker_data: dict):
    try:
        with open(DAILY_RUN_TRACKER_FILE, "w") as f:
            json.dump(tracker_data, f)
    except Exception as e:
        print(f"[CACHE ERROR] Gagal menyimpan file cache: {e}")


def check_and_trigger_daily(context: CallbackContext = None):
    wib_tz = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib_tz)
    today_str = now_wib.strftime("%Y-%m-%d")

    tracker = load_daily_run_tracker()

    for server, sched in SCHEDULE_CONFIG.items():
        last_run_date = tracker.get(server)
        target_h = sched["hour"]
        target_m = sched["minute"]

        # Cek apakah sudah lewat jam target & belum dikirim hari ini
        if last_run_date != today_str:
            if (now_wib.hour, now_wib.minute) >= (target_h, target_m):
                time_str = f"{target_h:02d}:{target_m:02d}"
                print(
                    f"[{now_wib.strftime('%Y-%m-%d %H:%M:%S')}] [OTOMASI {server.upper()} - {time_str}] Mengevaluasi job ES..."
                )

                server_job_map = fetch_and_evaluate_jobs(hours_back=24)
                send_report_check_etl(
                    target_chat_ids=TARGET_CHAT_IDS,
                    server_job_map=server_job_map,
                    target_servers=[server],
                    is_auto=True,
                )

                tracker[server] = today_str
                save_daily_run_tracker(tracker)
                print(
                    f"[{now_wib.strftime('%Y-%m-%d %H:%M:%S')}] [OTOMASI {server.upper()}] Sukses dikirim ke {TARGET_CHAT_IDS} & di-cache."
                )


def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    chat_id = update.message.chat_id
    parts = text.split()
    cmd = parts[0]

    hours_back = 24
    if len(parts) > 1 and parts[1].endswith("h"):
        try:
            hours_back = int(parts[1][:-1])
        except ValueError:
            hours_back = 24

    if cmd in ["/check_etl_gagal", "/notif_gagal"]:
        bot.send_message(
            chat_id=chat_id,
            text=f"⏳ *Memeriksa {len(REQUIRED_JOBS)} Job ETL Wajib per Server...*",
            parse_mode="Markdown",
        )
        server_job_map = fetch_and_evaluate_jobs(hours_back=hours_back)

        if cmd == "/check_etl_gagal":
            send_report_check_etl(chat_id, server_job_map, is_auto=False)
        elif cmd == "/notif_gagal":
            send_report_notif_gagal(chat_id, server_job_map)


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("check_etl_gagal", handle_message))
    dp.add_handler(CommandHandler("notif_gagal", handle_message))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    job_queue = updater.job_queue
    # Loop pengecekan interval 60 detik
    job_queue.run_repeating(check_and_trigger_daily, interval=60, first=5)

    print(
        f"[INFO] Bot Berjalan... Standby London (08:45 WIB) & New York (13:45 WIB). Target IDs: {TARGET_CHAT_IDS}"
    )

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()