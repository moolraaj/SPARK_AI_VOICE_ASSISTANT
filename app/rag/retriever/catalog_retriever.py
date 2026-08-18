from app.rag.vectorstore.qdrant_store import qdrant_store
from app.modules.catalogs.catalog_repository import CatalogRepository


class CatalogRetriever:

    def __init__(self):
        self.catalog_repository = CatalogRepository()

    async def search_and_verify(self, owner_id: str, query: str, top_k: int = 5) -> list[dict]:
        """
        1. Queries Qdrant for top matching vectors scoped by owner_id.
        2. Tries to verify against live MongoDB catalog_items.
        3. Falls back to Qdrant payload directly when MongoDB item not found
           (handles seed data or items not yet persisted to catalog_items).
        """
        if not query or not query.strip():
            return []

        # Step 1: Vector Search in Qdrant
        vector_results = await qdrant_store.search(owner_id=owner_id, query=query, top_k=top_k)
        if not vector_results:
            return []

        # Step 2: Verify against MongoDB (with graceful fallback to Qdrant payload)
        verified_items = []
        for v in vector_results:
            mongo_id = v.get("mongo_id") or v.get("id")
            if not mongo_id:
                continue

            db_item = await self.catalog_repository.get_item_by_id(str(mongo_id))
            if not db_item:
                from bson import ObjectId as BsonObjectId
                from app.database.mongodb import mongodb
                try:
                    db_item = await mongodb.database["menu_items"].find_one({"_id": BsonObjectId(str(mongo_id))})
                except Exception:
                    db_item = None

            if db_item and db_item.get("status", "ACTIVE") == "ACTIVE":
                # MongoDB verified — enrich with live category name
                category_name = v.get("category", "General")
                if db_item.get("category_id"):
                    cat_doc = await self.catalog_repository.get_category_by_id(str(db_item["category_id"]))
                    if cat_doc:
                        category_name = cat_doc.get("name", category_name)
                verified_items.append({
                    "id": str(db_item["_id"]),
                    "item_name": db_item.get("item_name", v.get("item_name")),
                    "category": category_name,
                    "price": db_item.get("price", v.get("price")),
                    "is_veg": db_item.get("is_veg", v.get("is_veg", True)),
                    "description": db_item.get("description", ""),
                    "score": v.get("score", 0.0),
                })
            elif not db_item:
                # MongoDB item not found — use Qdrant payload directly as fallback
                verified_items.append({
                    "id": str(mongo_id),
                    "item_name": v.get("item_name", ""),
                    "category": v.get("category", "General"),
                    "price": v.get("price", 0),
                    "is_veg": v.get("is_veg", True),
                    "description": "",
                    "score": v.get("score", 0.0),
                })
            # If db_item exists but is INACTIVE — skip it (item genuinely disabled)

        return verified_items


catalog_retriever = CatalogRetriever()
