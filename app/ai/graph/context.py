from typing import Any, TypedDict


class RestaurantGraphContext(TypedDict):

    owner_id: str

    business_type: str

    ai_employee_id: str

    ai_employee: dict[str, Any]

    customer_id: str

    customer_phone: str

    session_id: str