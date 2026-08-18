from fastapi import APIRouter, Query, Depends
from .user_service import UserService
from .schemas.user_schema import UpdateUserRequest
from app.middleware.auth import get_current_user, require_super_admin


service = UserService()

users_router = APIRouter(prefix="/users", tags=["Users"])
user_router = APIRouter(prefix="/user", tags=["User"])


@users_router.get("")
async def get_all_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Get registered users list.
    """
    return await service.get_all_users(page, limit)


@user_router.get("/get-by-id/{user_id}")
async def get_user_by_id(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Read user profile by ID. User can only view their own profile unless Super Admin.
    """
    return await service.get_user_by_id(user_id, current_user)


@user_router.put("/update/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Update user profile. Regular user can only update their own profile; Super Admin can update any profile.
    """
    return await service.update_user(user_id, request, current_user)


@user_router.delete("/remove/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(require_super_admin)
):
    """
    SUPER ADMIN ONLY: Delete user.
    """
    return await service.delete_user(user_id, current_user)
