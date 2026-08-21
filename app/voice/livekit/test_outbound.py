import asyncio
import uuid

from app.voice.livekit.sip import create_outbound_call


async def main():

    # Unique room name har run me — reused "restaurant-test" room ke saath
    # token-based dispatch ignore ho jaata agar room already exist karta ho.
    # API-based dispatch (upar sip.py me) is issue se bachata hai, phir bhi
    # unique room naming safest practice hai testing ke liye.
    room_name = f"restaurant-test-{uuid.uuid4().hex[:8]}"

    response = await create_outbound_call(
        phone_number="+916230097248",
        room_name=room_name,
        participant_identity="customer-7018616800",
        agent_name="restaurant-agent",   # server.py ke @server.rtc_session(agent_name=...) se match hona chahiye
    )

    print("CALL CREATED")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())