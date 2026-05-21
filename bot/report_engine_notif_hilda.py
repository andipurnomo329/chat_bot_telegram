import json,base64
import urllib3
import xlsxwriter
from datetime import datetime,timedelta
from io import BytesIO
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

ES_HOST = "https://192.168.45.15:443"
ES_USERNAME="app_super"
ES_PASSWORD="appsuperpassw0rd"

http = urllib3.PoolManager(cert_reqs='CERT_NONE', assert_hostname=False)

TOKEN = "8469715430:AAGpWw9g4zTBIe51NlA7fRACK9Jy7I1eMZw"
bot = Bot(token=TOKEN)

def es_api_for_rqst(http, method, path, body=None):
    url = f"{ES_HOST}{path}"
    token = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {token}"}
    try:
        r = http.request(method.upper(), url, body=json.dumps(body) if body else None, headers=headers)
        return json.loads(r.data.decode("utf-8")) if r.data else {}
    except Exception as e:
        return {"error": str(e)}


def cmd_report_engine_notif(chat_id, user_id, username, interval=None):
    # set_time_for_report = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
    # now_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    query_body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"responseMaverick": 1}},
                    {"range": {"date_origin": {"gte": "now-14d/d", "lte": "now/d"}}}
                ]
            }
        },
        "aggs": {
            "per_day": {
                "date_histogram": {
                    "field": "date_origin",
                    "fixed_interval": "1d",
                    "min_doc_count": 0,   # penting: biar hari kosong tetap muncul
                    "extended_bounds": {
                       "min": "now-14d/d",
                       "max": "now/d"
                    }
                },
                "aggs": {
                    "jumlah_mvrk": {"value_count": {"field": "_id"}},
                    "avg_responsetime": {"avg": {"field": "lifespan"}}
                }
            }
        }

    }

    result = es_api_for_rqst(http, "GET", "/log-enginenotif*/_search", query_body)

    # Debug: tampilkan hasil query di terminal
    print("=== RAW RESULT ===")
    print(json.dumps(result, indent=2))

    buckets = result.get("aggregations", {}).get("per_day", {}).get("buckets", [])
    print("=== BUCKETS ===")
    for b in buckets:
        print(b["key_as_string"], b.get("jumlah_mvrk", {}).get("value", 0))

    output = BytesIO()
    with xlsxwriter.Workbook(output, {'in_memory': True}) as workbook:
        worksheet = workbook.add_worksheet("Report")
        headers = ["no", "datetime", "jumlah_mvrk", "avg_responsetime"]
        for col, h in enumerate(headers):
            worksheet.write(0, col, h)

        for i, bucket in enumerate(buckets, start=1):
            date_str = bucket["key_as_string"][:10]  # ambil YYYY-MM-DD
            jumlah_mvrk = bucket.get("jumlah_mvrk", {}).get("value", bucket.get("doc_count", 0))
            avg_responsetime = bucket.get("avg_responsetime", {}).get("value", 0) or 0

            worksheet.write(i, 0, i)
            worksheet.write(i, 1, date_str)
            worksheet.write(i, 2, jumlah_mvrk)
            worksheet.write(i, 3, avg_responsetime)

    output.seek(0)

    bot.send_document(chat_id,output,filename="report_engine_notif_trial.xlsx")

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    if text.startswith("/engine_notif_"):
        param = text.split("_", 1)[1]  
        cmd_report_engine_notif(chat_id, user_id, username, interval=param)
    elif text == "/report_engine_notif":
        cmd_report_engine_notif(chat_id, user_id, username)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("report_engine_notif", handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

    