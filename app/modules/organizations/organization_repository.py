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

    async def count_by_owner(self, owner_id: str):
        return await self.organizations.count_documents({"owner_id": owner_id})

    async def get_by_id(self, organization_id: ObjectId):
        return await self.organizations.find_one({"_id": organization_id})

    async def get_by_slug(self, slug: str):
        return await self.organizations.find_one({"slug": slug})

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
