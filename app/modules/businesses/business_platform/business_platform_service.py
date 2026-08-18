from bson import ObjectId
from bson.errors import InvalidId

from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from .business_platform_repository import BusinessPlatformRepository
from ..schemas.business_platform_schema import (
    CreateBusinessPlatformRequest,
    UpdateBusinessPlatformRequest,
)


def _bp_response(bp: dict) -> dict:
    return {
        "id": str(bp["_id"]),
        "business_type_id": bp["business_type_id"],
        "name": bp["name"],
        "description": bp.get("description"),
        "features": bp.get("features", []),
        "duration": bp.get("duration", 1),
        "pricing": bp.get("pricing", {}),
        "is_active": bp["is_active"],
        "created_at": bp["created_at"],
        "updated_at": bp["updated_at"],
    }


class BusinessPlatformService:

    def __init__(self):
        self.repository = BusinessPlatformRepository()

    # ─── Get All ──────────────────────────────────────────────────────────────

    async def get_all(self, page: int, limit: int):
        skip = (page - 1) * limit
        business_platforms = await self.repository.get_all(skip=skip, limit=limit)
        total_records = await self.repository.count()

        return {
            "success": True,
            "data": [_bp_response(bp) for bp in business_platforms],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get By ID ────────────────────────────────────────────────────────────

    async def get_by_id(self, business_platform_id: str):
        try:
            object_id = ObjectId(business_platform_id)
        except InvalidId:
            return {"success": False, "message": "Invalid business platform id."}

        bp = await self.repository.get_by_id(object_id)
        if not bp:
            return {"success": False, "message": "Business platform not found."}

        return {"success": True, "data": _bp_response(bp)}

    # ─── Create (SuperAdmin only) ─────────────────────────────────────────────

    async def create(self, request: CreateBusinessPlatformRequest):
        existing = await self.repository.get_by_name(request.name)
        if existing:
            return {
                "success": False,
                "message": "Business platform with this name already exists.",
            }

        data = {
            "business_type_id": request.business_type_id,
            "name": request.name,
            "description": request.description,
            "features": request.features,
            "duration": request.duration,
            "pricing": {
                "base_price": request.pricing.base_price,
                "selling_price": request.pricing.selling_price,
                "currency": request.pricing.currency,
            },
            "is_active": True,
            **timestamps(),
        }

        business_platform_id = await self.repository.create(data)

        return {
            "success": True,
            "message": "Business platform created successfully.",
            "data": {
                "id": business_platform_id,
                "business_type_id": request.business_type_id,
                "name": request.name,
                "description": request.description,
                "features": request.features,
                "duration": request.duration,
                "pricing": {
                    "base_price": request.pricing.base_price,
                    "selling_price": request.pricing.selling_price,
                    "currency": request.pricing.currency,
                },
            },
        }

    # ─── Update (SuperAdmin only) ─────────────────────────────────────────────

    async def update(self, business_platform_id: str, request: UpdateBusinessPlatformRequest):
        try:
            object_id = ObjectId(business_platform_id)
        except InvalidId:
            return {"success": False, "message": "Invalid business platform id."}

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            return {"success": False, "message": "No fields provided to update."}

        # Serialize pricing if updated
        if "pricing" in update_data and request.pricing:
            update_data["pricing"] = {
                "base_price": request.pricing.base_price,
                "selling_price": request.pricing.selling_price,
                "currency": request.pricing.currency,
            }

        update_data["updated_at"] = utc_now()
        result = await self.repository.update(object_id, update_data)

        if result.matched_count == 0:
            return {"success": False, "message": "Business platform not found."}

        updated = await self.repository.get_by_id(object_id)
        return {
            "success": True,
            "message": "Business platform updated successfully.",
            "data": _bp_response(updated),
        }

    # ─── Delete (SuperAdmin only) ─────────────────────────────────────────────

    async def delete(self, business_platform_id: str):
        try:
            object_id = ObjectId(business_platform_id)
        except InvalidId:
            return {"success": False, "message": "Invalid business platform id."}

        result = await self.repository.delete(object_id)
        if result is None or result.deleted_count == 0:
            return {"success": False, "message": "Business platform not found."}

        return {"success": True, "message": "Business platform deleted successfully."}
