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

    async def get_business_type_for_owner(self, owner_id: str, user_role: str = "BUSINESS_OWNER") -> tuple[str, str]:
        """
        Auto-resolves the owner's Business Type ID and Name by looking up:
        1. Organization owned by owner_id -> direct business_type_id or business_platform.
        2. Fallback to any organization or default BusinessType for SUPER_ADMIN or new owners.
        """
        try:
            # 1. Look for Organization owned by owner_id
            org = await self.organizations_collection.find_one({"owner_id": owner_id})

            # If org not found, check if SUPER_ADMIN or pick first existing org as fallback
            if not org:
                org = await self.organizations_collection.find_one()

            # 2. Check direct business_type_id on org
            if org and org.get("business_type_id"):
                bt_id = org["business_type_id"]
                try:
                    bt_obj_id = ObjectId(bt_id)
                    bt = await self.business_types_collection.find_one({"_id": bt_obj_id})
                except Exception:
                    bt = await self.business_types_collection.find_one({"_id": bt_id})

                if bt and "name" in bt:
                    return str(bt.get("_id", bt_id)), bt["name"]

            # 3. Check business_platform_id on org
            if org and org.get("business_platform_id"):
                bp_id = org["business_platform_id"]
                try:
                    bp_obj_id = ObjectId(bp_id)
                    bp = await self.business_platforms_collection.find_one({"_id": bp_obj_id})
                except Exception:
                    bp = await self.business_platforms_collection.find_one({"_id": bp_id})

                if bp and bp.get("business_type_id"):
                    bt_id = bp["business_type_id"]
                    try:
                        bt_obj_id = ObjectId(bt_id)
                        bt = await self.business_types_collection.find_one({"_id": bt_obj_id})
                    except Exception:
                        bt = await self.business_types_collection.find_one({"_id": bt_id})

                    if bt and "name" in bt:
                        return str(bt.get("_id", bt_id)), bt["name"]

            # 4. Fallback to first available BusinessType in database
            first_bt = await self.business_types_collection.find_one()
            if first_bt:
                return str(first_bt["_id"]), first_bt.get("name", "General Business")

            # 5. Default fallback
            return "general_business_id", "General Business"

        except Exception as e:
            print(f"Error resolving business type for owner {owner_id}: {e}")
            return "general_business_id", "General Business"

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