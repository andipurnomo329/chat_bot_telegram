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
