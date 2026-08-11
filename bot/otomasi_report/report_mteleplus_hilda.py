import json
import base64
import os
import urllib3
import xlsxwriter
from datetime import datetime
from io import BytesIO
from pathlib import Path
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from utils.env_loader import load_env_file

load_env_file(Path(__file__).resolve().parents[2] / ".env")

# =====================================================================
# GLOBAL CONFIGURATION (PURE STANDALONE MTELEPLUS)
# =====================================================================
ES_HOST = os.environ.get("ES_HOST", "")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")
INDEX_PATTERN = "log-mteleplus*"
DATE_FIELD = "date_origin"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http = urllib3.PoolManager(cert_reqs='CERT_NONE', assert_hostname=False)

TOKEN = os.environ.get("TELEGRAM_TOKEN_REPORTS", "")
bot = Bot(token=TOKEN)

# Rule Query String khusus log-mteleplus*
MTELEPLUS_RULES = {
    "akt": {
        "success": '(sms_content:("Kartu Kredit BNI Anda telah aktif*" OR "Kartu Kredit BNI Anda sudah aktif*" OR "Terima kasih, Kartu Kredit BNI Anda telah aktif*")) OR (send_to_hp:("Kartu Kredit BNI Anda telah aktif*" OR "Kartu Kredit BNI Anda sudah aktif*"))',
        "fail": '(sms_content:("Aktivasi Kartu Kredit BNI Anda tidak dapat kami proses*" OR "Maaf, permintaan Aktivasi Anda ditolak*")) OR (send_to_hp:("Aktivasi Kartu Kredit BNI Anda tidak dapat kami proses*" OR "Maaf, permintaan Aktivasi Anda ditolak*")) OR send_to_hp.keyword:"Aktivasi Kartu Kredit BNI Anda tidak dapat kami proses. Silakan Hubungi BNI Call 1500046." OR send_to_hp.keyword:"Maaf, transaksi Anda tidak dapat kami proses. Silakan hubungi BNI Call 1500046."'
    },
    "rpin": {
        "success": '(sms_content:("Permintaan PIN berhasil*" OR "RPIN*")) OR (send_to_hp:("Permintaan PIN berhasil*")) OR (message_cc:("Permintaan PIN berhasil*"))',
        "fail": 'sms_content:"Maaf, transaksi RPIN anda ditolak*" OR send_to_hp:"Maaf, transaksi RPIN anda ditolak,*"'
    }
}

# =====================================================================
# CORE ELASTICSEARCH FUNCTION
# =====================================================================
def es_api_for_rqst(http, method, path, body=None):
    url = f"{ES_HOST}{path}"
    token = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {token}"}
    try:
        r = http.request(method.upper(), url, body=json.dumps(body) if body else None, headers=headers)
        return json.loads(r.data.decode("utf-8")) if r.data else {}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------------------
