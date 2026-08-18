import json
import redis.asyncio as aioredis
from app.core.config import REDIS_URL

PREVIEW_TTL = 7200  # 2 hours in seconds


class RedisClient:

    def __init__(self):
        self.client: aioredis.Redis | None = None

    async def connect(self):
        self.client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        # Ping to verify connection
        await self.client.ping()
        print("✅ Redis Connected")

    async def disconnect(self):
        if self.client:
            await self.client.aclose()
            print("❌ Redis Disconnected")

    # ── Preview Helpers ──────────────────────────────────────────────────────

    def _preview_key(self, doc_id: str) -> str:
        return f"preview:{doc_id}"

    async def save_preview(self, doc_id: str, data: dict) -> None:
        """Save extracted categories + items to Redis with 2hr TTL."""
        key = self._preview_key(doc_id)
        await self.client.set(key, json.dumps(data, default=str), ex=PREVIEW_TTL)

    async def get_preview(self, doc_id: str) -> dict | None:
        """Read preview data from Redis. Returns None if expired or not found."""
        key = self._preview_key(doc_id)
        raw = await self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def update_preview(self, doc_id: str, data: dict) -> bool:
        """Overwrite preview data in Redis (resets TTL). Returns False if key not found."""
        key = self._preview_key(doc_id)
        exists = await self.client.exists(key)
        if not exists:
            return False
        await self.client.set(key, json.dumps(data, default=str), ex=PREVIEW_TTL)
        return True

    async def delete_preview(self, doc_id: str) -> None:
        """Delete preview from Redis after data is confirmed to MongoDB."""
        key = self._preview_key(doc_id)
        await self.client.delete(key)


redis_client = RedisClient()
