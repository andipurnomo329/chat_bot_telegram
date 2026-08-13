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

load_env_file(Path(__file__).resolve().parents[1] / ".env")

# ================================
# KONFIGURASI & KREDENSIAL
# ================================
ES_HOST = os.environ.get("ES_HOST", "")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_REPORTS", "")
AUTO_NOTIF_CHAT_ID = 1399365875

CACHE_FILE = "auto_notif_cache.json"

# --- KONFIGURASI JADWAL OTOMASI HARIAN ---
# Ubah nilai di sini jika ingin mengganti jam/menit (Misal ke 17:30 -> TARGET_HOUR = 17, TARGET_MINUTE = 30)
TARGET_HOUR = 8
TARGET_MINUTE = 0

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
# HELPER CACHE & ELASTICSEARCH
# ================================
def load_cache() -> set:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[CACHE WARNING] Gagal membaca file cache: {e}")
    return set()


def save_cache(cache_set: set):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(list(cache_set), f)
    except Exception as e:
        print(f"[CACHE ERROR] Gagal menyimpan file cache: {e}")


notified_auto_cache = load_cache()


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


# ================================
# HELPER PARSING TIMEZONE
# ================================
def parse_es_timestamp(ts_raw: str):
    """Merapikan format @timestamp Elasticsearch dan konversi ke Waktu Lokal (WIB)."""
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

    # Cek Current Day berdasarkan Waktu Lokal
    if dt.date() != now.date():
        return False

    t = dt.time()
    if server == "london_dc":
        return time(8, 0, 0) <= t <= time(9, 0, 59)
    elif server == "newyork_dc":
        return time(13, 15, 0) <= t <= time(23, 59, 59)

    return False


# ================================
# FUNGSI CORE PENGECEKAN JOB ETL
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
                                "gte": "now-24h",
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

        start_time = (
            source.get("start_time") or source.get("START_TIME") or "-"
        )
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
                            server_job_map[server][req_job]["error_msg"] = (
                                error_msg
                            )

    return server_job_map


# ================================
# FUNGSI FORMATTING LAPORAN
# ================================
def send_report_check_etl(
    chat_id, server_job_map, hours_back=24, is_auto=False
):
    tag_title = "🤖 *[AUTOMATIC NOTIFICATION]*\n" if is_auto else ""
    msg = f"{tag_title}📊 *LAPORAN AUDIT BATCH ETL (HARI INI)*\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for server in SERVERS:
        job_map = server_job_map.get(server, {})
        srv_name = server.upper()

        window_info = (
            "Jam 08:00 - 09:00"
            if server == "london_dc"
            else "Jam 13:15 - 23:59"
        )

        failed_jobs = []
        missing_jobs = []
        successful_jobs = []

        for req_job in REQUIRED_JOBS:
            if req_job in job_map:
                job_info = job_map[req_job]
                if (
                    job_info["status"]
                    == ETL_INDEX_CONFIG["fail_value"].upper()
                ):
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
                        msg += (
                            f"   💬 _Err:_ `{str(f['error_msg'])[:80]}`\n"
                        )

            if missing_jobs:
                msg += f"🚫 *Job Missing/Belum Jalan ({len(missing_jobs)}):*\n"
                for m in missing_jobs:
                    msg += f" • `{m}`\n"

        msg += f"📋 *Detail Status Job:*\n"
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

    bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")


def send_report_notif_gagal(chat_id, server_job_map, hours_back=24):
    has_issues = False
    msg = f"🚨 *[ALERT] DETEKSI MASALAH JOB ETL!* 🚨\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for server in SERVERS:
        job_map = server_job_map.get(server, {})
        srv_name = server.upper()
        failed_jobs = []
        missing_jobs = []

        for req_job in REQUIRED_JOBS:
            if req_job in job_map:
                job_info = job_map[req_job]
                if (
                    job_info["status"]
                    == ETL_INDEX_CONFIG["fail_value"].upper()
                ):
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
        msg = f"✅ *[OK]* Semua Job ETL di London & NewYork DC berjalan sukses sesuai jadwal."

    bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")


