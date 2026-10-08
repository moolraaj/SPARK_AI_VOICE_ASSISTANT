from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.organization_schema import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
    LinkDeviceRequest,
)
from .organization_service import OrganizationService


service = OrganizationService()

# Plural — list routes
organizations_router = APIRouter(prefix="/organizations", tags=["Organizations"])

# Singular — resource routes
organization_router = APIRouter(prefix="/organization", tags=["Organization"])

# Device management routes (hardware SPARK devices)
devices_router = APIRouter(prefix="/devices", tags=["Hardware Devices"])


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


# ══════════════════════════════════════════════════════════════════════════════
# HARDWARE DEVICE APIs
# ══════════════════════════════════════════════════════════════════════════════

# ─── List All Seen Devices ────────────────────────────────────────────────────

@devices_router.get("")
async def get_all_devices(
    current_user = Depends(get_current_user),
):
    """
    List all SPARK hardware devices seen by the system.

    - **SUPER_ADMIN**: sees every device
    - **BUSINESS_OWNER**: sees devices linked to their own orgs + any unregistered
    
    Each device shows:
    - `device_id` — the hardware ID (e.g. SPARK-F89A4E40C86C)
    - `status` — `registered` | `unregistered`
    - `org_id` — which org it's linked to (null if unregistered)
    - `first_seen`, `last_seen`, `linked_at`
    """
    return await service.get_all_devices(current_user)


# ─── Link Device to Org ───────────────────────────────────────────────────────

@organization_router.post("/link-device/{organization_id}")
async def link_device_to_org(
    organization_id: str,
    request: LinkDeviceRequest,
    current_user = Depends(get_current_user),
):
    """
    **Link a SPARK hardware device to an organization.**

    Call this once from your dashboard after the device appears in `GET /devices`.

    - `organization_id` — your org's MongoDB `_id`
    - `device_id` — the device ID shown in the device list (e.g. `SPARK-F89A4E40C86C`)

    After linking, the device will be able to route calls to this org automatically.
    """
    return await service.link_device(organization_id, request, current_user)


# ─── Unlink Device from Org ───────────────────────────────────────────────────

@organization_router.delete("/unlink-device/{organization_id}")
async def unlink_device_from_org(
    organization_id: str,
    current_user = Depends(get_current_user),
):
    """
    **Unlink the currently linked SPARK hardware device from an organization.**

    After this, calls from that device will fail to resolve until re-linked.
    """
    return await service.unlink_device(organization_id, current_user)
