import logging

from dotenv import load_dotenv

from livekit.agents import (
    AgentServer,
    JobContext,
    cli,
)

from app.voice.livekit.agent import RestaurantVoiceAgent
from app.voice.services.voice_session import VoiceSession


load_dotenv()


logger = logging.getLogger(
    "restaurant-livekit-agent"
)

logger.setLevel(logging.INFO)


server = AgentServer()


@server.rtc_session(
    agent_name="restaurant-agent",
)
async def entrypoint(ctx: JobContext):

    logger.info(
        "New LiveKit job received | room=%s",
        ctx.room.name,
    )

    await ctx.connect()

    # ---------------------------------------------
    # VOICE SESSION
    # ---------------------------------------------

    voice_session = VoiceSession(
        agent=RestaurantVoiceAgent(),
    )

    await voice_session.start(
        room=ctx.room,
    )

    logger.info(
        "Restaurant voice session started | room=%s",
        ctx.room.name,
    )


if __name__ == "__main__":
    cli.run_app(server)