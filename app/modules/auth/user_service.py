from .repository import AuthRepository
from app.core.datetime import utc_now
from bson.errors import InvalidId
from bson import ObjectId
from app.common.pagination.pagination import pagination_response


from app.common.tenant.tenant_scope import validate_resource_ownership


class UserService:

    def __init__(self):
        self.repository = AuthRepository()

    async def get_user_by_id_public(self, user_id: str):
        try:
            object_id = ObjectId(user_id)
        except InvalidId:
            return {
                "success": False,
                "message": "Please provide a valid user id."
            }

        user = await self.repository.get_user_by_id(object_id)

        if not user:
            return {
                "success": False,
                "message": "User not found."
            }

        return {
            "success": True,
            "data": {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "phone_number": user["phone_number"],
                "role": user["role"],
                "is_active": user["is_active"],
                "is_verified": user["is_verified"],
                "created_at": user["created_at"],
                "updated_at": user["updated_at"],
            }
        }

    async def get_user_by_id(self, user_id: str, current_user: dict):
        # Validate that user can only view their own profile unless SUPER_ADMIN
        if not validate_resource_ownership(user_id, current_user):
            return {
                "success": False,
                "message": "You are not authorized to view this user profile."
            }
        return await self.get_user_by_id_public(user_id)

    async def delete_user(self, user_id: str, current_user: dict):
        # Only SUPER_ADMIN can delete users
        if str(current_user.get("role", "")).upper() != "SUPER_ADMIN":
            return {
                "success": False,
                "message": "Only Super Admin can delete users."
            }

        try:
            object_id = ObjectId(user_id)
        except InvalidId:
            return {
                "success": False,
                "message": "Invalid user id"
            }

        result = await self.repository.delete_user(object_id)

        if result is None or result.deleted_count == 0:
            return {
                "success": False,
                "message": "User not found"
            }

        return {
            "success": True,
            "message": "User deleted successfully"
        }

    async def update_user(self, user_id: str, request, current_user: dict):
        # Users can only update their own profile unless SUPER_ADMIN
        if not validate_resource_ownership(user_id, current_user):
            return {
                "success": False,
                "message": "You are not authorized to update this user profile."
            }

        try:
            object_id = ObjectId(user_id)
        except InvalidId:
            return {
                "success": False,
                "message": "Invalid user id"
            }

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            return {
                "success": False,
                "message": "No fields provided to update"
            }

        update_data["updated_at"] = utc_now()

        result = await self.repository.update_user(
            object_id,
            update_data
        )

        if result.matched_count == 0:
            return {
                "success": False,
                "message": "User not found"
            }

        updated_user = await self.repository.get_user_by_id(object_id)
        response = {
            "id": str(updated_user["_id"]),
            "name": updated_user["name"],
            "email": updated_user["email"],
            "phone_number": updated_user["phone_number"],
            "role": updated_user["role"],
            "is_active": updated_user["is_active"]
        }
        return {
            "success": True,
            "message": "User updated successfully",
            "data": response
        }

    async def get_all_users(
        self,
        page: int,
        limit: int
    ):

        skip = (page - 1) * limit

        users = await self.repository.get_all_users(
            skip=skip,
            limit=limit
        )

        total_records = await self.repository.count_users()

        response = []

        for user in users:

            response.append(
                {
                    "id": str(user["_id"]),
                    "name": user["name"],
                    "email": user["email"],
                    "phone_number": user["phone_number"],
                    "role": user["role"],
                    "is_active": user["is_active"],
                    "is_verified": user["is_verified"],
                    "created_at": user["created_at"],
                    "updated_at": user["updated_at"],
                }
            )

        return {

            "success": True,
            "data": response,
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit
            )

        }