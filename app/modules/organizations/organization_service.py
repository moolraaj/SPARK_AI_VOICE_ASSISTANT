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
    LinkDeviceRequest,
    UnlinkDeviceRequest,
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
            "business_type_id": request.business_type_id,
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
                "business_type_id": request.business_type_id,
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

    # ─── Link Hardware Device to Org ──────────────────────────────────────────

    async def link_device(
        self,
        organization_id: str,
        request: LinkDeviceRequest,
        current_user: dict,
    ):
        """
        Link a hardware device_id to an organization.

        Rules:
        - Only the org owner (or SUPER_ADMIN) can link a device.
        - If device_id is already linked to ANOTHER org, return an error.
        - Saves device_id in org.hardware_device_id AND updates spark_devices
          collection status → 'registered'.
        """
        try:
            object_id = ObjectId(organization_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.repository.get_by_id(object_id)
        if not org:
            return {"success": False, "message": "Organization not found."}

        # Ownership check
        if not validate_resource_ownership(org.get("owner_id"), current_user):
            return {"success": False, "message": "You are not authorized to manage this organization."}

        # Check: does THIS org ALREADY have a hardware device assigned?
        current_linked_device = org.get("hardware_device_id")
        if current_linked_device and current_linked_device != request.device_id:
            return {
                "success": False,
                "message": (
                    f"Organization '{org.get('name')}' already has device '{current_linked_device}' linked. "
                    "Only 1 device can be assigned per organization. Please unlink the existing device first."
                ),
            }

        # Check: is this device_id already linked to a DIFFERENT org?
        existing_org = await self.repository.get_by_device_id(request.device_id)
        if existing_org and str(existing_org["_id"]) != organization_id:
            return {
                "success": False,
                "message": (
                    f"Device '{request.device_id}' is already linked to org "
                    f"'{existing_org.get('name', 'unknown')}'. "
                    "Unlink it from that org first."
                ),
            }

        # Save device_id on org
        await self.repository.update(
            object_id,
            {"hardware_device_id": request.device_id, "updated_at": utc_now()},
        )

        # Update spark_devices collection: mark as registered
        from app.database.mongodb import mongodb
        await mongodb.database["spark_devices"].update_one(
            {"device_id": request.device_id},
            {"$set": {
                "status": "registered",
                "org_id": organization_id,
                "linked_at": utc_now(),
            }},
            upsert=True,
        )

        return {
            "success": True,
            "message": f"Device '{request.device_id}' successfully linked to org '{org.get('name')}'.",
            "data": {
                "org_id": organization_id,
                "org_name": org.get("name"),
                "device_id": request.device_id,
            },
        }

    # ─── Unlink Hardware Device from Org ──────────────────────────────────────

    async def unlink_device(
        self,
        organization_id: str,
        current_user: dict,
    ):
        """
        Remove the hardware_device_id from an organization (unlink device).
        """
        try:
            object_id = ObjectId(organization_id)
        except InvalidId:
            return {"success": False, "message": "Invalid organization id."}

        org = await self.repository.get_by_id(object_id)
        if not org:
            return {"success": False, "message": "Organization not found."}

        if not validate_resource_ownership(org.get("owner_id"), current_user):
            return {"success": False, "message": "You are not authorized to manage this organization."}

        device_id = org.get("hardware_device_id")
        if not device_id:
            return {"success": False, "message": "No device is linked to this organization."}

        # Remove from org
        await self.repository.update(
            object_id,
            {"hardware_device_id": None, "updated_at": utc_now()},
        )

        # Update spark_devices collection: mark as unregistered
        from app.database.mongodb import mongodb
        await mongodb.database["spark_devices"].update_one(
            {"device_id": device_id},
            {"$set": {"status": "unregistered", "org_id": None}},
        )

        return {
            "success": True,
            "message": f"Device '{device_id}' unlinked from org '{org.get('name')}'.",
        }

    # ─── List All Unregistered Spark Devices ──────────────────────────────────

    async def get_all_devices(self, current_user: dict):
        """
        Return all devices seen in spark_devices collection.
        SUPER_ADMIN sees all. BUSINESS_OWNER sees only devices linked to their orgs.
        """
        from app.database.mongodb import mongodb

        role = str(current_user.get("role", "")).upper()

        if role == "SUPER_ADMIN":
            devices = await mongodb.database["spark_devices"].find({}).to_list(length=None)
        else:
            # Get all org_ids this owner has
            owner_id = str(current_user["_id"])
            owner_orgs = await self.repository.get_all_by_owner(owner_id)
            owner_org_ids = [str(o["_id"]) for o in owner_orgs]

            # Devices linked to their orgs OR unregistered (status=unregistered shows to admin)
            devices = await mongodb.database["spark_devices"].find(
                {"org_id": {"$in": owner_org_ids + [None]}}
            ).to_list(length=None)

        result = []
        for d in devices:
            result.append({
                "device_id":   d.get("device_id"),
                "status":      d.get("status", "unregistered"),
                "org_id":      d.get("org_id"),
                "first_seen":  d.get("first_seen"),
                "last_seen":   d.get("last_seen"),
                "linked_at":   d.get("linked_at"),
            })

        return {"success": True, "data": result, "total": len(result)}
