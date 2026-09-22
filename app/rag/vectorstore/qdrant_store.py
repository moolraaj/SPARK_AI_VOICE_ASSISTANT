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

        try:
            client = AsyncQdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY or None,
                timeout=3,
                check_compatibility=False,
            )
            await client.get_collections()
            self.client = client
            await self._ensure_collection()
            print("✅ Qdrant Connected Successfully (Server Mode)")
        except Exception as e:
            print(f"⚠️ Qdrant server at {QDRANT_URL} not reachable ({e}). Switching to Embedded Local Storage Mode...")
            client = AsyncQdrantClient(path="./qdrant_local_db")
            self.client = client
            await self._ensure_collection()
            print("✅ Qdrant Connected Successfully (Embedded Local Storage Mode)")

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
        organization_id: str | None = None,
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

            item_org_id = organization_id or item.get("organization_id") or owner_id

            points.append(
                PointStruct(
                    id=point_uuid,
                    vector=vector,
                    payload={
                        "mongo_id": str(item["mongo_id"]),
                        "owner_id": owner_id,
                        "organization_id": item_org_id,
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
        organization_id: str | None = None,
    ) -> list[dict]:

        # Important for standalone scripts
        if self.client is None:
            await self.connect()

        vector = await self._embed(query)

        must_conditions = []
        if organization_id:
            must_conditions.append(
                FieldCondition(
                    key="organization_id",
                    match=MatchValue(value=organization_id),
                )
            )
        elif owner_id:
            must_conditions.append(
                FieldCondition(
                    key="owner_id",
                    match=MatchValue(value=owner_id),
                )
            )

        res = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=top_k,
            query_filter=Filter(must=must_conditions) if must_conditions else None,
            with_payload=True,
        )

        return [
            {
                "score": point.score,
                **point.payload,
            }
            for point in res.points
        ]

    async def get_all_vector_data(self) -> dict:
        if self.client is None:
            await self.connect()

        try:
            collections_res = await self.client.get_collections()
            collections_list = []
            total_records = 0

            for col in collections_res.collections:
                col_name = col.name
                try:
                    info = await self.client.get_collection(collection_name=col_name)
                    points_count = getattr(info, "points_count", 0) or getattr(info, "vectors_count", 0) or 0
                    
                    # Scroll all records iteratively using Qdrant offset pagination
                    records = []
                    next_offset = None
                    while True:
                        scroll_res = await self.client.scroll(
                            collection_name=col_name,
                            limit=250,
                            offset=next_offset,
                            with_payload=True,
                            with_vectors=False,
                        )
                        points_batch = scroll_res[0] if scroll_res and len(scroll_res) > 0 else []
                        next_offset = scroll_res[1] if scroll_res and len(scroll_res) > 1 else None

                        for point in points_batch:
                            records.append({
                                "id": str(point.id),
                                "payload": point.payload or {}
                            })

                        if not next_offset or len(points_batch) == 0:
                            break

                    total_records += points_count
                    collections_list.append({
                        "name": col_name,
                        "points_count": points_count,
                        "records": records
                    })
                except Exception as e:
                    print(f"Error reading collection {col_name}: {e}")

            return {
                "success": True,
                "total_collections": len(collections_list),
                "total_records": total_records,
                "collections": collections_list
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to get vector store data: {str(e)}"}

    async def get_vector_data_by_owner(self, owner_id: str, organization_id: str | None = None) -> dict:
        if self.client is None:
            await self.connect()

        target_id = organization_id or owner_id

        try:
            collections_res = await self.client.get_collections()
            collections_list = []
            total_records = 0

            for col in collections_res.collections:
                col_name = col.name
                try:
                    filter_org = Filter(
                        must=[
                            FieldCondition(
                                key="organization_id",
                                match=MatchValue(value=target_id),
                            )
                        ]
                    )
                    filter_owner = Filter(
                        must=[
                            FieldCondition(
                                key="owner_id",
                                match=MatchValue(value=target_id),
                            )
                        ]
                    )

                    records_dict = {}
                    for query_filter in [filter_org, filter_owner]:
                        next_offset = None
                        while True:
                            scroll_res = await self.client.scroll(
                                collection_name=col_name,
                                scroll_filter=query_filter,
                                limit=250,
                                offset=next_offset,
                                with_payload=True,
                                with_vectors=False,
                            )
                            points_batch = scroll_res[0] if scroll_res and len(scroll_res) > 0 else []
                            next_offset = scroll_res[1] if scroll_res and len(scroll_res) > 1 else None

                            for point in points_batch:
                                p_id = str(point.id)
                                p_payload = point.payload or {}
                                if p_id not in records_dict:
                                    p_org = p_payload.get("organization_id")
                                    p_owner = p_payload.get("owner_id")
                                    if p_org == target_id or (not p_org and p_owner == target_id):
                                        records_dict[p_id] = {
                                            "id": p_id,
                                            "payload": p_payload
                                        }

                            if not next_offset or len(points_batch) == 0:
                                break

                    records = list(records_dict.values())
                    total_records += len(records)
                    collections_list.append({
                        "name": col_name,
                        "points_count": len(records),
                        "records": records
                    })
                except Exception as e:
                    print(f"Error reading collection {col_name} for owner/org {target_id}: {e}")

            return {
                "success": True,
                "owner_id": owner_id,
                "organization_id": target_id,
                "total_collections": len(collections_list),
                "total_records": total_records,
                "collections": collections_list
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to get vector store data for owner/org '{target_id}': {str(e)}"}

    async def clear_collection(self, collection_name: str = COLLECTION_NAME) -> dict:
        if self.client is None:
            await self.connect()

        try:
            await self.client.delete_collection(collection_name=collection_name)
            await self._ensure_collection()
            return {"success": True, "message": f"Successfully cleared vector collection '{collection_name}'."}
        except Exception as e:
            return {"success": False, "message": f"Failed to clear collection '{collection_name}': {str(e)}"}

    async def delete_record(self, point_id: str, collection_name: str = COLLECTION_NAME) -> dict:
        if self.client is None:
            await self.connect()

        try:
            await self.client.delete(
                collection_name=collection_name,
                points_selector=[point_id],
            )
            return {"success": True, "message": f"Vector record '{point_id}' deleted successfully."}
        except Exception as e:
            return {"success": False, "message": f"Failed to delete vector record '{point_id}': {str(e)}"}


qdrant_store = QdrantStore()