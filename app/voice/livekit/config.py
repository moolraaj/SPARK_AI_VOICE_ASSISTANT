from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_URL,
    LIVEKIT_OUTBOUND_TRUNK_ID
)


class LiveKitSettings(BaseSettings):
    """
    Configuration for the self-hosted LiveKit
    agent worker.
    """

    LIVEKIT_URL: str = LIVEKIT_URL
    LIVEKIT_API_KEY: str = LIVEKIT_API_KEY
    LIVEKIT_API_SECRET: str = LIVEKIT_API_SECRET
    LIVEKIT_OUTBOUND_TRUNK_ID:str=LIVEKIT_OUTBOUND_TRUNK_ID

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = LiveKitSettings()