"""
LiveKit Agent Server — Multi-Tenant Dynamic Routing.

Inbound Call Flow:
  Vobiz → LiveKit Room (room.metadata has 'to_number')
  → DB Lookup: organizations.did_number == to_number
  → Org → Owner (owner_id) → Active AI Employee
  → business_type → SparkAgentGraph (dynamic tools)
  → SparkVoiceAgent starts voice session
"""

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
from app.modules.organizations.organization_repository import OrganizationRepository
from app.modules.ai_employees.ai_employee_repository import AIEmployeeRepository
from app.modules.businesses.business_type.business_type_repository import BusinessTypeRepository

from app.voice.livekit.agent import SparkVoiceAgent
from app.voice.services.voice_session import VoiceSession


load_dotenv()


logger = logging.getLogger("global-livekit-server")
logger.setLevel(logging.INFO)


server = AgentServer()


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


async def resolve_from_did(to_number: str):
    """
    Multi-tenant inbound routing:
      to_number (DID) → organizations.did_number match
      → org_id, owner_id, org_name → active AI Employee
      → employee.business_type_id → BusinessType.name (dynamic)

    Returns: (owner_id, org_id, org_name, employee_dict) or (None, None, None, None)
    employee_dict has 'business_type' field injected dynamically from DB.
    """
    org_repo           = OrganizationRepository()
    employee_repo      = AIEmployeeRepository()
    business_type_repo = BusinessTypeRepository()

    # Step 1: Find org by the DID number customer called
    org = await org_repo.get_by_did_number(to_number)
    if not org:
        # Fallback: try without country code prefix
        stripped = to_number.lstrip("+").lstrip("91")
        org = await org_repo.get_by_did_number(stripped)

    if not org:
        logger.error("No org found for DID/to_number: %s", to_number)
        return None, None, None, None

    org_id    = str(org["_id"])
    owner_id  = str(org.get("owner_id", ""))
    org_name  = org.get("name", "")

    logger.info("Org resolved | org_id=%s | org_name=%s | owner=%s", org_id, org_name, owner_id)

    # Step 2: Get active AI Employee for this org
    employee = await employee_repo.get_active_by_org(org_id)
    if not employee:
        logger.error("No active AI employee for org: %s", org_id)
        return owner_id, org_id, org_name, None

    # Step 3: Dynamically resolve business_type string from BusinessType collection
    # employee.business_type_id (ObjectId ref) → business_types.name (e.g. "RESTAURANT")
    business_type_str = "GENERAL"   # safe fallback
    raw_bt_id = employee.get("business_type_id")
    if raw_bt_id:
        try:
            from bson import ObjectId as _ObjId
            bt_doc = await business_type_repo.get_by_id(_ObjId(str(raw_bt_id)))
            if bt_doc and bt_doc.get("name"):
                business_type_str = bt_doc["name"].upper().strip()
                logger.info(
                    "business_type resolved | id=%s → name=%s",
                    raw_bt_id, business_type_str,
                )
            else:
                logger.warning(
                    "BusinessType doc not found for id=%s — falling back to GENERAL",
                    raw_bt_id,
                )
        except Exception as exc:
            logger.error("business_type lookup failed: %s — falling back to GENERAL", exc)

    # Inject resolved business_type string into employee dict
    employee["business_type"] = business_type_str

    return owner_id, org_id, org_name, employee


# ──────────────────────────────────────────────────────────────────
# ENTRYPOINT — called on every dispatched job
# ──────────────────────────────────────────────────────────────────

@server.rtc_session(
    agent_name="spark-agent",
)
async def entrypoint(ctx: JobContext):

    logger.info("Job received | room=%s", ctx.room.name)

    await ctx.connect()
    await mongodb.connect()

    # ── Extract to_number from room metadata (set by Vobiz inbound) ────────
    raw_metadata = ctx.room.metadata or "{}"
    try:
        metadata = json.loads(raw_metadata)
    except Exception:
        metadata = {}

    to_number = (
        metadata.get("to_number")
        or metadata.get("called_number")
        or metadata.get("did")
        or ""
    ).strip()

    if not to_number:
        logger.warning(
            "No to_number in room metadata — room=%s | metadata=%s",
            ctx.room.name, raw_metadata,
        )

    # ── Resolve org + employee from DID number ──────────────────────────────
    owner_id, org_id, org_name, employee = await resolve_from_did(to_number)

    if not employee:
        logger.error(
            "Cannot start session — employee not resolved | to_number=%s", to_number
        )
        return

    ai_employee_id = str(employee["_id"])
    employee_data  = _sanitize(employee)   # ObjectId → str, LangGraph safe
    session_id     = f"SESSION_{uuid.uuid4().hex[:8]}"

    logger.info(
        "Session ready | owner=%s | org=%s | org_name=%s | employee=%s | "
        "business_type=%s | session=%s",
        owner_id, org_id, org_name,
        ai_employee_id,
        employee_data.get("business_type", "RESTAURANT"),
        session_id,
    )

    # ── Build dynamic agent — business_type auto-detected inside SparkVoiceAgent ──
    agent = SparkVoiceAgent(
        owner_id       = owner_id,
        ai_employee_id = ai_employee_id,
        employee_data  = employee_data,
        session_id     = session_id,
        org_name       = org_name,
    )

    # ── Start voice session (STT + TTS + VAD + Agent) ──────────────────────
    voice_session = VoiceSession(agent=agent)
    await voice_session.start(room=ctx.room)

    logger.info("Voice session started | room=%s | session=%s", ctx.room.name, session_id)


if __name__ == "__main__":
    cli.run_app(server)