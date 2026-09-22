"""
SessionContextResolver — Global Validator for every AI session.

Resolution chain:
    DID Number (the Vobiz number a customer CALLED)
        ↓  OrganizationRepository.get_by_did_number()
    Organization  →  org_id, owner_id, business_type_id
        ↓  AIEmployeeRepository.get_active_by_org()
    AI Employee   →  name, role, persona, language
        ↓  PlatformConfigRepository.get_by_business_type_id()
    Platform Config  →  instructions, rules  (optional — super admin may not have set one yet)
        ↓  CustomerRepository.get_or_create_by_phone()
    Customer record  →  customer_id

If any required step fails a descriptive RuntimeError is raised immediately
so the caller layer (SIP handler / API endpoint) can reject the call early.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.modules.organizations.organization_repository import OrganizationRepository
from app.modules.ai_employees.ai_employee_repository import AIEmployeeRepository
from app.modules.platform_configs.platform_config_repository import PlatformConfigRepository
from app.modules.customers.customer_repository import CustomerRepository
from app.core.datetime import timestamps


# ─────────────────────────────────────────────────────────────────────────────
# Resolved Context (the output of a successful resolution)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ResolvedSessionContext:
    """All context needed to run an AI session, fully resolved and validated."""

    # ── Organization ──────────────────────────────────────────────────────────
    owner_id: str                       # MongoDB user _id (org owner)
    org_id: str                         # MongoDB org _id
    business_type: str                  # uppercase slug, e.g. "RESTAURANT"
    business_type_id: str               # MongoDB business_type _id

    # ── AI Employee ───────────────────────────────────────────────────────────
    ai_employee: dict                   # raw MongoDB document
    ai_employee_id: str

    # ── Platform Config (Super Admin layer, may be None) ──────────────────────
    platform_config: Optional[dict] = field(default=None)

    # ── Customer (the actual caller) ──────────────────────────────────────────
    customer_id: Optional[str] = field(default=None)
    caller_phone: Optional[str] = field(default=None)

    # ── DID (for reference / logging) ─────────────────────────────────────────
    did_number: Optional[str] = field(default=None)


# ─────────────────────────────────────────────────────────────────────────────
# SessionContextResolver
# ─────────────────────────────────────────────────────────────────────────────

class SessionContextResolver:
    """
    Central resolver that validates the full DID → Org → AI Employee chain
    before an AI session starts.

    Usage:
        resolver = SessionContextResolver()
        ctx = await resolver.resolve(did_number="+919876500001", caller_phone="+917018616800")

    The resolver is intentionally stateless so a single instance can be shared
    across the application (e.g. injected as a FastAPI dependency).
    """

    def __init__(self):
        self._org_repo      = OrganizationRepository()
        self._emp_repo      = AIEmployeeRepository()
        self._config_repo   = PlatformConfigRepository()
        self._customer_repo = CustomerRepository()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def resolve(
        self,
        did_number: str,
        caller_phone: Optional[str] = None,
    ) -> ResolvedSessionContext:
        """
        Resolve the full session context from the DID number that was called.

        Args:
            did_number:    The Vobiz DID number the customer dialled.
                           Must match an org's did_number field in MongoDB.
            caller_phone:  The actual caller's phone number (customer).
                           Used to look up / create a customer record.

        Returns:
            ResolvedSessionContext — all data needed to start an AI session.

        Raises:
            RuntimeError — with a descriptive message at the first failing step.
        """

        # ── Step 1: DID → Organization ────────────────────────────────────────
        # Owner's registered phone number = DID number = number customer calls.
        # We first try the did_number field; if not set yet (old records),
        # also try the org's phone field as a fallback.
        organization = await self._org_repo.get_by_did_number(did_number)

        if not organization:
            # Fallback: check org.phone (for orgs created before did_number field was added)
            organization = await self._org_repo.organizations.find_one({"phone": did_number})

        if not organization:
            raise RuntimeError(
                f"[SessionContextResolver] No organization found for DID number: {did_number}. "
                "Ensure the DID is assigned to an org in the DB."
            )

        org_id            = str(organization["_id"])
        owner_id          = str(organization.get("owner_id", ""))
        business_type_id  = str(organization.get("business_type_id", ""))

        # ── Step 2: Org → Active AI Employee ──────────────────────────────────
        ai_employee = await self._emp_repo.get_active_by_org(org_id)

        if not ai_employee:
            raise RuntimeError(
                f"[SessionContextResolver] No active AI Employee found for org_id={org_id}. "
                "Please create and activate an AI Employee in the tenant dashboard."
            )

        ai_employee_id = str(ai_employee["_id"])

        # Derive business_type slug (used for TOOL_REGISTRY lookup):
        # Priority: ai_employee.business_type → org.business_type → default RESTAURANT
        business_type = (
            ai_employee.get("business_type")
            or organization.get("business_type")
            or "RESTAURANT"          # safe default
        ).upper().strip()

        # ── Step 3: business_type_id → Platform Config (optional) ─────────────
        platform_config: Optional[dict] = None
        if business_type_id:
            platform_config = await self._config_repo.get_by_business_type_id(
                business_type_id
            )
            # Not a hard failure — super admin may not have configured one yet.
            if not platform_config:
                print(
                    f"[SessionContextResolver] ⚠️  No platform config for "
                    f"business_type_id={business_type_id}. "
                    "AI will use core + employee layers only."
                )

        # ── Step 4: caller_phone → Customer (get or create) ───────────────────
        customer_id: Optional[str] = None
        if caller_phone:
            existing = await self._customer_repo.get_by_phone(owner_id, caller_phone)
            if existing:
                customer_id = str(existing["_id"])
            else:
                import uuid
                customer_id = await self._customer_repo.create_customer({
                    "owner_id":         owner_id,
                    "org_id":           org_id,
                    "phone_number":     caller_phone,
                    "customer_uuid":    f"CUSTOMER_{caller_phone}_{uuid.uuid4().hex[:8]}",
                    "name":             None,
                    "role":             "CUSTOMER",
                    "total_conversations": 1,
                    **timestamps(),
                })

        # ── Return fully resolved context ─────────────────────────────────────
        return ResolvedSessionContext(
            owner_id         = owner_id,
            org_id           = org_id,
            business_type    = business_type,
            business_type_id = business_type_id,
            ai_employee      = self._serialize_doc(ai_employee),
            ai_employee_id   = ai_employee_id,
            platform_config  = self._serialize_doc(platform_config) if platform_config else None,
            customer_id      = customer_id,
            caller_phone     = caller_phone,
            did_number       = did_number,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_doc(doc: dict) -> dict:
        """
        Convert all ObjectId / datetime values in a MongoDB document to plain
        Python types so LangGraph's MemorySaver (msgpack) can serialize them.
        """
        from bson import ObjectId
        from datetime import datetime

        result = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = SessionContextResolver._serialize_doc(value)
            elif isinstance(value, list):
                result[key] = [
                    SessionContextResolver._serialize_doc(v) if isinstance(v, dict)
                    else str(v) if isinstance(v, ObjectId)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result
