from bson import ObjectId
from bson.errors import InvalidId
from app.database.mongodb import mongodb
from app.core.datetime import utc_now


class CatalogRepository:

    @property
    def categories(self):
        return mongodb.database["catalog_categories"]

    @property
    def items(self):
        return mongodb.database["catalog_items"]

    # ── Categories ───────────────────────────────────────────────────────────

    async def create_category(self, data: dict) -> str:
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        data["status"] = data.get("status", "ACTIVE")
        result = await self.categories.insert_one(data)
        return str(result.inserted_id)

    async def upsert_category(self, owner_id: str, document_id: str, name: str, display_order: int) -> str:
        """
        Insert or update a category by (owner_id, name).
        Returns the MongoDB _id as string.
        """
        result = await self.categories.find_one_and_update(
            {"owner_id": owner_id, "name": name},
            {
                "$set": {
                    "document_id": document_id,
                    "display_order": display_order,
                    "status": "ACTIVE",
                    "updated_at": utc_now(),
                },
                "$setOnInsert": {
                    "owner_id": owner_id,
                    "name": name,
                    "created_at": utc_now(),
                },
            },
            upsert=True,
            return_document=True,
        )
        return str(result["_id"])

    async def get_categories_by_owner(self, owner_id: str) -> list[dict]:
        docs = await self.categories.find(
            {"owner_id": owner_id, "status": "ACTIVE"}
        ).sort("display_order", 1).to_list(length=200)
        return [
            {
                "id": str(d["_id"]),
                "owner_id": d.get("owner_id"),
                "document_id": d.get("document_id"),
                "name": d["name"],
                "display_order": d.get("display_order", 0),
                "status": d.get("status", "ACTIVE"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
            for d in docs
        ]

    async def get_category_by_id(self, cat_id: str) -> dict | None:
        try:
            return await self.categories.find_one({"_id": ObjectId(cat_id)})
        except (InvalidId, TypeError):
            return None

    async def update_category(self, cat_id: str, update_data: dict):
        update_data["updated_at"] = utc_now()
        try:
            return await self.categories.update_one(
                {"_id": ObjectId(cat_id)},
                {"$set": update_data}
            )
        except (InvalidId, TypeError):
            return None

    async def delete_category(self, cat_id: str):
        try:
            return await self.categories.delete_one({"_id": ObjectId(cat_id)})
        except (InvalidId, TypeError):
            return None

    # ── Catalog Items ────────────────────────────────────────────────────────

    async def create_item(self, data: dict) -> str:
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        data["status"] = data.get("status", "ACTIVE")
        result = await self.items.insert_one(data)
        return str(result.inserted_id)

    async def insert_items_bulk(self, items: list[dict]) -> list[str]:
        """
        Bulk insert catalog items. Returns list of inserted _id strings.
        """
        if not items:
            return []
        result = await self.items.insert_many(items)
        return [str(oid) for oid in result.inserted_ids]

    async def get_items_by_owner(
        self,
        owner_id: str,
        category_id: str | None = None,
        skip: int = 0,
        limit: int = 100
    ) -> list[dict]:
        query = {"owner_id": owner_id, "status": "ACTIVE"}
        if category_id:
            query["category_id"] = category_id
        docs = await self.items.find(query).sort("category_id", 1).skip(skip).limit(limit).to_list(length=limit)
        return [
            {
                "id": str(d["_id"]),
                "owner_id": d.get("owner_id"),
                "document_id": d.get("document_id"),
                "category_id": d.get("category_id"),
                "item_name": d.get("item_name"),
                "price": d.get("price"),
                "is_veg": d.get("is_veg", True),
                "description": d.get("description"),
                "status": d.get("status", "ACTIVE"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
            for d in docs
        ]

    async def count_items_by_owner(self, owner_id: str, category_id: str | None = None) -> int:
        query = {"owner_id": owner_id, "status": "ACTIVE"}
        if category_id:
            query["category_id"] = category_id
        return await self.items.count_documents(query)

    async def get_item_by_id(self, item_id: str) -> dict | None:
        try:
            return await self.items.find_one({"_id": ObjectId(item_id)})
        except (InvalidId, TypeError):
            return None

    async def update_item(self, item_id: str, update_data: dict):
        update_data["updated_at"] = utc_now()
        try:
            return await self.items.update_one(
                {"_id": ObjectId(item_id)},
                {"$set": update_data}
            )
        except (InvalidId, TypeError):
            return None

    async def delete_item(self, item_id: str):
        try:
            return await self.items.delete_one({"_id": ObjectId(item_id)})
        except (InvalidId, TypeError):
            return None

    async def delete_items_by_document(self, owner_id: str, document_id: str) -> int:
        result = await self.items.delete_many({"owner_id": owner_id, "document_id": document_id})
        return result.deleted_count

    async def get_item_by_name(
        self,
        owner_id: str,
        item_name: str,
    ) -> dict | None:

        if not owner_id or not item_name:
            return None

        return await self.items.find_one(
            {
                "owner_id": owner_id,
                "item_name": {
                    "$regex": f"^{item_name.strip()}$",
                    "$options": "i",
                },
                "status": "ACTIVE",
            }
        )

    async def get_items_by_category(
        self,
        owner_id: str,
        category_id: str,
    ) -> list[dict]:

        if not owner_id or not category_id:
            return []

        docs = await self.items.find(
            {
                "owner_id": owner_id,
                "category_id": category_id,
                "status": "ACTIVE",
            }
        ).sort(
            "item_name",
            1
        ).to_list(length=200)

        return [
            {
                "id": str(d["_id"]),
                "owner_id": d.get("owner_id"),
                "document_id": d.get("document_id"),
                "category_id": d.get("category_id"),
                "item_name": d.get("item_name"),
                "price": d.get("price"),
                "is_veg": d.get("is_veg", True),
                "description": d.get("description"),
                "status": d.get("status", "ACTIVE"),
            }
            for d in docs
        ]

    async def get_category_by_name(
        self,
        owner_id: str,
        category_name: str,
    ) -> dict | None:

        if not owner_id or not category_name:
            return None

        return await self.categories.find_one(
            {
                "owner_id": owner_id,
                "name": {
                    "$regex": f"^{category_name.strip()}$",
                    "$options": "i",
                },
                "status": "ACTIVE",
            }
        )