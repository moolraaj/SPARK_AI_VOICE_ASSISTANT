def live_feed_response(feed: dict) -> dict:
    org_id = str(
        feed.get("org_id")
        or feed.get("organization_id")
        or feed.get("tenant_id")
        or ""
    )
    return {
        "id": str(feed["_id"]),
        "org_id": org_id,
        "user_id": str(feed.get("user_id", "")),
        "type": feed.get("type", "general"),
        "title": feed.get("title", ""),
        "message": feed.get("message", ""),
        "valid_from": feed.get("valid_from"),
        "valid_until": feed.get("valid_until"),
        "is_active": feed.get("is_active", True),
        "created_at": feed.get("created_at"),
        "updated_at": feed.get("updated_at"),
    }
