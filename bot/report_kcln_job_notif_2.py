import base64
import json
import os
import urllib3
from telegram import Bot, Update
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    Filters,
    MessageHandler,
    Updater,
)

# ================================
# KONFIGURASI & KREDENSIAL
# ================================
ES_HOST = "https://192.168.45.15:443"
ES_USERNAME = "app_super"
ES_PASSWORD = "appsuperpassw0rd"

TELEGRAM_TOKEN = "8469715430:AAGpWw9g4zTBIe51NlA7fRACK9Jy7I1eMZw"
AUTO_NOTIF_CHAT_ID = 1399365875

# File lokal untuk persitensi cache agar tahan saat bot restart
CACHE_FILE = "auto_notif_cache.json"

# Nonaktifkan warning SSL Certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http = urllib3.PoolManager(cert_reqs="CERT_NONE", assert_hostname=False)
bot = Bot(token=TELEGRAM_TOKEN)

# Konfigurasi Index ETL
ETL_INDEX_CONFIG = {
    "index": "reportingkcln-*",
    "date_field": "@timestamp",
    "job_name_field": "job_name.keyword",
    "file_name_field": "filename.keyword",
    "status_field": "status.keyword",
    "error_msg_field": "error_message",
    "fail_value": "GAGAL",
}

# DAFTAR 9 JOB WAJIB (REQUIRED JOBS)
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
# HELPER PERSISTENSI CACHE (FILE)
# ================================
def load_cache() -> set:
    """Membaca cache dari file JSON jika ada."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                return set(data)
        except Exception as e:
            print(f"[CACHE WARNING] Gagal membaca file cache: {e}")
    return set()


def save_cache(cache_set: set):
    """Menyimpan cache ke file JSON."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(list(cache_set), f)
    except Exception as e:
        print(f"[CACHE ERROR] Gagal menyimpan file cache: {e}")


# Inisialisasi cache dari file saat bot pertama kali nyala
notified_auto_cache = load_cache()


# ================================
# HELPER ELASTICSEARCH API
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


# ================================
# FUNGSI CORE PENGECEKAN JOB ETL
# ================================
def fetch_and_evaluate_jobs(hours_back=24):
    cfg = ETL_INDEX_CONFIG
    
    # KITA REVISI QUERY: Filter langsung dari Elasticsearch agar tidak tertutup log lain!
    should_clauses = [{"wildcard": {"*": f"*{job}*"}} for job in REQUIRED_JOBS]
    
    query = {
        "size": 500,  # Naikkan batas jika perlu
        "sort": [{cfg["date_field"]: {"order": "desc"}}],
        "query": {
            "bool": {
                "must": [
                    {"range": {cfg["date_field"]: {"gte": f"now-{hours_back}h", "lte": "now"}}}
                ]
            }
        }
    }

    res = es_api_for_rqst(http, "GET", f"/{cfg['index']}/_search", query)
    hits = res.get("hits", {}).get("hits", [])

    job_status_map = {}

    for hit in hits:
        doc_id = hit.get("_id", "")
        source = hit.get("_source", {})
        
        # Ubah seluruh isi dokumen menjadi string JSON lowercase untuk pencarian cepat
        source_str_lower = json.dumps(source).lower()

        status = (
            source.get(cfg["status_field"])
            or source.get("status")
            or source.get("STATUS")
            or "UNKNOWN"
        )
        error_msg = source.get(cfg["error_msg_field"]) or source.get("ERROR_MESSAGE") or source.get("error_message")
        end_time = (
            source.get("end_time")
            or source.get("END_TIME")
            or source.get(cfg["date_field"])
            or "-"
        )

        for req_job in REQUIRED_JOBS:
            # Pengecekan fleksibel: Jika nama file sh ada di dalam isi dokumen log
            if req_job.lower() in source_str_lower:
                if req_job not in job_status_map:
                    job_status_map[req_job] = {
                        "doc_id": doc_id,
                        "job_name": req_job,
                        "status": str(status).upper(),
                        "error_msg": error_msg,
                        "end_time": end_time,
                    }

    return job_status_map


