# app/voice/livekit/sip.py

from livekit import api

from .config import settings


async def create_outbound_participant(
    phone_number: str,
    room_name: str,
    participant_identity: str,
):

    livekit_api = api.LiveKitAPI(
        settings.LIVEKIT_URL,
        settings.LIVEKIT_API_KEY,
        settings.LIVEKIT_API_SECRET,
    )

    request = api.CreateSIPParticipantRequest(
        sip_trunk_id=settings.LIVEKIT_OUTBOUND_TRUNK_ID,
        sip_call_to=phone_number,
        room_name=room_name,
        participant_identity=participant_identity,
        participant_name="Customer",
        wait_until_answered=True,
    )

    try:
        response = await livekit_api.sip.create_sip_participant(
            request
        )

        return response

    finally:
        await livekit_api.aclose()