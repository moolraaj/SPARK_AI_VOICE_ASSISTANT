from bson import ObjectId
from bson.errors import InvalidId

from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from .ai_employee_repository import AIEmployeeRepository
from .mapper import ai_employee_response
from .schemas.ai_employee_schema import (
    CreateAIEmployeeRequest,
    UpdateAIEmployeeRequest,
)
from app.modules.organizations.organization_repository import OrganizationRepository
from app.modules.businesses.business_platform.business_platform_repository import BusinessPlatformRepository


from app.common.tenant.tenant_scope import apply_tenant_filter, validate_resource_ownership


class AIEmployeeService:

    def __init__(self):
        self.repository       = AIEmployeeRepository()
        self.org_repository   = OrganizationRepository()
        self.bp_repository    = BusinessPlatformRepository()

    # ─── Admin: Get All (Tenant Isolated) ───────────────────────────────────

    async def get_all(self, page: int, limit: int, current_user: dict):
        skip = (page - 1) * limit
        filter_query = apply_tenant_filter(current_user)
        employees     = await self.repository.get_all(skip=skip, limit=limit, query=filter_query)
        total_records = await self.repository.count(query=filter_query)

        return {
            "success": True,
            "data": [ai_employee_response(e) for e in employees],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get by Org ───────────────────────────────────────────────────────────

    async def get_by_org(self, org_id: str, page: int, limit: int, current_user: dict):
        try:
            org_object_id = ObjectId(org_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.org_repository.get_by_id(org_object_id)
        if not org or not validate_resource_ownership(org.get("owner_id"), current_user):
            return {"success": False, "message": "You are not authorized to view AI employees for this organization."}

        skip = (page - 1) * limit
        employees     = await self.repository.get_by_org(org_id=org_id, skip=skip, limit=limit)
        total_records = await self.repository.count_by_org(org_id)

        return {
            "success": True,
            "data": [ai_employee_response(e) for e in employees],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get by ID ────────────────────────────────────────────────────────────

    async def get_by_id(self, ai_employee_id: str, current_user: dict):
        try:
            object_id = ObjectId(ai_employee_id)
        except InvalidId:
            return {"success": False, "message": "Invalid AI employee id."}

        employee = await self.repository.get_by_id(object_id)
        if not employee:
            return {"success": False, "message": "AI employee not found."}

        # Validate organization owner matching logged-in user via central helper
        try:
            org_object_id = ObjectId(employee["org_id"])
            org = await self.org_repository.get_by_id(org_object_id)
            if not org or not validate_resource_ownership(org.get("owner_id"), current_user):
                return {"success": False, "message": "You are not authorized to access this AI employee."}
        except (InvalidId, KeyError, TypeError):
            return {"success": False, "message": "You are not authorized to access this AI employee."}

        return {"success": True, "data": ai_employee_response(employee)}

    # ─── Create ───────────────────────────────────────────────────────────────

    async def create(self, request: CreateAIEmployeeRequest, current_user: dict):

        # ── Validate org exists ───────────────────────────────────────────────
        try:
            org_object_id = ObjectId(request.org_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.org_repository.get_by_id(org_object_id)
        if not org:
            return {"success": False, "message": "Organization not found."}

        # ── Only owner of this org can create AI employee ─────────────────────
        if org["owner_id"] != str(current_user["_id"]):
            return {"success": False, "message": "You are not authorized to create AI employee for this organization."}

        # ── Auto-fetch business_type_id from org → business_platform ──────────
        try:
            bp_object_id = ObjectId(org["business_platform_id"])
        except InvalidId:
            return {"success": False, "message": "Invalid business platform reference in organization."}

        platform = await self.bp_repository.get_by_id(bp_object_id)
        if not platform:
            return {"success": False, "message": "Business platform not found for this organization."}

        business_type_id = platform["business_type_id"]

        # ── Prevent duplicate name in same org ────────────────────────────────
        existing = await self.repository.get_by_name_and_org(request.name, request.org_id)
        if existing:
            return {"success": False, "message": "An AI employee with this name already exists in this organization."}

        data = {
            "org_id":           request.org_id,
            "business_type_id": business_type_id,     # ← auto-fetched
            "name":             request.name,
            "role":             request.role,
            "persona":          request.persona,
            "language":         request.language,
            "greeting_message": request.greeting_message,
            "voice_id":         request.voice_id,
            "is_active":        True,
            **timestamps(),
        }

        ai_employee_id = await self.repository.create(data)

        return {
            "success": True,
            "message": "AI employee created successfully.",
            "data": {
                "id":               ai_employee_id,
                "org_id":           request.org_id,
                "business_type_id": business_type_id,
                "name":             request.name,
                "role":             request.role,
                "persona":          request.persona,
                "language":         request.language,
            },
        }

    # ─── Update ───────────────────────────────────────────────────────────────

    async def update(
        self,
        ai_employee_id: str,
        request: UpdateAIEmployeeRequest,
        current_user: dict,
    ):
        try:
            object_id = ObjectId(ai_employee_id)
        except InvalidId:
            return {"success": False, "message": "Invalid AI employee id."}

        employee = await self.repository.get_by_id(object_id)
        if not employee:
            return {"success": False, "message": "AI employee not found."}

        # ── Only org owner can update ─────────────────────────────────────────
        try:
            org_object_id = ObjectId(employee["org_id"])
        except InvalidId:
            return {"success": False, "message": "Invalid organization reference."}

        org = await self.org_repository.get_by_id(org_object_id)
        if not org or org["owner_id"] != str(current_user["_id"]):
            return {"success": False, "message": "You are not authorized to update this AI employee."}

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            return {"success": False, "message": "No fields provided to update."}

        update_data["updated_at"] = utc_now()
        await self.repository.update(object_id, update_data)
        updated = await self.repository.get_by_id(object_id)

        return {
            "success": True,
            "message": "AI employee updated successfully.",
            "data": ai_employee_response(updated),
        }

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete(self, ai_employee_id: str, current_user: dict):
        try:
            object_id = ObjectId(ai_employee_id)
        except InvalidId:
            return {"success": False, "message": "Invalid AI employee id."}

        employee = await self.repository.get_by_id(object_id)
        if not employee:
            return {"success": False, "message": "AI employee not found."}

        # ── Only org owner can delete ─────────────────────────────────────────
        try:
            org_object_id = ObjectId(employee["org_id"])
        except InvalidId:
            return {"success": False, "message": "Invalid organization reference."}

        org = await self.org_repository.get_by_id(org_object_id)
        if not org or org["owner_id"] != str(current_user["_id"]):
            return {"success": False, "message": "You are not authorized to delete this AI employee."}

        result = await self.repository.delete(object_id)

        if result is None or result.deleted_count == 0:
            return {"success": False, "message": "AI employee could not be deleted."}

        return {"success": True, "message": "AI employee deleted successfully."}
