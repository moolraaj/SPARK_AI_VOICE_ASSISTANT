"""
AgentNodes — LangGraph node implementations.

llm_node:
  - Pulls full context from AgentState (owner_id, org_id, business_type,
    ai_employee, platform_config)
  - Builds a 4-layer system prompt via RuntimePromptBuilder on first turn
  - Binds tools dynamically from TOOL_REGISTRY[business_type]
  - Compacts older ToolMessages to keep token count low
  - Streams LLM response tokens
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, ToolMessage

from app.core.config import MODEL_NAME
from app.ai.tools.tool_mapping import TOOL_REGISTRY
from app.ai.prompts.prompt_builder import RuntimePromptBuilder

# Legacy import kept so any external code that imports restaurant_prompt still works
from app.ai.prompts.restaurant_prompt import build_system_prompt as _legacy_build_system_prompt  # noqa: F401


class AgentNodes:

    def __init__(self):
        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=400,   # 150 was too low — tool call JSON schema alone uses ~80-120 tokens
            streaming=True,   # Required for sentence-by-sentence TTS streaming
        )

    async def llm_node(self, state):

        # ── Tool binding (dynamic per business_type) ──────────────────────────
        business_type = (
            state.get("business_type", "RESTAURANT")
            .upper()
            .strip()
        )

        tools = TOOL_REGISTRY.get(business_type)
        if not tools:
            raise ValueError(
                f"[AgentNodes] No tools configured for business type: {business_type}"
            )

        llm = self.llm.bind_tools(tools)

        # ── System prompt (inject once at session start) ───────────────────────
        has_system_message = any(
            isinstance(m, SystemMessage) for m in state["messages"]
        )

        if has_system_message:
            messages = list(state["messages"])
        else:
            # Build 4-layer prompt from resolved session context
            system_prompt = RuntimePromptBuilder.build(
                ai_employee     = state.get("ai_employee", {}),
                organization_name = state.get("org_name") or state.get("ai_employee", {}).get("name", "Spark AI"),
                platform_config = state.get("platform_config"),
            )
            messages = [
                SystemMessage(content=system_prompt),
                *state["messages"],
            ]

        # ── Compact older ToolMessages to save tokens ─────────────────────────
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        compacted_messages = []
        for msg in messages:
            if (
                isinstance(msg, ToolMessage)
                and tool_messages
                and msg is not tool_messages[-1]
            ):
                compacted_messages.append(
                    ToolMessage(
                        content="[Tool response already processed]",
                        tool_call_id=msg.tool_call_id,
                    )
                )
            else:
                compacted_messages.append(msg)

        # ── LLM call (streaming) ──────────────────────────────────────────────
        # NOTE: astream() is used instead of ainvoke() so that LangGraph's
        # astream_events() emits on_chat_model_stream events per token.
        # ainvoke() inside a graph node does NOT trigger those events,
        # which means hardware_websocket.py never captures the LLM reply.
        # Chunks are accumulated so tool_calls are preserved for tools_condition.
        import time
        t_start  = time.perf_counter()

        response = None
        async for chunk in llm.astream(compacted_messages):
            if response is None:
                response = chunk
            else:
                response = response + chunk

        llm_ms = (time.perf_counter() - t_start) * 1000
        print(f"⏱️ LLM Call Latency: {llm_ms:.2f} ms ({llm_ms/1000:.3f}s)")

        return {"messages": [response]}