# FUNCTION: KHUSUS MTELEPLUS REPORT (MURNI VOLUME HITS)
# ---------------------------------------------------------------------
def cmd_report_mteleplus(chat_id, user_id, username, target_index):
    """Fungsi mandiri mTeleplus untuk menghitung volume hit harian incoming/outgoing"""
    bot.send_message(chat_id, f"Sedang diproses ... ⏳")
    print(f"=== MTELEPLUS VOLUME REPORT REQUESTED BY {username} ({user_id}) FOR INDEX {target_index} ===")

    # DSL Query murni aggr terms bawaan Elasticsearch (Sangat Ringan)
    dsl_query = {
        "size": 0,
        "query": {"range": {DATE_FIELD: {"gte": "now-31d/d", "lte": "now-1d/d"}}},
        "aggs": {
            "per_day": {
                "date_histogram": {"field": DATE_FIELD, "calendar_interval": "1d", "min_doc_count": 0},
                "aggs": {
                    "by_direction": {
                        "terms": {"field": "direction.keyword", "missing": "unknown"}
                    }
                }
            }
        }
    }
    
    # Injeksi filter rules hit count (akt & rpin)
    for group_name, rule in MTELEPLUS_RULES.items():
        dsl_query["aggs"]["per_day"]["aggs"][f"{group_name}_success"] = {"filter": {"query_string": {"query": rule["success"]}}}
        dsl_query["aggs"]["per_day"]["aggs"][f"{group_name}_fail"] = {"filter": {"query_string": {"query": rule["fail"]}}}
        
    res = es_api_for_rqst(http, "GET", f"/{target_index}/_search", dsl_query)
    
    if "aggregations" not in res:
        bot.send_message(chat_id, "Data mTeleplus tidak tersedia ❌")
        return

    report_data = {}
    for bucket in res["aggregations"]["per_day"]["buckets"]:
        date_str = bucket["key_as_string"][:10]
        day_data = {
            "total_incoming": 0,
            "total_outgoing": 0
        }
        
        # Ambil volume hits berdasarkan rule pencocokan string string
        for group_name in MTELEPLUS_RULES.keys():
            day_data[f"{group_name}_success"] = bucket.get(f"{group_name}_success", {}).get("doc_count", 0)
            day_data[f"{group_name}_fail"] = bucket.get(f"{group_name}_fail", {}).get("doc_count", 0)
            
        # Ambil volume murni data direction dari terms sub-bucket (incoming / outgoing)
        for d_bucket in bucket.get("by_direction", {}).get("buckets", []):
            direction_key = d_bucket["key"]
            doc_count_val = d_bucket.get("doc_count", 0)
            
            if direction_key == "incoming": 
                day_data["total_incoming"] = doc_count_val
            elif direction_key == "outgoing": 
                day_data["total_outgoing"] = doc_count_val
                
        report_data[date_str] = day_data

    # Proses generate Excel spreadsheet
    output = BytesIO()
    with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
        ws = workbook.add_worksheet("MTeleplus Summary")
        
        # Susunan Header Kolom Baru Tanpa Metrik Rata-rata Waktu (Avg RT)
        headers = ["no", "date"]
        for group in MTELEPLUS_RULES.keys():
            headers += [f"{group}_success", f"{group}_fail", f"{group}_total"]
        headers += ["total_success", "total_fail", "total_incoming", "total_outgoing"]
        
        for col, h in enumerate(headers):
            ws.write(0, col, h)
            
        # Write rows
        for i, d in enumerate(sorted(report_data.keys()), 1):
            data = report_data[d]
            row = [i, d]
            ts, tf = 0, 0
            
            for group in MTELEPLUS_RULES.keys():
                succ = data[f"{group}_success"]
                fail = data[f"{group}_fail"]
                total = succ + fail
                row += [succ, fail, total]
                ts += succ
                tf += fail
                
            # Memasukkan total success, total fail, serta hit harian incoming & outgoing
            row += [ts, tf, data["total_incoming"], data["total_outgoing"]]
            
            for col, val in enumerate(row):
                ws.write(i, col, val)

            print(f"=== Report Row {i} === Date={d} Incoming={data['total_incoming']} Outgoing={data['total_outgoing']}")

    output.seek(0)
    bot.send_document(chat_id, output, filename="report_mteleplus_volume.xlsx")


# ---------------------------------------------------------------------
# EXISTING FUNCTION: UNTUK ENGINE NOTIF (DIJAGA TETAP SEPERTI ASLINYA)
# ---------------------------------------------------------------------
def cmd_report_engine_notif(chat_id, user_id, username, index_name):
    """Fungsi lama untuk engine notif asli Anda"""
    bot.send_message(chat_id, f"Sedang diproses (Engine Notif) ... ⏳")
    print(f"=== ENGINE NOTIF REQUESTED BY {username} ({user_id}) FOR INDEX ALIAS {index_name} ===")
    bot.send_message(chat_id, f"Fitur core engine_notif beralih ke index: {index_name}")


# =====================================================================
# DISPATCHER AND MAIN INITIALIZATION
# =====================================================================
def handle_message(update: Update, context: CallbackContext):
    text     = update.message.text
    chat_id  = update.message.chat_id
    user_id  = update.message.from_user.id
    username = update.message.from_user.username

    # Routing logic berdasarkan keyword chat command
    if text.startswith("/engine_notif_"):
        idx = text.split("_", 2)[2]
        cmd_report_engine_notif(chat_id, user_id, username, idx)
        
    elif text == "/report_engine_notif":
        cmd_report_engine_notif(chat_id, user_id, username, "enginenotif_ttrx")
        
    elif text == "/report_mteleplus":
        # Jalur terpisah khusus memanggil fungsi volume mTeleplus mandiri
        cmd_report_mteleplus(chat_id, user_id, username, INDEX_PATTERN)


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Text Message Handler untuk chat biasa
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    # Command Handlers resmi agar dikenali oleh bot menu Telegram
    dp.add_handler(CommandHandler("report_engine_notif", handle_message))
    dp.add_handler(CommandHandler("report_mteleplus", handle_message))
    
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()