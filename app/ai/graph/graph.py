"""
SparkAgentGraph — dynamic, multi-tenant LangGraph agent.

Replaces the hardcoded RestaurantAgentGraph.
The graph is built at session-start time after the SessionContextResolver
has determined the business_type for this call.

RestaurantAgentGraph is kept as an alias for backward compatibility.
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from app.ai.tools.tool_mapping import TOOL_REGISTRY

from .state import AgentState
from .nodes import AgentNodes

logger = logging.getLogger(__name__)


class SparkAgentGraph:
    """
    Dynamic agent graph — tools are selected based on the business_type
    resolved by SessionContextResolver (e.g. RESTAURANT, HOTEL).

    Usage:
        graph = SparkAgentGraph(business_type="RESTAURANT").build()
    """

    def __init__(self, business_type: str = "RESTAURANT"):

        self.business_type = business_type.upper().strip()
        self.nodes         = AgentNodes()

        tools = TOOL_REGISTRY.get(self.business_type)

        if not tools:
            logger.warning(
                "[SparkAgentGraph] No tools registered for business_type '%s'. "
                "Falling back to GENERAL tools.",
                self.business_type,
            )
            tools = TOOL_REGISTRY.get("GENERAL")

        self.tool_node = ToolNode(tools)

    def build(self):

        graph = StateGraph(AgentState)

        graph.add_node("llm",   self.nodes.llm_node)
        graph.add_node("tools", self.tool_node)

        graph.add_edge(START, "llm")

        graph.add_conditional_edges(
            "llm",
            tools_condition,
            {
                "tools": "tools",
                END:     END,
            },
        )

        graph.add_edge("tools", "llm")

        # Checkpointer: maintains conversation state across turns via thread_id
        checkpointer = MemorySaver()
        return graph.compile(checkpointer=checkpointer)


# ── Backward-compatibility alias ──────────────────────────────────────────────
class RestaurantAgentGraph(SparkAgentGraph):
    """Legacy alias — uses SparkAgentGraph with business_type='RESTAURANT'."""

    def __init__(self):
        super().__init__(business_type="RESTAURANT")