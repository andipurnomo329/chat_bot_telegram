import requests

def safe_post(url, json_payload=None, params=None, timeout=10):
    try:
        return requests.post(url, json=json_payload, params=params,
                             timeout=timeout, verify=False)
    except:
        return None
def safe_post_pict(url, data=None, json_payload=None, files=None, headers=None):
    try:
        resp = requests.post(
            url,
            data=data,
            json=json_payload,
            files=files,
            headers=headers,
            timeout=20
        )
        return resp
    except Exception as e:
        print(f"[safe_post] ERROR: {e}")
        return None
