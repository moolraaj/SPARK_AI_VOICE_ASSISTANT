from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import mongodb


class BusinessPlatformRepository:

    @property
    def business_platforms(self):
        return mongodb.database["business_platforms"]

    async def get_all(self, skip: int, limit: int):
        return await self.business_platforms.find().skip(skip).limit(limit).to_list(length=limit)

    async def count(self):
        return await self.business_platforms.count_documents({})

    async def get_by_id(self, business_platform_id: ObjectId):
        return await self.business_platforms.find_one({"_id": business_platform_id})

    async def get_by_name(self, name: str):
        return await self.business_platforms.find_one({"name": name})


    async def create(self, data: dict):
        result = await self.business_platforms.insert_one(data)
        return str(result.inserted_id)

    async def update(self, business_platform_id: ObjectId, data: dict):
        return await self.business_platforms.update_one(
            {"_id": business_platform_id},
            {"$set": data}
        )

    async def delete(self, business_platform_id: ObjectId):
        try:
            return await self.business_platforms.delete_one({"_id": business_platform_id})
        except (InvalidId, TypeError):
            return None
