# from typing import Any, Annotated

# from langchain_core.tools import tool
# from langgraph.prebuilt import InjectedState

# from .tools import RestaurantTools


# restaurant_service = RestaurantTools()


# # =============================================================================
# # MENU SEARCH
# # =============================================================================

# @tool
# async def search_menu(
#     query: str,
#     top_k: int = 5,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Search the restaurant menu using semantic/vector search.

#     PURPOSE:
#     Use this tool to discover and identify menu items from the restaurant's
#     menu using natural-language or semantic search.

#     USE THIS TOOL WHEN:
#     - The customer asks whether a menu item exists in the restaurant menu.
#     - The customer asks whether a specific dish is available.
#     - The customer mentions a specific menu item and wants to know if it is
#       present in the menu.
#     - The customer asks for menu recommendations.
#     - The customer describes a food preference, craving, or requirement.
#     - The customer asks for similar dishes.
#     - The customer wants to discover menu items.

#     DO NOT USE THIS TOOL FOR:
#     - Retrieving authoritative price information.
#     - Retrieving the authoritative MongoDB menu_item_id.
#     - Creating an order.
#     - Updating an existing order.
#     - Cancelling an order.

#     DATA SOURCE RULES:
#     - Qdrant/vector search is used for menu discovery and item identification.
#     - Use the search result to determine whether the requested item exists
#       in the restaurant menu.
#     - Never treat Qdrant metadata as authoritative for price,
#       menu_item_id, or order information.
#     - When authoritative price or menu_item_id information is required,
#       use get_menu_item.
#     - Before creating an order, authoritative menu information must be
#       obtained according to the order-creation workflow.
#     - Never invent a menu item when the search result does not identify it.

#     RESPONSE HANDLING:
#     - Base the customer-facing response only on the actual menu information
#       returned by the tool.
#     - If the requested item is found, the assistant may tell the customer
#       that the item is available in the menu.
#     - If the requested item is not found, do not claim that it is available.
#     - Do not invent availability, price, or other menu details.

#     ARGUMENTS:
#     - query:
#         The customer's natural-language menu request, dish name,
#         preference, or search query.

#     - top_k:
#         Maximum number of relevant menu results to return.

#     - owner_id:
#         Automatically injected from authenticated application state.
#         Never ask the customer for this value or invent it.

#     IMPORTANT:
#     This tool is responsible for menu discovery and identification.
#     Authoritative pricing, menu IDs, and order data must come from the
#     appropriate MongoDB-backed tools.
#     """
#     return await restaurant_service.search_menu(
#         owner_id=owner_id,
#         query=query,
#         top_k=top_k,
#     )


# # =============================================================================
# # EXACT MENU ITEM
# # =============================================================================

# @tool
# async def get_menu_item(
#     menu_item_name: str,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Retrieve authoritative menu item details from MongoDB.

#     PURPOSE:
#     Use this tool when a menu item has already been identified and
#     authoritative database information is required.

#     This tool is responsible for retrieving the item's authoritative
#     MongoDB data, including its menu_item_id and current price.

#     USE THIS TOOL WHEN:
#     - The customer asks for the price of a known menu item.
#     - An authoritative menu_item_id is required for an order.
#     - Current authoritative menu item details are required after the item
#       has already been identified.
#     - The ordering workflow requires authoritative MongoDB information
#       for a specific menu item.

#     DO NOT USE THIS TOOL FOR:
#     - Discovering or searching menu items.
#     - Semantic search.
#     - Recommendations or suggestions.
#     - Broad or vague food requests.
#     - Browsing menu categories.
#     - Creating an order.
#     - Updating an existing order.
#     - Cancelling an order.

#     DATA SOURCE RULES:
#     - MongoDB is the authoritative source for menu_item_id and price.
#     - Never use Qdrant/vector-search metadata as the authoritative source
#       for menu_item_id or price.
#     - Never invent a menu_item_id.
#     - Never guess the price.
#     - Only return or communicate information supported by the MongoDB
#       result.

#     IMPORTANT:
#     - The menu item should already be identified before using this tool.
#     - Use search_menu for menu discovery and identification.
#     - Use this tool when authoritative MongoDB details are required.
#     - The backend may also use this authoritative lookup internally
#       during order creation.

#     ARGUMENTS:
#     - menu_item_name:
#         The menu item name that has already been identified.

#     - owner_id:
#         Automatically injected from authenticated application state.
#         Never ask the customer for this value or invent it.

#     RESPONSE HANDLING:
#     - Base any customer-facing information on the actual MongoDB result.
#     - If the item cannot be found or verified, do not invent its details.
#     - Do not expose internal database information or implementation details.
#     """
#     return await restaurant_service.get_menu_item(
#         owner_id=owner_id,
#         menu_item_name=menu_item_name,
#     )


# # =============================================================================
# # MENU CATEGORIES
# # =============================================================================

# @tool
# async def get_menu_categories(
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Retrieve the restaurant's available menu categories.

#     PURPOSE:
#     Show the customer the available menu categories.

#     WHEN TO USE:
#     - Customer asks what categories are available.
#     - Customer asks to see the menu at category level.

#     DO NOT USE:
#     - For items inside a category → use get_menu_items_by_category.
#     - For an exact item → use get_menu_item.
#     - For recommendations → use search_menu.

#     ARGUMENTS:
#     - owner_id: Automatically injected. Never ask the customer for it.

#     IMPORTANT:
#     - Use only real categories returned by the tool.
#     - Never invent or assume categories.
#     - Never repeat a category already told to the customer.

