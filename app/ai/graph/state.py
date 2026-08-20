from typing import Annotated, TypedDict, Any

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

    owner_id: str

    business_type: str

    ai_employee_id: str

    ai_employee: dict[str, Any]