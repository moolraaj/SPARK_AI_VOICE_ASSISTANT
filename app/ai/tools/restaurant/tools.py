# import time
# from typing import Any
# import re
# from ....modules.catalogs.catalog_service import CatalogService
# from app.rag.vectorstore.qdrant_store import qdrant_store
# from app.database.mongodb import mongodb


# # ── Voice response size ───────────────────────────────────────────────
# # Voice pe zyada items bolna confusing hota hai.
# # Yeh constant control karta hai ki tool ek baar mein
# # maximum kitne items/categories LLM ko de.
# # DB mein saare items rahenge — sirf LLM ko dene wala
# # slice yahan se control hota hai.
# VOICE_RES_COUNT: int = 3


# class RestaurantTools:


#     async def _resolve_catalog_item(
#         self,
#         owner_id: str,
#         raw_name: str,
#     ) -> dict[str, Any] | None:
#         """
#         Resolve a menu item against the authoritative catalog.

#         Handles the case where the caller passed a name with a trailing
#         category tag attached, e.g.
#             "Chili Mushroom (Dry / Gravy) (STARTERS)"
#         instead of the catalog's actual stored name
#             "Chili Mushroom (Dry / Gravy)"
#         """
#         name = raw_name.strip()
#         if not name:
#             return None

#         # 1) Try the exact name as given.
#         item = await self.catalog_service.get_item_by_name(
#             owner_id=owner_id,
#             item_name=name,
#         )
#         if item:
#             return item

#         # 2) If the name ends with a "(...)" group, strip only the LAST
#         #    one and retry — covers "<dish> (<category>)" style names
#         #    without touching parentheses that are part of the dish name
#         #    itself (e.g. "(Dry / Gravy)").
#         stripped = re.sub(r"\s*\([^()]*\)\s*$", "", name).strip()
#         if stripped and stripped != name:
#             item = await self.catalog_service.get_item_by_name(
#                 owner_id=owner_id,
#                 item_name=stripped,
#             )
#             if item:
#                 return item

#         return None

#     async def create_order(
#         self,
#         owner_id: str,
#         items: list[dict[str, Any]],
#         special_notes: str | None = None,
#         customer_phone: str | None = None,
#         order_type: str = "DELIVERY",
#         table_number: str | None = None,
#     ) -> dict[str, Any]:
#         """
#         Create a new restaurant order in MongoDB.
#         """
#         if not owner_id:
#             return {
#                 "success": False,
#                 "error": "owner_id is required.",
#             }

#         if not items:
#             return {
#                 "success": False,
#                 "error": "items list cannot be empty.",
#             }

#         try:
#             processed_items = []
#             unresolved_items = []
#             total_amount = 0.0

#             for item in items:
#                 raw_name = (item.get("item_name") or item.get("name") or "").strip()
#                 qty = max(1, int(item.get("quantity", 1)))
#                 notes = item.get("notes") or ""

#                 if not raw_name:
#                     unresolved_items.append("Unknown Item")
#                     continue

#                 cat_item = None
#                 try:
#                     cat_item = await self._resolve_catalog_item(owner_id, raw_name)
#                 except Exception as e:
#                     print(f"⚠️ catalog lookup failed for '{raw_name}': {e}")

#                 # Reject instead of silently defaulting price to 0.
#                 if not cat_item or cat_item.get("price") in (None, ""):
#                     unresolved_items.append(raw_name)
#                     continue

#                 price = float(cat_item["price"])
#                 item_total = price * qty
#                 total_amount += item_total

#                 processed_items.append({
#                     # store the CLEAN catalog name, not the messy raw one
#                     "item_name": cat_item.get("item_name", raw_name),
#                     "quantity": qty,
#                     "unit_price": price,
#                     "total_price": item_total,
#                     "notes": notes,
#                 })

#             # If even one item couldn't be resolved, don't create a
#             # partial / ₹0 order — fail loudly instead.
#             if unresolved_items:
#                 return {
#                     "success": False,
#                     "error": (
#                         "These items could not be found in the menu: "
#                         + ", ".join(unresolved_items)
#                     ),
#                 }

