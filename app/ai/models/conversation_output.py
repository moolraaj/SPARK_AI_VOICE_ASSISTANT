from typing import Any

from pydantic import BaseModel, Field


class ConversationUnderstanding(BaseModel):

    # =========================================================
    # INTENT
    # =========================================================

    intent: str = Field(
        description=(
            "What the customer is actually trying to "
            "accomplish in the current turn."
        )
    )

    # =========================================================
    # TONE
    # =========================================================

    tone: str = Field(
        description=(
            "The customer's conversational tone, such as "
            "casual, friendly, neutral, frustrated, angry, "
            "urgent, confused, positive, or appreciative."
        )
    )

    # =========================================================
    # LANGUAGE
    # =========================================================

    language: str = Field(
        description=(
            "The customer's communication language/style. "
            "Use hinglish when Hindi and English are naturally "
            "mixed, hindi for primarily Hindi, and english for "
            "primarily English."
        )
    )

    # =========================================================
    # ENTITIES
    # =========================================================

    entities: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Important entities explicitly mentioned by the "
            "customer or safely resolved from conversation context."
        )
    )

    # =========================================================
    # REQUESTED INFORMATION
    # =========================================================

    requested_information: list[str] = Field(
        default_factory=list,
        description=(
            "The exact information the customer is asking for "
            "in the current turn."
        )
    )

    # =========================================================
    # ANSWER SCOPE
    # =========================================================

    answer_scope: str = Field(
        description=(
            "Defines what information should be included in "
            "the answer. Examples: availability_only, "
            "price_only, details_only, recommendation, "
            "category_listing, order_action, general_information."
        )
    )

    # =========================================================
    # TOOL
    # =========================================================

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