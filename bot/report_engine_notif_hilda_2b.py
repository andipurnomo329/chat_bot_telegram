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
    

INDEX_CONFIG = {
    "enginenotif_ttrx": {
        "index": "enginenotif-ttrx-*",
        "date_field": "trxtime",
        "sending_field": "sendingtype.keyword",
        "status_fields": {
            "general": {"field": "status.keyword", "success": "1", "fail": "0"}
        },
        "agg_name": "avg_response_time_daily"
    },
    "logenginenotif": {
        "index": "log-enginenotif-*",
        "date_field": "date_origin",
        "sending_field": None,
        "status_fields": {
            "mvrk": {"field": "responseMaverick.keyword", "success": "1", "fail": "-1"},
            "sms":      {"field": "responseLimitSMS.keyword", "success": "1", "fail": "-1"},
            "email":    {"field": "responseLimitEmail.keyword", "success": "1", "fail": "-1"}
        },
        "agg_name": "log_avg_rt",
        "avg_field": "lifespan"
    },
    "custom_index": {
        "index": "custom-*",
        "date_field": "event_time",
        "sending_field": "channel.keyword",
        "status_fields": {
            "delivery": {"field": "delivery_status.keyword", "success": "SUCCESS", "fail": "FAIL"}
        },
        "agg_name": "custom_avg_rt"
    }
}

def build_date_range(date_field,year_offset=0,days=365):
    if year_offset==0:
        return{"gte": f"now-{days}d/d", "lte": "now-1d/d"}
    else: 
        return{
            "gte":f"now-{year_offset}y-{days}d/d",
            "lte":f"now-{year_offset}y-1d/d"
        }


def build_query(cfg, sendingtype=None,year_offset=0):
    date_field = cfg["date_field"]
    range_query = build_date_range(date_field,year_offset)
    
    query = {
        "size": 0,
        "query": {
            "range": {date_field: range_query}
        },
        "aggs": {
            "per_day": {
                "date_histogram": {
                    "field": date_field,
                    "calendar_interval": "1d",
                    "min_doc_count": 0
                },
                "aggs": {}
            }
        }
    }

    if sendingtype and cfg.get("sending_field"):
        query["query"] = {
            "bool": {
                "must": [
                    {"term": {cfg["sending_field"]: str(sendingtype)}},
                    {"range": {date_field: range_query}}
                ]
            }
        }
    
    for name, sf in cfg["status_fields"].items():
        query["aggs"]["per_day"]["aggs"][f"{name}_success"] = {
            "filter": {"term": {sf["field"]: sf["success"]}},
            "aggs": {"jumlah": {"value_count": {"field": "_id"}}}
        }
        query["aggs"]["per_day"]["aggs"][f"{name}_fail"] = {
            "filter": {"term": {sf["field"]: sf["fail"]}},
            "aggs": {"jumlah": {"value_count": {"field": "_id"}}}
        }
    
    return query
    
def build_query_avg_rt(cfg,year_offset=0):
    date_field = cfg["date_field"]
    sending_field = cfg.get("sending_field")
    agg_name = cfg.get("agg_name", "per_day_avg_rt")
    avg_field = cfg.get("avg_field")  
    range_query = build_date_range(date_field,year_offset)

    if avg_field:
        avg_responsetime = {"avg": {"field": avg_field}}
    else:
        script_expr = (
            "Math.abs(doc['sendingtime'].value.toInstant().toEpochMilli() - "
            f"doc['{date_field}'].value.toInstant().toEpochMilli())"
        )
        avg_responsetime = {"avg": {"script": {"source": script_expr}}}

    aggs = {"avg_responsetime": avg_responsetime}
    if sending_field:
        aggs["by_sendingtype"] = {
            "terms": {"field": sending_field},
            "aggs": {"avg_responsetime": avg_responsetime}
        }

    return {
        "size": 0,
        "query": {
            "range": {date_field: range_query}
        },
        "aggs": {
            agg_name: {
                "date_histogram": {
                    "field": date_field,
                    "calendar_interval": "1d",
                    "min_doc_count": 0
                },
                "aggs": aggs
            }
        }
    }


def parse_multi_status_buckets(result, cfg):
    if "aggregations" not in result: return {}
    out = {}
    buckets = result.get("aggregations", {}).get("per_day", {}).get("buckets", [])
    for day in buckets:
        date = day["key_as_string"][:10]
        out[date] = {}
        for name in cfg["status_fields"].keys():
            succ = day.get(f"{name}_success", {}).get("jumlah", {}).get("value")
            if succ is None:
                succ = day.get(f"{name}_success", {}).get("doc_count", 0)
            fail = day.get(f"{name}_fail", {}).get("jumlah", {}).get("value")
            if fail is None:
                fail = day.get(f"{name}_fail", {}).get("doc_count", 0)
            out[date][f"{name}_success"] = succ
            out[date][f"{name}_fail"] = fail
    return out

