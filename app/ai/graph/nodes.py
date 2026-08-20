from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, ToolMessage

from app.core.config import MODEL_NAME
from app.ai.tools.tool_mapping import TOOL_REGISTRY

# CHANGED: import the function that FILLS the template,
# not the raw unformatted template string.
from app.ai.prompts.restaurant_prompt import build_system_prompt


class AgentNodes:

    def __init__(self):

        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=150
        )

    async def llm_node(self, state):

        business_type = (
            state["business_type"]
            .upper()
            .strip()
        )

        tools = TOOL_REGISTRY.get(business_type)

        if not tools:
            raise ValueError(
                f"No tools configured for "
                f"business type: {business_type}"
            )

        llm = self.llm.bind_tools(tools)

        has_system_message = any(
            isinstance(m, SystemMessage) for m in state["messages"]
        )

        if has_system_message:

            messages = list(state["messages"])
        else:

            system_prompt = build_system_prompt(state["ai_employee"])
            messages = [
                SystemMessage(content=system_prompt),
                *state["messages"],
            ]

        # Compact older ToolMessages so only the latest tool response is full-size
        compacted_messages = []
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        for msg in messages:
            if isinstance(msg, ToolMessage) and tool_messages and msg is not tool_messages[-1]:
                compacted_messages.append(
                    ToolMessage(
                        content="[Tool response already processed]",
                        tool_call_id=msg.tool_call_id,
                    )
                )
            else:
                compacted_messages.append(msg)

        import time
        t_llm_start = time.perf_counter()
        response = await llm.ainvoke(compacted_messages)
        llm_ms = (time.perf_counter() - t_llm_start) * 1000
        print(f"⏱️ LLM Call Latency: {llm_ms:.2f} ms ({llm_ms/1000:.3f}s)")

        return {
            "messages": [response],
        }