#     REPRESENTATION RULE:
#     - Tell the customer a maximum of 5 categories at a time.
#     - Use a natural conversational sentence.
#     - Say:
#     "Hamare menu mein [categories] available hain."
#     - Do NOT use:
#     "Ye categories available hain:"
#     "Available categories hain:"
#     or similar list-introduction phrases.
#     - If more categories remain, ask:
#     "Aur bhi categories hain, kya woh bhi bataun?"
#     - STOP and wait for the customer's response.
#     - Only continue when the customer asks for more.
#     - Continue with the next 5 unseen categories.
#     - NEVER repeat previously mentioned categories.
#     - If fewer than 5 remain, tell only those remaining.
#     - If no categories remain, do not ask for more.

#     CATEGORY SELECTION:
#     - If the customer selects a category, stop listing categories.
#     - Use get_menu_items_by_category for that category.

#     REPEATED REQUEST:
#     - If the customer asks about categories already mentioned, answer briefly.
#     - Do not repeat the complete category list.
#     - Only provide new categories if the customer asks for more.

#     REMINDER:
#     5 categories → WAIT → next 5.
#     Use REAL tool results only.
#     Never repeat already-mentioned categories.
#     """
#     return await restaurant_service.get_menu_categories(
#         owner_id=owner_id,
#     )


# # =============================================================================
# # MENU ITEMS BY CATEGORY
# # =============================================================================

# @tool
# async def get_menu_items_by_category(
#     category_name: str,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Retrieve menu items belonging to a specific restaurant category.
#     PURPOSE:
#     Show the customer the items available inside one requested category.
#     USE THIS TOOL WHEN:
#     - The customer asks what items are available in a specific category.
#     - The customer wants to browse a category.
#     EXAMPLES:
#     - "Desserts mein kya hai?"
#     - "Roti ke options batao."
#     - "Soups mein kya kya hai?"
#     - "Rice category mein kya hai?"
#     DO NOT USE THIS TOOL WHEN:
#     - The customer asks for broad food recommendations.
#     - The customer asks for one exact item.
#     - The customer wants to modify or place an order.
#     ARGUMENTS:
#     - category_name:
#         The category requested by the customer.
#     - owner_id:
#         Automatically injected from authenticated application state.
#         Never ask the customer for owner_id.
#     EXAMPLE FLOW:
#     Customer: "Desserts mein kya hai?"
#     Assistant: Call get_menu_items_by_category(category_name="Desserts")
#     Tool: Returns category items.
#     Assistant: Present the available desserts.

#     PRESENTATION FLOW:
#     - Present menu items in batches of 6 items at a time.
#     - NEVER list all items from the category at once.
#     - First, present ONLY the first 6 available items.
#     - After presenting the first 6 items, stop and wait for the customer's
#       response.
#     - If more items are available after the first 6, ask naturally:
#       "Hamare paas is category mein [first 6 items] available hain.
#       Aur bhi items hain, kya woh bhi bataun?"
#     - Do NOT automatically provide the next 6 items.
#     - WAIT for the customer's response.
#     - If the customer says "haan", "yes", "aur batao", "batao",
#       "next", "aur items batao", or gives a similar positive response,
#       then present the NEXT 6 items only.
#     - After every batch of 6 items, if more items remain, again ask:
#       "Aur bhi items hain, kya woh bhi bataun?"
#     - WAIT for the customer before presenting the next batch.
#     - Continue this 6-by-6 conversational flow until:
#         1. The customer selects an item, OR
#         2. The customer says they do not want to hear more items, OR
#         3. No more items remain.
#     - NEVER repeat items that have already been presented.
#     - If fewer than 6 items remain, present only the remaining items.
#       Do not add or invent extra items to make the batch of 6.
#     - If exactly 6 items remain, present those 6 items and do not ask
#       "Aur bhi items hain?" because there are no more items.
#     CUSTOMER SELECTION:
#     - If the customer selects an item from the items already presented,
#       stop listing additional items and continue with that selected item.
#     - If required for ordering, use get_menu_item to retrieve the
#       authoritative details before adding the item to an order.
#     IMPORTANT:
#     - The 6-item limit applies to what you SPEAK/PRESENT to the customer.
#     - Even if the tool returns more than 6 items, do not present more
#       than 6 items in a single response.
#     - Maintain conversation context so previously presented items are
#       not repeated.
#     EXAMPLE:
#     If the Paneer category contains:
#     Kadai Paneer,
#     Paneer Butter Masala,
#     Paneer Lababdar,
#     Paneer Kofta,
#     Paneer Palak,
#     Paneer Mutter,
#     Paneer Bhurji in Butter,
#     Paneer Lazeze,
#     Paneer Methi Malai,
#     Paneer Mushroom Masala,
#     Shahi Paneer Korma,
#     Paneer Chole
#     FIRST RESPONSE:
#     "Hamare paas Paneer category mein Kadai Paneer,
#     Paneer Butter Masala, Paneer Lababdar, Paneer Kofta,
#     Paneer Palak aur Paneer Mutter available hain.
#     Aur bhi items hain, kya woh bhi bataun?"
#     WAIT FOR CUSTOMER.
#     Customer similar like this:
#     "Haan, batao."
#     "yes"
#     SECOND RESPONSE:
#     "Aur 6 items hain: Paneer Bhurji in Butter, Paneer Lazeze,
#     Paneer Methi Malai, Paneer Mushroom Masala, Shahi Paneer Korma
#     aur Paneer Chole."
#     If more items remain, ask again whether the customer wants
#     to hear more.
#     DO NOT:
#     - List more than 6 items in one response.
#     - Automatically continue to the next batch.
#     - Repeat previously presented items.
#     - Invent menu items.
#     - Invent prices or availability.
#     - Use this tool for broad semantic recommendations.
#     - Use this tool as a replacement for get_menu_item when exact
#     - authoritative item details are required.
#     IMPORTANT:
#     This example is ONLY a demonstration of the 6-item presentation format.
#     NEVER use these example menu items as actual restaurant menu items.
#     Always replace the example items with the actual items returned by
#     get_menu_items_by_category.
#     REMINDER:
#     Use the 6-by-6 presentation format with REAL tool results only.
#     """
#     return await restaurant_service.get_menu_items_by_category(
#         owner_id=owner_id,
#         category_name=category_name,
#     )


