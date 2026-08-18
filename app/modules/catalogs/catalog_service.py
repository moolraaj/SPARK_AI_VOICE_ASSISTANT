from app.core.datetime import timestamps, utc_now
from app.common.pagination.pagination import pagination_response
from .catalog_repository import CatalogRepository
from .schemas.catalog_schema import (
    CreateCategoryRequest,
    UpdateCategoryRequest,
    CreateCatalogItemRequest,
    UpdateCatalogItemRequest,
)
from app.rag.vectorstore.qdrant_store import qdrant_store


class CatalogService:

    def __init__(self):
        self.repository = CatalogRepository()

    # ── Upload Confirm & Bulk Save ───────────────────────────────────────────

    async def confirm_and_save(
        self,
        owner_id: str,
        document_id: str,
        preview_data: dict
    ) -> dict:
        """
        Takes preview data from Redis (categories + items),
        saves to MongoDB catalog_categories + catalog_items,
        embeds + upserts into Qdrant,
        and returns a summary.
        """
        raw_items: list[dict] = preview_data.get("items", [])
        if not raw_items:
            return {"success": False, "message": "No items found in preview data."}

        # Step 1: Collect unique categories in order
        seen_cats: dict[str, int] = {}
        for item in raw_items:
            cat = item.get("category", "General")
            if cat not in seen_cats:
                seen_cats[cat] = len(seen_cats) + 1

        # Step 2: Upsert categories -> get _id map
        cat_id_map: dict[str, str] = {}
        for cat_name, order in seen_cats.items():
            cat_id = await self.repository.upsert_category(
                owner_id=owner_id,
                document_id=document_id,
                name=cat_name,
                display_order=order
            )
            cat_id_map[cat_name] = cat_id

        # Step 3: Build item documents for MongoDB
        now = utc_now()
        mongo_items = []
        for item in raw_items:
            name = str(item.get("item_name", "")).strip()
            if not name:
                continue
            cat = item.get("category", "General")
            cat_id = cat_id_map.get(cat, "")

            raw_price = item.get("price", 0)
            try:
                price = float(raw_price) if "." in str(raw_price) else int(raw_price)
            except Exception:
                price = 0

            mongo_items.append({
                "owner_id": owner_id,
                "document_id": document_id,
                "category_id": cat_id,
                "item_name": name,
                "price": price,
                "is_veg": item.get("is_veg", True),
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
            })

        # Step 4: Bulk insert items into MongoDB
        inserted_ids = await self.repository.insert_items_bulk(mongo_items)

        # Step 5: Upsert into Qdrant (embed each item)
        qdrant_items = []
        for i, item_doc in enumerate(mongo_items):
            qdrant_items.append({
                "mongo_id": inserted_ids[i],
                "item_name": item_doc["item_name"],
                "category": next(
                    (name for name, cid in cat_id_map.items() if cid == item_doc["category_id"]),
                    "General"
                ),
                "category_id": item_doc["category_id"],
                "price": item_doc["price"],
                "is_veg": item_doc["is_veg"],
            })

        vectors_saved = await qdrant_store.upsert_items(
            owner_id=owner_id,
            document_id=document_id,
            items=qdrant_items
        )

        return {
            "success": True,
            "message": "Catalog saved to database and vector store successfully.",
            "data": {
                "categories_saved": len(cat_id_map),
                "items_saved": len(inserted_ids),
                "vectors_saved": vectors_saved,
                "category_map": {name: cid for name, cid in cat_id_map.items()},
            }
        }

    # ── Category CRUD ────────────────────────────────────────────────────────

    async def get_categories_by_owner_id(self, owner_id: str) -> dict:
        categories = await self.repository.get_categories_by_owner(owner_id)
        return {
            "success": True,
            "message": "Categories fetched successfully.",
            "data": categories
        }

    async def get_my_categories(self, current_user: dict, owner_id: str | None = None) -> dict:
        user_id = str(current_user["_id"])
        user_role = current_user.get("role", "OWNER")

        if owner_id and owner_id != user_id and user_role != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to view another owner's categories."}

        target_owner_id = owner_id if owner_id else user_id
        return await self.get_categories_by_owner_id(target_owner_id)

    async def create_category(self, request: CreateCategoryRequest, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        data = {
            "owner_id": owner_id,
            "name": request.name.strip(),
            "display_order": request.display_order or 0,
        }
        cat_id = await self.repository.create_category(data)
        data["id"] = cat_id
        return {
            "success": True,
            "message": "Category created successfully.",
            "data": data
        }

    async def update_category(self, cat_id: str, request: UpdateCategoryRequest, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        category = await self.repository.get_category_by_id(cat_id)
        if not category:
            return {"success": False, "message": "Category not found."}

        if category.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to edit this category."}

        update_data = {k: v for k, v in request.model_dump().items() if v is not None}
        if "name" in update_data:
            update_data["name"] = update_data["name"].strip()

        await self.repository.update_category(cat_id, update_data)
        return {
            "success": True,
            "message": "Category updated successfully.",
            "data": {"id": cat_id, **update_data}
        }

    async def delete_category(self, cat_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        category = await self.repository.get_category_by_id(cat_id)
        if not category:
            return {"success": False, "message": "Category not found."}

        if category.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to delete this category."}

        await self.repository.delete_category(cat_id)
        return {"success": True, "message": "Category deleted successfully."}

    # ── Catalog Item CRUD ───────────────────────────────────────────────────

    async def get_items_by_owner_id(self, owner_id: str, category_id: str | None, page: int, limit: int) -> dict:
        skip = (page - 1) * limit
        items = await self.repository.get_items_by_owner(
            owner_id=owner_id,
            category_id=category_id,
            skip=skip,
            limit=limit
        )
        total_records = await self.repository.count_items_by_owner(owner_id=owner_id, category_id=category_id)

        return {
            "success": True,
            "data": items,
            "pagination": pagination_response(
                total_records=total_records,
                page=page,
                limit=limit
            )
        }

    async def get_my_items(self, current_user: dict, category_id: str | None, page: int, limit: int, owner_id: str | None = None) -> dict:
        user_id = str(current_user["_id"])
        user_role = current_user.get("role", "OWNER")

        if owner_id and owner_id != user_id and user_role != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to view another owner's catalog items."}

        target_owner_id = owner_id if owner_id else user_id
        return await self.get_items_by_owner_id(owner_id=target_owner_id, category_id=category_id, page=page, limit=limit)

    async def get_item_by_id_public(self, item_id: str) -> dict:
        item = await self.repository.get_item_by_id(item_id)
        if not item:
            return {"success": False, "message": "Catalog item not found."}

        return {
            "success": True,
            "data": {
                "id": str(item["_id"]),
                "owner_id": item.get("owner_id"),
                "document_id": item.get("document_id"),
                "category_id": item.get("category_id"),
                "item_name": item.get("item_name"),
                "price": item.get("price"),
                "is_veg": item.get("is_veg", True),
                "description": item.get("description"),
                "status": item.get("status", "ACTIVE"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        }

    async def get_item_by_id(self, item_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        item = await self.repository.get_item_by_id(item_id)
        if not item:
            return {"success": False, "message": "Catalog item not found."}

        if item.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to view this item."}

        return await self.get_item_by_id_public(item_id)

        return {
            "success": True,
            "data": {
                "id": str(item["_id"]),
                "owner_id": item.get("owner_id"),
                "document_id": item.get("document_id"),
                "category_id": item.get("category_id"),
                "item_name": item.get("item_name"),
                "price": item.get("price"),
                "is_veg": item.get("is_veg", True),
                "description": item.get("description"),
                "status": item.get("status", "ACTIVE"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        }

    async def create_item(self, request: CreateCatalogItemRequest, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])

        category = await self.repository.get_category_by_id(request.category_id)
        if not category:
            return {"success": False, "message": "Category not found."}

        doc_data = {
            "owner_id": owner_id,
            "category_id": request.category_id,
            "item_name": request.item_name.strip(),
            "price": request.price,
            "is_veg": request.is_veg if request.is_veg is not None else True,
            "description": request.description.strip() if request.description else None,
            "status": "ACTIVE"
        }

        mongo_id = await self.repository.create_item(doc_data)

        # Sync vector to Qdrant automatically
        try:
            await qdrant_store.upsert_items(
                owner_id=owner_id,
                document_id="manual_entry",
                items=[{
                    "mongo_id": mongo_id,
                    "item_name": doc_data["item_name"],
                    "category": category.get("name", "General"),
                    "category_id": doc_data["category_id"],
                    "price": doc_data["price"],
                    "is_veg": doc_data["is_veg"],
                }]
            )
        except Exception as e:
            print(f"⚠️  Qdrant sync warning on catalog item create: {e}")

        doc_data["id"] = mongo_id
        return {
            "success": True,
            "message": "Catalog item created and synced to Vector DB successfully.",
            "data": doc_data
        }

    async def update_item(self, item_id: str, request: UpdateCatalogItemRequest, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        item = await self.repository.get_item_by_id(item_id)
        if not item:
            return {"success": False, "message": "Catalog item not found."}

        if item.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to edit this item."}

        update_data = {k: v for k, v in request.model_dump().items() if v is not None}
        if "item_name" in update_data:
            update_data["item_name"] = update_data["item_name"].strip()
        if "description" in update_data and update_data["description"]:
            update_data["description"] = update_data["description"].strip()

        await self.repository.update_item(item_id, update_data)

        # Re-fetch category and sync updated item to Qdrant vector store
        try:
            merged_item = {**item, **update_data}
            cat = await self.repository.get_category_by_id(merged_item["category_id"])
            cat_name = cat.get("name", "General") if cat else "General"

            await qdrant_store.upsert_items(
                owner_id=owner_id,
                document_id=merged_item.get("document_id", "manual_entry"),
                items=[{
                    "mongo_id": item_id,
                    "item_name": merged_item.get("item_name", ""),
                    "category": cat_name,
                    "category_id": merged_item.get("category_id", ""),
                    "price": merged_item.get("price", 0),
                    "is_veg": merged_item.get("is_veg", True),
                }]
            )
        except Exception as e:
            print(f"⚠️  Qdrant sync warning on catalog item update: {e}")

        return {
            "success": True,
            "message": "Catalog item updated and vector store synced successfully.",
            "data": {"id": item_id, **update_data}
        }

    async def delete_item(self, item_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        item = await self.repository.get_item_by_id(item_id)
        if not item:
            return {"success": False, "message": "Catalog item not found."}

        if item.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to delete this item."}

        await self.repository.delete_item(item_id)

        # Delete point from Qdrant vector store
        try:
            if qdrant_store.client:
                from qdrant_client.models import PointIdsList
                await qdrant_store.client.delete(
                    collection_name="catalog_items",
                    points_selector=PointIdsList(points=[item_id])
                )
        except Exception as e:
            print(f"⚠️  Qdrant vector point delete warning: {e}")

        return {"success": True, "message": "Catalog item deleted successfully."}
