from langgraph.graph import (
    StateGraph,
    START,
    END,
)

from langgraph.prebuilt import (
    ToolNode,
    tools_condition,
)

from langgraph.checkpoint.memory import MemorySaver

from app.ai.tools.tool_mapping import TOOL_REGISTRY

from .state import AgentState
from .nodes import AgentNodes


class RestaurantAgentGraph:

    def __init__(self):

        self.nodes = AgentNodes()

        self.tools = TOOL_REGISTRY[
            "RESTAURANT"
        ]

        self.tool_node = ToolNode(
            self.tools
        )

    def build(self):

        graph = StateGraph(AgentState)

        graph.add_node("llm", self.nodes.llm_node)
        graph.add_node("tools", self.tool_node)

        graph.add_edge(START, "llm")

        graph.add_conditional_edges(
            "llm",
            tools_condition,
            {
                "tools": "tools",
                END: END,
            },
        )

        graph.add_edge("tools", "llm")

        # Checkpointer: maintains conversation state across turns using thread_id
        checkpointer = MemorySaver()
        return graph.compile(checkpointer=checkpointer)