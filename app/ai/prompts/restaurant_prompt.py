from app.ai.intents.restaurant_intents import RESTAURANT_INTENTS


RESTAURANT_INTENT_PROMPT = f"""
## RESTAURANT INTENTS

{RESTAURANT_INTENTS}

## RESTAURANT CLASSIFICATION RULES

1. Select exactly ONE best matching restaurant intent.

2. Understand the customer's meaning and context,
   not only individual keywords.

3. If the customer provides incomplete information,
   still select the correct intent.

4. Missing information will be collected later
   by the appropriate workflow.

5. Never invent missing entities.

6. Extract only entities explicitly present
   in the customer's message.

7. If a greeting is combined with a restaurant request,
   select the restaurant intent instead of GREETING_CIVILITY.

8. MENU_PRICE_INQUIRY is specifically for asking
   the price of a known/specific menu item.

9. MENU_AVAILABILITY_INQUIRY is specifically for asking
   whether a specific item is available.

10. MENU_ITEM_DETAILS is for information about an item,
    such as ingredients, spice level, dietary properties,
    allergens, portion, or preparation.

11. MENU_CATEGORY_LISTING is for browsing menu categories
    or the full menu.

12. FOOD_RECOMMENDATION is for personal recommendations.

13. BESTSELLER_POPULAR_ITEMS is for asking what is popular,
    famous, signature, or most ordered.

14. ORDER_STATUS_INQUIRY is for an existing order.

15. ORDER_CREATE is for creating or adding to an order.

16. ORDER_CANCEL is for cancelling an existing order.

17. TABLE_BOOKING_CREATE is for creating a reservation.

18. TABLE_AVAILABILITY_CHECK is for checking whether
    a table is available.

19. TABLE_BOOKING_CANCEL is for cancelling an existing
    reservation.

20. COMPLAINT_FEEDBACK is for dissatisfaction or service issues.

21. RESTAURANT_INFORMATION is for factual restaurant information
    such as address, hours, parking, WiFi, delivery area, etc.

EXAMPLES:

"Good morning sir, Paneer tikka kitne ka hai?"
→ MENU_PRICE_INQUIRY

"Hello, kal 8 baje 4 logon ke liye table chahiye."
→ TABLE_BOOKING_CREATE

"Hi, mera order kaha tak pahucha?"
→ ORDER_STATUS_INQUIRY

"Kuch spicy suggest karo."
→ FOOD_RECOMMENDATION

"Restaurant kitne baje close hota hai?"
→ RESTAURANT_INFORMATION
"""