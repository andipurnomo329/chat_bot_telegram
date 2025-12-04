import requests
import urllib3
from config.settings import *
# from tabulate import tabulate  # pip install tabulate

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_elastic_data():
    print("massook")
    INDEXES = ["trx-goaml*"]
    KEY_VALUE = ["LTKT", "CIF", "LTKL"]    
    KOLOM = "label.keyword"
    SOURCE = ["label", "count_trx", "date_origin"]
    RANGE = "30m"
    query = {
        "_source": SOURCE,
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": f"now-{RANGE}",
                                "lte": "now"
                            }
                        }
                    },
                    {
                        "terms": {
                            KOLOM : KEY_VALUE
                        }
                    }
                ]
            }
        },
        "sort": [
            {
                "@timestamp": {
                    "order": "asc"
                }
            }
        ],
        "size": 1000  # tambah size supaya dapat semua data 3 jam terakhir
    }

    url = f"{ES_HOST}/" + ",".join(INDEXES) + "/_search"
    response = requests.post(url, json=query, verify=False, auth=(USERNAME, PASSWORD))

    if response.status_code != 200:
        return f"Error: {response.status_code} {response.text}"

    data = response.json()
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return "Tidak ada data ditemukan"

    # ===============================
    # Proses max, min, last_value per label
    # ===============================
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
    # ===============================
    # Buat string output untuk Telegram
    # ===============================
    mes = f"📊 CTR Queue ({duration_text})\n\n"
    for label, stats in result.items():
        mes += f"🔹 *{label}*\n"
        mes += f"   🔝 Max Count Trx : {stats['max']}\n"
        mes += f"   🔻 Min Count Trx : {stats['min']}\n"
        mes += f"   ⚡ Last Value    : {stats['last_value']}\n\n"

    return mes

def get_notifcc():
    # print("masookk")
    INDEXES = ["enginenotif-ttrx*"]
    query = {
        "size": 0,
        "query": {
            "range": {
            "@timestamp": {
                "gte": "now-30m",
                "lte": "now"
            }
            }
        },
        "aggs": {
            "by_sendingtype": {
            "terms": {
                "field": "sendingtype.keyword",
                "size": 10
            },
            "aggs": {
                "status_count": {
                "terms": {
                    "field": "status.keyword",
                    "size": 2
                }
                }
            }
            }
        }
    }

    url = f"{ES_HOST}/" + ",".join(INDEXES) + "/_search"
    response = requests.post(url, json=query, verify=False, auth=(USERNAME, PASSWORD))

    if response.status_code != 200:
        return f"Error: {response.status_code} {response.text}"

    data = response.json()
    
    print(data)
    sendingtype_map = {
        "1": "SMS",
        "2": "EMAIL",
        "4": "MVRK"
    }
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

        result_text += f"🔹 *SendingType {alias}*\n"
        result_text += f"   ✔️ Success : {status_1}\n"
        result_text += f"   ❌ Failed  : {status_0}\n"

        # Add non 0/1 statuses dynamically
        for k, v in status_other.items():
            result_text += f"   ⚠️ Status {k}: {v}\n"

        result_text += "\n"
    # Build pesan Telegram
    return result_text
