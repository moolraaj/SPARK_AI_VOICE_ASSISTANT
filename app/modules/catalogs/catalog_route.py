from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.catalog_schema import (
    CreateCategoryRequest,
    UpdateCategoryRequest,
    CreateCatalogItemRequest,
    UpdateCatalogItemRequest,
)
from .catalog_service import CatalogService


service = CatalogService()

# ── Router Definitions ───────────────────────────────────────────────────────

catalog_categories_router = APIRouter(prefix="/catalog-categories", tags=["Catalog Categories"])
catalog_category_router   = APIRouter(prefix="/catalog-category", tags=["Catalog Category"])

catalog_items_router = APIRouter(prefix="/catalog-items", tags=["Catalog Items"])
catalog_item_router  = APIRouter(prefix="/catalog-item", tags=["Catalog Item"])


# ─── Category Routes ─────────────────────────────────────────────────────────

@catalog_categories_router.get("/my-categories")
async def get_my_categories(
    owner_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get catalog categories for the logged-in owner (or specified owner_id for Super Admin).
    """
    return await service.get_my_categories(current_user=current_user, owner_id=owner_id)


@catalog_category_router.post("/create")
async def create_category(
    request: CreateCategoryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Create a new catalog category (Only Owner).
    """
    return await service.create_category(request, current_user)


@catalog_category_router.put("/update/{cat_id}")
async def update_category(
    cat_id: str,
    request: UpdateCategoryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Update an existing catalog category (Only Owner).
    """
    return await service.update_category(cat_id, request, current_user)


@catalog_category_router.delete("/remove/{cat_id}")
async def delete_category(
    cat_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Delete a catalog category (Only Owner).
    """
    return await service.delete_category(cat_id, current_user)


# ─── Catalog Item Routes ─────────────────────────────────────────────────────

@catalog_items_router.get("/my-items")
async def get_my_catalog_items(
    owner_id: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get catalog items for the logged-in owner (or specified owner_id for Super Admin).
    """
    return await service.get_my_items(current_user=current_user, owner_id=owner_id, category_id=category_id, page=page, limit=limit)


@catalog_item_router.post("/create")
async def create_catalog_item(
    request: CreateCatalogItemRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Create a new catalog item (Only Owner). Auto-syncs to Qdrant vector DB.
    """
    return await service.create_item(request, current_user)


@catalog_item_router.get("/get-by-id/{item_id}")
async def get_catalog_item_by_id(
    item_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get single catalog item by its MongoDB _id.
    """
    return await service.get_item_by_id(item_id, current_user)


@catalog_item_router.put("/update/{item_id}")
async def update_catalog_item(
    item_id: str,
    request: UpdateCatalogItemRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Update a catalog item (Only Owner). Auto-syncs to Qdrant vector DB.
    """
    return await service.update_item(item_id, request, current_user)


@catalog_item_router.delete("/remove/{item_id}")
async def delete_catalog_item(
    item_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Delete a catalog item (Only Owner). Removes vector from Qdrant.
    """
    return await service.delete_item(item_id, current_user)
