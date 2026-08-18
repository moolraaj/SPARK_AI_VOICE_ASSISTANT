import uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from openai import AsyncOpenAI
from app.core.config import QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY

COLLECTION_NAME = "catalog_items"
VECTOR_SIZE = 1536          # text-embedding-3-small output size
EMBED_MODEL = "text-embedding-3-small"


class QdrantStore:

    def __init__(self):
        self.client: AsyncQdrantClient | None = None
        self.openai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def connect(self):
        """Initialize Qdrant client (tries remote QDRANT_URL or falls back to local embedded ./qdrant_data)."""
        if QDRANT_URL and not QDRANT_URL.startswith("./"):
            try:
                self.client = AsyncQdrantClient(
                    url=QDRANT_URL,
                    api_key=QDRANT_API_KEY or None,
                    check_compatibility=False,
                    timeout=2.0,
                )
                await self._ensure_collection()
                print("✅ Qdrant Connected (Server Mode)")
                return
            except Exception:
                print("ℹ️ Remote Qdrant server not found — switching to Embedded Local Vector DB (No Docker needed)...")

        # Embedded mode — runs 100% inside Python process, stores vectors in ./qdrant_data
        try:
            self.client = AsyncQdrantClient(path="./qdrant_data")
            await self._ensure_collection()
            print("✅ Qdrant Connected Successfully")
        except Exception as e:
            print(f"⚠️ Embedded Qdrant warning: {e}")

    async def disconnect(self):
        if self.client:
            await self.client.close()
            print("❌ Qdrant Disconnected")

    async def _ensure_collection(self):
        """Create collection if it doesn't exist yet."""
        existing = await self.client.get_collections()
        names = [c.name for c in existing.collections]
        if COLLECTION_NAME not in names:
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE
                )
            )
            print(f"✅ Qdrant collection '{COLLECTION_NAME}' created")

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding vector for given text using OpenAI."""
        response = await self.openai.embeddings.create(
            model=EMBED_MODEL,
            input=text
        )
        return response.data[0].embedding

    def _build_vector_text(self, item: dict) -> str:
        """Build a descriptive string for embedding."""
        veg_label = "vegetarian" if item.get("is_veg") else "non-vegetarian"
        return (
            f"{item['item_name']} | "
            f"category: {item['category']} | "
            f"price: {item['price']} | "
            f"{veg_label}"
        )

    async def upsert_items(self, owner_id: str, document_id: str, items: list[dict]) -> int:
        """
        Embed and upsert a list of menu items into Qdrant.
        Each item must have: item_name, category, category_id, price, is_veg, mongo_id
        Returns count of vectors upserted.
        """
        points = []
        for item in items:
            vector_text = self._build_vector_text(item)
            vector = await self._embed(vector_text)

            point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(item["mongo_id"])))

            points.append(PointStruct(
                id=point_uuid,
                vector=vector,
                payload={
                    "mongo_id": str(item["mongo_id"]),
                    "owner_id": owner_id,
                    "document_id": document_id,
                    "category_id": item.get("category_id"),
                    "item_name": item["item_name"],
                    "category": item["category"],
                    "price": item["price"],
                    "is_veg": item.get("is_veg", True),
                }
            ))

        if points:
            await self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )

        return len(points)

    async def delete_by_document(self, owner_id: str, document_id: str) -> None:
        """Delete all vectors belonging to a specific uploaded document."""
        await self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(key="owner_id", match=MatchValue(value=owner_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]
            )
        )

    async def search(self, owner_id: str, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search for menu items belonging to an owner."""
        if self.client is None:
            await self.connect()
        if self.client is None:
            return []

        try:
            vector = await self._embed(query)
            res = await self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                limit=top_k,
                query_filter=Filter(
                    must=[FieldCondition(key="owner_id", match=MatchValue(value=owner_id))]
                ),
                with_payload=True,
            )
            return [{"score": r.score, **r.payload} for r in res.points]
        except Exception as e:
            print(f"⚠️  Qdrant search warning: {e}")
            return []


qdrant_store = QdrantStore()
