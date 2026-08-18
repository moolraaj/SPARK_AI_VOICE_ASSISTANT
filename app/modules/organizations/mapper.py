def organization_response(org: dict) -> dict:
    return {
        "id": str(org["_id"]),
        "owner_id": org["owner_id"],
        "business_platform_id": org["business_platform_id"],
        "tenant_id": org["tenant_id"],
        "name": org["name"],
        "slug": org["slug"],
        "description": org.get("description"),
        "logo_url": org.get("logo_url"),
        "website": org.get("website"),
        "phone": org.get("phone"),
        "email": org.get("email"),
        "address": org.get("address"),
        "is_active": org["is_active"],
        "created_at": org["created_at"],
        "updated_at": org["updated_at"],
    }
