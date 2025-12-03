import requests

def safe_post(url, json_payload=None, params=None, timeout=10):
    try:
        return requests.post(url, json=json_payload, params=params,
                             timeout=timeout, verify=False)
    except:
        return None