#             order_doc = {
#                 "owner_id": owner_id,
#                 "customer_phone": customer_phone or "",
#                 "items": processed_items,
#                 "total_amount": round(total_amount, 2),
#                 "order_type": order_type,
#                 "table_number": table_number or "",
#                 "special_notes": special_notes or "",
#                 "status": "CONFIRMED",
#                 "created_at": time.time(),
#                 "updated_at": time.time(),
#             }

#             db = mongodb.database
#             if db is not None:
#                 result = await db["orders"].insert_one(order_doc)
#                 order_id = str(result.inserted_id)
#             else:
#                 order_id = "ORD_" + str(int(time.time()))

#             return {
#                 "success": True,
#                 "order_id": order_id,
#                 "message": "Order placed successfully.",
#                 "order_type": order_type,
#                 "total_amount": round(total_amount, 2),
#                 "items": processed_items,
#             }

#         except Exception as e:
#             print(f"❌ create_order error: {e}")
#             return {
#                 "success": False,
#                 "error": f"Failed to create order: {str(e)}",
#             }

#     def __init__(self):
#         self.catalog_service = CatalogService()

#     async def search_menu(
#         self,
#         owner_id: str,
#         query: str,
#         top_k: int = VOICE_RES_COUNT,   # default = VOICE_RES_COUNT
#     ) -> dict[str, Any]:
#         """
#         Semantically search the restaurant menu.

#         This tool searches only the menu belonging to the
#         specified restaurant/owner.

#         Args:
#             owner_id:
#                 Restaurant owner ID.

#             query:
#                 Natural-language menu search query.

#                 Examples:
#                     "dal makhni"
#                     "spicy veg food"
#                     "something under 300"
#                     "paneer dishes"

#             top_k:
#                 Maximum number of menu items to return.

#         Returns:
#             Structured menu search result.
#         """

#         # ── Validate owner ───────────────────────────────────────────────

#         if not owner_id:
#             return {
#                 "success": False,
#                 "error": "owner_id is required.",
#                 "items": [],
#             }

#         # ── Validate query ───────────────────────────────────────────────

#         if not query or not query.strip():
#             return {
#                 "success": False,
#                 "error": "Menu search query is required.",
#                 "items": [],
#             }

#         query = query.strip()

#         # ── Validate top_k ───────────────────────────────────────────────

#         top_k = max(1, min(top_k, 20))

#         # ── Semantic search ──────────────────────────────────────────────

#         try:
#             results = await qdrant_store.search(
#                 owner_id=owner_id,
#                 query=query,
#                 top_k=top_k,
#             )

#         except Exception as e:
#             print(f"❌ Restaurant menu search error: {e}")

#             return {
#                 "success": False,
#                 "error": str(e),
#                 "items": [],
#             }

#         # ── No results ───────────────────────────────────────────────────

#         if not results:
#             return {
#                 "success": True,
#                 "query": query,
#                 "count": 0,
#                 "items": [],
#                 "message": "No matching menu items found.",
#             }

#         # ── Normalize Qdrant payload ─────────────────────────────────────

#         items = []

#         for result in results:
#             items.append(
#                 {
#                     "item_name": result.get("item_name"),
#                     "price": result.get("price"),
#                     "is_veg": result.get("is_veg", True),
#                 }
#             )

#         # ── Final tool response ──────────────────────────────────────────

#         return {
#             "success": True,
#             "query": query,
#             "count": len(items),
#             "items": items,
#         }

#     async def get_menu_item(
#         self,
#         owner_id: str,
#         menu_item_name: str,
#     ) -> dict[str, Any]:

#         # ── Validate owner ───────────────────────────────────────────────

#         if not owner_id:
#             return {
#                 "found": False,
#                 "error": "owner_id is required.",
#                 "item": None,
#             }

#         # ── Validate item name ──────────────────────────────────────────

#         if not menu_item_name or not menu_item_name.strip():
#             return {
#                 "found": False,
#                 "error": "menu_item_name is required.",
#                 "item": None,
#             }

#         menu_item_name = menu_item_name.strip()

#         # ── Fetch from catalog ───────────────────────────────────────────