# ================================
# FUNGSI FORMATTING LAPORAN
# ================================
def send_report_check_etl(chat_id, job_status_map, hours_back=24, is_auto=False):
    failed_jobs = []
    missing_jobs = []
    successful_jobs = []

    for req_job in REQUIRED_JOBS:
        if req_job in job_status_map:
            job_info = job_status_map[req_job]
            if job_info["status"] == ETL_INDEX_CONFIG["fail_value"].upper():
                failed_jobs.append(job_info)
            else:
                successful_jobs.append(job_info)
        else:
            missing_jobs.append(req_job)

    total_req = len(REQUIRED_JOBS)
    total_ok = len(successful_jobs)

    tag_title = "🤖 *[AUTOMATIC NOTIFICATION]*\n" if is_auto else ""
    msg = f"{tag_title}📊 *LAPORAN AUDIT BATCH ETL ({hours_back} JAM TERAKHIR)*\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📈 *Ringkasan Status:* `{total_ok}/{total_req}` Job Berhasil\n\n"

    if failed_jobs or missing_jobs:
        msg += f"❌ *STATUS KESELURUHAN: GAGAL / INCOMPLETE*\n\n"

        if failed_jobs:
            msg += f"⚠️ *Daftar Job Gagal ({len(failed_jobs)}):*\n"
            for f in failed_jobs:
                msg += f"• `{f['job_name']}` (Selesai: `{f['end_time']}`)\n"
                if f["error_msg"]:
                    msg += f"   💬 _Err:_ `{str(f['error_msg'])[:100]}`\n"
            msg += "\n"

        if missing_jobs:
            msg += f"🚫 *Daftar Job Missing/Belum Jalan ({len(missing_jobs)}):*\n"
            for m in missing_jobs:
                msg += f"• `{m}`\n"
            msg += "\n"
    else:
        msg += f"✅ *STATUS KESELURUHAN: BERHASIL LENGKAP*\n\n"

    msg += f"📋 *Rincian Ke-9 Job ETL Wajib:*\n"
    for req_job in REQUIRED_JOBS:
        if req_job in job_status_map:
            st = job_status_map[req_job]["status"]
            time_finish = job_status_map[req_job]["end_time"]
            icon = "✅" if st != "GAGAL" else "❌"
            msg += f"{icon} `{req_job}` → *{st}* (🕒 `{time_finish}`)\n"
        else:
            msg += f"❓ `{req_job}` → *MISSING*\n"

    bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")


def send_report_notif_gagal(chat_id, job_status_map, hours_back=24):
    failed_jobs = []
    missing_jobs = []

    for req_job in REQUIRED_JOBS:
        if req_job in job_status_map:
            job_info = job_status_map[req_job]
            if job_info["status"] == ETL_INDEX_CONFIG["fail_value"].upper():
                failed_jobs.append(job_info)
        else:
            missing_jobs.append(req_job)

    if not failed_jobs and not missing_jobs:
        msg = f"✅ *[OK]* Semua {len(REQUIRED_JOBS)} Job ETL berjalan sukses dalam {hours_back} jam terakhir."
        bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        return

    msg = f"🚨 *[ALERT] DETEKSI MASALAH JOB ETL!* 🚨\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    if failed_jobs:
        msg += f"❌ *JOB GAGAL ({len(failed_jobs)}):*\n"
        for f in failed_jobs:
            msg += f"⚙️ Job: `{f['job_name']}`\n"
            msg += f"🕒 Selesai: `{f['end_time']}`\n"
            if f["error_msg"]:
                msg += f"💬 Error: `{str(f['error_msg'])[:150]}`\n"
            msg += "-----------------------------\n"

    if missing_jobs:
        msg += f"⚠️ *JOB MISSING ({len(missing_jobs)}):*\n"
        for m in missing_jobs:
            msg += f"• `{m}` (Tidak ada log)\n"

    bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")


# ================================
# LOGIKA OTOMASI MURNI
# ================================
def auto_trigger_notif(context: CallbackContext):
    global notified_auto_cache
    chat_id = AUTO_NOTIF_CHAT_ID

    try:
        job_status_map = fetch_and_evaluate_jobs(hours_back=24)

        status_signature_list = []
        for req_job in sorted(REQUIRED_JOBS):
            if req_job in job_status_map:
                info = job_status_map[req_job]
                status_signature_list.append(
                    f"{req_job}:{info['doc_id']}:{info['status']}:{info['end_time']}"
                )
            else:
                status_signature_list.append(f"{req_job}:MISSING")

        current_auto_key = "|".join(status_signature_list)

        # Cek apakah state ini sudah pernah dikirim (meskipun bot pernah di-restart)
        if current_auto_key not in notified_auto_cache:
            send_report_check_etl(
                chat_id=chat_id,
                job_status_map=job_status_map,
                hours_back=24,
                is_auto=True,
            )
            # Simpan ke memori dan tulis ke file lokal (JSON)
            notified_auto_cache.add(current_auto_key)
            save_cache(notified_auto_cache)
            print("[OTOMASI] Notifikasi otomatis berhasil dikirimkan.")
        else:
            print("[OTOMASI] State log ini sudah pernah dikirim secara otomatis. Skip.")

    except Exception as e:
        print(f"[OTOMASI ERROR] Gagal mengeksekusi otomatisasi: {e}")


# ================================
# HANDLER COMMAND TELEGRAM
# ================================
def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    chat_id = update.message.chat_id

    print(f"Pesan Diterima dari Chat ID: {chat_id}")

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
            text=f"⏳ *Memeriksa {len(REQUIRED_JOBS)} Job ETL Wajib ({hours_back} jam terakhir)...*",
            parse_mode="Markdown",
        )
        job_status_map = fetch_and_evaluate_jobs(hours_back=hours_back)

        if cmd == "/check_etl_gagal":
            send_report_check_etl(
                chat_id, job_status_map, hours_back=hours_back, is_auto=False
            )
        elif cmd == "/notif_gagal":
            send_report_notif_gagal(
                chat_id, job_status_map, hours_back=hours_back
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

    # Pengaturan toleransi latensi (misfire_grace_time) agar peringatan 'Run time missed' tidak muncul
    job_queue.run_once(auto_trigger_notif, when=3, job_kwargs={'misfire_grace_time': 60})
    job_queue.run_repeating(auto_trigger_notif, interval=900, first=10, job_kwargs={'misfire_grace_time': 60})

    print("Bot Berjalan... Menunggu pengecekan otomatis...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()