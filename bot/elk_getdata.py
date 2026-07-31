import requests
import urllib3
from utils.telegram import *
from config.settings import *
from bot.queryElk.notifcc import notifcc_query
from bot.queryElk.goaml import *   
from bot.queryElk.mtel import *   
from bot.queryElk.ams import amsQuery   
from bot.queryElk.wicpbi import wicQuery   
from bot.playwrigth import capture 
from datetime import datetime, timezone, timedelta
import pandas as pd
# from tabulate import tabulate  # pip install tabulate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sendingtype_map = {
    "1": "SMS",
    "2": "EMAIL",
    "4": "MVRK"
}

def elastic_search(indexes, query):

    url = f"{ES_HOST}/" + ",".join(indexes) + "/_search"
    resp = requests.post(url, json=query, auth=(USERNAME, PASSWORD), verify=False)
    if resp.status_code != 200:
        raise Exception(f"[ELK ERROR] {resp.status_code}: {resp.text}")
    return resp.json()

def elastic_kbn(indexes, query):

    url = f"{KBNHUB}/" + ",".join(indexes) + "/_search"
    resp = requests.post(url, json=query, auth=(USERKBNHUB, PASSWORDKBNHUB), verify=False)
    if resp.status_code != 200:
        raise Exception(f"[ELK ERROR] {resp.status_code}: {resp.text}")
    return resp.json()

def get_goaml_detail_datecode():
    INDEXES = ["trx-goaml*"]
    query = detailDatecode()
    data = elastic_search(INDEXES, query)
    return data.get("aggregations", {}).get("by_datecode", {}).get("buckets", [])

def get_goaml_data():
    INDEXES = ["trx-goaml*"]
    query = goamlQuery()
    data = elastic_search(INDEXES, query)
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return "Tidak ada data ditemukan"
    
    summary = {}
    for item in hits:
        source = item.get("_source", {})
        label = source.get("label", "")
        count = source.get("count_trx", 0)
        date_origin = source.get("date_origin", "")

        if label not in summary:
            summary[label] = {
                "values": [],
                "dates": []
            }
        summary[label]["values"].append(count)
        summary[label]["dates"].append(date_origin)

    # Hitung statistik
    result = {}
    for label, info in summary.items():
        values = info["values"]
        dates = info["dates"]
        # urutkan berdasarkan date_origin untuk last_value
        sorted_pairs = sorted(zip(dates, values), key=lambda x: x[0])
        last_value = sorted_pairs[-1][1]

        result[label] = {
            "max": max(values),
            "min": min(values),
            "last_value": last_value
        }

    gte_value = query["query"]["bool"]["must"][0]["range"]["@timestamp"]["gte"]

    if gte_value.startswith("now-"):
        num = gte_value[4:-1]
        unit = gte_value[-1]

        if unit == "h":
            duration_text = f"{num} jam terakhir"
        elif unit == "m":
            duration_text = f"{num} menit terakhir"
        else:
            duration_text = "periode terakhir"
    else:
        duration_text = "periode terakhir"
    mes = f"📊 CTR Queue ({duration_text})\n\n"
    for label, stats in result.items():
        mes += f"🔹 *{label}*\n"
        mes += f"   🔝 Max Count Trx : {stats['max']}\n"
        mes += f"   🔻 Min Count Trx : {stats['min']}\n"
        mes += f"   ⚡ Last Value    : {stats['last_value']}\n\n"
    mes += "🗂️ Detail Datecode:\n"
    detailDatecode_data = get_goaml_detail_datecode()
    for bucket in detailDatecode_data:
        datecode = bucket.get("key", "-")
        latest_doc = bucket.get("latest_doc", {}).get("hits", {}).get("hits", [])
        if latest_doc:
            source = latest_doc[0].get("_source", {})
            label = source.get("label", "-")
            count_trx = source.get("count_trx", 0)
            date_origin = source.get("date_origin", "-")
            mes += f"   • {label}-*{datecode}*: {count_trx}\n"
    return mes

