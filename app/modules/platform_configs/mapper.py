def platform_config_response(config: dict) -> dict:
    return {
        "id": str(config["_id"]),
        "business_type_id": str(config.get("business_type_id", "")),
        "instructions": config.get("instructions", ""),
        "rules": config.get("rules", ""),
        "is_active": config.get("is_active", True),
        "created_at": config.get("created_at"),
        "updated_at": config.get("updated_at"),
    }
