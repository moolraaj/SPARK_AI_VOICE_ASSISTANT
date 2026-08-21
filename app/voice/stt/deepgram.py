from livekit.plugins import deepgram
from app.core.config import DEEPGRAM_API_KEY

class DeepgramSTT:

    def __init__(
        self,
        model: str = "nova-3",
        language: str = "multi",
    ) -> None:
        self.model = model
        self.language = language

    def create(self):
        return deepgram.STT(
            model=self.model,
            language=self.language,
            api_key=DEEPGRAM_API_KEY,
        )


# Ready-to-use instance — imported directly by server.py
stt = DeepgramSTT().create()