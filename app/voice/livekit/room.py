from livekit import api

from .config import settings


def create_livekit_api() -> api.LiveKitAPI:
    """
    Create a LiveKit API client for the self-hosted server.
    """

    return api.LiveKitAPI(
        settings.LIVEKIT_URL,
        settings.LIVEKIT_API_KEY,
        settings.LIVEKIT_API_SECRET,
    )