# ================================
# LOGIKA OTOMASI & HANDLER
# ================================
def auto_trigger_notif(context: CallbackContext):
    global notified_auto_cache
    chat_id = AUTO_NOTIF_CHAT_ID

    try:
        server_job_map = fetch_and_evaluate_jobs(hours_back=24)

        status_signature_list = []
        for srv in sorted(SERVERS):
            job_map = server_job_map.get(srv, {})
            for req_job in sorted(REQUIRED_JOBS):
                if req_job in job_map:
                    info = job_map[req_job]
                    status_signature_list.append(
                        f"{srv}:{req_job}:{info['doc_id']}:{info['status']}:{info['count']}:{info['runs_history']}"
                    )
                else:
                    status_signature_list.append(f"{srv}:{req_job}:MISSING")

        current_auto_key = "|".join(status_signature_list)

        if current_auto_key not in notified_auto_cache:
            send_report_check_etl(
                chat_id=chat_id,
                server_job_map=server_job_map,
                hours_back=24,
                is_auto=True,
            )
            notified_auto_cache.add(current_auto_key)
            save_cache(notified_auto_cache)
            print("[OTOMASI] Notifikasi otomatis berhasil dikirimkan.")
        else:
            print("[OTOMASI] State log ini sudah pernah dikirim. Skip.")

    except Exception as e:
        print(f"[OTOMASI ERROR] Gagal mengeksekusi otomatisasi: {e}")


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
            send_report_check_etl(
                chat_id, server_job_map, hours_back=hours_back, is_auto=False
            )
        elif cmd == "/notif_gagal":
            send_report_notif_gagal(
                chat_id, server_job_map, hours_back=hours_back
            )


# ================================
# FUNGSI CACHE & OTOMASI HARIAN
# ================================
LAST_DAILY_RUN_FILE = "last_daily_run_bot_kcln.txt"


def has_run_today() -> bool:
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_DAILY_RUN_FILE):
        try:
            with open(LAST_DAILY_RUN_FILE, "r") as f:
                return f.read().strip() == today_str
        except Exception:
            pass
    return False


def record_run_today():
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(LAST_DAILY_RUN_FILE, "w") as f:
            f.write(today_str)
    except Exception as e:
        print(f"[ERROR] Gagal mencatat cache tanggal: {e}")


def check_and_trigger_daily(context: CallbackContext = None):
    # Menggunakan datetime dengan Timezone Asia/Jakarta secara konsisten
    wib_tz = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib_tz)

    # Cek apakah sudah pernah berjalan sukses hari ini
    if not has_run_today():
        # Cek apakah jam saat ini sudah melewati target (17:30 WIB)
        if (now_wib.hour, now_wib.minute) >= (TARGET_HOUR, TARGET_MINUTE):
            time_str = f"{TARGET_HOUR:02d}:{TARGET_MINUTE:02d}"
            print(
                f"[{now_wib.strftime('%Y-%m-%d %H:%M:%S')}] [OTOMASI {time_str}] Memulai evaluasi job ES harian..."
            )
            
            # PAKSA KIRIM TANPA SKIPPING VIA CACHE STATE DENGAN MENGIRIM REPORT DIRECTLY
            server_job_map = fetch_and_evaluate_jobs(hours_back=24)
            send_report_check_etl(
                chat_id=AUTO_NOTIF_CHAT_ID,
                server_job_map=server_job_map,
                hours_back=24,
                is_auto=True,
            )
            
            # Catat bahwa laporan harian tanggal ini SUDAH berhasil dikirim
            record_run_today()
            print(
                f"[{now_wib.strftime('%Y-%m-%d %H:%M:%S')}] [OTOMASI {time_str}] Sukses dikirim dan di-cache."
            )
    else:
        time_str = f"{TARGET_HOUR:02d}:{TARGET_MINUTE:02d}"
        print(
            f"[{now_wib.strftime('%Y-%m-%d %H:%M:%S')}] Notifikasi harian {time_str} WIB sudah pernah dikirim hari ini. Skip."
        )


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("check_etl_gagal", handle_message))
    dp.add_handler(CommandHandler("notif_gagal", handle_message))
    dp.add_handler(
        MessageHandler(Filters.text & ~Filters.command, handle_message)
    )

    job_queue = updater.job_queue

    # Periodic check setiap 60 detik untuk otomasi 17:30 WIB
    job_queue.run_repeating(
        check_and_trigger_daily, 
        interval=60, 
        first=5
    )

    time_str = f"{TARGET_HOUR:02d}:{TARGET_MINUTE:02d}"
    print(
        f"[INFO] Bot Berjalan... Standby penjadwalan harian jam {time_str} WIB aktif."
    )
    
    # === BARIS PENTING DARI SINI ===
    updater.start_polling()
    updater.idle()  # <--- PASTIKAN BARIS INI ADA! Ini yang menahan script agar tidak exit code 0.
    
if __name__ == "__main__":
    main()