# # =============================================================================
# # CREATE ORDER
# # =============================================================================

# @tool
# async def create_order(
#     items: list[dict[str, Any]],
#     special_notes: str | None = None,
#     customer_phone: str | None = None,
#     order_type: str = "DELIVERY",
#     table_number: str | None = None,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Create a new finalized restaurant order in MongoDB.

#     PURPOSE:
#     Create the customer's final order after the customer has explicitly
#     confirmed the complete order summary and total amount.

#     USE THIS TOOL ONLY WHEN:
#     - The customer has explicitly confirmed the final order.
#     - The final items and quantities are known.
#     - The required menu item IDs have been obtained from authoritative
#       menu data.
#     - The order type and required order information are available.

#     EXPLICIT CONFIRMATION IS REQUIRED:
#     The customer must clearly confirm that they want the final order placed.

#     VALID CONFIRMATIONS INCLUDE:
#     - "Haan order kar do."
#     - "Yes, place the order."
#     - "Order final kar do."
#     - "Haan, yehi order chahiye."
#     - "Confirm kar do."

#     DO NOT USE THIS TOOL:
#     - Before explicit customer confirmation.
#     - While the customer is still deciding what to order.
#     - While the customer is adding/removing/changing items.
#     - To calculate or guess prices.
#     - To invent menu_item_id values.
#     - To modify an existing order.

#     REQUIREMENTS:
#     1. Customer confirmation must happen BEFORE this tool call.
#     2. Every ordered item must contain item_name and quantity.
#     3. item_name must be the exact dish name (e.g. "Paneer Butter Masala").
#     4. The backend will re-fetch the real menu_item_id from the database
#        using item_name — you do NOT need to pass menu_item_id.
#     5. NEVER invent or pass a menu_item_id — it will be ignored and
#        overwritten by the authoritative database value.
#     6. Quantity must be valid and greater than zero.
#     7. order_type must be DELIVERY, TAKEAWAY, or DINE_IN.
#     8. table_number is required for DINE_IN.
#     9. Backend validation remains authoritative for item existence,
#        availability, price, quantity, and order total.

#     ARGUMENTS:
#     - items:
#         List of ordered items. Each item must contain:
#         - item_name  : The exact menu item name (REQUIRED — used to look up
#                        the real ID from the database).
#         - quantity   : Number of this item to order (REQUIRED).
#         - notes      : Optional item-specific instruction (e.g. "No onion").
#         DO NOT pass menu_item_id — the backend fetches it from the DB.

#     - special_notes:
#         Optional order-level instructions.
#         Examples:
#         "Deliver after 7 PM."
#         "Bring extra ketchup packets."

#     - customer_phone:
#         Optional customer phone number associated with the order.

#     - order_type:
#         Order fulfillment type:
#         DELIVERY, TAKEAWAY, or DINE_IN.

#     - table_number:
#         Table number for DINE_IN orders.

#     - owner_id:
#         Automatically injected from authenticated application state.
#         Never ask the customer for owner_id or invent it.

#     AFTER SUCCESS:
#     - Check the tool result.
#     - If the order was successfully created, give the customer a brief,
#     natural confirmation that the order has been successfully placed.
#     - The confirmation must be short and concise.
#     - Do NOT repeat the ordered items or quantities.
#     - Do NOT repeat the delivery address.
#     - Do NOT repeat the total amount or bill.
#     - Do NOT mention the order ID.
#     - Do NOT ask for confirmation again.
#     - Do NOT provide any additional order details.

#     IMPORTANT:
#     - After successful order creation, respond with ONLY a short,
#     natural order-success confirmation.
#     - The wording should be generated naturally by the assistant.
#     - Do not use a fixed or hard-coded sentence.
#     - The assistant may phrase the confirmation differently each time,
#     while keeping the same meaning.
#     - The examples below are ONLY for demonstrating the expected style.
#     They are NOT actual customer responses and must NOT be copied or
#     treated as real order information.
#     - Always generate the final confirmation based on the current
#     conversation and successful tool result.

#     EXAMPLE STYLE ONLY:
#     - "Aapka order successfully place ho gaya hai."
#     - "Ji, aapka order place ho gaya hai."
#     - "Order successfully confirm ho gaya hai."

#     IMPORTANT:
#     The example phrases above are illustrative only. Do NOT use these
#     examples as actual order data or assume their wording must be repeated.

#     EXAMPLE FLOW:
#     Customer: "Haan, order final kar do."
#     Assistant: Call create_order(...)
#     Tool: Successful order creation.
#     Assistant: Confirm successful order creation to the customer.
#     """
#     return await restaurant_service.create_order(
#         owner_id=owner_id,
#         items=items,
#         special_notes=special_notes,
#         customer_phone=customer_phone,
#         order_type=order_type,
#         table_number=table_number,
#     )


# # =============================================================================
# # UPDATE ORDER
# # =============================================================================

