from typing import Optional
from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.live_feed_schema import (
    CreateLiveFeedRequest,
    UpdateLiveFeedRequest,
)
from .live_feed_service import LiveFeedService


service = LiveFeedService()

# Plural — list routes
live_feeds_router = APIRouter(prefix="/live-feeds", tags=["Live Feeds"])

# Singular — item routes
live_feed_router = APIRouter(prefix="/live-feed", tags=["Live Feed"])


# ─── Get All Live Feeds ────────────────────────────────────────────────────────

@live_feeds_router.get("")
async def get_all_live_feeds(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    type: Optional[str] = Query(default=None, description="Filter by feed type: 'general' or 'special'"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    current_user: dict = Depends(get_current_user),
):
    return await service.get_all(
        page=page,
        limit=limit,
        current_user=current_user,
        feed_type=type,
        is_active=is_active,
    )


# ─── Get by ID ────────────────────────────────────────────────────────────────

@live_feed_router.get("/get-by-id/{feed_id}")
async def get_live_feed_by_id(
    feed_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await service.get_by_id(feed_id, current_user)


# ─── Create (Business Owner Only) ─────────────────────────────────────────────

@live_feed_router.post("/create")
async def create_live_feed(
    request: CreateLiveFeedRequest,
    current_user: dict = Depends(get_current_user),
):
    return await service.create(request, current_user)


# ─── Update (Business Owner Only) ─────────────────────────────────────────────

@live_feed_router.put("/update/{feed_id}")
async def update_live_feed(
    feed_id: str,
    request: UpdateLiveFeedRequest,
    current_user: dict = Depends(get_current_user),
):
    return await service.update(feed_id, request, current_user)


# ─── Delete (Business Owner Only) ─────────────────────────────────────────────

@live_feed_router.delete("/remove/{feed_id}")
async def delete_live_feed(
    feed_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await service.delete(feed_id, current_user)
