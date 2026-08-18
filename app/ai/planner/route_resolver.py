from typing import Any
from app.ai.models.intent_output import IntentRouterOutput
from app.ai.intents.common_intents import CommonIntent
from app.ai.intents.restaurant_intents import RestaurantIntent


RESTAURANT_INTENT_ROUTES: dict[str, dict[str, Any]] = {

    RestaurantIntent.MENU_PRICE_INQUIRY.value: {
        "route_type": "TOOL",
        "tool_name": "get_menu_item",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.MENU_AVAILABILITY_INQUIRY.value: {
        "route_type": "TOOL",
        "tool_name": "check_menu_item_availability",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.MENU_ITEM_DETAILS.value: {
        "route_type": "TOOL",
        "tool_name": "get_menu_item_details",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.MENU_CATEGORY_LISTING.value: {
        "route_type": "TOOL",
        "tool_name": "get_menu_categories",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.MENU_CATEGORY_ITEMS_LISTING.value: {
        "route_type": "TOOL",
        "tool_name": "get_menu_items_by_category",
        "execution_mode": "DIRECT",
    },

    # ── Recommendations ──────────────────────────────────────

    RestaurantIntent.FOOD_RECOMMENDATION.value: {
        "route_type": "TOOL",
        "tool_name": "search_menu",
        "execution_mode": "SEMANTIC",
    },

    RestaurantIntent.BESTSELLER_POPULAR_ITEMS.value: {
        "route_type": "TOOL",
        "tool_name": "search_menu",
        "execution_mode": "SEMANTIC",
    },

    # ── Orders ────────────────────────────────────────────────

    RestaurantIntent.ORDER_CREATE.value: {
        "route_type": "TOOL",
        "tool_name": "create_order",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.ORDER_STATUS_INQUIRY.value: {
        "route_type": "TOOL",
        "tool_name": "get_order_status",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.ORDER_CANCEL.value: {
        "route_type": "TOOL",
        "tool_name": "cancel_order",
        "execution_mode": "DIRECT",
    },

    # ── Tables ────────────────────────────────────────────────

    RestaurantIntent.TABLE_BOOKING_CREATE.value: {
        "route_type": "TOOL",
        "tool_name": "create_table_booking",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.TABLE_AVAILABILITY_CHECK.value: {
        "route_type": "TOOL",
        "tool_name": "check_table_availability",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.TABLE_BOOKING_CANCEL.value: {
        "route_type": "TOOL",
        "tool_name": "cancel_table_booking",
        "execution_mode": "DIRECT",
    },

    # ── Support ───────────────────────────────────────────────

    RestaurantIntent.COMPLAINT_FEEDBACK.value: {
        "route_type": "TOOL",
        "tool_name": "create_complaint",
        "execution_mode": "DIRECT",
    },

    RestaurantIntent.RESTAURANT_INFORMATION.value: {
        "route_type": "DIRECT_RESPONSE",
        "tool_name": None,
        "execution_mode": "DIRECT",
    },
}


# ─────────────────────────────────────────────────────────────
# Common Intent → Execution Route
# ─────────────────────────────────────────────────────────────

COMMON_INTENT_ROUTES: dict[str, dict[str, Any]] = {

    CommonIntent.GREETING_CIVILITY.value: {
        "route_type": "DIRECT_RESPONSE",
        "tool_name": None,
        "execution_mode": "DIRECT",
    },

    CommonIntent.OUT_OF_SCOPE.value: {
        "route_type": "DIRECT_RESPONSE",
        "tool_name": None,
        "execution_mode": "DIRECT",
    },
}


# ─────────────────────────────────────────────────────────────
# Route Resolver
# ─────────────────────────────────────────────────────────────

class RouteResolver:

    def resolve(
        self,
        router_output: IntentRouterOutput,
        business_type: str,
    ) -> dict[str, Any]:

        business_type = business_type.upper().strip()
        intent = router_output.intent.upper().strip()

        # Currently only restaurant routing is implemented.
        if business_type != "RESTAURANT":
            raise ValueError(
                f"Unsupported business type: {business_type}"
            )

        # Common intents are checked first.
        route = COMMON_INTENT_ROUTES.get(intent)

        # Then restaurant-specific intents.
        if route is None:
            route = RESTAURANT_INTENT_ROUTES.get(intent)

        if route is None:
            raise ValueError(
                f"No route configured for intent: {intent}"
            )

        return {
            "business_type": business_type,
            "intent": intent,
            "entities": router_output.entities,
            **route,
        }