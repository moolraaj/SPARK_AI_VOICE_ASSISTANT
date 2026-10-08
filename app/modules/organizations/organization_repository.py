from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import mongodb


class OrganizationRepository:

    @property
    def organizations(self):
        return mongodb.database["organizations"]

    async def get_all(self, skip: int, limit: int, query: dict | None = None):
        filter_query = query if query is not None else {}
        return await self.organizations.find(filter_query).skip(skip).limit(limit).to_list(length=limit)

    async def count(self, query: dict | None = None):
        filter_query = query if query is not None else {}
        return await self.organizations.count_documents(filter_query)

    async def get_by_owner(self, owner_id: str, skip: int, limit: int):
        return await self.organizations.find({"owner_id": owner_id}).skip(skip).limit(limit).to_list(length=limit)

    async def get_all_by_owner(self, owner_id: str):
        """Return ALL orgs owned by a user (no pagination) — used for device linking."""
        return await self.organizations.find({"owner_id": owner_id}).to_list(length=None)

    async def count_by_owner(self, owner_id: str):
        return await self.organizations.count_documents({"owner_id": owner_id})

    async def link_device_to_all_owner_orgs(self, owner_id: str, device_id: str) -> int:
        """
        Set hardware_device_id = device_id on EVERY org owned by owner_id.
        Returns the number of orgs updated.

        Flow:
            caller_phone → user._id (owner_id) → all orgs → bulk update hardware_device_id
        """
        from app.core.datetime import utc_now
        result = await self.organizations.update_many(
            {"owner_id": owner_id},
            {"$set": {"hardware_device_id": device_id, "updated_at": utc_now()}}
        )
        return result.modified_count

    async def get_by_id(self, organization_id: ObjectId):
        return await self.organizations.find_one({"_id": organization_id})

    async def get_by_slug(self, slug: str):
        return await self.organizations.find_one({"slug": slug})

    async def get_by_phone(self, phone: str):
        """Resolve an org by its phone / DID number (the number a customer calls)."""
        return await self.organizations.find_one({
            "$or": [{"phone": phone}, {"did_number": phone}]
        })

    async def get_by_did_number(self, did_number: str):
        """Legacy helper — delegates to get_by_phone."""
        return await self.get_by_phone(did_number)

    async def get_by_device_id(self, device_id: str):
        """Resolve an org by its registered hardware device ID (ESP32 SPARK-XXXX)."""
        return await self.organizations.find_one({"hardware_device_id": device_id})

    async def get_by_slug_excluding(self, slug: str, exclude_id: ObjectId):
        return await self.organizations.find_one({
            "slug": slug,
            "_id": {"$ne": exclude_id}
        })

    async def create(self, data: dict):
        result = await self.organizations.insert_one(data)
        return str(result.inserted_id)

    async def update(self, organization_id: ObjectId, data: dict):
        return await self.organizations.update_one(
            {"_id": organization_id},
            {"$set": data}
        )

    async def delete(self, organization_id: ObjectId):
        try:
            return await self.organizations.delete_one({"_id": organization_id})
        except (InvalidId, TypeError):
            return None
