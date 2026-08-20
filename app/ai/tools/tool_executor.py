from typing import Any

from app.ai.models.tool_result import ToolResult

from .tool_mapping import TOOL_REGISTRY


class ToolExecutor:

    def __init__(self):

        self.tool_registry = TOOL_REGISTRY

        print(
            "REGISTERED RESTAURANT TOOLS:",
            [
                tool.name
                for tool in self.tool_registry.get(
                    "RESTAURANT",
                    [],
                )
            ],
        )

    async def execute(
        self,
        business_type: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ToolResult:

        arguments = arguments or {}
        context = context or {}

        if not business_type:
            raise ValueError(
                "business_type is required."
            )

        business_type = business_type.upper().strip()

        tools = self.tool_registry.get(
            business_type
        )

        if not tools:
            raise ValueError(
                f"No tools registered for business type: "
                f"{business_type}"
            )

        tool = next(
            (
                registered_tool
                for registered_tool in tools
                if registered_tool.name == tool_name
            ),
            None,
        )

        if tool is None:
            raise ValueError(
                f"Tool '{tool_name}' is not registered "
                f"for business type '{business_type}'."
            )

        tool_arguments = {
            **context,
            **arguments,
        }

        print("\n🔧 TOOL EXECUTION")
        print(f"Business Type : {business_type}")
        print(f"Tool Name     : {tool_name}")
        print(f"Arguments     : {tool_arguments}")

        try:

            result = await tool.ainvoke(
                tool_arguments
            )

        except Exception as exc:

            return ToolResult(
                success=False,
                tool_name=tool_name,
                data=None,
                error=str(exc),
            )

        return ToolResult(
            success=True,
            tool_name=tool_name,
            data=result,
        )