from typing import Any, Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from .tools import RestaurantTools


restaurant_service = RestaurantTools()


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
    Search the restaurant menu using natural language.

    Use this for recommendations, multiple dishes,
    preferences, ingredients, characteristics, or
    semantic menu searches.

    Examples:
    - "Kuch spicy veg suggest karo."
    - "Paneer ke dishes batao."
    - "Kuch light khana hai."
    - "300 ke andar kuch achha batao."
    - "Non-veg mein kya achha hai."

    Do NOT use this for one specific known menu item.
    """

    return await restaurant_service.search_menu(
        owner_id=owner_id,
        query=query,
        top_k=top_k,
    )


@tool
async def get_menu_item(
    menu_item_name: str,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Get information about ONE SPECIFIC known menu item.

    Use this for price, existence, or basic details
    of one specific menu item.

    Examples:
    - "Papdi Chaat kitne ki hai?"
    - "Dal Makhni ka price kya hai?"
    - "Paneer Tikka menu mein hai?"
    - "Butter Naan kitne ka hai?"

    Do NOT use this for recommendations or broad
    semantic searches.
    """

    return await restaurant_service.get_menu_item(
        owner_id=owner_id,
        menu_item_name=menu_item_name,
    )


@tool
async def get_menu_categories(
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Get the available menu categories of the restaurant.

    Use this when the customer wants to know the
    restaurant's menu sections or categories.

    Examples:
    - "Menu mein kya kya hai?"
    - "Kaun kaun si categories hain?"
    - "Food ke sections batao."
    - "Menu dikhao."
    """

    return await restaurant_service.get_menu_categories(
        owner_id=owner_id,
    )


@tool
async def get_menu_items_by_category(
    category_name: str,
    owner_id: Annotated[
        str,
        InjectedState("owner_id"),
    ] = "",
) -> dict[str, Any]:
    """
    Get menu items belonging to one specific category.

    Use this when the customer asks what items are
    available inside a specific category.

    Examples:
    - "Desserts mein kya hai?"
    - "Roti ke options batao."
    - "Soups mein kya milta hai."
    - "Rice category mein kya hai."
    """

    return await restaurant_service.get_menu_items_by_category(
        owner_id=owner_id,
        category_name=category_name,
    )


RESTAURANT_TOOLS = [
    search_menu,
    get_menu_item,
    get_menu_categories,
    get_menu_items_by_category,
]