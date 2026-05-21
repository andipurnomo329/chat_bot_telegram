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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
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


def build_query_by_sendingtype(sendingtype):
    return {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"sendingtype.keyword": str(sendingtype)}},
                    {
                        "range": {
                            "trxtime": {
                                "gte": "now-14d/d",
                                "lte": "now/d"
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "by_status": {
                "terms": {
                    "field": "status.keyword",
                    "include": ["0", "1"]
                },
                "aggs": {
                    "per_day": {
                        "date_histogram": {
                            "field": "trxtime",
                            "calendar_interval": "1d"
                        },
                        "aggs": {
                            "jumlah": {
                                "value_count": {"field": "_id"}
                            }
                        }
                    }
                }
            }
        }
    }


def build_query_avg_rt():
    return {
        "size": 0,
        "query": {
            "range": {
                "trxtime": {
                    "gte": "now-14d/d",
                    "lte": "now/d"
                }
            }
        },
        "aggs": {
            "per_day_avg_rt": {
                "date_histogram": {
                    "field": "trxtime",
                    "calendar_interval": "1d"
                },
                "aggs": {
                    "avg_responsetime": {
                        "avg": {
                            "script": {
                                "source": (
                                    "doc['sendingtime'].value.toInstant().toEpochMilli() - "
                                    "doc['trxtime'].value.toInstant().toEpochMilli()"
                                )
                            }
                        }
                    }
                }
            }
        }
    }



def parse_status_buckets(result):
    buckets = result.get("aggregations", {}).get("by_status", {}).get("buckets", [])
    success = {
        b["key_as_string"][:10]: {"jumlah": b.get("jumlah", {}).get("value", b.get("doc_count", 0))}
        for sb in buckets if sb["key"] == "1"
        for b in sb.get("per_day", {}).get("buckets", [])
    }
    fail = {
        b["key_as_string"][:10]: {"jumlah": b.get("jumlah", {}).get("value", b.get("doc_count", 0))}
        for sb in buckets if sb["key"] == "0"
        for b in sb.get("per_day", {}).get("buckets", [])
    }
    return success, fail


def parse_avg_rt_buckets(result):
    return {
        b["key_as_string"][:10]: (b.get("avg_responsetime", {}).get("value") or 0) / 1000
        for b in result.get("aggregations", {}).get("per_day_avg_rt", {}).get("buckets", [])
    }


def cmd_report_engine_notif(chat_id, user_id, username, interval=None):
    result_mvrk   = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_by_sendingtype(4))
    result_sms    = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_by_sendingtype(1))
    result_email  = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_by_sendingtype(2))
    result_avg_rt = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_avg_rt())

    mvrk_s, mvrk_f   = parse_status_buckets(result_mvrk)
    sms_s, sms_f     = parse_status_buckets(result_sms)
    email_s, email_f = parse_status_buckets(result_email)
    avg_rt_buckets   = parse_avg_rt_buckets(result_avg_rt)

    all_dates = sorted(
        set(mvrk_s) | set(mvrk_f) |
        set(sms_s)  | set(sms_f)  |
        set(email_s)| set(email_f)
    )

    output = BytesIO()
    with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
        ws = workbook.add_worksheet("Report")
        headers = [
            "no", "date",
            "mvrk_success", "mvrk_fail", "mvrk_total",
            "sms_success", "sms_fail", "sms_total",
            "email_success", "email_fail", "email_total",
            "total_success", "total_fail",
            "avg_responsetime(s)"
        ]
        for col, h in enumerate(headers):
            ws.write(0, col, h)

        for i, d in enumerate(all_dates, 1):
            ms = mvrk_s.get(d, {"jumlah": 0})["jumlah"]
            mf = mvrk_f.get(d, {"jumlah": 0})["jumlah"]
            ss = sms_s.get(d, {"jumlah": 0})["jumlah"]
            sf = sms_f.get(d, {"jumlah": 0})["jumlah"]
            es = email_s.get(d, {"jumlah": 0})["jumlah"]
            ef = email_f.get(d, {"jumlah": 0})["jumlah"]

            mt, st, et = ms + mf, ss + sf, es + ef
            ts, tf     = ms + ss + es, mf + sf + ef
            avg_rt     = avg_rt_buckets.get(d, 0)

            row = [
                i, d,
                ms, mf, mt,
                ss, sf, st,
                es, ef, et,
                ts, tf,
                avg_rt
            ]
            for col, val in enumerate(row):
                ws.write(i, col, val)

    output.seek(0)
    bot.send_document(chat_id, output, filename="report_engine_notif_combined.xlsx")


def handle_message(update: Update, context: CallbackContext):
    text     = update.message.text
    chat_id  = update.message.chat_id
    user_id  = update.message.from_user.id
    username = update.message.from_user.username

    if text.startswith("/engine_notif_"):
        cmd_report_engine_notif(chat_id, user_id, username, interval=text.split("_", 1)[1])
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
