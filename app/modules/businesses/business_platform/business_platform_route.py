from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user, require_super_admin
from ..schemas.business_platform_schema import (
    CreateBusinessPlatformRequest,
    UpdateBusinessPlatformRequest,
)
from .business_platform_service import BusinessPlatformService


service = BusinessPlatformService()

business_platforms_router = APIRouter(prefix="/business-platforms", tags=["Business Platforms"])
business_platform_router = APIRouter(prefix="/business-platform", tags=["Business Platform"])


@business_platforms_router.get("")
async def get_all_business_platforms(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    _ = Depends(get_current_user),
):
    return await service.get_all(page, limit)


@business_platform_router.get("/get-by-id/{business_platform_id}")
async def get_business_platform_by_id(
    business_platform_id: str,
    _ = Depends(get_current_user),
):
    return await service.get_by_id(business_platform_id)


@business_platform_router.post("/create")
async def create_business_platform(
    request: CreateBusinessPlatformRequest,
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Create Business Platform.
    """
    return await service.create(request)


@business_platform_router.put("/update/{business_platform_id}")
async def update_business_platform(
    business_platform_id: str,
    request: UpdateBusinessPlatformRequest,
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Update Business Platform.
    """
    return await service.update(business_platform_id, request)


@business_platform_router.delete("/remove/{business_platform_id}")
async def delete_business_platform(
    business_platform_id: str,
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Delete Business Platform.
    """
    return await service.delete(business_platform_id)
