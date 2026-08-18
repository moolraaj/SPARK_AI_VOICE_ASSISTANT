from bson import ObjectId
from bson.errors import InvalidId

from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from .business_type_repository import BusinessTypeRepository
from ..schemas.business_type_schema import (
    CreateBusinessTypeRequest,
    UpdateBusinessTypeRequest,
)


class BusinessTypeService:

    def __init__(self):
        self.repository = BusinessTypeRepository()

    async def get_all(self, page: int, limit: int):

        skip = (page - 1) * limit

        business_types = await self.repository.get_all(skip=skip, limit=limit)
        total_records = await self.repository.count()

        response = []
        for bt in business_types:
            response.append({
                "id": str(bt["_id"]),
                "name": bt["name"],
                "description": bt.get("description"),
                "is_active": bt["is_active"],
                "created_at": bt["created_at"],
                "updated_at": bt["updated_at"],
            })

        return {
            "success": True,
            "data": response,
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit
            )
        }

    async def get_by_id(self, business_type_id: str):

        try:
            object_id = ObjectId(business_type_id)
        except InvalidId:
            return {
                "success": False,
                "message": "Invalid business type id."
            }

        bt = await self.repository.get_by_id(object_id)

        if not bt:
            return {
                "success": False,
                "message": "Business type not found."
            }

        return {
            "success": True,
            "data": {
                "id": str(bt["_id"]),
                "name": bt["name"],
                "description": bt.get("description"),
                "is_active": bt["is_active"],
                "created_at": bt["created_at"],
                "updated_at": bt["updated_at"],
            }
        }

    async def create(self, request: CreateBusinessTypeRequest):

        existing = await self.repository.get_by_name(request.name)
        if existing:
            return {
                "success": False,
                "message": "Business type with this name already exists."
            }

        data = {
            "name": request.name,
            "description": request.description,
            "is_active": True,
            **timestamps(),
        }

        business_type_id = await self.repository.create(data)

        return {
            "success": True,
            "message": "Business type created successfully.",
            "data": {
                "id": business_type_id,
                "name": request.name,
                "description": request.description,
            }
        }

    async def update(self, business_type_id: str, request: UpdateBusinessTypeRequest):

        try:
            object_id = ObjectId(business_type_id)
        except InvalidId:
            return {
                "success": False,
                "message": "Invalid business type id."
            }

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            return {
                "success": False,
                "message": "No fields provided to update."
            }

        update_data["updated_at"] = utc_now()

        result = await self.repository.update(object_id, update_data)

        if result.matched_count == 0:
            return {
                "success": False,
                "message": "Business type not found."
            }

        updated = await self.repository.get_by_id(object_id)

        return {
            "success": True,
            "message": "Business type updated successfully.",
            "data": {
                "id": str(updated["_id"]),
                "name": updated["name"],
                "description": updated.get("description"),
                "is_active": updated["is_active"],
                "updated_at": updated["updated_at"],
            }
        }

    async def delete(self, business_type_id: str):

        try:
            object_id = ObjectId(business_type_id)
        except InvalidId:
            return {
                "success": False,
                "message": "Invalid business type id."
            }

        result = await self.repository.delete(object_id)

        if result is None or result.deleted_count == 0:
            return {
                "success": False,
                "message": "Business type not found."
            }

        return {
            "success": True,
            "message": "Business type deleted successfully."
        }
