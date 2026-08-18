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

from app.core.config import (
    QDRANT_URL,
    QDRANT_API_KEY,
    OPENAI_API_KEY,
)


COLLECTION_NAME = "catalog_items"
VECTOR_SIZE = 1536
EMBED_MODEL = "text-embedding-3-small"


class QdrantStore:

    def __init__(self):
        self.client: AsyncQdrantClient | None = None

        self.openai = AsyncOpenAI(
            api_key=OPENAI_API_KEY
        )

    async def connect(self):

        # Already connected
        if self.client is not None:
            print("ℹ️ Qdrant already connected")
            return

        print(f"🔌 Connecting to Qdrant: {QDRANT_URL}")

        client = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY or None,
            timeout=10,
            check_compatibility=False,
        )

        # Actually verify connection
        await client.get_collections()

        self.client = client

        await self._ensure_collection()

        print("✅ Qdrant Connected Successfully")

    async def disconnect(self):

        if self.client:

            await self.client.close()

            self.client = None

            print("❌ Qdrant Disconnected")

    async def _ensure_collection(self):

        if self.client is None:
            raise RuntimeError(
                "Qdrant client is not connected"
            )

        collections = await self.client.get_collections()

        names = [
            collection.name
            for collection in collections.collections
        ]

        if COLLECTION_NAME not in names:

            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )

            print(
                f"✅ Collection created: {COLLECTION_NAME}"
            )

    async def _embed(self, text: str) -> list[float]:

        response = await self.openai.embeddings.create(
            model=EMBED_MODEL,
            input=text,
        )

        return response.data[0].embedding

    def _build_vector_text(self, item: dict) -> str:

        veg_label = (
            "vegetarian"
            if item.get("is_veg")
            else "non-vegetarian"
        )

        return (
            f"{item['item_name']} | "
            f"category: {item['category']} | "
            f"price: {item['price']} | "
            f"{veg_label}"
        )

    async def upsert_items(
        self,
        owner_id: str,
        document_id: str,
        items: list[dict],
    ) -> int:

        if self.client is None:
            await self.connect()

        points = []

        for item in items:

            vector_text = self._build_vector_text(item)

            vector = await self._embed(vector_text)

            point_uuid = str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    str(item["mongo_id"]),
                )
            )

            points.append(
                PointStruct(
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
                        "is_veg": item.get(
                            "is_veg",
                            True,
                        ),
                    },
                )
            )

        if points:

            await self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
            )

        return len(points)

    async def delete_by_document(
        self,
        owner_id: str,
        document_id: str,
    ):

        if self.client is None:
            await self.connect()

        await self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="owner_id",
                        match=MatchValue(
                            value=owner_id
                        ),
                    ),
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(
                            value=document_id
                        ),
                    ),
                ]
            ),
        )

    async def search(
        self,
        owner_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:

        # Important for standalone scripts
        if self.client is None:
            await self.connect()

        vector = await self._embed(query)

        res = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=top_k,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="owner_id",
                        match=MatchValue(
                            value=owner_id,
                        ),
                    )
                ]
            ),
            with_payload=True,
        )

        return [
            {
                "score": point.score,
                **point.payload,
            }
            for point in res.points
        ]


qdrant_store = QdrantStore()