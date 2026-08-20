import time
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
                    "item_name": result.get("item_name"),
                    "price": result.get("price"),
                    "is_veg": result.get("is_veg", True),
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

        # ── Validate owner ───────────────────────────────────────────────

        if not owner_id:
            return {
                "found": False,
                "error": "owner_id is required.",
                "item": None,
            }

        # ── Validate item name ──────────────────────────────────────────

        if not menu_item_name or not menu_item_name.strip():
            return {
                "found": False,
                "error": "menu_item_name is required.",
                "item": None,
            }

        menu_item_name = menu_item_name.strip()

        # ── Fetch from catalog ───────────────────────────────────────────

        try:
            result = await self.catalog_service.get_item_by_name(
                owner_id=owner_id,
                item_name=menu_item_name,
            )

        except Exception as e:
            print(f"❌ get_menu_item failed | item={menu_item_name} | error={e}")

            return {
                "found": False,
                "error": str(e),
                "item": None,
            }

        if result is None:
            return {
                "found": False,
                "item": None,
            }

        return {
            "found": True,
            "item": {
                "item_name": result.get("item_name"),
                "price": result.get("price"),
                "is_veg": result.get("is_veg", True),
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
            t0 = time.perf_counter()
            categories = await self.catalog_service.get_menu_categories(
                owner_id=owner_id,
            )
            db_ms = (time.perf_counter() - t0) * 1000
            print(f"⏱️ DB (MongoDB) Latency [get_menu_categories]: {db_ms:.2f} ms ({db_ms/1000:.3f}s)")

            category_names = [
                cat.get("name") if isinstance(cat, dict) else str(cat)
                for cat in categories
            ]

            return {
                "success": True,
                "count": len(category_names),
                "categories": category_names,
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
            t0 = time.perf_counter()
            items = await self.catalog_service.get_items_by_category_name(
                owner_id=owner_id,
                category_name=category_name,
            )
            db_ms = (time.perf_counter() - t0) * 1000
            print(f"⏱️ DB (MongoDB) Latency [get_menu_items_by_category]: {db_ms:.2f} ms ({db_ms/1000:.3f}s)")

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

        trimmed_items = [
            {
                "item_name": item.get("item_name"),
                "price": item.get("price"),
                "is_veg": item.get("is_veg", True),
            }
            for item in items
        ]

        return {
            "success": True,
            "category_name": category_name,
            "count": len(trimmed_items),
            "items": trimmed_items,
        }