def get_notifcc():
    # print("masookk")
    data = elastic_search(["enginenotif-ttrx*"], notifcc_query())
    # print(data)
    agg = data.get("aggregations", {}) \
              .get("by_sendingtype", {}) \
              .get("buckets", [])
    if not agg:
        return "No aggregation data found"
    result_text = "📨 *EngineNotif Status Summary (Last 30 minutes)*\n\n"
    for bucket in agg:
        sending_type = bucket.get("key")
        alias = sendingtype_map.get(sending_type, "unknown")
        statuses = bucket.get("status_count", {}).get("buckets", [])
        # Default values
        status_1 = 0
        status_0 = 0
        status_other = {}
        for s in statuses:
            key = str(s.get("key"))
            count = s.get("doc_count", 0)
            if key == "1":
                status_1 = count
            elif key == "0":
                status_0 = count
            else:
                status_other[key] = count
        total = status_1 + status_0
        if total > 0:
            success_percent = (status_1 / total) * 100
            failed_percent  = (status_0 / total) * 100
        else:
            success_percent = 0
            failed_percent = 0
        result_text += f"🔹 *SendingType {alias}*\n"
        result_text += f"   ✔️ Success : {status_1} ({success_percent:.2f}%)\n"
        result_text += f"   ❌ Failed  : {status_0} ({failed_percent:.2f}%)\n"
        for k, v in status_other.items():
            result_text += f"   ⚠️ Status {k}: {v}\n"
        result_text += "\n"
    return result_text

def get_mtel():
    data = elastic_search(["log-mteleplus*"], mtelQuery())
    agg = (data.get("aggregations", {})
               .get("by_channel", {})
               .get("buckets", []))
    if not agg:
        return "No aggregation data found"
    result_text = "📨 *Mtel Summary (Last 30 minutes)*\n\n"
    for bucket in agg:
        channel = bucket.get("key", "-")
        total_channel = bucket.get("doc_count", 0)
        result_text += f"*Channel:* `{channel}` — *Total:* {total_channel}\n"
        directions = bucket.get("by_direction", {}).get("buckets", [])
        if not directions:
            result_text += "  • No direction data\n"
            continue
        for d in directions:
            direction = d.get("key", "-")
            total_dir = d.get("doc_count", 0)
            result_text += f"  • `{direction}` → {total_dir}\n"
        result_text += "\n"  
    data2 = elastic_search(["log-mteleplus-*"], getSmsContentMtel())
    agg2 = data2.get('hits', {}).get('hits', [])
    print(agg2)
    # if not agg:
    #     return "No aggregation data found"
    # for bucket in agg:
    #     sms_content = bucket.get("key", "-")
    #     total_sms = bucket.get("doc_count", 0)
    #     result_text += f"*SMS Content:* `{sms_content}` — *Total:* {total_sms}\n"   
    return result_text

def get_ams_data():
    result_text = "📨 *AMS Summary (Last 30 minutes)*\n\n"
    data = elastic_kbn(["metricbeat-*"], amsQuery())
    for hit in data.get("hits", {}).get("hits", []):
        fs = hit["_source"]["system"]["filesystem"]
        used = fs["used"]["bytes"] / 1024 /  1024 / 1024
        total = fs["total"] / 1024 /  1024 / 1024
        usedPersent = (used / total) * 100
    status = "⚠️" if usedPersent > 80 else "✅"
    result_text += f"{status} *ORA_ARC:*{used:.2f} GB/ {total:.2f} GB ({usedPersent:.2f}%)\n"
    print(result_text)
    return result_text

