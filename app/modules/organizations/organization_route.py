from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.organization_schema import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
)
from .organization_service import OrganizationService


service = OrganizationService()

# Plural — list routes
organizations_router = APIRouter(prefix="/organizations", tags=["Organizations"])

# Singular — resource routes
organization_router = APIRouter(prefix="/organization", tags=["Organization"])


# ─── Admin: All Organizations ─────────────────────────────────────────────────

@organizations_router.get("")
async def get_all_organizations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user = Depends(get_current_user),
):
    return await service.get_all(page, limit, current_user)


# ─── Owner: My Organizations ──────────────────────────────────────────────────

@organizations_router.get("/my")
async def get_my_organizations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user = Depends(get_current_user),
):
    return await service.get_my_organizations(current_user, page, limit)


# ─── Get By ID ────────────────────────────────────────────────────────────────

@organization_router.get("/get-by-id/{organization_id}")
async def get_organization_by_id(
    organization_id: str,
    current_user = Depends(get_current_user),
):
    return await service.get_by_id(organization_id, current_user)


# ─── Create ───────────────────────────────────────────────────────────────────

@organization_router.post("/create")
async def create_organization(
    request: CreateOrganizationRequest,
    current_user = Depends(get_current_user),
):
    return await service.create(request, current_user)


# ─── Update ───────────────────────────────────────────────────────────────────

@organization_router.put("/update/{organization_id}")
async def update_organization(
    organization_id: str,
    request: UpdateOrganizationRequest,
    current_user = Depends(get_current_user),
):
    return await service.update(organization_id, request, current_user)


# ─── Delete ───────────────────────────────────────────────────────────────────

@organization_router.delete("/remove/{organization_id}")
async def delete_organization(
    organization_id: str,
    current_user = Depends(get_current_user),
):
    return await service.delete(organization_id, current_user)
