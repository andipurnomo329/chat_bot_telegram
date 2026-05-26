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
                                "gte": "now-31d/d",
                                "lte": "now-1d/d"
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
                    "gte": "now-31d/d",
                    "lte": "now-1d/d"
                }
            }
        },
        "aggs": {
            "per_day_avg_rt": {
                "date_histogram": {
                    "field": "trxtime",
                    "calendar_interval": "1d",
                    "min_doc_count": 0   # supaya hari kosong tetap muncul
                },
                "aggs": {
                    "avg_responsetime": {   # gabungan semua channel
                        "avg": {
                            "script": {
                                "source": (
                                    "doc['sendingtime'].value.toInstant().toEpochMilli() - "
                                    "doc['trxtime'].value.toInstant().toEpochMilli()"
                                )
                            }
                        }
                    },
                    "by_sendingtype": {     # breakdown per channel
                        "terms": {
                            "field": "sendingtype.keyword"
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
        }
    }

def build_query_log():
    return {
        "size": 0,
        "query": {
            "range": {
                "date_origin": {
                    "gte": "now-31d/d",
                    "lte": "now-1d/d"
                }
            }
        },
        "aggs": {
            "per_day": {
                "date_histogram": {
                    "field": "date_origin",
                    "calendar_interval": "1d",
                    "min_doc_count": 0
                },
                "aggs": {
                    "maverick_success": {
                        "filter": { "term": { "responseMaverick.keyword": "1" } },
                        "aggs": { "jumlah": { "value_count": { "field": "_id" } } }
                    },
                    "maverick_fail": {
                        "filter": { "term": { "responseMaverick.keyword": "-1" } },
                        "aggs": { "jumlah": { "value_count": { "field": "_id" } } }
                    },
                    "sms_success": {
                        "filter": { "term": { "responseLimitSMS.keyword": "1" } },
                        "aggs": { "jumlah": { "value_count": { "field": "_id" } } }
                    },
                    "sms_fail": {
                        "filter": { "term": { "responseLimitSMS.keyword": "-1" } },
                        "aggs": { "jumlah": { "value_count": { "field": "_id" } } }
                    },
                    "email_success": {
                        "filter": { "term": { "responseLimitEmail.keyword": "1" } },
                        "aggs": { "jumlah": { "value_count": { "field": "_id" } } }
                    },
                    "email_fail": {
                        "filter": { "term": { "responseLimitEmail.keyword": "-1" } },
                        "aggs": { "jumlah": { "value_count": { "field": "_id" } } }
                    },
                    "avg_responsetime": { "avg": { "field": "lifespan" } }
                }
            }
        }
    }



def parse_status_buckets(result):
    if "aggregations" not in result:
        print("DEBUG: Tidak ada aggregations untuk status:", result)
        return {}, {}
    buckets = result["aggregations"]["by_status"]["buckets"]
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
    if "aggregations" not in result:
        print("DEBUG: Tidak ada aggregations untuk avg_rt:", result)
        return {}
    out = {}
    for day in result["aggregations"]["per_day_avg_rt"]["buckets"]:
        date = day["key_as_string"][:10]
        avg_all = (day.get("avg_responsetime", {}).get("value") or 0) / 1000
        per_type = {}
        for st in day.get("by_sendingtype", {}).get("buckets", []):
            sendingtype = str(st["key"])
            avg_val = (st.get("avg_responsetime", {}).get("value") or 0) / 1000
            per_type[sendingtype] = avg_val
        out[date] = {"avg_all": avg_all, "per_type": per_type}
    return out

def parse_log_buckets(result):
    if "aggregations" not in result:
        print("DEBUG: Tidak ada aggregations untuk log:", result)
        return {}
    out = {}
    for day in result["aggregations"]["per_day"]["buckets"]:
        date = day["key_as_string"][:10]
        out[date] = {
            "mvrk_success": day["maverick_success"]["jumlah"]["value"],
            "mvrk_fail":    day["maverick_fail"]["jumlah"]["value"],
            "sms_success":  day["sms_success"]["jumlah"]["value"],
            "sms_fail":     day["sms_fail"]["jumlah"]["value"],
            "email_success":day["email_success"]["jumlah"]["value"],
            "email_fail":   day["email_fail"]["jumlah"]["value"],
            "avg_rt":       day["avg_responsetime"]["value"] or 0
        }
    for d, vals in out.items():
        print(f"[DEBUG Compare log-enginenotif] Date={d} "
              f"Mvrk: success={vals['mvrk_success']} fail={vals['mvrk_fail']} "
              f"SMS: success={vals['sms_success']} fail={vals['sms_fail']} "
              f"Email: success={vals['email_success']} fail={vals['email_fail']} "
              f"AvgRT={vals['avg_rt']:.2f}")
    return out


def cmd_report_engine_notif(chat_id, user_id, username, interval=None):

    bot.send_message(chat_id, "Sedang diproses... ⏳")

    result_mvrk   = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_by_sendingtype(4))
    result_sms    = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_by_sendingtype(1))
    result_email  = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_by_sendingtype(2))
    result_avg_rt = es_api_for_rqst(http, "GET", "/enginenotif-ttrx-*/_search", build_query_avg_rt())
    result_log = es_api_for_rqst(http, "GET", "/log-enginenotif-*/_search", build_query_log())
    
    log_buckets      = parse_log_buckets(result_log)
    mvrk_s, mvrk_f   = parse_status_buckets(result_mvrk)
    sms_s, sms_f     = parse_status_buckets(result_sms)
    email_s, email_f = parse_status_buckets(result_email)
    avg_rt_buckets   = parse_avg_rt_buckets(result_avg_rt)

    all_dates = sorted(
        set(mvrk_s) | set(mvrk_f) |
        set(sms_s)  | set(sms_f)  |
        set(email_s)| set(email_f)
    )

    # ERROR HANDLING: kalau tidak ada data
    if not all_dates:
        bot.send_message(chat_id, "Data tidak tersedia ❌")
        print("DEBUG: Tidak ada data untuk Report.")
        return

    output = BytesIO()
    with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
        ws = workbook.add_worksheet("Report")
        ws2 = workbook.add_worksheet("Compare log-enginenotif")

        # Buat format angka dengan 2 digit desimal
        num_format_2dec = workbook.add_format({'num_format': '0.00'})
        
        headers = [
            "no", "date",
            "mvrk_success", "mvrk_fail", "mvrk_total",
            "sms_success", "sms_fail", "sms_total",
            "email_success", "email_fail", "email_total",
            "total_success", "total_fail",
            "avg_rt_maverick(s)", "avg_rt_sms(s)", "avg_rt_email(s)",
            "avg_responsetime(s)"
        ]

        headers2 = [
            "no", "date",
            "mvrk_success", "mvrk_fail", "mvrk_total",
            "sms_success", "sms_fail", "sms_total",
            "email_success", "email_fail", "email_total",
            "total_success", "total_fail",
            "avg_responsetime(s)"
        ]

        for col, h in enumerate(headers):
            ws.write(0, col, h)

        if not all_dates:
            ws.write(1,0,"No data available")

        else:
            for i, d in enumerate(all_dates, 1):
                ms = mvrk_s.get(d, {"jumlah": 0})["jumlah"]
                mf = mvrk_f.get(d, {"jumlah": 0})["jumlah"]
                ss = sms_s.get(d, {"jumlah": 0})["jumlah"]
                sf = sms_f.get(d, {"jumlah": 0})["jumlah"]
                es = email_s.get(d, {"jumlah": 0})["jumlah"]
                ef = email_f.get(d, {"jumlah": 0})["jumlah"]

                mt, st, et = ms + mf, ss + sf, es + ef
                ts, tf     = ms + ss + es, mf + sf + ef
                avg_rt     = avg_rt_buckets.get(d, {}).get("avg_all", 0)
                avg_mvrk   = avg_rt_buckets.get(d, {}).get("per_type", {}).get("4",0)
                avg_sms    = avg_rt_buckets.get(d, {}).get("per_type", {}).get("1",0)
                avg_email  = avg_rt_buckets.get(d, {}).get("per_type", {}).get("2",0) 

                print(f"=== Report Row {i} ===")
                print(f"Date            : {d}")
                print(f"Maverick        : success={ms}, fail={mf}, total={mt}, avg_rt={avg_mvrk:.2f}")
                print(f"SMS             : success={ss}, fail={sf}, total={st}, avg_rt={avg_sms:.2f}")
                print(f"Email           : success={es}, fail={ef}, total={et}, avg_rt={avg_email:.2f}")
                print(f"Total           : success={ts}, fail={tf}")
                print(f"Avg Response All: {avg_rt:.2f}")
                print()

                row = [
                    i, d,
                    ms, mf, mt,
                    ss, sf, st,
                    es, ef, et,
                    ts, tf,
                    avg_mvrk,avg_sms,avg_email,
                    avg_rt
                ]
                for col, val in enumerate(row):
                    if col >= len(row)-4:
                        ws.write(i, col, val, num_format_2dec)
                    else:
                        ws.write(i,col,val)

        for col, h in enumerate(headers2):
            ws2.write(0, col, h)

        if not log_buckets:
            ws2.write(1,0,"No data available")

        else:
            for i,d in enumerate(sorted(log_buckets.keys()),1):
                ms, mf = log_buckets[d]["mvrk_success"], log_buckets[d]["mvrk_fail"]
                ss, sf = log_buckets[d]["sms_success"], log_buckets[d]["sms_fail"]
                es, ef = log_buckets[d]["email_success"], log_buckets[d]["email_fail"]

                mt, st, et = ms+mf, ss+sf, es+ef
                ts, tf     = ms+ss+es, mf+sf+ef
                avg_rt     = log_buckets[d]["avg_rt"]

                row = [i,d,ms,mf,mt,ss,sf,st,es,ef,et,ts,tf,avg_rt]
                for col,val in enumerate(row):
                    if col == len(row)-1:
                        ws2.write(i,col,val,num_format_2dec)
                    else:
                        ws2.write(i,col,val)
                
                print(f"[DEBUG Excel Compare log-enginenotif] Row {i} Date={d} "
                    f"Mvrk={ms}/{mf} SMS={ss}/{sf} Email={es}/{ef} "
                    f"Total={ts}/{tf} AvgRT={avg_rt:.2f}")

    if not log_buckets:
        print("DEBUG: Tidak ada data untuk Compare log-enginenotif.")

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
