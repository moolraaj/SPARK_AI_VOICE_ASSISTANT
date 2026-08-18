from typing import Any

from .tool_mapping import RESTAURANT_TOOLS


class ToolExecutor:

    def __init__(self):
        self.tool_registry = {
            "RESTAURANT": RESTAURANT_TOOLS,
        }


        print(
            "REGISTERED RESTAURANT TOOLS:",
            list(RESTAURANT_TOOLS.keys())
        )

    async def execute(
        self,
        route: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        context = context or {}

        business_type = route.get("business_type")
        tool_name = route.get("tool_name")
        route_type = route.get("route_type")

        # ---------------------------------------------------------
        # No tool required
        # ---------------------------------------------------------

        if route_type != "TOOL":
            return {
                "success": True,
                "route_type": route_type,
                "tool_name": None,
                "result": None,
            }

        if not business_type:
            raise ValueError(
                "business_type is required for tool execution."
            )

        if not tool_name:
            raise ValueError(
                f"No tool configured for intent: "
                f"{route.get('intent')}"
            )

        business_type = business_type.upper().strip()

        # ---------------------------------------------------------
        # Get tools for business type
        # ---------------------------------------------------------

        tools = self.tool_registry.get(business_type)

        if not tools:
            raise ValueError(
                f"No tools registered for business type: "
                f"{business_type}"
            )

        # ---------------------------------------------------------
        # Find actual Python function
        # ---------------------------------------------------------

        tool = tools.get(tool_name)

        if tool is None:
            raise ValueError(
                f"Tool '{tool_name}' is not registered "
                f"for business type '{business_type}'."
            )

        # ---------------------------------------------------------
        # Convert IntentEntity list → dict
        # ---------------------------------------------------------

        raw_entities = route.get("entities") or []

        entity_dict = {}

        for entity in raw_entities:
            entity_dict[entity.name] = entity.value

        # ---------------------------------------------------------
        # Prepare tool arguments
        # ---------------------------------------------------------

        tool_arguments = {
            **context,
            **entity_dict,
        }

        # ---------------------------------------------------------
        # Logs
        # ---------------------------------------------------------

        print(f"Context   : {context}")
        print(f"Arguments : {tool_arguments}")

        # ---------------------------------------------------------
        # Execute tool
        # ---------------------------------------------------------

        try:

            result = await tool(**tool_arguments)

        except TypeError as exc:

            raise ValueError(
                f"Invalid arguments for tool '{tool_name}': "
                f"{exc}"
            ) from exc

        except Exception as exc:

            raise RuntimeError(
                f"Tool '{tool_name}' execution failed: "
                f"{exc}"
            ) from exc

        # ---------------------------------------------------------
        # Return normalized result
        # ---------------------------------------------------------

        return {
            "success": True,
            "route_type": "TOOL",
            "intent": route.get("intent"),
            "tool_name": tool_name,
            "execution_mode": route.get("execution_mode"),
            "arguments": tool_arguments,
            "result": result,
        }