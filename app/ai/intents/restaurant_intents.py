from enum import Enum


class RestaurantIntent(str, Enum):

    # Menu & Catalog
    MENU_PRICE_INQUIRY = "MENU_PRICE_INQUIRY"
    MENU_AVAILABILITY_INQUIRY = "MENU_AVAILABILITY_INQUIRY"
    MENU_ITEM_DETAILS = "MENU_ITEM_DETAILS"
    MENU_CATEGORY_LISTING = "MENU_CATEGORY_LISTING"
    MENU_CATEGORY_ITEMS_LISTING = "MENU_CATEGORY_ITEMS_LISTING"

    # Suggestions & Recommendations
    FOOD_RECOMMENDATION = "FOOD_RECOMMENDATION"
    BESTSELLER_POPULAR_ITEMS = "BESTSELLER_POPULAR_ITEMS"

    # Ordering & Cart
    ORDER_CREATE = "ORDER_CREATE"
    ORDER_STATUS_INQUIRY = "ORDER_STATUS_INQUIRY"
    ORDER_CANCEL = "ORDER_CANCEL"

    # Table Booking & Reservations
    TABLE_BOOKING_CREATE = "TABLE_BOOKING_CREATE"
    TABLE_AVAILABILITY_CHECK = "TABLE_AVAILABILITY_CHECK"
    TABLE_BOOKING_CANCEL = "TABLE_BOOKING_CANCEL"

    # General & Support
    COMPLAINT_FEEDBACK = "COMPLAINT_FEEDBACK"
    RESTAURANT_INFORMATION = "RESTAURANT_INFORMATION"


