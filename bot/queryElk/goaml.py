def goamlQuery():
    KEY_VALUE = ["LTKT", "CIF", "LTKL"]    
    KOLOM = "label.keyword"
    SOURCE = ["label", "count_trx", "date_origin"]
    RANGE = "60m"
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
                ],
                "must_not": [
                    {
                    "exists": {
                        "field": "datecode"
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
        "size": 10  # tambah size supaya dapat semua data 3 jam terakhir
    }
    return query
def detailDatecode():
    query = {
        "size": 0,
        "query": {
            "bool": {
            "filter": [
                { "range": { "@timestamp": { "gte": "now-120m", "lte": "now" } } },
                { "terms": { "label.keyword": ["LTKT", "CIF", "LTKL"] } }
            ]
            }
        },
        "aggs": {
            "by_datecode": {
            "terms": {
                "field": "datecode.keyword",
                "size": 1000,
                "order": { "_key": "asc" }
            },
            "aggs": {
                "latest_doc": {
                "top_hits": {
                    "sort": [
                    { "@timestamp": { "order": "desc" } }
                    ],
                    "_source": {
                    "includes": ["label", "count_trx", "date_origin", "datecode"]
                    },
                    "size": 1
                }
                }
            }
            }
        }
    }

    return query