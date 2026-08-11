def amsQuery():
    query = {
        "_source": [
            "host.ip",
            "system.filesystem.total",
            "system.filesystem.used.bytes",
            "agent.hostname"
        ],
        "query": {
            "bool": {
            "must": [
                {
                "range": {
                    "@timestamp": {
                    "gte": "now-60m",
                    "lte": "now"
                    }
                }
                },
                {
                "term": {
                    "environment": "new-ams"
                }
                },
                {
                "term": {
                    "agent.hostname": "NEWAMSDBDC"
                }
                },
                {
                "term": {
                    "system.filesystem.mount_point": "/oraarc"
                }
                }
            ]
            }
        },
        "size": 1,
        "sort": [
            {
            "@timestamp": {
                "order": "desc"
            }
            }
        ]
    }


    return query
