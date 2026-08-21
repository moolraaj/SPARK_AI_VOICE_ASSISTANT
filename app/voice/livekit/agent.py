from livekit.agents import Agent


class RestaurantVoiceAgent(Agent):
    """
    Minimal voice agent.

    This is intentionally separate from RestaurantAgentGraph.

    Later this agent will call:
        RestaurantAgentGraph
    """

    def __init__(self) -> None:
        super().__init__(
            instructions="""
You are a simple restaurant voice assistant.

Speak naturally and briefly.

You are currently running in a development voice test.

Do not invent restaurant information.

If the customer asks a restaurant-specific question,
keep the response short and natural.
"""
        )