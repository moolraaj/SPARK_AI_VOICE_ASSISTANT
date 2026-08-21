from livekit.plugins import sarvam
from app.core.config import SARVAM_API_KEY


class SarvamTTS:

    def __init__(
        self,
        target_language_code: str = "hi-IN",
        model: str = "bulbul:v3",
        speaker: str = "shubh",
        pace: float = 1.0,
    ) -> None:
        self.target_language_code = target_language_code
        self.model = model
        self.speaker = speaker
        self.pace = pace

    def create(self):

        return sarvam.TTS(
            target_language_code=self.target_language_code,
            model=self.model,
            speaker=self.speaker,
            pace=self.pace,
            api_key=SARVAM_API_KEY,

        )


# Ready-to-use instance — imported directly by server.py
tts = SarvamTTS().create()