#         try:
#             result = await self.catalog_service.get_item_by_name(
#                 owner_id=owner_id,
#                 item_name=menu_item_name,
#             )

#         except Exception as e:
#             print(f"❌ get_menu_item failed | item={menu_item_name} | error={e}")

#             return {
#                 "found": False,
#                 "error": str(e),
#                 "item": None,
#             }

#         if result is None:
#             return {
#                 "found": False,
#                 "item": None,
#             }

#         return {
#             "found": True,
#             "item": {
#                 "item_name": result.get("item_name"),
#                 "price": result.get("price"),
#                 "is_veg": result.get("is_veg", True),
#             },
#         }


#     async def get_menu_categories(
#         self,
#         owner_id: str,
#     ) -> dict[str, Any]:

#         if not owner_id:
#             return {
#                 "success": False,
#                 "error": "owner_id is required.",
#                 "categories": [],
#             }

#         try:
#             t0 = time.perf_counter()
#             categories = await self.catalog_service.get_menu_categories(
#                 owner_id=owner_id,
#             )
#             db_ms = (time.perf_counter() - t0) * 1000
#             print(f"⏱️ DB (MongoDB) Latency [get_menu_categories]: {db_ms:.2f} ms ({db_ms/1000:.3f}s)")

#             all_category_names = [
#                 cat.get("name") if isinstance(cat, dict) else str(cat)
#                 for cat in categories
#             ]

#             total          = len(all_category_names)
#             sliced         = all_category_names[:VOICE_RES_COUNT]
#             has_more       = total > VOICE_RES_COUNT

#             return {
#                 "success":         True,
#                 "count":           len(sliced),
#                 "total_available": total,
#                 "has_more":        has_more,
#                 "categories":      sliced,
#             }

#         except Exception as e:
#             return {
#                 "success": False,
#                 "error": str(e),
#                 "categories": [],
#             }

#     async def get_menu_items_by_category(
#         self,
#         owner_id: str,
#         category_name: str,
#     ) -> dict[str, Any]:

#         if not owner_id:
#             return {
#                 "success": False,
#                 "error": "owner_id is required.",
#                 "items": [],
#             }

#         if not category_name or not category_name.strip():
#             return {
#                 "success": False,
#                 "error": "category_name is required.",
#                 "items": [],
#             }

#         category_name = category_name.strip()

#         try:
#             t0 = time.perf_counter()
#             items = await self.catalog_service.get_items_by_category_name(
#                 owner_id=owner_id,
#                 category_name=category_name,
#             )
#             db_ms = (time.perf_counter() - t0) * 1000
#             print(f"⏱️ DB (MongoDB) Latency [get_menu_items_by_category]: {db_ms:.2f} ms ({db_ms/1000:.3f}s)")

#         except Exception as e:
#             print(
#                 f"❌ get_menu_items_by_category failed | "
#                 f"category={category_name} | "
#                 f"error={e}"
#             )

#             return {
#                 "success": False,
#                 "error": str(e),
#                 "items": [],
#             }

#         if not items:
#             return {
#                 "success":      True,
#                 "category_name": category_name,
#                 "count":        0,
#                 "has_more":     False,
#                 "total_available": 0,
#                 "items":        [],
#                 "message": (
#                     f"No menu items found in "
#                     f"'{category_name}'."
#                 ),
#             }

#         trimmed_items = [
#             {
#                 "item_name": item.get("item_name"),
#                 "price":     item.get("price"),
#                 "is_veg":    item.get("is_veg", True),
#             }
#             for item in items
#         ]

#         total    = len(trimmed_items)
#         sliced   = trimmed_items[:VOICE_RES_COUNT]
#         has_more = total > VOICE_RES_COUNT

#         return {
#             "success":         True,
#             "category_name":   category_name,
#             "count":           len(sliced),
#             "total_available": total,
#             "has_more":        has_more,
#             "items":           sliced,
#         }

#     # ── PDF Knowledge Search ─────────────────────────────────────────────────

#     async def search_pdf_knowledge(
#         self,
#         owner_id: str,
#         query: str,
#         top_k: int = VOICE_RES_COUNT,
#     ) -> dict[str, Any]:
#         """
#         Search the uploaded PDF / vector knowledge base for this restaurant.