# @tool
# async def update_order(
#     order_id: str | None = None,
#     customer_phone: str | None = None,
#     items: list[dict[str, Any]] | None = None,
#     special_notes: str | None = None,
#     order_type: str | None = None,
#     table_number: str | None = None,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Modify an existing active/pending restaurant order.

#     PURPOSE:
#     Update an order that has already been created and is still eligible
#     for modification.

#     USE THIS TOOL WHEN:
#     - The customer wants to change item quantity.
#     - The customer wants to add or remove an item.
#     - The customer wants to update item notes.
#     - The customer wants to update order-level special notes.
#     - The customer wants to change the order type when permitted.
#     - The customer wants to update the table number when applicable.

#     EXAMPLES:
#     - "Dal Makhni 2 kar do."
#     - "Ek naan add kar do."
#     - "Paneer Tikka hata do."
#     - "Order mein less spicy likh do."
#     - "Table number 12 kar do."

#     DO NOT USE THIS TOOL:
#     - To create a new order.
#     - To cancel an order.
#     - If there is no existing active/pending order.
#     - If the requested update contains no actual business-field change.

#     ORDER IDENTIFICATION:
#     - Use order_id when the exact order ID is known.
#     - Otherwise customer_phone may be used to locate the customer's
#       eligible pending/active order.
#     - Never use another customer's order.
#     - The backend must scope order lookup by owner_id.

#     ITEMS:
#     Each item update should contain:
#     - menu_item_id
#     - quantity
#     - notes, when applicable

#     QUANTITY RULE:
#     - quantity > 0 means set/update the quantity.
#     - quantity = 0 means remove the item, if supported by the backend.

#     IMPORTANT:
#     - Never invent menu_item_id.
#     - Use authoritative menu data when a new menu item is being added.
#     - Do not call this tool with an empty update request.
#     - The backend must validate that the order exists, belongs to the
#       correct owner, is still modifiable, and that requested changes
#       are valid.

#     ARGUMENTS:
#     - order_id:
#         MongoDB _id of the existing order.

#     - customer_phone:
#         Customer phone number used to locate an eligible pending order
#         when order_id is not known.

#     - items:
#         Optional list of item updates.

#     - special_notes:
#         Optional updated order-level instructions.

#     - order_type:
#         Optional new order type.

#     - table_number:
#         Optional table number, required when applicable to DINE_IN.

#     - owner_id:
#         Automatically injected from authenticated application state.

#     AFTER SUCCESS:
#     - Check the tool result.
#     - Tell the customer the order was updated only if the tool confirms
#       that an actual update was successfully performed.
#     """
#     return await restaurant_service.update_order(
#         owner_id=owner_id,
#         order_id=order_id,
#         customer_phone=customer_phone,
#         items=items,
#         special_notes=special_notes,
#         order_type=order_type,
#         table_number=table_number,
#     )


# # =============================================================================
# # CANCEL ORDER
# # =============================================================================

# @tool
# async def cancel_order(
#     order_id: str | None = None,
#     customer_phone: str | None = None,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Handle a customer's request to cancel an existing restaurant order.

#     BUSINESS RULE:
#     The assistant MUST NOT cancel the order directly.

#     WHEN TO USE:
#     - The customer explicitly asks to cancel their order.

#     EXAMPLES:
#     - "Mera order cancel kar do."
#     - "Order mat lao."
#     - "I want to cancel my order."
#     - "Cancel my pending order."

#     DO NOT:
#     - Change the order status to CANCELLED.
#     - Delete the order.
#     - Modify the order.
#     - Tell the customer that the order has been cancelled.

#     REQUIRED CUSTOMER RESPONSE:
#     Tell the customer:

#     "Sorry, cancellation ke liye hamare representative aapse baat karenge."

#     ORDER DATA:
#     - order_id may identify the customer's order.
#     - customer_phone may be used when order_id is not known.
#     - owner_id is automatically injected from authenticated application
#       state.

#     IMPORTANT:
#     This tool must not perform an actual cancellation unless the
#     restaurant's business workflow explicitly requires creating a
#     separate cancellation request.

#     AFTER TOOL EXECUTION:
#     Do not claim that the order was cancelled.
#     """
#     return {
#         "success": True,
#         "cancelled": False,
#         "message": (
#             "Sorry, cancellation ke liye hamare representative "
#             "aapse baat karenge."
#         ),
#     }


# # =============================================================================
# # PDF KNOWLEDGE SEARCH TOOL
# # =============================================================================

# @tool
# async def search_pdf_knowledge(
#     query: str,
#     owner_id: Annotated[
#         str,
#         InjectedState("owner_id"),
#     ] = "",
# ) -> dict[str, Any]:
#     """
#     Search the restaurant's uploaded PDF/vector database and answer
#     only the customer's actual question.

#     PURPOSE:
#     Use this tool to retrieve information from the restaurant's uploaded
#     PDF documents stored in the vector database.

#     This tool can retrieve:
#     - Restaurant information
#     - Address and contact information
#     - Restaurant policies and rules
#     - Menu categories
#     - Items inside a requested category
#     - Specific menu items
#     - Item variants
#     - Prices
#     - Other information explicitly contained in the uploaded PDF

#     CORE RESPONSE RULE:
#     ANSWER ONLY WHAT THE CUSTOMER ASKED.

#     Do NOT provide a general menu summary when the customer asks about
#     one specific category, item, price, policy, or piece of information.

#     Examples:

#     Customer:
#     "Breads mein kya hai?"

#     Correct:
#     Return only the relevant BREADS information.

#     Incorrect:
#     Do NOT additionally list Soups, Starters, Salads, Main Course,
#     Meals, Party Packs, or other unrelated categories.