def get_wic_data(cif):
    Total_Pbi = 0
    trxlimit_rows = []
    trxpbi_rows = []
    data = elastic_search(
        ["wic-trx-pbi-ceklimit-*", "log-wic-trx-pbi*"],
        wicQuery(cif)
    )
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return f"❌ Data CIF {cif} tidak ditemukan", None
    for hit in hits:
        src = hit["_source"]
        index_name = hit["_index"]
        # =========================
        # AMBIL TIME (SIMPLE INLINE)
        # =========================
        raw_time = src.get("RequestTime") or src.get("DateTime")
        if raw_time:
            dt = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            dt_wib = dt + timedelta(hours=7)
            time_str = dt_wib.strftime("%d-%m-%Y %H:%M:%S")
        else:
            time_str = "-"
        # =========================
        # TRX LIMIT
        # =========================
        if "wic-trx-pbi-ceklimit" in index_name:
            trxlimit_rows.append({
                "RequestTime": time_str,
                "CCY1": src.get("CCY1", "-"),
                "CCY2": src.get("CCY2", "-"),
                "CIF": src.get("CIF", "-"),
                "NoRek": src.get("Norek", "-"),
                "Rate": float(src.get("Rate", 0)),
                "NominalUSD": float(src.get("NominalEqUSD", 0)),
                "NominalIDR": float(src.get("Nominal", 0))
            })
            
        # =========================
        # TRX PBI
        # =========================
        elif "log-wic-trx-pbi" in index_name:
            nominal_usd = float(src.get("NominalEqUSD", 0))
            Total_Pbi += nominal_usd
            trxpbi_rows.append({
                "DateTime": time_str,
                "CCY1": src.get("CCY1", "-"),
                "CCY2": src.get("CCY2", "-"),
                "CIF": src.get("CIF", "-"),
                "NoRek": src.get("NoRek", "-"),
                "Rate": float(src.get("Rate", 0)),
                "NominalUSD": nominal_usd,
                "NominalIDR": float(src.get("Nominal", 0)),
                "NoJurnal": src.get("NoJurnal", "-")
            })
    # =========================
    # EXPORT EXCEL
    # =========================

    file_name = f"WIC_{cif}.xlsx"
    with pd.ExcelWriter(file_name, engine="openpyxl") as writer:
        pd.DataFrame(trxlimit_rows).to_excel(writer, sheet_name="TrxLimit", index=False)
        pd.DataFrame(trxpbi_rows).to_excel(writer, sheet_name="TrxPBI", index=False)
    result_text = (
        f"✅ Data WIC berhasil diproses\n"
        f"👤 CIF : {cif}\n"
        f"💵 Total PBI USD : {Total_Pbi:,.2f}\n"
        f"📁 Excel siap dikirim"
    )
    return result_text, file_name

def export_wic_to_excel(cif, hits):
    trxlimit_rows = []
    trxpbi_rows = []
    total_pbi = 0
    for hit in hits:
        src = hit["_source"]
        index_name = hit["_index"]
        # ======================================
        # TRX LIMIT
        # ======================================
        if "ceklimit" in index_name:
            request_time = datetime.strptime(
                src.get('RequestTime'),
                '%Y-%m-%dT%H:%M:%S.%fZ'
            ).strftime('%d-%m-%Y %H:%M:%S')
            trxlimit_rows.append({
                "RequestTime": request_time,
                "CCY1": src.get("CCY1", "-"),
                "CCY2": src.get("CCY2", "-"),
                "CIF": src.get("CIF", "-"),
                "NoRek": src.get("Norek", "-"),
                "Rate": float(src.get("Rate", 0)),
                "NominalUSD": float(src.get("NominalEqUSD", 0)),
                "NominalIDR": float(src.get("Nominal", 0))
            })
        # ======================================
        # TRX PBI
        # ======================================
        else:
            date_time = datetime.strptime(
                src.get('DateTime'),
                '%Y-%m-%dT%H:%M:%S.%fZ'
            ).strftime('%d-%m-%Y %H:%M:%S')
            nominal_usd = float(src.get("NominalEqUSD", 0))
            total_pbi += nominal_usd
            trxpbi_rows.append({
                "DateTime": date_time,
                "CCY1": src.get("CCY1", "-"),
                "CCY2": src.get("CCY2", "-"),
                "CIF": src.get("CIF", "-"),
                "NoRek": src.get("NoRek", "-"),
                "Rate": float(src.get("Rate", 0)),
                "NominalUSD": nominal_usd,
                "NominalIDR": float(src.get("Nominal", 0)),
                "NoJurnal": src.get("NoJurnal", "-")
            })
    # ======================================
    # DATAFRAME
    # ======================================
    df_limit = pd.DataFrame(trxlimit_rows)
    df_pbi = pd.DataFrame(trxpbi_rows)
    # ======================================
    # NAMA FILE
    # ======================================
    file_name = f"WIC_{cif}.xlsx"
    # ======================================
    # EXPORT 2 SHEET
    # ======================================
    with pd.ExcelWriter(file_name, engine="openpyxl") as writer:
        df_limit.to_excel(
            writer,
            sheet_name="TrxLimit",
            index=False
        )
        df_pbi.to_excel(
            writer,
            sheet_name="TrxPBI",
            index=False
        )
    return file_name, total_pbi

def getDashboardScreenshot(app_name):
    print(app_name)
    filename = capture(app_name)  
    print(filename)
    return filename