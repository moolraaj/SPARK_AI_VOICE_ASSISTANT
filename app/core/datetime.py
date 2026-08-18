from datetime import UTC, datetime

def utc_now() -> datetime:
    return datetime.now(UTC)

def timestamps() -> dict:
    now = utc_now()
    return {
        "created_at": now,
        "updated_at": now,
    }