def wicQuery(cif):

    return {

        "size": 10,

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
                "should": [
                    {
                        "term": {
                            "CIF": str(cif)
                        }
                    }

                ],
                "minimum_should_match": 1
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