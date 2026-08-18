import re
import uuid

from bson import ObjectId
from bson.errors import InvalidId

from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from .organization_repository import OrganizationRepository
from .mapper import organization_response
from .schemas.organization_schema import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
)
from app.modules.auth.repository import AuthRepository


def _generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


from app.common.tenant.tenant_scope import apply_tenant_filter, validate_resource_ownership


class OrganizationService:

    def __init__(self):
        self.repository = OrganizationRepository()
        self.auth_repository = AuthRepository()

    # ─── Admin: Get All (Tenant Isolated) ───────────────────────────────────

    async def get_all(self, page: int, limit: int, current_user: dict):
        skip = (page - 1) * limit
        filter_query = apply_tenant_filter(current_user)
        orgs          = await self.repository.get_all(skip=skip, limit=limit, query=filter_query)
        total_records = await self.repository.count(query=filter_query)

        return {
            "success": True,
            "data": [organization_response(o) for o in orgs],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get My Organizations (owner) ─────────────────────────────────────────

    async def get_my_organizations(self, current_user: dict, page: int, limit: int):
        owner_id = str(current_user["_id"])
        skip = (page - 1) * limit

        orgs = await self.repository.get_by_owner(
            owner_id=owner_id, skip=skip, limit=limit
        )
        total_records = await self.repository.count_by_owner(owner_id)

        return {
            "success": True,
            "data": [organization_response(o) for o in orgs],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get By ID ────────────────────────────────────────────────────────────

    async def get_by_id(self, organization_id: str, current_user: dict):
        try:
            object_id = ObjectId(organization_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.repository.get_by_id(object_id)
        if not org:
            return {"success": False, "message": "Organization not found."}

        if not validate_resource_ownership(org.get("owner_id"), current_user):
            return {"success": False, "message": "You are not authorized to access this organization."}

        return {"success": True, "data": organization_response(org)}

    # ─── Create ───────────────────────────────────────────────────────────────

    async def create(self, request: CreateOrganizationRequest, current_user: dict):

        # ── Block SUPER_ADMIN from creating organizations ──────────────────────
        if current_user["role"] == "SUPER_ADMIN":
            return {
                "success": False,
                "message": "Super admin cannot create organizations."
            }

        owner_id = str(current_user["_id"])

        # Generate unique slug
        base_slug = _generate_slug(request.name)
        slug = base_slug
        counter = 1
        while await self.repository.get_by_slug(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Auto-generate unique tenant_id for this org
        tenant_id = f"TENANT_{uuid.uuid4()}"

        address_data = request.address.model_dump() if request.address else None

        data = {
            "owner_id": owner_id,
            "business_platform_id": request.business_platform_id,
            "tenant_id": tenant_id,
            "name": request.name,
            "slug": slug,
            "description": request.description,
            "logo_url": None,
            "website": request.website,
            "phone": request.phone,
            "email": request.email,
            "address": address_data,
            "is_active": True,
            **timestamps(),
        }

        org_id = await self.repository.create(data)

        # ── Auto-upgrade role: CUSTOMER → BUSINESS_OWNER (first org only) ───────
        if current_user["role"] == "CUSTOMER":
            await self.auth_repository.update_user(
                object_id=current_user["_id"],
                update_data={
                    "role": "BUSINESS_OWNER",
                    "updated_at": utc_now(),
                },
            )

        return {
            "success": True,
            "message": "Organization created successfully.",
            "data": {
                "id": org_id,
                "owner_id": owner_id,
                "tenant_id": tenant_id,
                "name": request.name,
                "slug": slug,
                "business_platform_id": request.business_platform_id,
            },
        }

    # ─── Update ───────────────────────────────────────────────────────────────

    async def update(
        self,
        organization_id: str,
        request: UpdateOrganizationRequest,
        current_user: dict,
    ):
        try:
            object_id = ObjectId(organization_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.repository.get_by_id(object_id)
        if not org:
            return {"success": False, "message": "Organization not found."}

        # Only owner can update
        if org["owner_id"] != str(current_user["_id"]):
            return {"success": False, "message": "You are not authorized to update this organization."}

        update_data = request.model_dump(exclude_none=True)

        if not update_data:
            return {"success": False, "message": "No fields provided to update."}

        # If name is being changed, regenerate slug
        if "name" in update_data:
            base_slug = _generate_slug(update_data["name"])
            slug = base_slug
            counter = 1
            while await self.repository.get_by_slug_excluding(slug, object_id):
                slug = f"{base_slug}-{counter}"
                counter += 1
            update_data["slug"] = slug

        update_data["updated_at"] = utc_now()
        await self.repository.update(object_id, update_data)
        updated = await self.repository.get_by_id(object_id)

        return {
            "success": True,
            "message": "Organization updated successfully.",
            "data": organization_response(updated),
        }

    # ─── Delete ───────────────────────────────────────────────────────────────

    async def delete(self, organization_id: str, current_user: dict):
        try:
            object_id = ObjectId(organization_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.repository.get_by_id(object_id)
        if not org:
            return {"success": False, "message": "Organization not found."}

        # Only owner can delete
        if org["owner_id"] != str(current_user["_id"]):
            return {"success": False, "message": "You are not authorized to delete this organization."}

        result = await self.repository.delete(object_id)

        if result is None or result.deleted_count == 0:
            return {"success": False, "message": "Organization could not be deleted."}

        return {"success": True, "message": "Organization deleted successfully."}
