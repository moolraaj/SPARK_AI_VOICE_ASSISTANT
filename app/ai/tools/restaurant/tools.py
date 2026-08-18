from typing import Any

from app.rag.vectorstore.qdrant_store import qdrant_store


class RestaurantTools:

    def __init__(self):
        pass

    async def search_menu(
        self,
        owner_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """
        Semantically search the restaurant menu.

        This tool searches only the menu belonging to the
        specified restaurant/owner.

        Args:
            owner_id:
                Restaurant owner ID.

            query:
                Natural-language menu search query.

                Examples:
                    "dal makhni"
                    "spicy veg food"
                    "something under 300"
                    "paneer dishes"

            top_k:
                Maximum number of menu items to return.

        Returns:
            Structured menu search result.
        """

        # ── Validate owner ───────────────────────────────────────────────

        if not owner_id:
            return {
                "success": False,
                "error": "owner_id is required.",
                "items": [],
            }

        # ── Validate query ───────────────────────────────────────────────

        if not query or not query.strip():
            return {
                "success": False,
                "error": "Menu search query is required.",
                "items": [],
            }

        query = query.strip()

        # ── Validate top_k ───────────────────────────────────────────────

        top_k = max(1, min(top_k, 20))

        # ── Semantic search ──────────────────────────────────────────────

        try:
            results = await qdrant_store.search(
                owner_id=owner_id,
                query=query,
                top_k=top_k,
            )

        except Exception:
            return {
                "success": False,
                "error": "Unable to search the restaurant menu.",
                "items": [],
            }

        # ── No results ───────────────────────────────────────────────────

        if not results:
            return {
                "success": True,
                "query": query,
                "count": 0,
                "items": [],
                "message": "No matching menu items found.",
            }

        # ── Normalize Qdrant payload ─────────────────────────────────────

        items = []

        for result in results:
            items.append(
                {
                    "mongo_id": result.get("mongo_id"),
                    "item_name": result.get("item_name"),
                    "category": result.get("category"),
                    "category_id": result.get("category_id"),
                    "price": result.get("price"),
                    "is_veg": result.get("is_veg", True),
                    "score": result.get("score"),
                }
            )

        # ── Final tool response ──────────────────────────────────────────

        return {
            "success": True,
            "query": query,
            "count": len(items),
            "items": items,
        }