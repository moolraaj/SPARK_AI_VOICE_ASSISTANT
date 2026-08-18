from typing import Any

from typing import Any

from ....modules.catalogs.catalog_service import CatalogService
from app.rag.vectorstore.qdrant_store import qdrant_store


class RestaurantTools:

    def __init__(self):
        self.catalog_service = CatalogService()

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

        except Exception as e:
            print(f"❌ Restaurant menu search error: {e}")

            return {
                "success": False,
                "error": str(e),
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

    async def get_menu_item(
        self,
        owner_id: str,
        menu_item_name: str,
    ) -> dict[str, Any]:

        if not owner_id:
            return {
                "success": False,
                "found": False,
                "error": "owner_id is required.",
                "item": None,
            }

        if not menu_item_name or not menu_item_name.strip():
            return {
                "success": False,
                "found": False,
                "error": "menu_item_name is required.",
                "item": None,
            }

        menu_item_name = menu_item_name.strip()

        result = await self.catalog_service.get_item_by_name(
            owner_id=owner_id,
            item_name=menu_item_name,
        )

        # VERY IMPORTANT
        if result is None:
            return {
                "success": True,
                "found": False,
                "item": None,
                "message": f"Menu item '{menu_item_name}' not found.",
            }

        return {
            "success": True,
            "found": True,
            "item": {
                "id": result.get("id"),
                "item_name": result.get("item_name"),
                "category_id": result.get("category_id"),
                "price": result.get("price"),
                "is_veg": result.get("is_veg", True),
                "description": result.get("description"),
            },
        }



    async def get_menu_categories(
        self,
        owner_id: str,
    ) -> dict[str, Any]:

        if not owner_id:
            return {
                "success": False,
                "error": "owner_id is required.",
                "categories": [],
            }

        try:
            categories = await self.catalog_service.get_menu_categories(
                owner_id=owner_id,
            )

            return {
                "success": True,
                "count": len(categories),
                "categories": categories,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "categories": [],
            }

    async def get_menu_items_by_category(
        self,
        owner_id: str,
        category_name: str,
    ) -> dict[str, Any]:

        if not owner_id:
            return {
                "success": False,
                "error": "owner_id is required.",
                "items": [],
            }

        if not category_name or not category_name.strip():
            return {
                "success": False,
                "error": "category_name is required.",
                "items": [],
            }

        category_name = category_name.strip()

        try:
            items = await self.catalog_service.get_items_by_category_name(
                owner_id=owner_id,
                category_name=category_name,
            )

        except Exception as e:
            print(
                f"❌ get_menu_items_by_category failed | "
                f"category={category_name} | "
                f"error={e}"
            )

            return {
                "success": False,
                "error": str(e),
                "items": [],
            }

        if not items:
            return {
                "success": True,
                "category_name": category_name,
                "count": 0,
                "items": [],
                "message": (
                    f"No menu items found in "
                    f"'{category_name}'."
                ),
            }

        return {
            "success": True,
            "category_name": category_name,
            "count": len(items),
            "items": items,
        }