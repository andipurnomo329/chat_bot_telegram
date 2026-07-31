def wicQuery(cif):
    return {
        "size": 100,
        "_source": [
            "RequestTime",
            "DateTime",
            "CCY1",
            "CCY2",
            "CIF",
            "Norek",
            "NoRek",
            "Rate",
            "NominalEqUSD",
            "Nominal",
            "NoJurnal"
        ],
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now/M",
                                "lte": "now"
                            }
                        }
                    },
                    {
                        "term": {
                            "CIF": str(cif)
                        }
                    }
                ]
            }
        },
        "sort": [
            {
                "@timestamp": {
                    "order": "desc"
                }
            }
        ]
    }