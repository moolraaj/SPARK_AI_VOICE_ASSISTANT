# app/voice/livekit/sip.py

from livekit import api

from .config import settings


async def create_outbound_call(
    phone_number: str,
    room_name: str,
    participant_identity: str,
    agent_name: str = "restaurant-agent",
):
    """
    Correct outbound flow (per LiveKit docs):
      1) Explicitly dispatch the named agent to the room FIRST.
      2) Only then dial the customer via CreateSIPParticipant.

    `agent_name` is set on the worker (@server.rtc_session(agent_name=...)),
    which DISABLES automatic dispatch. Without step 1, the agent never
    joins the room — call connects but there's total silence.
    """

    livekit_api = api.LiveKitAPI(
        settings.LIVEKIT_URL,
        settings.LIVEKIT_API_KEY,
        settings.LIVEKIT_API_SECRET,
    )

    try:
        # ── Step 1: Explicit agent dispatch ──────────────────────────
        dispatch = await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
            )
        )
        print(f"✅ Agent dispatched: {dispatch}")

        # ── Step 2: Dial the customer ────────────────────────────────
        request = api.CreateSIPParticipantRequest(
            sip_trunk_id=settings.LIVEKIT_OUTBOUND_TRUNK_ID,
            sip_call_to=phone_number,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name="Customer",
            wait_until_answered=True,
        )

        response = await livekit_api.sip.create_sip_participant(request)
        return response

    finally:
        await livekit_api.aclose()