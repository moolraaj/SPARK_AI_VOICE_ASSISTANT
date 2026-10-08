from typing import Any

from pydantic import BaseModel, Field


class ConversationUnderstanding(BaseModel):
    intent: str = Field(
        description=(
            "What the customer is actually trying to "
            "accomplish in the current turn."
        )
    )
    tone: str = Field(
        description=(
            "The customer's conversational tone, such as "
            "casual, friendly, neutral, frustrated, angry, "
            "urgent, confused, positive, or appreciative."
        )
    )
    language: str = Field(
        description=(
            "The customer's communication language/style. "
            "Use hinglish when Hindi and English are naturally "
            "mixed, hindi for primarily Hindi, and english for "
            "primarily English."
        )
    )

    entities: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Important entities explicitly mentioned by the "
            "customer or safely resolved from conversation context."
        )
    )

    requested_information: list[str] = Field(
        default_factory=list,
        description=(
            "The exact information the customer is asking for "
            "in the current turn."
        )
    )

    answer_scope: str = Field(
        description=(
            "Defines what information should be included in "
            "the answer. Examples: availability_only, "
            "price_only, details_only, recommendation, "
            "category_listing, order_action, general_information."
        )
    )

    needs_tool: bool = Field(
        description=(
            "Whether real restaurant data is required."
        )
    )

    selected_tool: str | None = Field(
        default=None,
        description=(
            "The most appropriate restaurant tool when "
            "restaurant data is required."
        )
    )