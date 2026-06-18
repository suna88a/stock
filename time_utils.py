"""Datetime helpers for Discord display."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


JST = ZoneInfo('Asia/Tokyo')


def now_jst():
    return datetime.now(JST)


def format_datetime_jst(dt_or_text):
    if not dt_or_text:
        return '-'
    if isinstance(dt_or_text, datetime):
        dt = dt_or_text
    else:
        text = str(dt_or_text).strip()
        try:
            dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            dt = None
            for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    pass
            if dt is None:
                return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S')