#     Customer:
#     "Murg Kali Mirch kitne ki hai?"

#     Correct:
#     Return only the relevant Murg Kali Mirch price/variant information.

#     Incorrect:
#     Do NOT list other Main Course items.

#     Customer:
#     "Restaurant ka address kya hai?"

#     Correct:
#     Return only the restaurant address supported by the PDF.

#     Incorrect:
#     Do NOT return the complete restaurant menu.

#     Customer:
#     "Menu mein kaunsi categories hain?"

#     Correct:
#     Return the available categories from the PDF.

#     Incorrect:
#     Do NOT list every item inside every category unless the customer
#     explicitly asks for those items.

#     Customer:
#     "Soups mein kya kya hai?"

#     Correct:
#     Return only the items belonging to the SOUPS category.

#     Incorrect:
#     Do NOT include Salads, Starters, Breads, Main Course, etc.

#     SEARCH RULES:
#     - Search only the uploaded PDF/vector database.
#     - Use the customer's query as the search intent.
#     - Return information supported by the retrieved PDF content.
#     - Do not invent or guess information.
#     - Do not add unrelated information.
#     - Do not generate a broad menu summary unless the customer explicitly
#       asks for a full menu or broad menu overview.
#     - Preserve the actual names, prices, categories, subcategories,
#       variants, and other terminology found in the PDF.
#     - If the requested information is not found, clearly say that it
#       could not be found in the uploaded PDF.

#     CATEGORY SEARCH:
#     When the customer asks for items from a specific category, return
#     only items belonging to that category.

#     For example:
#     "Breads mein kya hai?"
#     → Return BREADS items only.

#     "Desserts mein kya hai?"
#     → Return DESSERTS items only.

#     "Rice mein kya hai?"
#     → Return RICE items only.

#     Do NOT mix results from other categories simply because they are
#     semantically similar.

#     SPECIFIC ITEM SEARCH:
#     When the customer asks about one item, focus only on that item.

#     If multiple variants exist, return only the variants relevant to the
#     customer's question. If the customer asks generally about the item,
#     variants may be included when they are necessary to answer correctly.

#     PRICE:
#     - Return the actual price found in the PDF.
#     - Never invent or guess a price.
#     - Do not substitute a price from another item.
#     - Keep different variants and their prices correctly associated.

#     RESTAURANT INFORMATION:
#     For questions about address, phone number, restaurant rules,
#     policies, packing charges, timings, or other restaurant-specific
#     information contained in the uploaded PDF, use the vector database
#     result as the source.

#     OWNER ISOLATION:
#     - Search only the data belonging to the injected owner_id.
#     - Never ask the customer for owner_id.
#     - Never invent owner_id.

#     RESPONSE SIZE:
#     - Be concise.
#     - Give exactly the information necessary to answer the customer's
#       question.
#     - Do not add unrelated categories or menu sections.
#     - Do not provide a "summary" unless the customer asks for a summary.
#     - Do not say "menu mein aur bhi items hain" unless this is actually
#       relevant to the customer's request.

#     IMPORTANT:
#     The tool retrieves information.
#     The assistant must then answer the customer naturally using only
#     the relevant retrieved information.

#     Never fabricate information.
#     Never broaden the customer's request.
#     Never turn a specific question into a complete menu response.

#     RETRIEVAL RULE:
#     - For specific-item or general semantic questions, retrieve only the
#     most relevant results.
#     - For category browsing, do not use a fixed semantic top_k as the
#     category limit.
#     - Category requests must use the category metadata/filter and retrieve
#     only items belonging to the requested category.
#     - The customer-facing response should present the category items in
#     controlled batches.

#     ARGUMENTS:
#     - query:
#         The customer's natural-language question.

#     - owner_id:
#         Automatically injected from authenticated application state.
#         Never ask the customer for this value.
#     """
#     return await restaurant_service.search_pdf_knowledge(
#         owner_id=owner_id,
#         query=query,
#         top_k=5,
#     )


# RESTAURANT_TOOLS = [
#     search_menu,
#     search_pdf_knowledge,
#     get_menu_item,
#     get_menu_categories,
#     get_menu_items_by_category,
#     create_order,
#     update_order,
#     cancel_order,
# ]




from typing import Any, Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from .tools import RestaurantTools


restaurant_service = RestaurantTools()


# =============================================================================
# MENU SEARCH  (PRIMARY discovery tool — Qdrant)
# =============================================================================

