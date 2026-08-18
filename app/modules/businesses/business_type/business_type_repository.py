from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import mongodb


class BusinessTypeRepository:

    @property
    def business_types(self):
        return mongodb.database["business_types"]

    async def get_all(self, skip: int, limit: int):
        return await self.business_types.find().skip(skip).limit(limit).to_list(length=limit)

    async def count(self):
        return await self.business_types.count_documents({})

    async def get_by_id(self, business_type_id: ObjectId):
        return await self.business_types.find_one({"_id": business_type_id})

    async def get_by_name(self, name: str):
        return await self.business_types.find_one({"name": name})

    async def create(self, data: dict):
        result = await self.business_types.insert_one(data)
        return str(result.inserted_id)

    async def update(self, business_type_id: ObjectId, data: dict):
        return await self.business_types.update_one(
            {"_id": business_type_id},
            {"$set": data}
        )

    async def delete(self, business_type_id: ObjectId):
        try:
            return await self.business_types.delete_one({"_id": business_type_id})
        except (InvalidId, TypeError):
            return None
