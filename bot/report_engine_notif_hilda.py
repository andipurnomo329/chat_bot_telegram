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

http = urllib3.PoolManager()

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


def cmd_report_engine_notif(chat_id, user_id, username):
    set_time_for_report = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
    query_body = {
        "size":0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"sendingtype.keyword": "4"}},
                    {"term": {"status": 0}},
                    {
                        "range": {
                            "@timestamp": {
                                "gte": set_time_for_report
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "jumlah_mvrk": {
                "value_count": {"field": "_id"}  # hitung jumlah dokumen
            },
            "avg_responsetime": {
                "avg": {"field": "responsetime"}
            }
        }
    }

    result = es_api_for_rqst(http, "GET", "/log-enginenotif*/_search", query_body)

    jumlah_mvrk = result["aggregations"]["jumlah_mvrk"]["doc_count"]
    avg_responsetime = result["aggregations"]["avg_responsetime"]["value"]

    output = BytesIO()
    with xlsxwriter.Workbook(output,{'in_memory':True}) as workbook:
        worksheet = workbook.add_worksheet("Report")
        headers = ["No","datetime","jumla_mvrk","avg_responsetime"]
        for col,h in enumerate(headers):
            worksheet.write(0,col,h)

        worksheet.write(1,0,1)
        worksheet.write(1,1,datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        worksheet.write(1,2,jumlah_mvrk)
        worksheet.write(1,3,avg_responsetime)

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

# Main loop polling
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("report_engine_notif", handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

    