#         Used for price queries, menu items, restaurant policies, address,
#         and any information contained in the owner's uploaded PDF catalog.

#         Args:
#             owner_id: Restaurant owner ID (injected from state).
#             query:    Customer's natural-language question.
#             top_k:    Maximum number of relevant results to return.
#         """

#         if not owner_id:
#             return {
#                 "success": False,
#                 "error":   "owner_id is required.",
#                 "results": [],
#             }

#         if not query or not query.strip():
#             return {
#                 "success": False,
#                 "error":   "Search query is required.",
#                 "results": [],
#             }

#         query   = query.strip()
#         top_k   = max(1, min(top_k, 20))

#         try:
#             results = await qdrant_store.search(
#                 owner_id = owner_id,
#                 query    = query,
#                 top_k    = top_k,
#             )
#         except Exception as e:
#             print(f"❌ PDF knowledge search error: {e}")
#             return {
#                 "success": False,
#                 "error":   f"Search failed: {str(e)}",
#                 "results": [],
#             }

#         if not results:
#             return {
#                 "success": True,
#                 "count":   0,
#                 "results": [],
#                 "message": "No relevant information found in the uploaded PDF.",
#             }

#         trimmed = [
#             {
#                 "text":     hit.get("text") or hit.get("content") or "",
#                 "score":    round(hit.get("score", 0), 3),
#                 "category": hit.get("payload", {}).get("category", ""),
#                 "name":     hit.get("payload", {}).get("name", ""),
#                 "price":    hit.get("payload", {}).get("price", ""),
#             }
#             for hit in results
#         ]

#         return {
#             "success": True,
#             "count":   len(trimmed),
#             "results": trimmed,
#         }

#     # ── Create Order ─────────────────────────────────────────────────────────

#     async def create_order(
#         self,
#         owner_id: str,
#         items: list[dict[str, Any]],
#         special_notes: str | None = None,
#         customer_phone: str | None = None,
#         order_type: str = "DELIVERY",
#         table_number: str | None = None,
#     ) -> dict[str, Any]:
#         """
#         Create a new restaurant order in MongoDB.
#         """
#         if not owner_id:
#             return {
#                 "success": False,
#                 "error": "owner_id is required.",
#             }

#         if not items:
#             return {
#                 "success": False,
#                 "error": "items list cannot be empty.",
#             }

#         try:
#             processed_items = []
#             total_amount = 0.0

#             for item in items:
#                 name = item.get("item_name") or item.get("name") or "Unknown Item"
#                 qty = max(1, int(item.get("quantity", 1)))
#                 notes = item.get("notes") or ""

#                 price = 0.0
#                 if name:
#                     try:
#                         cat_item = await self.catalog_service.get_item_by_name(
#                             owner_id=owner_id,
#                             item_name=name,
#                         )
#                         if cat_item and cat_item.get("price"):
#                             price = float(cat_item["price"])
#                     except Exception:
#                         price = 0.0

#                 item_total = price * qty
#                 total_amount += item_total

#                 processed_items.append({
#                     "item_name": name,
#                     "quantity": qty,
#                     "unit_price": price,
#                     "total_price": item_total,
#                     "notes": notes,
#                 })

#             order_doc = {
#                 "owner_id": owner_id,
#                 "customer_phone": customer_phone or "",
#                 "items": processed_items,
#                 "total_amount": round(total_amount, 2),
#                 "order_type": order_type,
#                 "table_number": table_number or "",
#                 "special_notes": special_notes or "",
#                 "status": "CONFIRMED",
#                 "created_at": time.time(),
#                 "updated_at": time.time(),
#             }

#             db = mongodb.database
#             if db is not None:
#                 result = await db["orders"].insert_one(order_doc)
#                 order_id = str(result.inserted_id)
#             else:
#                 order_id = "ORD_" + str(int(time.time()))

#             return {
#                 "success": True,
#                 "order_id": order_id,
#                 "message": "Order placed successfully.",
#                 "order_type": order_type,
#                 "total_amount": round(total_amount, 2),
#                 "items": processed_items,
#             }

