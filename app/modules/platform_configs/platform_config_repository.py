from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import mongodb


class PlatformConfigRepository:

    @property
    def platform_configs(self):
        return mongodb.database["platform_configs"]

    # ─── Read ─────────────────────────────────────────────────────────────────

    async def get_all(self, skip: int, limit: int, query: dict | None = None):
        filter_query = query if query is not None else {}
        return (
            await self.platform_configs.find(filter_query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )

    async def count(self, query: dict | None = None):
        filter_query = query if query is not None else {}
        return await self.platform_configs.count_documents(filter_query)

    async def get_by_id(self, config_id: ObjectId):
        return await self.platform_configs.find_one({"_id": config_id})

    async def get_by_business_type_id(self, business_type_id: str):
        return await self.platform_configs.find_one({"business_type_id": business_type_id})

    # ─── Write ────────────────────────────────────────────────────────────────

    async def create(self, data: dict):
        result = await self.platform_configs.insert_one(data)
        return str(result.inserted_id)

    async def update(self, config_id: ObjectId, data: dict):
        return await self.platform_configs.update_one(
            {"_id": config_id},
            {"$set": data}
        )

    async def delete(self, config_id: ObjectId):
        try:
            return await self.platform_configs.delete_one({"_id": config_id})
        except (InvalidId, TypeError):
            return None
