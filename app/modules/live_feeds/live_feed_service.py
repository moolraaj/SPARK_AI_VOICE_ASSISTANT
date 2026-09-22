from bson import ObjectId
from bson.errors import InvalidId

from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from app.common.tenant.tenant_scope import (
    apply_tenant_filter_by_field,
    validate_resource_ownership,
    require_role,
)
from .live_feed_repository import LiveFeedRepository
from .mapper import live_feed_response
from .schemas.live_feed_schema import (
    CreateLiveFeedRequest,
    UpdateLiveFeedRequest,
)
from app.modules.organizations.organization_repository import OrganizationRepository


class LiveFeedService:

    def __init__(self):
        self.repository = LiveFeedRepository()
        self.org_repository = OrganizationRepository()

    async def _resolve_org_id(
        self, current_user: dict, requested_org_id: str | None = None
    ) -> str:
        """
        Resolves the Organization ID (org_id / organization_id) for a live feed:
          1. If explicitly provided in request body → use it directly
          2. Check if user's JWT/dict has org_id / organization_id / tenant_id
          3. Look up Organization from DB by owner_id
          4. Fallback: use user's own _id
        """
        # 1. Explicit override from request body
        if requested_org_id and requested_org_id.strip():
            return requested_org_id.strip()

        # 2. User token already carries org_id
        org_id = (
            current_user.get("org_id")
            or current_user.get("organization_id")
            or current_user.get("tenant_id")
        )
        if org_id:
            return str(org_id)

        # 3. Look up Organization owned by this user from DB
        user_id = str(current_user.get("_id", ""))
        orgs = await self.org_repository.get_by_owner(user_id, skip=0, limit=1)
        if orgs:
            return str(orgs[0]["_id"])

        # 4. Fallback
        return user_id

    # Backward compatibility helper alias
    async def _resolve_tenant_id(
        self, current_user: dict, requested_tenant_id: str | None = None
    ) -> str:
        return await self._resolve_org_id(current_user, requested_tenant_id)

    # ─── Get All ──────────────────────────────────────────────────────────────

    async def get_all(
        self,
        page: int,
        limit: int,
        current_user: dict,
        feed_type: str | None = None,
        is_active: bool | None = None,
    ):
        skip = (page - 1) * limit

        # Resolve org_id once (only used if not SUPER_ADMIN)
        org_id = await self._resolve_org_id(current_user)

        # Use global helper — adds org_id filter only for non-SUPER_ADMIN
        role = str(current_user.get("role", "")).upper()
        filter_query: dict = {}
        if role != "SUPER_ADMIN":
            filter_query["$or"] = [
                {"org_id": org_id},
                {"organization_id": org_id},
                {"tenant_id": org_id},
            ]

        if feed_type:
            filter_query["type"] = feed_type.lower()

        if is_active is not None:
            filter_query["is_active"] = is_active

        feeds = await self.repository.get_all(skip=skip, limit=limit, query=filter_query)
        total_records = await self.repository.count(query=filter_query)

        return {
            "success": True,
            "data": [live_feed_response(f) for f in feeds],
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit,
            ),
        }

    # ─── Get by ID ────────────────────────────────────────────────────────────

    async def get_by_id(self, feed_id: str, current_user: dict):
        try:
            feed_obj_id = ObjectId(feed_id)
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid feed ID."}

        feed = await self.repository.get_by_id(feed_obj_id)
        if not feed:
            return {"success": False, "message": "Live feed item not found."}

        feed_org_id = str(feed.get("org_id") or feed.get("organization_id") or feed.get("tenant_id", ""))

        # Ownership check using global validator
        if not validate_resource_ownership(feed_org_id, current_user):
            user_org_id = await self._resolve_org_id(current_user)
            if feed_org_id != user_org_id:
                return {"success": False, "message": "You are not authorized to view this live feed."}

        return {
            "success": True,
            "data": live_feed_response(feed),
        }

    # ─── Create (Business Owner Only) ─────────────────────────────────────────

    async def create(self, request: CreateLiveFeedRequest, current_user: dict):
        if not require_role(current_user, "BUSINESS_OWNER", "SUPER_ADMIN", "OWNER"):
            return {
                "success": False,
                "message": "Only business owners are authorized to create live feeds."
            }

        user_id = str(current_user.get("_id", ""))
        org_id = await self._resolve_org_id(current_user, request.org_id)
        now = utc_now()

        new_feed = {
            "org_id": org_id,
            "user_id": user_id,
            "type": request.type.value if hasattr(request.type, "value") else str(request.type),
            "title": request.title.strip(),
            "message": request.message.strip(),
            "valid_from": request.valid_from if request.valid_from is not None else now,
            "valid_until": request.valid_until,
            "is_active": request.is_active,
            **timestamps(),
        }

        inserted_id = await self.repository.create(new_feed)
        created_feed = await self.repository.get_by_id(ObjectId(inserted_id))

        return {
            "success": True,
            "message": "Live feed created successfully.",
            "data": live_feed_response(created_feed) if created_feed else None,
        }

    # ─── Update (Business Owner Only) ─────────────────────────────────────────

    async def update(self, feed_id: str, request: UpdateLiveFeedRequest, current_user: dict):
        if not require_role(current_user, "BUSINESS_OWNER", "SUPER_ADMIN", "OWNER"):
            return {
                "success": False,
                "message": "Only business owners are authorized to update live feeds."
            }

        try:
            feed_obj_id = ObjectId(feed_id)
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid feed ID."}

        existing_feed = await self.repository.get_by_id(feed_obj_id)
        if not existing_feed:
            return {"success": False, "message": "Live feed item not found."}

        feed_org_id = str(existing_feed.get("org_id") or existing_feed.get("organization_id") or existing_feed.get("tenant_id", ""))

        user_org_id = await self._resolve_org_id(current_user)
        if not validate_resource_ownership(feed_org_id, current_user):
            if feed_org_id != user_org_id:
                return {"success": False, "message": "You are not authorized to update this live feed."}

        update_data: dict = {}
        if request.type is not None:
            update_data["type"] = request.type.value if hasattr(request.type, "value") else str(request.type)
        if request.title is not None:
            update_data["title"] = request.title.strip()
        if request.message is not None:
            update_data["message"] = request.message.strip()
        if request.valid_from is not None:
            update_data["valid_from"] = request.valid_from
        if request.valid_until is not None:
            update_data["valid_until"] = request.valid_until
        if request.is_active is not None:
            update_data["is_active"] = request.is_active

        if update_data:
            update_data["updated_at"] = utc_now()
            await self.repository.update(feed_obj_id, update_data)

        updated_feed = await self.repository.get_by_id(feed_obj_id)
        return {
            "success": True,
            "message": "Live feed updated successfully.",
            "data": live_feed_response(updated_feed) if updated_feed else None,
        }

    # ─── Delete (Business Owner Only) ─────────────────────────────────────────

    async def delete(self, feed_id: str, current_user: dict):
        if not require_role(current_user, "BUSINESS_OWNER", "SUPER_ADMIN", "OWNER"):
            return {
                "success": False,
                "message": "Only business owners are authorized to delete live feeds."
            }

        try:
            feed_obj_id = ObjectId(feed_id)
        except (InvalidId, TypeError):
            return {"success": False, "message": "Invalid feed ID."}

        existing_feed = await self.repository.get_by_id(feed_obj_id)
        if not existing_feed:
            return {"success": False, "message": "Live feed item not found."}

        feed_org_id = str(existing_feed.get("org_id") or existing_feed.get("organization_id") or existing_feed.get("tenant_id", ""))

        user_org_id = await self._resolve_org_id(current_user)
        if not validate_resource_ownership(feed_org_id, current_user):
            if feed_org_id != user_org_id:
                return {"success": False, "message": "You are not authorized to delete this live feed."}

        await self.repository.delete(feed_obj_id)

        return {
            "success": True,
            "message": "Live feed deleted successfully."
        }
