from typing import Any

from pydantic import BaseModel, Field


class IntentEntity(BaseModel):
    name: str = Field(
        description="Entity name, for example menu_item_name, quantity, date, or time."
    )

    value: str = Field(
        description="Entity value extracted from the customer message."
    )


class IntentRouterOutput(BaseModel):
    intent: str = Field(
        description="The single best matching intent."
    )

    entities: list[IntentEntity] = Field(
        default_factory=list,
        description=(
            "Entities explicitly extracted from the customer message. "
            "Return an empty list when no entities are present."
        ),
    )