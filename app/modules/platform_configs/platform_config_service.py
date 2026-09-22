from bson import ObjectId
from bson.errors import InvalidId

from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from app.common.tenant.tenant_scope import require_role
from .platform_config_repository import PlatformConfigRepository
from .mapper import platform_config_response
from .schemas.platform_config_schema import (
    CreatePlatformConfigRequest,
    UpdatePlatformConfigRequest,
)
from app.modules.businesses.business_type.business_type_repository import BusinessTypeRepository


class PlatformConfigService:

    def __init__(self):
        self.repository = PlatformConfigRepository()
        self.business_type_repository = BusinessTypeRepository()

    # ─── Get All ──────────────────────────────────────────────────────────────

    async def get_all(
        self,
        page: int,
        limit: int,
        current_user: dict,
        is_active: bool | None = None,
    ):
        skip = (page - 1) * limit

        filter_query: dict = {}
        if is_active is not None:
            filter_query["is_active"] = is_active

        configs = await self.repository.get_all(skip=skip, limit=limit, query=filter_query)
        total_records = await self.repository.count(query=filter_query)

        return {
            "success": True,
            "data": [platform_config_response(c) for c in configs],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get by ID ────────────────────────────────────────────────────────────

    async def get_by_id(self, config_id: str, current_user: dict):
        try:
            config_obj_id = ObjectId(config_id)
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid config ID."}

        config = await self.repository.get_by_id(config_obj_id)
        if not config:
            return {"success": False, "message": "Platform config not found."}

        return {
            "success": True,
            "data": platform_config_response(config),
        }

    # ─── Get by Business Type ID ──────────────────────────────────────────────

    async def get_by_business_type_id(self, business_type_id: str, current_user: dict):
        config = await self.repository.get_by_business_type_id(business_type_id)
        if not config:
            return {"success": False, "message": "Platform config not found for given business type."}

        return {
            "success": True,
            "data": platform_config_response(config),
        }

    # ─── Create ───────────────────────────────────────────────────────────────

    async def create(self, request: CreatePlatformConfigRequest, current_user: dict):
        if not require_role(current_user, "SUPER_ADMIN"):
            return {
                "success": False,
                "message": "Only super admin is authorized to create platform configs.",
            }

        # ── Validate business_type_id ──────────────────────────────────────────
        try:
            bt_obj_id = ObjectId(request.business_type_id.strip())
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid business_type_id format."}

        existing_bt = await self.business_type_repository.get_by_id(bt_obj_id)
        if not existing_bt:
            return {"success": False, "message": "Business type not found with the given ID."}

        # ── Duplicate check: 1 config per business_type_id ────────────────────
        already_exists = await self.repository.get_by_business_type_id(request.business_type_id.strip())
        if already_exists:
            bt_name = existing_bt.get("name", request.business_type_id)
            return {
                "success": False,
                "message": f"A platform prompt for '{bt_name}' already exists. Only one prompt per business type is allowed.",
            }
        # ─────────────────────────────────────────────────────────────────────

        new_config = {
            "business_type_id": request.business_type_id.strip(),
            "instructions": request.instructions.strip(),
            "rules": request.rules.strip(),
            "is_active": request.is_active,
            **timestamps(),
        }

        inserted_id = await self.repository.create(new_config)
        created_config = await self.repository.get_by_id(ObjectId(inserted_id))

        return {
            "success": True,
            "message": "Platform config created successfully.",
            "data": platform_config_response(created_config) if created_config else None,
        }

    # ─── Update ───────────────────────────────────────────────────────────────

    async def update(self, config_id: str, request: UpdatePlatformConfigRequest, current_user: dict):
        if not require_role(current_user, "SUPER_ADMIN"):
            return {
                "success": False,
                "message": "Only super admin is authorized to update platform configs.",
            }

        try:
            config_obj_id = ObjectId(config_id)
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid config ID."}

        existing = await self.repository.get_by_id(config_obj_id)
        if not existing:
            return {"success": False, "message": "Platform config not found."}

        update_data: dict = {}
        if request.instructions is not None:
            update_data["instructions"] = request.instructions.strip()
        if request.rules is not None:
            update_data["rules"] = request.rules.strip()
        if request.is_active is not None:
            update_data["is_active"] = request.is_active

        if update_data:
            update_data["updated_at"] = utc_now()
            await self.repository.update(config_obj_id, update_data)

        updated_config = await self.repository.get_by_id(config_obj_id)
        return {
            "success": True,
            "message": "Platform config updated successfully.",
            "data": platform_config_response(updated_config) if updated_config else None,
        }

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete(self, config_id: str, current_user: dict):
        if not require_role(current_user, "SUPER_ADMIN"):
            return {
                "success": False,
                "message": "Only super admin is authorized to delete platform configs.",
            }

        try:
            config_obj_id = ObjectId(config_id)
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid config ID."}

        existing = await self.repository.get_by_id(config_obj_id)
        if not existing:
            return {"success": False, "message": "Platform config not found."}

        await self.repository.delete(config_obj_id)

        return {
            "success": True,
            "message": "Platform config deleted successfully.",
        }