def parse_avg_rt_buckets(result, cfg):
    agg_name = cfg.get("agg_name","per_day_avg_rt")
    if "aggregations" not in result: return {}
    out = {}
    for day in result["aggregations"][agg_name]["buckets"]:
        date = day["key_as_string"][:10]
        val = day.get("avg_responsetime", {}).get("value") or 0
        # cek apakah pakai avg_field (lifespan) atau script
        if cfg.get("avg_field"):
            avg_all = val   # langsung pakai detik
        else:
            avg_all = val / 1000   # convert ms → detik
        per_type = {}
        for st in day.get("by_sendingtype", {}).get("buckets", []):
            avg_val = st.get("avg_responsetime", {}).get("value") or 0
            if cfg.get("avg_field"):
                per_type[str(st["key"])] = avg_val
            else:
                per_type[str(st["key"])] = avg_val / 1000
        out[date] = {"avg_all": avg_all, "per_type": per_type}
    return out


def cmd_report_engine_notif(chat_id, user_id, username, index_name, sendingtypes=None,year_offset=0):

    bot.send_message(chat_id, f"Sedang diproses ... ⏳")
    cfg = INDEX_CONFIG[index_name]

    # Query status buckets
    status_buckets = {}
    if cfg.get("sending_field"):   # untuk enginenotif_ttrx
        sendingtypes_map = {1: "sms", 2: "email", 4: "mvrk"}
        for st, name in sendingtypes_map.items():
            q = build_query(cfg, sendingtype=st,year_offset=0)
            res = es_api_for_rqst(http, "GET", f"/{cfg['index']}/_search", q)
            print(f"=== RAW RESULT STATUS ENGINENOTIF TTRX ===")
            print(json.dumps(res, indent=2)) 
            parsed = parse_multi_status_buckets(res, cfg)
            for d, vals in parsed.items():
                if d not in status_buckets:
                    status_buckets[d] = {}
                status_buckets[d][f"{name}_success"] = vals.get("general_success", 0)
                status_buckets[d][f"{name}_fail"]    = vals.get("general_fail", 0)
    else:   # untuk logenginenotif atau custom_index
        q = build_query(cfg, year_offset=0)
        res = es_api_for_rqst(http, "GET", f"/{cfg['index']}/_search", q)
        print("=== RAW RESULT STATUS LOGENGINENOTIF ATAU CUSTOM INDEX ===")
        print(json.dumps(res, indent=2))
        status_buckets = parse_multi_status_buckets(res, cfg)

    # Query avg response time
    avg_query = build_query_avg_rt(cfg,year_offset=0)
    result_avg = es_api_for_rqst(http, "GET", f"/{cfg['index']}/_search", avg_query)
    # Debug print untuk avg response time
    print("=== RAW RESULT AVG RESPONSE TIME ===")
    # print(json.dumps(result_avg, indent=2))
    avg_rt_buckets = parse_avg_rt_buckets(result_avg, cfg)

    # Compare dengan logenginenotif
    cfg_log = INDEX_CONFIG["logenginenotif"]
    query_log = build_query(cfg_log,year_offset=0)
    result_log = es_api_for_rqst(http, "GET", f"/{cfg_log['index']}/_search", query_log)
    # Debug print untuk logenginenotif status
    print("=== RAW RESULT LOGENGINENOTIF STATUS ===")
    # print(json.dumps(result_log, indent=2))
    log_buckets = parse_multi_status_buckets(result_log, cfg_log)
    avg_query_log = build_query_avg_rt(cfg_log,year_offset=0)
    result_avg_log = es_api_for_rqst(http, "GET", f"/{cfg_log['index']}/_search", avg_query_log)
    # Debug print untuk logenginenotif avg response time
    print("=== RAW RESULT LOGENGINENOTIF AVG RESPONSE TIME ===")
    # print(json.dumps(result_avg_log, indent=2))
    avg_rt_log_buckets = parse_avg_rt_buckets(result_avg_log, cfg_log)

    # Error handling
    if not status_buckets:
        bot.send_message(chat_id, "Data tidak tersedia ❌")
        print(f"DEBUG: Tidak ada data untuk Report {cfg['index'].replace('-*','')}.")
        return

    output = BytesIO()
    with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:

        ws = workbook.add_worksheet("Report")
        ws2 = workbook.add_worksheet(f"Compare {cfg_log['index'].replace('-*','')}")

        # Buat format angka dengan 2 digit desimal
        num_format_2dec = workbook.add_format({'num_format': '0.00'})
        
        headers = ["no", "date"]

        if cfg.get("sending_field"):  # khusus enginenotif_ttrx
            channel_names = ["mvrk", "sms", "email"]
            for name in channel_names:
                headers += [f"{name}_success", f"{name}_fail", f"{name}_total"]
        else:  # logenginenotif atau custom_index
            for name in cfg["status_fields"].keys():
                headers += [f"{name}_success", f"{name}_fail", f"{name}_total"]

        headers += ["total_success", "total_fail"]

        # avg response time per channel
        if cfg.get("sending_field"):
            headers += ["avg_rt_mvrk(s)", "avg_rt_sms(s)", "avg_rt_email(s)"]
        else:
            for name in cfg["status_fields"].keys():
                headers.append(f"avg_rt_{name}(s)")

        headers.append("avg_responsetime(s)")

        
        headers2 = ["no", "date"]
        for name in cfg_log["status_fields"].keys():
            headers2 += [f"{name}_success", f"{name}_fail", f"{name}_total"]
        headers2 += ["total_success", "total_fail", "avg_responsetime(s)"]

        for col, h in enumerate(headers):
            ws.write(0, col, h)

        if not status_buckets:
            ws.write(1,0,"No data available")

        else:
            for i, d in enumerate(sorted(status_buckets.keys()), 1):
                ms = status_buckets[d].get("mvrk_success",0)
                mf = status_buckets[d].get("mvrk_fail", 0)
                ss = status_buckets[d].get("sms_success", 0)
                sf = status_buckets[d].get("sms_fail", 0)
                es = status_buckets[d].get("email_success", 0)
                ef = status_buckets[d].get("email_fail", 0)

                mt, st, et = ms + mf, ss + sf, es + ef
                ts, tf     = ms + ss + es, mf + sf + ef
                avg_rt     = avg_rt_buckets.get(d, {}).get("avg_all", 0)
                avg_mvrk   = avg_rt_buckets.get(d, {}).get("per_type", {}).get("4",0)
                avg_sms    = avg_rt_buckets.get(d, {}).get("per_type", {}).get("1",0)
                avg_email  = avg_rt_buckets.get(d, {}).get("per_type", {}).get("2",0) 

                row = [i, d, ms, mf, mt, ss, sf, st, es, ef, et,
                       ts, tf, avg_mvrk, avg_sms, avg_email, avg_rt]

                for col, val in enumerate(row):
                    ws.write(i, col, val, num_format_2dec if isinstance(val, float) else None)

                print(f"=== Report Row {i} === Date={d} "
                      f"Mvrk={ms}/{mf} SMS={ss}/{sf} Email={es}/{ef} "
                      f"Total={ts}/{tf} AvgRT={avg_rt:.2f}")

        for col, h in enumerate(headers2):
            ws2.write(0, col, h)

        if not log_buckets:
            ws2.write(1, 0, "No data available")
            print(f"DEBUG: Tidak ada data untuk Compare {cfg_log['index'].replace('-*','')}.")

        else:
            for i,d in enumerate(sorted(log_buckets.keys()),1):
                ms = log_buckets[d].get("mvrk_success", 0)
                mf = log_buckets[d].get("mvrk_fail", 0)
                ss = log_buckets[d].get("sms_success", 0)
                sf = log_buckets[d].get("sms_fail", 0)
                es = log_buckets[d].get("email_success", 0)
                ef = log_buckets[d].get("email_fail", 0)

                mt, st, et = ms+mf, ss+sf, es+ef
                ts, tf     = ms+ss+es, mf+sf+ef
                avg_rt     = avg_rt_log_buckets.get(d, {}).get("avg_all", 0)

                row = [i,d,ms,mf,mt,ss,sf,st,es,ef,et,ts,tf,avg_rt]

                for col, val in enumerate(row):
                    ws2.write(i, col, val, num_format_2dec if isinstance(val, float) else None)

                print(f"[DEBUG Excel Compare log-enginenotif] Row {i} Date={d} "
                      f"Mvrk={ms}/{mf} SMS={ss}/{sf} Email={es}/{ef} "
                      f"Total={ts}/{tf} AvgRT={avg_rt:.2f}")

    output.seek(0)
    bot.send_document(chat_id, output, filename="report_engine_notif_combined.xlsx")


def handle_message(update: Update, context: CallbackContext):
    text     = update.message.text
    chat_id  = update.message.chat_id
    user_id  = update.message.from_user.id
    username = update.message.from_user.username
    
    parts = text.split()
    cmd = parts[0]
    year_offset = 0
    if len(parts) > 1 and parts[1].endswith("y"):
        try:
            year_offset = int(parts[1][:-1])
        except ValueError:
            year_offset = 0

    if cmd.startswith("/engine_notif_"):
        idx = cmd.split("_", 2)[2]
        cmd_report_engine_notif(chat_id, user_id, username, idx, year_offset=year_offset)
    elif cmd == "/report_engine_notif":
        cmd_report_engine_notif(chat_id, user_id, username, "enginenotif_ttrx", year_offset=year_offset)


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("report_engine_notif", handle_message))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
