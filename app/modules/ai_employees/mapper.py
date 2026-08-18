def ai_employee_response(ai: dict) -> dict:
    return {
        "id":               str(ai["_id"]),
        "org_id":           ai["org_id"],
        "business_type_id": ai["business_type_id"],
        "name":             ai["name"],
        "role":             ai["role"],
        "persona":          ai["persona"],
        "language":         ai["language"],
        "greeting_message": ai.get("greeting_message"),
        "voice_id":         ai.get("voice_id"),
        "is_active":        ai["is_active"],
        "created_at":       ai["created_at"],
        "updated_at":       ai["updated_at"],
    }
