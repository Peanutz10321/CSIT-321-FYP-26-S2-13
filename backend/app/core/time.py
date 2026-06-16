from datetime import datetime, timedelta

SGT_OFFSET = timedelta(hours=8)


def now_sgt() -> datetime:
    return datetime.utcnow() + SGT_OFFSET
