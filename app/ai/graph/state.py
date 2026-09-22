from typing import Annotated, TypedDict, Any, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):

    # =========================================================
    # CONVERSATION
    # =========================================================

    messages: Annotated[
        list[AnyMessage],
        add_messages,
    ]

    # =========================================================
    # BUSINESS CONTEXT
    # =========================================================

    owner_id: str               # MongoDB user _id (org owner)

    org_id: str                 # MongoDB org _id  ← NEW: used for org-scoped RAG

    business_type: str          # e.g. "RESTAURANT"

    business_type_id: str       # MongoDB business_type _id  ← NEW

    ai_employee_id: str

    ai_employee: dict[str, Any]

    org_name: str                   # Organization display name for prompt builder

    # =========================================================
    # PLATFORM CONFIG (Super Admin layer)
    # =========================================================

    platform_config: Optional[dict[str, Any]]   # ← NEW: may be None