from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """
    Standard result returned by every AI tool execution.

    Tool-specific business data is stored inside `data`.
    """

    success: bool = Field(
        description="Whether the tool executed successfully."
    )

    tool_name: str = Field(
        description="Name of the tool that was executed."
    )

    data: Any = Field(
        default=None,
        description="Tool-specific business data returned by the tool."
    )

    message: str | None = Field(
        default=None,
        description="Human-readable informational message."
    )

    error: str | None = Field(
        default=None,
        description="Error message when tool execution fails."
    )