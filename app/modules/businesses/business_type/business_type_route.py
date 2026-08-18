from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user, require_super_admin
from ..schemas.business_type_schema import (
    CreateBusinessTypeRequest,
    UpdateBusinessTypeRequest,
)
from .business_type_service import BusinessTypeService


service = BusinessTypeService()

business_types_router = APIRouter(prefix="/business-types", tags=["Business Types"])
business_type_router = APIRouter(prefix="/business-type", tags=["Business Type"])


@business_types_router.get("")
async def get_all_business_types(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    _ = Depends(get_current_user),
):
    return await service.get_all(page, limit)


@business_type_router.get("/get-by-id/{business_type_id}")
async def get_business_type_by_id(
    business_type_id: str,
    _ = Depends(get_current_user),
):
    return await service.get_by_id(business_type_id)


@business_type_router.post("/create")
async def create_business_type(
    request: CreateBusinessTypeRequest,
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Create Business Type.
    """
    return await service.create(request)


@business_type_router.put("/update/{business_type_id}")
async def update_business_type(
    business_type_id: str,
    request: UpdateBusinessTypeRequest,
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Update Business Type.
    """
    return await service.update(business_type_id, request)


@business_type_router.delete("/remove/{business_type_id}")
async def delete_business_type(
    business_type_id: str,
    _ = Depends(require_super_admin),
):
    """
    SUPER ADMIN ONLY: Delete Business Type.
    """
    return await service.delete(business_type_id)