RESTAURANT_INTENTS = {

    # =========================================================
    # MENU
    # =========================================================

    "MENU_PRICE_INQUIRY": {
        "description": (
            "Customer explicitly asks for the price, rate, cost, "
            "or amount of a specific menu item."
        ),
        "examples": [
            "Paneer tikka kitne ka hai?",
            "What is the price of Butter Chicken?",
            "Cold coffee ka price batao.",
            "Bhai iska rate kya hai?",
            "Dal makhni kitne ki hai?",
        ],
        "entities": [
            "menu_item_name",
        ],
    },

    "MENU_AVAILABILITY_INQUIRY": {
        "description": (
            "Customer explicitly asks whether a specific food or drink "
            "item is available or can be served currently or on a "
            "specified date/time."
        ),
        "examples": [
            "Aaj Hakka Noodles available hain?",
            "Do you have Cold Coffee right now?",
            "Pizza milega kya abhi?",
            "Butter chicken hai kya aaj?",
            "Dal makhni available hai?",
        ],
        "entities": [
            "menu_item_name",
        ],
    },

    "MENU_ITEM_DETAILS": {
        "description": (
            "Customer asks for factual details about a specific menu item, "
            "such as ingredients, preparation, veg/non-veg status, "
            "spice level, allergens, calories, portion size, or customization."
        ),
        "examples": [
            "Kya Dal Makhani veg hai?",
            "Pizza mein extra cheese hota hai kya?",
            "Is dish mein garlic hai?",
            "Kitna spicy hai ye paneer tikka?",
            "Kya is dish mein nuts hain?",
            "Dal makhni kaise banti hai?",
        ],
        "entities": [
            "menu_item_name",
            "detail_type",
        ],
    },

    "MENU_CATEGORY_LISTING": {
        "description": (
            "Customer wants to browse or list menu items under a category "
            "or wants to see the complete menu."
        ),
        "examples": [
            "Aapke paas desserts mein kya kya hai?",
            "Starters me kya kya hai?",
            "Full menu dikhao.",
            "Kya kya milta hai yahan?",
            "Drinks mein kya kya hai?",
        ],
        "entities": [
            "category_name",
        ],
    },

    "MENU_CATEGORY_ITEMS_LISTING": {
        "description": (
            "Customer wants to see menu items belonging to a specific "
            "category such as starters, desserts, beverages, or main course."
        ),
        "examples": [
            "Cold Beverages mein kya kya hai?",
            "Starters mein kya milta hai?",
            "Spicy category mein kya kya dishes hain?",
            "Desserts dikhao.",
            "Main course mein kya options hain?",
        ],
        "entities": [
            "category_name",
        ],
    },

    # =========================================================
    # RECOMMENDATIONS
    # =========================================================

    "FOOD_RECOMMENDATION": {
        "description": (
            "Customer asks for a personal food or drink recommendation "
            "based on taste, dietary preference, budget, meal type, "
            "occasion, or similar preference."
        ),
        "examples": [
            "Kuch spicy suggest karo.",
            "₹200 ke under koi acha snack batao.",
            "Dinner ke liye kya best rahega?",
            "Koi light veg option hai?",
            "What should I try for lunch?",
            "Mujhe spicy veg food chahiye, kya lu?",
        ],
        "entities": [
            "preference",
            "diet",
            "budget",
            "meal_type",
            "occasion",
        ],
    },

    "BESTSELLER_POPULAR_ITEMS": {
        "description": (
            "Customer asks which items are popular, famous, bestselling, "
            "signature, most ordered, or highly rated at the restaurant."
        ),
        "examples": [
            "Aapke cafe ki sabse best dish konsi hai?",
            "Top 3 most ordered items batao.",
            "Signature dish kya hai aapki?",
            "What's your specialty?",
            "Sabse zyada kya bikta hai?",
            "Aapka bestseller kya hai?",
        ],
        "entities": [],
    },

    # =========================================================
    # ORDER
    # =========================================================

    "ORDER_CREATE": {
        "description": (
            "Customer explicitly wants to place a new order or add "
            "food/drink items to an order for delivery, takeaway, "
            "or dine-in."
            
            "An explicit ordering intention is REQUIRED. "
            "Do NOT use this intent when the customer only mentions "
            "a food item or dish name without saying they want to order it."
        ),
        "examples": [
            "2 Plate Butter Naan aur 1 Kadhai Paneer pack kar do.",
            "Ek Cold Coffee order kar do.",
            "Mujhe 1 Cheese Pizza chahiye delivery ke liye.",
            "Dal makhani aur naan lena hai.",
            "Dal makhni order kar do.",
            "2 samose pack kar do.",
        ],
        "entities": [
            "order_items",
            "quantity",
            "order_type",
        ],
    },

    "ORDER_STATUS_INQUIRY": {
        "description": (
            "Customer asks about an existing order's status, progress, "
            "preparation, readiness, delivery, or estimated completion time."
        ),
        "examples": [
            "Mera order kaha tak pahucha?",
            "Kitna time aur lagega food aane mein?",
            "Is my pizza order ready?",
            "Kab tak deliver hoga?",
            "Maine jo order diya tha wo bana kya?",
        ],
        "entities": [
            "order_id",
            "customer_phone",
        ],
    },

    "ORDER_CANCEL": {
        "description": (
            "Customer explicitly wants to cancel an existing order "
            "or remove a specific item from an existing order."
        ),
        "examples": [
            "Mera order cancel kar do.",
            "Mujhe Cold Coffee cancel karni hai.",
            "Please cancel my order.",
            "Order rok do abhi.",
            "Jo order diya tha usko cancel karo.",
        ],
        "entities": [
            "order_id",
            "item_name",
        ],
    },

    # =========================================================
    # TABLE
    # =========================================================

    "TABLE_BOOKING_CREATE": {
        "description": (
            "Customer explicitly wants to create, reserve, or book "
            "a restaurant table."
        ),
        "examples": [
            "Aaj raat 8 baje 4 logon ke liye table book kar do.",
            "Can I reserve a table for 2 people tomorrow?",
            "Table booking karni hai kal sham ko.",
            "Aaj ke liye table chahiye.",
            "4 logon ke liye table reserve kar do.",
        ],
        "entities": [
            "guests_count",
            "date",
            "time",
        ],
    },

    "TABLE_AVAILABILITY_CHECK": {
        "description": (
            "Customer wants to know whether a table is available "
            "for a specified or implied date, time, or number of guests. "
            "This is an availability question, not a booking request."
        ),
        "examples": [
            "Kya 7 baje table khaali milegi?",
            "Do you have space for 6 people tonight?",
            "Aaj table milegi kya?",
            "Kal 4 logon ke liye table available hogi?",
        ],
        "entities": [
            "guests_count",
            "time",
            "date",
        ],
    },

    "TABLE_BOOKING_CANCEL": {
        "description": (
            "Customer explicitly wants to cancel an existing "
            "table reservation."
        ),
        "examples": [
            "Meri table booking cancel kar do.",
            "Kal ki reservation cancel karni hai.",
            "Please cancel my table reservation.",
        ],
        "entities": [
            "booking_id",
            "date",
            "time",
        ],
    },

    # =========================================================
    # SUPPORT
    # =========================================================

    "COMPLAINT_FEEDBACK": {
        "description": (
            "Customer expresses dissatisfaction, reports a problem, "
            "or gives negative feedback about food, an order, or service."
        ),
        "examples": [
            "Khana thanda aaya tha.",
            "Order bohot late ho gaya.",
            "Aapne galat item bhej diya.",
            "Food quality theek nahi thi.",
            "Mere khane mein baal aa gaya.",
            "Service bahut kharab thi.",
        ],
        "entities": [
            "complaint_text",
            "order_id",
            "item_name",
        ],
    },

    "RESTAURANT_INFORMATION": {
        "description": (
            "Customer asks for factual information about the restaurant, "
            "such as address, opening hours, closing hours, parking, WiFi, "
            "delivery area, contact number, or home delivery."
        ),
        "examples": [
            "WiFi password kya hai?",
            "Parking available hai?",
            "Restaurant kitne baje close hota hai?",
            "Address kya hai aapka?",
            "Do you have home delivery?",
        ],
        "entities": [
            "info_type",
        ],
    },
}