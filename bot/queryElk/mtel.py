def mtelQuery():
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
            "by_channel": {
            "terms": {
                "field": "channel.keyword",
                "size": 50
            },
            "aggs": {
                "by_direction": {
                "terms": {
                    "field": "direction.keyword",
                    "size": 10
                }
                }
            }
            }
        }
    }

    return query
def getSmsContentMtel():
    query = {
        "size": 0,
        "query": {
            "bool": {
            "filter": [
                { "range": { "@timestamp": { "gte": "now-1h", "lte": "now" } } },
                {
                "terms": {
                    "sms_content.keyword": [
                    "Permintaan PIN berhasil",
                    "Terima kasih, Kartu Kredit BNI Anda telah aktif. Gunakan segera Kartu Kredit BNI Anda untuk menikmati promo menarik dari BNI. Info promo klik bit.ly/PROMOKKBNI",
                    "Aktivasi Kartu Kredit BNI Anda tidak dapat kami proses. Silakan hubungi BNI Call 1500046.",
                    "Maaf, transaksi Anda tidak dapat kami proses. Silakan hubungi BNI Call 1500046."
                    ]
                }
                }
            ]
            }
        },
        "aggs": {
            "per_sms_content": {
            "terms": {
                "field": "sms_content.keyword",
                "size": 10
            }
            }
        }
    }