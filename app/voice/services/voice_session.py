from livekit.agents import Agent, AgentSession
from livekit.plugins import silero

from app.voice.stt.deepgram import stt
from app.voice.tts.sarvam import tts


# ── Module-level VAD cache ──────────────────────────────────────────────
# silero.VAD.load() ek model load karta hai. Pehle ye har naye call/job
# (VoiceSession() instantiate hone) pe fresh load ho raha tha, jo call
# setup me avoidable delay add karta hai. Ab worker process ke andar
# ek hi baar load hoga aur saare sessions isko reuse karenge.
_shared_vad = None


def _get_vad():
    global _shared_vad
    if _shared_vad is None:
        _shared_vad = silero.VAD.load()
    return _shared_vad


class VoiceSession:

    def __init__(
        self,
        agent: Agent,
    ) -> None:

        self.agent = agent

        self.vad = _get_vad()

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