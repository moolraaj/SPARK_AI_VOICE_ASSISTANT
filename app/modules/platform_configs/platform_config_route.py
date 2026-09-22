from typing import Optional
from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.platform_config_schema import (
    CreatePlatformConfigRequest,
    UpdatePlatformConfigRequest,
)
from .platform_config_service import PlatformConfigService


service = PlatformConfigService()

# Plural — list routes
platform_configs_router = APIRouter(prefix="/platform-configs", tags=["Platform Configs"])

# Singular — item routes
platform_config_router = APIRouter(prefix="/platform-config", tags=["Platform Config"])


# ─── Get All Platform Configs ─────────────────────────────────────────────────

@platform_configs_router.get("")
async def get_all_platform_configs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    current_user: dict = Depends(get_current_user),
):
    return await service.get_all(
        page=page,
        limit=limit,
        current_user=current_user,
        is_active=is_active,
    )


# ─── Get by ID ────────────────────────────────────────────────────────────────

@platform_config_router.get("/get-by-id/{config_id}")
async def get_platform_config_by_id(
    config_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await service.get_by_id(config_id, current_user)


# ─── Get by Business Type ID ──────────────────────────────────────────────────

@platform_config_router.get("/get-by-business-type/{business_type_id}")
async def get_platform_config_by_business_type(
    business_type_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await service.get_by_business_type_id(business_type_id, current_user)


# ─── Create (Super Admin Only) ────────────────────────────────────────────────

@platform_config_router.post("/create")
async def create_platform_config(
    request: CreatePlatformConfigRequest,
    current_user: dict = Depends(get_current_user),
):
    return await service.create(request, current_user)


# ─── Update (Super Admin Only) ────────────────────────────────────────────────

@platform_config_router.put("/update/{config_id}")
async def update_platform_config(
    config_id: str,
    request: UpdatePlatformConfigRequest,
    current_user: dict = Depends(get_current_user),
):
    return await service.update(config_id, request, current_user)


# ─── Delete (Super Admin Only) ────────────────────────────────────────────────

@platform_config_router.delete("/remove/{config_id}")
async def delete_platform_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await service.delete(config_id, current_user)