@tool
async def search_menu(
    query: str,
    top_k: int = 5,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Search the restaurant menu using semantic/vector search (Qdrant).

    ⭐ THIS IS THE PRIMARY TOOL for almost everything menu-related:
    existence checks, recommendations, discovery, "kya kya hai" style
    questions, and general browsing. Use this FIRST for any menu
    question that is not an explicit price request.

    USE THIS TOOL WHEN:
    - The customer asks whether a menu item exists in the restaurant menu.
    - The customer asks whether a specific dish is available.
    - The customer mentions a specific menu item and wants to know if it is
      present in the menu.
    - The customer asks for menu recommendations.
    - The customer describes a food preference, craving, or requirement.
    - The customer asks for similar dishes.
    - The customer wants to discover menu items.

    DO NOT USE THIS TOOL FOR:
    - Retrieving authoritative PRICE information → use get_menu_item.
    - Creating an order.
    - Updating an existing order.
    - Cancelling an order.

    DATA SOURCE RULES:
    - Qdrant/vector search is used for menu discovery and item identification.
    - Use the search result to determine whether the requested item exists
      in the restaurant menu.
    - Never treat Qdrant metadata as authoritative for price. Price shown
      here (if any) is indicative only — for a customer-facing price
      quote or before placing an order, confirm with get_menu_item.
    - Before creating an order, authoritative price must be confirmed via
      get_menu_item / the order-creation workflow.
    - Never invent a menu item when the search result does not identify it.

    RESPONSE HANDLING:
    - Base the customer-facing response only on the actual menu information
      returned by the tool.
    - If the requested item is found, the assistant may tell the customer
      that the item is available in the menu.
    - If the requested item is not found, do not claim that it is available.
    - Do not invent availability, price, or other menu details.

    ARGUMENTS:
    - query:
        The customer's natural-language menu request, dish name,
        preference, or search query.

    - top_k:
        Maximum number of relevant menu results to return.

    - owner_id:
        Automatically injected from authenticated application state.
        Never ask the customer for this value or invent it.

    IMPORTANT:
    This tool is responsible for menu discovery and identification.
    Authoritative PRICE must come from get_menu_item — never rely on
    this tool's price field for a final quote.
    """
    return await restaurant_service.search_menu(
        owner_id=owner_id,
        query=query,
        top_k=top_k,
    )


# =============================================================================
# EXACT MENU ITEM  (PRICE-ONLY — MongoDB)
# =============================================================================

@tool
async def get_menu_item(
    menu_item_name: str,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Retrieve authoritative PRICE for a menu item from MongoDB.

    ⚠️ PRICE-ONLY TOOL. This is the ONLY reason to call MongoDB directly.
    Do NOT use this for discovery, browsing, existence checks, or
    category listing — use search_menu / search_pdf_knowledge (Qdrant)
    for all of that.

    USE THIS TOOL ONLY WHEN:
    - The customer explicitly asks for the PRICE of a specific,
      already-identified item.
    - You need the authoritative price right before confirming an order
      total with the customer.

    DO NOT USE THIS TOOL FOR:
    - Discovering or searching menu items → use search_menu.
    - Checking if an item exists → use search_menu.
    - Recommendations or "kya kya hai" style questions → use search_menu
      or search_pdf_knowledge.
    - Browsing categories or items inside a category → use
      search_pdf_knowledge.
    - Creating an order.
    - Updating an existing order.
    - Cancelling an order.

    DATA SOURCE RULES:
    - MongoDB is the authoritative source for price ONLY.
    - Never use Qdrant/vector-search metadata as the authoritative price.
    - Never guess the price.
    - Only return or communicate information supported by the MongoDB
      result.

    ARGUMENTS:
    - menu_item_name:
        The menu item name that has already been identified (via
        search_menu / search_pdf_knowledge, or stated directly by the
        customer).

    - owner_id:
        Automatically injected from authenticated application state.
        Never ask the customer for this value or invent it.

    RESPONSE HANDLING:
    - Base any customer-facing information on the actual MongoDB result.
    - If the item cannot be found or verified, do not invent its details.
    - Do not expose internal database information or implementation details.
    """
    return await restaurant_service.get_menu_item(
        owner_id=owner_id,
        menu_item_name=menu_item_name,
    )


# =============================================================================
# CREATE ORDER
# =============================================================================

@tool
async def create_order(
    items: list[dict[str, Any]],
    special_notes: str | None = None,
    customer_phone: str | None = None,
    order_type: str = "DELIVERY",
    table_number: str | None = None,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Create a new finalized restaurant order in MongoDB.

    PURPOSE:
    Create the customer's final order after the customer has explicitly
    confirmed the complete order summary and total amount.

    USE THIS TOOL ONLY WHEN:
    - The customer has explicitly confirmed the final order.
    - The final items and quantities are known.
    - The order type and required order information are available.

    EXPLICIT CONFIRMATION IS REQUIRED:
    The customer must clearly confirm that they want the final order placed.

    VALID CONFIRMATIONS INCLUDE:
    - "Haan order kar do."
    - "Yes, place the order."
    - "Order final kar do."
    - "Haan, yehi order chahiye."
    - "Confirm kar do."

    DO NOT USE THIS TOOL:
    - Before explicit customer confirmation.
    - While the customer is still deciding what to order.
    - While the customer is adding/removing/changing items.
    - To calculate or guess prices.
    - To invent menu_item_id values.
    - To modify an existing order.

    REQUIREMENTS:
    1. Customer confirmation must happen BEFORE this tool call.
    2. Every ordered item must contain item_name and quantity.
    3. item_name must be the exact dish name as identified via search_menu
       / search_pdf_knowledge (e.g. "Paneer Butter Masala") — do NOT
       append category names or extra text to it.
    4. The backend will authoritatively re-fetch price and menu_item_id
       from MongoDB using item_name — you do NOT need to pass them.
    5. NEVER invent or pass a menu_item_id — it will be ignored and
       overwritten by the authoritative database value.
    6. Quantity must be valid and greater than zero.
    7. order_type must be DELIVERY, TAKEAWAY, or DINE_IN.
    8. table_number is required for DINE_IN.
    9. Backend validation remains authoritative for item existence,
       availability, price, quantity, and order total. If any item
       cannot be matched in the database, the order will be REJECTED
       rather than saved with an incorrect price.

    ARGUMENTS:
    - items:
        List of ordered items. Each item must contain:
        - item_name  : The exact menu item name.
        - quantity   : Number of this item to order (REQUIRED).
        - notes      : Optional item-specific instruction (e.g. "No onion").
        DO NOT pass menu_item_id — the backend fetches it from the DB.

    - special_notes:
        Optional order-level instructions.

    - customer_phone:
        Optional customer phone number associated with the order.

    - order_type:
        Order fulfillment type: DELIVERY, TAKEAWAY, or DINE_IN.

    - table_number:
        Table number for DINE_IN orders.

    - owner_id:
        Automatically injected from authenticated application state.
        Never ask the customer for owner_id or invent it.

    AFTER SUCCESS:
    - If the tool result is a success, give the customer a brief, natural
      confirmation that the order has been placed. Do NOT repeat items,
      quantities, address, total, or order ID. Do NOT ask for confirmation
      again.

    AFTER FAILURE (e.g. item not found):
    - Tell the customer, naturally, that the item(s) could not be
      confirmed and ask them to re-select from the menu — do NOT claim
      the order was placed.

    EXAMPLE FLOW:
    Customer: "Haan, order final kar do."
    Assistant: Call create_order(...)
    Tool: Successful order creation.
    Assistant: Confirm successful order creation to the customer.
    """
    return await restaurant_service.create_order(
        owner_id=owner_id,
        items=items,
        special_notes=special_notes,
        customer_phone=customer_phone,
        order_type=order_type,
        table_number=table_number,
    )


# =============================================================================
# UPDATE ORDER
# =============================================================================

@tool
async def update_order(
    order_id: str | None = None,
    customer_phone: str | None = None,
    items: list[dict[str, Any]] | None = None,
    special_notes: str | None = None,
    order_type: str | None = None,
    table_number: str | None = None,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Modify an existing active/pending restaurant order.

    PURPOSE:
    Update an order that has already been created and is still eligible
    for modification.

    USE THIS TOOL WHEN:
    - The customer wants to change item quantity.
    - The customer wants to add or remove an item.
    - The customer wants to update item notes.
    - The customer wants to update order-level special notes.
    - The customer wants to change the order type when permitted.
    - The customer wants to update the table number when applicable.

    EXAMPLES:
    - "Dal Makhni 2 kar do."
    - "Ek naan add kar do."
    - "Paneer Tikka hata do."
    - "Order mein less spicy likh do."
    - "Table number 12 kar do."

    DO NOT USE THIS TOOL:
    - To create a new order.
    - To cancel an order.
    - If there is no existing active/pending order.
    - If the requested update contains no actual business-field change.

    ORDER IDENTIFICATION:
    - Use order_id when the exact order ID is known.
    - Otherwise customer_phone may be used to locate the customer's
      eligible pending/active order.
    - Never use another customer's order.
    - The backend must scope order lookup by owner_id.

    ITEMS:
    Each item update should contain:
    - item_name (exact dish name, from search_menu / search_pdf_knowledge)
    - quantity
    - notes, when applicable
    Do NOT pass menu_item_id — the backend resolves it authoritatively.

    QUANTITY RULE:
    - quantity > 0 means set/update the quantity.
    - quantity = 0 means remove the item, if supported by the backend.

    IMPORTANT:
    - Never invent menu_item_id.
    - Use search_menu / search_pdf_knowledge to identify a NEW item being
      added; authoritative price is resolved by the backend from MongoDB.
    - Do not call this tool with an empty update request.
    - The backend must validate that the order exists, belongs to the
      correct owner, is still modifiable, and that requested changes
      are valid. If an item cannot be matched in the database, that
      item update will be REJECTED rather than saved with price 0.

    ARGUMENTS:
    - order_id:
        MongoDB _id of the existing order.

    - customer_phone:
        Customer phone number used to locate an eligible pending order
        when order_id is not known.

    - items:
        Optional list of item updates.

    - special_notes:
        Optional updated order-level instructions.

    - order_type:
        Optional new order type.

    - table_number:
        Optional table number, required when applicable to DINE_IN.

    - owner_id:
        Automatically injected from authenticated application state.

    AFTER SUCCESS:
    - Check the tool result.
    - Tell the customer the order was updated only if the tool confirms
      that an actual update was successfully performed.

    AFTER FAILURE (e.g. item not found):
    - Tell the customer the item(s) could not be confirmed and do not
      claim the order was updated.
    """
    return await restaurant_service.update_order(
        owner_id=owner_id,
        order_id=order_id,
        customer_phone=customer_phone,
        items=items,
        special_notes=special_notes,
        order_type=order_type,
        table_number=table_number,
    )


# =============================================================================
# CANCEL ORDER
# =============================================================================

@tool
async def cancel_order(
    order_id: str | None = None,
    customer_phone: str | None = None,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Handle a customer's request to cancel an existing restaurant order.

    BUSINESS RULE:
    The assistant MUST NOT cancel the order directly.

    WHEN TO USE:
    - The customer explicitly asks to cancel their order.

    EXAMPLES:
    - "Mera order cancel kar do."
    - "Order mat lao."
    - "I want to cancel my order."
    - "Cancel my pending order."

    DO NOT:
    - Change the order status to CANCELLED.
    - Delete the order.
    - Modify the order.
    - Tell the customer that the order has been cancelled.

    REQUIRED CUSTOMER RESPONSE:
    Tell the customer:

    "Sorry, cancellation ke liye hamare representative aapse baat karenge."

    ORDER DATA:
    - order_id may identify the customer's order.
    - customer_phone may be used when order_id is not known.
    - owner_id is automatically injected from authenticated application
      state.

    IMPORTANT:
    This tool must not perform an actual cancellation unless the
    restaurant's business workflow explicitly requires creating a
    separate cancellation request.

    AFTER TOOL EXECUTION:
    Do not claim that the order was cancelled.
    """
    return {
        "success": True,
        "cancelled": False,
        "message": (
            "Sorry, cancellation ke liye hamare representative "
            "aapse baat karenge."
        ),
    }


# =============================================================================
# PDF KNOWLEDGE SEARCH TOOL  (PRIMARY tool for categories, browsing, info — Qdrant)
# =============================================================================

@tool
async def search_pdf_knowledge(
    query: str,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Search the restaurant's uploaded PDF/vector database and answer
    only the customer's actual question.

    ⭐ THIS IS THE PRIMARY TOOL for categories, category browsing, item
    listing, restaurant info (address, policies, timings), and any
    "kya hai / kaunsa hai" style question. Use this — NOT MongoDB —
    for all of that. Only use get_menu_item (MongoDB) when the customer
    explicitly wants a confirmed PRICE.

    PURPOSE:
    Use this tool to retrieve information from the restaurant's uploaded
    PDF documents stored in the vector database.

    This tool can retrieve:
    - Restaurant information
    - Address and contact information
    - Restaurant policies and rules
    - Menu categories
    - Items inside a requested category
    - Specific menu items
    - Item variants
    - Prices (indicative — for a final/confirmed price use get_menu_item)
    - Other information explicitly contained in the uploaded PDF

    CORE RESPONSE RULE:
    ANSWER ONLY WHAT THE CUSTOMER ASKED.

    Do NOT provide a general menu summary when the customer asks about
    one specific category, item, price, policy, or piece of information.

    Examples:

    Customer:
    "Breads mein kya hai?"

    Correct:
    Return only the relevant BREADS information.

    Incorrect:
    Do NOT additionally list Soups, Starters, Salads, Main Course,
    Meals, Party Packs, or other unrelated categories.

    Customer:
    "Murg Kali Mirch kitne ki hai?"

    Correct:
    Retrieve the item here for identification, but confirm the
    authoritative price via get_menu_item before quoting a final number.

    Incorrect:
    Do NOT list other Main Course items. Do NOT quote this tool's price
    as final — confirm with get_menu_item.

    Customer:
    "Restaurant ka address kya hai?"

    Correct:
    Return only the restaurant address supported by the PDF.

    Incorrect:
    Do NOT return the complete restaurant menu.

    Customer:
    "Menu mein kaunsi categories hain?"

    Correct:
    Return the available categories from the PDF.

    Incorrect:
    Do NOT list every item inside every category unless the customer
    explicitly asks for those items.

    Customer:
    "Soups mein kya kya hai?"

    Correct:
    Return only the items belonging to the SOUPS category.

    Incorrect:
    Do NOT include Salads, Starters, Breads, Main Course, etc.

    SEARCH RULES:
    - Search only the uploaded PDF/vector database.
    - Use the customer's query as the search intent.
    - Return information supported by the retrieved PDF content.
    - Do not invent or guess information.
    - Do not add unrelated information.
    - Do not generate a broad menu summary unless the customer explicitly
      asks for a full menu or broad menu overview.
    - Preserve the actual names, prices, categories, subcategories,
      variants, and other terminology found in the PDF.
    - If the requested information is not found, clearly say that it
      could not be found in the uploaded PDF.

    CATEGORY SEARCH:
    When the customer asks for items from a specific category, return
    only items belonging to that category.

    For example:
    "Breads mein kya hai?" → Return BREADS items only.
    "Desserts mein kya hai?" → Return DESSERTS items only.
    "Rice mein kya hai?" → Return RICE items only.

    Do NOT mix results from other categories simply because they are
    semantically similar.

    SPECIFIC ITEM SEARCH:
    When the customer asks about one item, focus only on that item.

    If multiple variants exist, return only the variants relevant to the
    customer's question.

    PRICE:
    - The price shown here is from the PDF/vector store and is
      INDICATIVE ONLY.
    - For a customer-facing price quote, or right before order creation,
      confirm the authoritative price via get_menu_item.
    - Never invent or guess a price. Never substitute a price from
      another item.

    RESTAURANT INFORMATION:
    For questions about address, phone number, restaurant rules,
    policies, packing charges, timings, or other restaurant-specific
    information contained in the uploaded PDF, use the vector database
    result as the source.

    OWNER ISOLATION:
    - Search only the data belonging to the injected owner_id.
    - Never ask the customer for owner_id.
    - Never invent owner_id.

    RESPONSE SIZE:
    - Be concise.
    - Give exactly the information necessary to answer the customer's
      question.
    - Do not add unrelated categories or menu sections.
    - Do not provide a "summary" unless the customer asks for a summary.

    IMPORTANT:
    The tool retrieves information. The assistant must then answer the
    customer naturally using only the relevant retrieved information.
    Never fabricate information. Never broaden the customer's request.

    RETRIEVAL RULE:
    - For specific-item or general semantic questions, retrieve only the
      most relevant results.
    - For category browsing, do not use a fixed semantic top_k as the
      category limit — retrieve by category metadata/filter and present
      in controlled batches.

    ARGUMENTS:
    - query:
        The customer's natural-language question.

    - owner_id:
        Automatically injected from authenticated application state.
        Never ask the customer for this value.
    """
    return await restaurant_service.search_pdf_knowledge(
        owner_id=owner_id,
        query=query,
        top_k=5,
    )


# NOTE: get_menu_categories and get_menu_items_by_category (MongoDB-backed)
# are intentionally NOT registered below. Category listing and category
# browsing are now handled entirely by search_pdf_knowledge (Qdrant).
# MongoDB is only ever hit via get_menu_item (price) or inside
# create_order / update_order (price resolution at order time). The
# service methods still exist in RestaurantTools for internal/admin use
# but are not exposed to the agent.

RESTAURANT_TOOLS = [
    search_menu,
    search_pdf_knowledge,
    get_menu_item,
    create_order,
    update_order,
    cancel_order,
]