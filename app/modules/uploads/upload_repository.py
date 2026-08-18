from bson import ObjectId
from bson.errors import InvalidId
from app.database.mongodb import mongodb


class UploadRepository:

    @property
    def collection(self):
        return mongodb.database["uploaded_documents"]

    @property
    def organizations_collection(self):
        return mongodb.database["organizations"]

    @property
    def business_platforms_collection(self):
        return mongodb.database["business_platforms"]

    @property
    def business_types_collection(self):
        return mongodb.database["business_types"]

    async def get_business_type_for_owner(self, owner_id: str) -> tuple[str | None, str | None]:
        """
        Auto-resolves the owner's Business Type ID and Name by looking up
        their Organization -> BusinessPlatform -> BusinessType.
        Returns (None, None) if the owner has no registered organization or business type.
        """
        try:
            org = await self.organizations_collection.find_one({"owner_id": owner_id})
            if not org or "business_platform_id" not in org:
                return None, None

            bp_id = org["business_platform_id"]
            try:
                bp_obj_id = ObjectId(bp_id)
                bp = await self.business_platforms_collection.find_one({"_id": bp_obj_id})
            except Exception:
                bp = await self.business_platforms_collection.find_one({"_id": bp_id})

            if not bp or "business_type_id" not in bp:
                return None, None

            bt_id = bp["business_type_id"]
            try:
                bt_obj_id = ObjectId(bt_id)
                bt = await self.business_types_collection.find_one({"_id": bt_obj_id})
            except Exception:
                bt = await self.business_types_collection.find_one({"_id": bt_id})

            if bt and "name" in bt:
                return str(bt.get("_id", bt_id)), bt["name"]

            return None, None

        except Exception:
            return None, None

    async def create(self, data: dict) -> str:
        result = await self.collection.insert_one(data)
        return str(result.inserted_id)

    async def get_by_id(self, doc_id: str) -> dict | None:
        """Fetch a document by its MongoDB _id."""
        try:
            return await self.collection.find_one({"_id": ObjectId(doc_id)})
        except (InvalidId, TypeError):
            return None

    async def update(self, doc_id: str, update_data: dict):
        """Update a document by its MongoDB _id."""
        try:
            return await self.collection.update_one(
                {"_id": ObjectId(doc_id)},
                {"$set": update_data}
            )
        except (InvalidId, TypeError):
            return None

    async def get_by_owner(self, owner_id: str, skip: int = 0, limit: int = 10):
        return (
            await self.collection
            .find({"owner_id": owner_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )

    async def count_by_owner(self, owner_id: str) -> int:
        return await self.collection.count_documents({"owner_id": owner_id})

    async def delete(self, doc_id: str):
        """Delete a document by its MongoDB _id."""
        try:
            return await self.collection.delete_one({"_id": ObjectId(doc_id)})
        except (InvalidId, TypeError):
            return None
