from typing import Any, Dict


def apply_tenant_filter(current_user: Dict[str, Any], query: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Applies multi-tenant data isolation filter based on logged-in user.
    - If user is SUPER_ADMIN: returns query as is (can view all records).
    - If user is regular Owner: restricts query to owner_id == current_user['_id'].
    """
    filter_query = dict(query) if query else {}

    if not current_user:
        return filter_query

    role = str(current_user.get("role", "")).upper()
    if role != "SUPER_ADMIN":
        user_id = str(current_user.get("_id"))
        filter_query["owner_id"] = user_id

    return filter_query


def validate_resource_ownership(resource_owner_id: str, current_user: Dict[str, Any]) -> bool:
    """
    Central helper to validate single resource ownership by matching ID & checking Role.
    - SUPER_ADMIN: returns True (Full Admin Access).
    - Regular Users: returns True ONLY if resource_owner_id matches current_user['_id'].
    """
    if not current_user or not resource_owner_id:
        return False

    role = str(current_user.get("role", "")).upper()
    if role == "SUPER_ADMIN":
        return True

    user_id = str(current_user.get("_id"))
    return str(resource_owner_id) == user_id
