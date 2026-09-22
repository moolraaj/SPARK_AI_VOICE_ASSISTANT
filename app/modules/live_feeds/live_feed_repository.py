from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import mongodb


class LiveFeedRepository:

    @property
    def live_feeds(self):
        return mongodb.database["live_feeds"]

    # ─── Read ─────────────────────────────────────────────────────────────────

    async def get_all(self, skip: int, limit: int, query: dict | None = None):
        filter_query = query if query is not None else {}
        return (
            await self.live_feeds.find(filter_query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )

    async def count(self, query: dict | None = None):
        filter_query = query if query is not None else {}
        return await self.live_feeds.count_documents(filter_query)

    async def get_by_id(self, feed_id: ObjectId):
        return await self.live_feeds.find_one({"_id": feed_id})

    # ─── Write ────────────────────────────────────────────────────────────────

    async def create(self, data: dict):
        result = await self.live_feeds.insert_one(data)
        return str(result.inserted_id)

    async def update(self, feed_id: ObjectId, data: dict):
        return await self.live_feeds.update_one(
            {"_id": feed_id},
            {"$set": data}
        )

    async def delete(self, feed_id: ObjectId):
        try:
            return await self.live_feeds.delete_one({"_id": feed_id})
        except (InvalidId, TypeError):
            return None
