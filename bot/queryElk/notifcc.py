def notifcc_query():
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
    return query