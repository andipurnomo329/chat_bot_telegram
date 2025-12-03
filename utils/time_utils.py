from datetime import datetime, timezone, timedelta

def iso_now():
    tz = timezone(timedelta(hours=7))
    return datetime.now(tz).isoformat()