#         except Exception as e:
#             print(f"❌ create_order error: {e}")
#             return {
#                 "success": False,
#                 "error": f"Failed to create order: {str(e)}",
#             }

#     # ── Update Order ─────────────────────────────────────────────────────────

#     async def update_order(
#         self,
#         owner_id: str,
#         order_id: str | None = None,
#         customer_phone: str | None = None,
#         items: list[dict[str, Any]] | None = None,
#         special_notes: str | None = None,
#         order_type: str | None = None,
#         table_number: str | None = None,
#     ) -> dict[str, Any]:
#         """
#         Update an existing restaurant order in MongoDB.
#         """
#         if not owner_id:
#             return {
#                 "success": False,
#                 "error": "owner_id is required.",
#             }

#         try:
#             db = mongodb.database
#             if db is None:
#                 return {
#                     "success": False,
#                     "error": "Database connection is not available.",
#                 }

#             query: dict[str, Any] = {"owner_id": owner_id}
#             if order_id:
#                 from bson import ObjectId
#                 try:
#                     query["_id"] = ObjectId(order_id)
#                 except Exception:
#                     query["order_id"] = order_id
#             elif customer_phone:
#                 query["customer_phone"] = customer_phone
#             else:
#                 return {
#                     "success": False,
#                     "error": "Either order_id or customer_phone is required to update an order.",
#                 }

#             existing_order = await db["orders"].find_one(query, sort=[("created_at", -1)])
#             if not existing_order:
#                 return {
#                     "success": False,
#                     "error": "Order not found.",
#                 }

#             update_fields: dict[str, Any] = {"updated_at": time.time()}

#             if special_notes is not None:
#                 update_fields["special_notes"] = special_notes
#             if order_type is not None:
#                 update_fields["order_type"] = order_type
#             if table_number is not None:
#                 update_fields["table_number"] = table_number

#             if items is not None:
#                 processed_items = []
#                 total_amount = 0.0
#                 for item in items:
#                     name = item.get("item_name") or item.get("name") or "Unknown Item"
#                     qty = int(item.get("quantity", 1))
#                     notes = item.get("notes") or ""

#                     if qty <= 0:
#                         continue

#                     price = 0.0
#                     if name:
#                         try:
#                             cat_item = await self.catalog_service.get_item_by_name(
#                                 owner_id=owner_id,
#                                 item_name=name,
#                             )
#                             if cat_item and cat_item.get("price"):
#                                 price = float(cat_item["price"])
#                         except Exception:
#                             price = 0.0

#                     item_total = price * qty
#                     total_amount += item_total
#                     processed_items.append({
#                         "item_name": name,
#                         "quantity": qty,
#                         "unit_price": price,
#                         "total_price": item_total,
#                         "notes": notes,
#                     })

#                 update_fields["items"] = processed_items
#                 update_fields["total_amount"] = round(total_amount, 2)

#             await db["orders"].update_one(
#                 {"_id": existing_order["_id"]},
#                 {"$set": update_fields}
#             )

#             return {
#                 "success": True,
#                 "order_id": str(existing_order["_id"]),
#                 "message": "Order updated successfully.",
#             }

#         except Exception as e:
#             print(f"❌ update_order error: {e}")
#             return {
#                 "success": False,
#                 "error": f"Failed to update order: {str(e)}",
#             }






import re
import time
from typing import Any

from ....modules.catalogs.catalog_service import CatalogService
from app.rag.vectorstore.qdrant_store import qdrant_store
from app.database.mongodb import mongodb


# ── Voice response size ───────────────────────────────────────────────
VOICE_RES_COUNT: int = 3


