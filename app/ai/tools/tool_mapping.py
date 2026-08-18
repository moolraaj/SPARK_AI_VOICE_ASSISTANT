from .restaurant.tools import RestaurantTools

tools=RestaurantTools()

RESTAURANT_TOOLS = {
    "search_menu": tools.search_menu,
    "get_menu_item": tools.get_menu_item,
    "get_menu_categories": tools.get_menu_categories,
    "get_menu_items_by_category": tools.get_menu_items_by_category,

}