def goamlQuery():
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
    return query