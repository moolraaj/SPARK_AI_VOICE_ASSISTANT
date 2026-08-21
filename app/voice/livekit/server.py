import logging
import uuid
import json

from bson import ObjectId
from dotenv import load_dotenv

from livekit.agents import (
    AgentServer,
    JobContext,
    cli,
)

from app.database.mongodb import mongodb
from app.modules.auth.repository import AuthRepository
from app.modules.organizations.organization_repository import OrganizationRepository
from app.modules.ai_employees.ai_employee_repository import AIEmployeeRepository

from app.voice.livekit.agent import RestaurantVoiceAgent
from app.voice.services.voice_session import VoiceSession


load_dotenv()


logger = logging.getLogger("restaurant-livekit-server")
logger.setLevel(logging.INFO)


server = AgentServer()


# ──────────────────────────────────────────────────────────────────
# OWNER PHONE → owner_id → org → ai_employee
# ──────────────────────────────────────────────────────────────────

# Outbound test: owner ka registered phone (users table)
# Production/inbound me ye ctx.room.metadata["to_number"] se aayega
OWNER_PHONE = "6230097248"


async def resolve_employee(owner_phone: str):
    """
    phone → users → org → active ai_employee
    Returns: (owner_id, employee_dict) or (None, None)
    """
    auth_repo     = AuthRepository()
    org_repo      = OrganizationRepository()
    employee_repo = AIEmployeeRepository()

    owner = await auth_repo.get_user_by_phone(owner_phone)
    if not owner:
        logger.error("Owner not found for phone: %s", owner_phone)
        return None, None

    owner_id = str(owner["_id"])

    orgs = await org_repo.get_by_owner(owner_id, skip=0, limit=1)
    if not orgs:
        logger.error("No org found for owner: %s", owner_id)
        return owner_id, None

    org_id   = str(orgs[0]["_id"])
    employee = await employee_repo.get_active_by_org(org_id)

    if not employee:
        logger.error("No active employee for org: %s", org_id)
        return owner_id, None

    return owner_id, employee


def _sanitize(doc: dict) -> dict:
    """
    MongoDB dict me ObjectId aur datetime fields ko str me convert karo.
    LangGraph msgpack me ObjectId serialize nahi kar sakta — ye fix karta hai.
    """
    clean = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            clean[k] = str(v)
        elif isinstance(v, dict):
            clean[k] = _sanitize(v)
        elif isinstance(v, list):
            clean[k] = [
                _sanitize(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i)
                for i in v
            ]
        else:
            # datetime → isoformat string, rest pass-through
            clean[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return clean


# ──────────────────────────────────────────────────────────────────
# ENTRYPOINT — called on every dispatched job
# ──────────────────────────────────────────────────────────────────

@server.rtc_session(
    agent_name="restaurant-agent",
)
async def entrypoint(ctx: JobContext):

    logger.info("Job received | room=%s", ctx.room.name)

    await ctx.connect()
    await mongodb.connect()

    # ── Resolve owner + employee ────────────────────────────────
    owner_id, employee = await resolve_employee(OWNER_PHONE)

    if not employee:
        logger.error("Cannot start session — employee not resolved.")
        return

    ai_employee_id = str(employee["_id"])
    employee_data  = _sanitize(employee)   # ObjectId → str, LangGraph safe
    session_id     = f"SESSION_{uuid.uuid4().hex[:8]}"

    logger.info(
        "Resolved | owner=%s | employee=%s | session=%s",
        owner_id, ai_employee_id, session_id,
    )


    # ── Build agent with full context ──────────────────────────
    agent = RestaurantVoiceAgent(
        owner_id       = owner_id,
        ai_employee_id = ai_employee_id,
        employee_data  = employee_data,   # sanitized — ObjectId already converted
        session_id     = session_id,
    )

    # ── Start voice session (STT + TTS + VAD + Agent) ──────────
    voice_session = VoiceSession(agent=agent)
    await voice_session.start(room=ctx.room)

    logger.info("Voice session started | room=%s | session=%s", ctx.room.name, session_id)


if __name__ == "__main__":
    cli.run_app(server)