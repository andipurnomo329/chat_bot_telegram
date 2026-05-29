import json
import base64
import urllib3
import xlsxwriter
from datetime import datetime
from io import BytesIO
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# =====================================================================
# GLOBAL CONFIGURATION (PURE STANDALONE MTELEPLUS)
# =====================================================================
ES_HOST = "https://192.168.45.15:443"
ES_USERNAME = "app_super"
ES_PASSWORD = "appsuperpassw0rd"
INDEX_PATTERN = "log-mteleplus*"
DATE_FIELD = "date_origin"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http = urllib3.PoolManager(cert_reqs='CERT_NONE', assert_hostname=False)

TOKEN = "8469715430:AAGpWw9g4zTBIe51NlA7fRACK9Jy7I1eMZw"
bot = Bot(token=TOKEN)

# Rule Query String khusus log-mteleplus-*
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
# CORE ELASTICSEARCH FUNCTION FOR MTELEPLUS
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

def cmd_report_engine_notif(chat_id, user_id, username, index_name, sendingtypes=None):
    """Fungsi utama mTeleplus standalone yang diikat ke nama fungsi lama Anda"""
    bot.send_message(chat_id, f"Sedang diproses ... ⏳")
    
    # Cetak log debug request ke console server
    print(f"=== REPORT REQUESTED BY {username} ({user_id}) FOR INDEX ALIAS {index_name} ===")

    # Membangun Query DSL Khusus Query String & Response Time Split Direction
    dsl_query = {
        "size": 0,
        "query": {"range": {DATE_FIELD: {"gte": "now-31d/d", "lte": "now-1d/d"}}},
        "aggs": {
            "per_day": {
                "date_histogram": {"field": DATE_FIELD, "calendar_interval": "1d", "min_doc_count": 0},
                "aggs": {
                    "avg_responsetime": {
                        "avg": {
                            "script": {
                                "source": "doc.containsKey('sendingtime') && !doc['sendingtime'].empty ? Math.abs(doc['sendingtime'].value.toInstant().toEpochMilli() - doc['" + DATE_FIELD + "'].value.toInstant().toEpochMilli()) : 0"
                            }
                        }
                    },
                    "by_direction": {
                        "terms": {"field": "direction.keyword", "missing": "unknown"},
                        "aggs": {
                            "avg_responsetime": {
                                "avg": {
                                    "script": {
                                        "source": "doc.containsKey('sendingtime') && !doc['sendingtime'].empty ? Math.abs(doc['sendingtime'].value.toInstant().toEpochMilli() - doc['" + DATE_FIELD + "'].value.toInstant().toEpochMilli()) : 0"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    # Injeksi kueri rules dinamis
    for group_name, rule in MTELEPLUS_RULES.items():
        dsl_query["aggs"]["per_day"]["aggs"][f"{group_name}_success"] = {"filter": {"query_string": {"query": rule["success"]}}}
        dsl_query["aggs"]["per_day"]["aggs"][f"{group_name}_fail"] = {"filter": {"query_string": {"query": rule["fail"]}}}
        
    res = es_api_for_rqst(http, "GET", f"/{INDEX_PATTERN}/_search", dsl_query)
    
    if "aggregations" not in res:
        bot.send_message(chat_id, "Data tidak tersedia ❌")
        return

    # Parsing JSON Response dari Elasticsearch
    report_data = {}
    for bucket in res["aggregations"]["per_day"]["buckets"]:
        date_str = bucket["key_as_string"][:10]
        day_data = {}
        for group_name in MTELEPLUS_RULES.keys():
            day_data[f"{group_name}_success"] = bucket.get(f"{group_name}_success", {}).get("doc_count", 0)
            day_data[f"{group_name}_fail"] = bucket.get(f"{group_name}_fail", {}).get("doc_count", 0)
            
        day_data["avg_all"] = (bucket.get("avg_responsetime", {}).get("value") or 0) / 1000
        day_data["avg_incoming"] = 0
        day_data["avg_outgoing"] = 0
        
        for d_bucket in bucket.get("by_direction", {}).get("buckets", []):
            avg_val = (d_bucket.get("avg_responsetime", {}).get("value") or 0) / 1000
            if d_bucket["key"] == "incoming": day_data["avg_incoming"] = avg_val
            elif d_bucket["key"] == "outgoing": day_data["avg_outgoing"] = avg_val
                
        report_data[date_str] = day_data

    # Generate File Spreadsheet Excel
    output = BytesIO()
    with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
        ws = workbook.add_worksheet("mTeleplus Summary")
        num_format_2dec = workbook.add_format({'num_format': '0.00'})
        
        # Susun susunan Header Kolom Excel baru Anda
        headers = ["no", "date"]
        for group in MTELEPLUS_RULES.keys():
            headers += [f"{group}_success", f"{group}_fail", f"{group}_total"]
        headers += ["total_success", "total_fail", "avg_rt_incoming(s)", "avg_rt_outgoing(s)", "avg_responsetime(s)"]
        
        for col, h in enumerate(headers):
            ws.write(0, col, h)
            
        # Mengisi data baris demi baris
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
                
            row += [ts, tf, data["avg_incoming"], data["avg_outgoing"], data["avg_all"]]
            
            for col, val in enumerate(row):
                ws.write(i, col, val, num_format_2dec if isinstance(val, float) else None)
                
            print(f"=== Report Row {i} === Date={d} Total_Success={ts} Total_Fail={tf} AvgRT={data['avg_all']:.2f}")

    output.seek(0)
    bot.send_document(chat_id, output, filename="report_mteleplus_standalone.xlsx")


# =====================================================================
# DISPATCHER AND MAIN INITIALIZATION (AS IS FROM YOUR PRINCIPLE)
# =====================================================================
def handle_message(update: Update, context: CallbackContext):
    text     = update.message.text
    chat_id  = update.message.chat_id
    user_id  = update.message.from_user.id
    username = update.message.from_user.username

    if text.startswith("/engine_notif_"):
        idx = text.split("_", 2)[2]   # ambil nama index setelah prefix
        cmd_report_engine_notif(chat_id, user_id, username, idx)
    elif text == "/report_engine_notif":
        cmd_report_engine_notif(chat_id, user_id, username, "enginenotif_ttrx")


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("report_engine_notif", handle_message))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()