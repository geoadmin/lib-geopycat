NS = {
    'csw': 'http://www.opengis.net/cat/csw/2.0.2',
    'gco': 'http://www.isotc211.org/2005/gco',
    'che': 'http://www.geocat.ch/2008/che',
    'gmd': 'http://www.isotc211.org/2005/gmd',
    'srv': 'http://www.isotc211.org/2005/srv',
    'gmx': 'http://www.isotc211.org/2005/gmx',
    'gts': 'http://www.isotc211.org/2005/gts',
    'gsr': 'http://www.isotc211.org/2005/gsr',
    'gmi': 'http://www.isotc211.org/2005/gmi',
    'gml': 'http://www.opengis.net/gml/3.2',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'geonet': 'http://www.fao.org/geonetwork',
    'java': 'java:org.fao.geonet.util.XslUtil',
}

ENV = {
    'int': 'https://geocat-int.dev.bgdi.ch',
    'prod': 'https://www.geocat.ch',
}

PROXY = [
    {
        "http": "proxy-bvcol.admin.ch:8080",
        "https": "proxy-bvcol.admin.ch:8080",
    },
    {
        "http": "proxy.admin.ch:8080",
        "https": "proxy.admin.ch:8080",
    },
    {}
]

LANG_ISO = {
    "ger": "DE",
    "fre": "FR",
    "ita": "IT",
    "eng": "EN",
    "roh": "RM"
}

SEARCH_UUID_API_BODY = {
    "from": 0,
    "query": {
        "bool": {
            "must": []
        }
    },
    "_source": {
        "includes": [
            "uuid"
        ]
    },
    "track_total_hits": True,
    "sort": {"_id": "asc"},
}

GET_MD_INDEX_API_BODY = {
    "query": {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": None,
                        "fields": [
                            "id",
                            "uuid"
                        ]
                    }
                },
                {
                    "terms": {
                        "isTemplate": [
                            "n",
                            "y"
                        ]
                    }
                }
            ]
        }
    }
}