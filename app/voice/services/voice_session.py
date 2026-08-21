from livekit.agents import Agent, AgentSession
from livekit.plugins import silero

from app.voice.stt.deepgram import stt
from app.voice.tts.sarvam import tts


class VoiceSession:

    def __init__(
        self,
        agent: Agent,
    ) -> None:

        self.agent = agent

        self.vad = silero.VAD.load()

        self.session = AgentSession(
            stt=stt,
            tts=tts,
            vad=self.vad,
        )

    async def start(
        self,
        room,
    ) -> None:

        await self.session.start(
            agent=self.agent,
            room=room,
        )