class RestaurantTools:

    def __init__(self):
        self.catalog_service = CatalogService()

    # ── Helper: resolve a (possibly messy) item name against catalog ──────

    async def _resolve_catalog_item(
        self,
        owner_id: str,
        raw_name: str,
    ) -> dict[str, Any] | None:
        """
        Resolve a menu item name against the authoritative catalog.

        Handles the case where the caller passed a name with a trailing
        category tag attached, e.g.
            "Chili Mushroom (Dry / Gravy) (STARTERS)"
        instead of the catalog's actual stored name
            "Chili Mushroom (Dry / Gravy)"
        """
        name = raw_name.strip()
        if not name:
            return None

        # 1) Try the exact name as given.
        item = await self.catalog_service.get_item_by_name(
            owner_id=owner_id,
            item_name=name,
        )
        if item:
            return item

        # 2) Strip only the LAST trailing "(...)" group and retry —
        #    covers "<dish> (<category>)" without touching parentheses
        #    that are part of the dish name itself.
        stripped = re.sub(r"\s*\([^()]*\)\s*$", "", name).strip()
        if stripped and stripped != name:
            item = await self.catalog_service.get_item_by_name(
                owner_id=owner_id,
                item_name=stripped,
            )
            if item:
                return item

        return None

    # ── Semantic menu search (Qdrant) ──────────────────────────────────────

    async def search_menu(
        self,
        owner_id: str,
        query: str,
        top_k: int = VOICE_RES_COUNT,
    ) -> dict[str, Any]:
        """
        Semantically search the restaurant menu.
        """
        if not owner_id:
            return {"success": False, "error": "owner_id is required.", "items": []}

        if not query or not query.strip():
            return {"success": False, "error": "Menu search query is required.", "items": []}

        query = query.strip()
        top_k = max(1, min(top_k, 20))

        try:
            results = await qdrant_store.search(
                owner_id=owner_id,
                query=query,
                top_k=top_k,
            )
        except Exception as e:
            print(f"❌ Restaurant menu search error: {e}")
            return {"success": False, "error": str(e), "items": []}

        if not results:
            return {
                "success": True,
                "query": query,
                "count": 0,
                "items": [],
                "message": "No matching menu items found.",
            }

        items = [
            {
                "item_name": r.get("item_name"),
                "price": r.get("price"),
                "is_veg": r.get("is_veg", True),
            }
            for r in results
        ]

        return {
            "success": True,
            "query": query,
            "count": len(items),
            "items": items,
        }

    # ── Authoritative PRICE lookup (MongoDB) ───────────────────────────────

    async def get_menu_item(
        self,
        owner_id: str,
        menu_item_name: str,
    ) -> dict[str, Any]:

        if not owner_id:
            return {"found": False, "error": "owner_id is required.", "item": None}

        if not menu_item_name or not menu_item_name.strip():
            return {"found": False, "error": "menu_item_name is required.", "item": None}

        menu_item_name = menu_item_name.strip()

        try:
            result = await self._resolve_catalog_item(owner_id, menu_item_name)
        except Exception as e:
            print(f"❌ get_menu_item failed | item={menu_item_name} | error={e}")
            return {"found": False, "error": str(e), "item": None}

        if result is None:
            return {"found": False, "item": None}

        return {
            "found": True,
            "item": {
                "item_name": result.get("item_name"),
                "price": result.get("price"),
                "is_veg": result.get("is_veg", True),
            },
        }

    # ── DEPRECATED for agent use: kept for internal/admin tooling only ────
    # Category listing/browsing is now handled by search_pdf_knowledge
    # (Qdrant). These methods are no longer registered as agent tools.

    async def get_menu_categories(self, owner_id: str) -> dict[str, Any]:
        if not owner_id:
            return {"success": False, "error": "owner_id is required.", "categories": []}

        try:
            t0 = time.perf_counter()
            categories = await self.catalog_service.get_menu_categories(owner_id=owner_id)
            db_ms = (time.perf_counter() - t0) * 1000
            print(f"⏱️ DB Latency [get_menu_categories]: {db_ms:.2f} ms")

            all_names = [c.get("name") if isinstance(c, dict) else str(c) for c in categories]
            total = len(all_names)
            sliced = all_names[:VOICE_RES_COUNT]

            return {
                "success": True,
                "count": len(sliced),
                "total_available": total,
                "has_more": total > VOICE_RES_COUNT,
                "categories": sliced,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "categories": []}

    async def get_menu_items_by_category(
        self,
        owner_id: str,
        category_name: str,
    ) -> dict[str, Any]:
        if not owner_id:
            return {"success": False, "error": "owner_id is required.", "items": []}

        if not category_name or not category_name.strip():
            return {"success": False, "error": "category_name is required.", "items": []}

        category_name = category_name.strip()

        try:
            t0 = time.perf_counter()
            items = await self.catalog_service.get_items_by_category_name(
                owner_id=owner_id,
                category_name=category_name,
            )
            db_ms = (time.perf_counter() - t0) * 1000
            print(f"⏱️ DB Latency [get_menu_items_by_category]: {db_ms:.2f} ms")
        except Exception as e:
            print(f"❌ get_menu_items_by_category failed | category={category_name} | error={e}")
            return {"success": False, "error": str(e), "items": []}

        if not items:
            return {
                "success": True,
                "category_name": category_name,
                "count": 0,
                "has_more": False,
                "total_available": 0,
                "items": [],
                "message": f"No menu items found in '{category_name}'.",
            }

        trimmed = [
            {"item_name": i.get("item_name"), "price": i.get("price"), "is_veg": i.get("is_veg", True)}
            for i in items
        ]
        total = len(trimmed)
        sliced = trimmed[:VOICE_RES_COUNT]

        return {
            "success": True,
            "category_name": category_name,
            "count": len(sliced),
            "total_available": total,
            "has_more": total > VOICE_RES_COUNT,
            "items": sliced,
        }

    # ── PDF / Vector Knowledge Search (categories, browsing, info) ─────────

    async def search_pdf_knowledge(
        self,
        owner_id: str,
        query: str,
        top_k: int = VOICE_RES_COUNT,
    ) -> dict[str, Any]:
        if not owner_id:
            return {"success": False, "error": "owner_id is required.", "results": []}

        if not query or not query.strip():
            return {"success": False, "error": "Search query is required.", "results": []}

        query = query.strip()
        top_k = max(1, min(top_k, 20))

        try:
            results = await qdrant_store.search(owner_id=owner_id, query=query, top_k=top_k)
        except Exception as e:
            print(f"❌ PDF knowledge search error: {e}")
            return {"success": False, "error": f"Search failed: {str(e)}", "results": []}

        if not results:
            return {
                "success": True,
                "count": 0,
                "results": [],
                "message": "No relevant information found in the uploaded PDF.",
            }

        trimmed = [
            {
                "text": hit.get("text") or hit.get("content") or "",
                "score": round(hit.get("score", 0), 3),
                "category": hit.get("payload", {}).get("category", ""),
                "name": hit.get("payload", {}).get("name", ""),
                "price": hit.get("payload", {}).get("price", ""),
            }
            for hit in results
        ]

        return {"success": True, "count": len(trimmed), "results": trimmed}

    # ── Create Order ─────────────────────────────────────────────────────

    async def create_order(
        self,
        owner_id: str,
        items: list[dict[str, Any]],
        special_notes: str | None = None,
        customer_phone: str | None = None,
        order_type: str = "DELIVERY",
        table_number: str | None = None,
    ) -> dict[str, Any]:
        if not owner_id:
            return {"success": False, "error": "owner_id is required."}

        if not items:
            return {"success": False, "error": "items list cannot be empty."}

        try:
            processed_items = []
            unresolved_items = []
            total_amount = 0.0

            for item in items:
                raw_name = (item.get("item_name") or item.get("name") or "").strip()
                qty = max(1, int(item.get("quantity", 1)))
                notes = item.get("notes") or ""

                if not raw_name:
                    unresolved_items.append("Unknown Item")
                    continue

                cat_item = None
                try:
                    cat_item = await self._resolve_catalog_item(owner_id, raw_name)
                except Exception as e:
                    print(f"⚠️ catalog lookup failed for '{raw_name}': {e}")

                if not cat_item or cat_item.get("price") in (None, ""):
                    unresolved_items.append(raw_name)
                    continue

                price = float(cat_item["price"])
                item_total = price * qty
                total_amount += item_total

                processed_items.append({
                    "item_name": cat_item.get("item_name", raw_name),
                    "quantity": qty,
                    "unit_price": price,
                    "total_price": item_total,
                    "notes": notes,
                })

            if unresolved_items:
                return {
                    "success": False,
                    "error": (
                        "These items could not be found in the menu: "
                        + ", ".join(unresolved_items)
                    ),
                }

            order_doc = {
                "owner_id": owner_id,
                "customer_phone": customer_phone or "",
                "items": processed_items,
                "total_amount": round(total_amount, 2),
                "order_type": order_type,
                "table_number": table_number or "",
                "special_notes": special_notes or "",
                "status": "CONFIRMED",
                "created_at": time.time(),
                "updated_at": time.time(),
            }

            db = mongodb.database
            if db is not None:
                result = await db["orders"].insert_one(order_doc)
                order_id = str(result.inserted_id)
            else:
                order_id = "ORD_" + str(int(time.time()))

            return {
                "success": True,
                "order_id": order_id,
                "message": "Order placed successfully.",
                "order_type": order_type,
                "total_amount": round(total_amount, 2),
                "items": processed_items,
            }

        except Exception as e:
            print(f"❌ create_order error: {e}")
            return {"success": False, "error": f"Failed to create order: {str(e)}"}

    # ── Update Order ─────────────────────────────────────────────────────

    async def update_order(
        self,
        owner_id: str,
        order_id: str | None = None,
        customer_phone: str | None = None,
        items: list[dict[str, Any]] | None = None,
        special_notes: str | None = None,
        order_type: str | None = None,
        table_number: str | None = None,
    ) -> dict[str, Any]:
        if not owner_id:
            return {"success": False, "error": "owner_id is required."}

        try:
            db = mongodb.database
            if db is None:
                return {"success": False, "error": "Database connection is not available."}

            query: dict[str, Any] = {"owner_id": owner_id}
            if order_id:
                from bson import ObjectId
                try:
                    query["_id"] = ObjectId(order_id)
                except Exception:
                    query["order_id"] = order_id
            elif customer_phone:
                query["customer_phone"] = customer_phone
            else:
                return {
                    "success": False,
                    "error": "Either order_id or customer_phone is required to update an order.",
                }

            existing_order = await db["orders"].find_one(query, sort=[("created_at", -1)])
            if not existing_order:
                return {"success": False, "error": "Order not found."}

            update_fields: dict[str, Any] = {"updated_at": time.time()}

            if special_notes is not None:
                update_fields["special_notes"] = special_notes
            if order_type is not None:
                update_fields["order_type"] = order_type
            if table_number is not None:
                update_fields["table_number"] = table_number

            if items is not None:
                processed_items = []
                unresolved_items = []
                total_amount = 0.0

                for item in items:
                    raw_name = (item.get("item_name") or item.get("name") or "").strip()
                    qty = int(item.get("quantity", 1))
                    notes = item.get("notes") or ""

                    if qty <= 0:
                        continue

                    if not raw_name:
                        unresolved_items.append("Unknown Item")
                        continue

                    cat_item = None
                    try:
                        cat_item = await self._resolve_catalog_item(owner_id, raw_name)
                    except Exception as e:
                        print(f"⚠️ catalog lookup failed for '{raw_name}': {e}")

                    if not cat_item or cat_item.get("price") in (None, ""):
                        unresolved_items.append(raw_name)
                        continue

                    price = float(cat_item["price"])
                    item_total = price * qty
                    total_amount += item_total
                    processed_items.append({
                        "item_name": cat_item.get("item_name", raw_name),
                        "quantity": qty,
                        "unit_price": price,
                        "total_price": item_total,
                        "notes": notes,
                    })

                if unresolved_items:
                    return {
                        "success": False,
                        "error": (
                            "These items could not be found in the menu: "
                            + ", ".join(unresolved_items)
                        ),
                    }

                update_fields["items"] = processed_items
                update_fields["total_amount"] = round(total_amount, 2)

            await db["orders"].update_one(
                {"_id": existing_order["_id"]},
                {"$set": update_fields},
            )

            return {
                "success": True,
                "order_id": str(existing_order["_id"]),
                "message": "Order updated successfully.",
            }

        except Exception as e:
            print(f"❌ update_order error: {e}")
            return {"success": False, "error": f"Failed to update order: {str(e)}"}