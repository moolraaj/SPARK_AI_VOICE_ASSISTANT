from enum import Enum


class RestaurantIntent(str, Enum):

    # Menu & Catalog
    MENU_PRICE_INQUIRY = "MENU_PRICE_INQUIRY"
    MENU_AVAILABILITY_INQUIRY = "MENU_AVAILABILITY_INQUIRY"
    MENU_ITEM_DETAILS = "MENU_ITEM_DETAILS"
    MENU_CATEGORY_LISTING = "MENU_CATEGORY_LISTING"

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

    "MENU_PRICE_INQUIRY": {
        "description": (
            "Customer asks for the price, rate, or cost of a specific "
            "menu item. Use ONLY when a specific item is mentioned. "
            "NOT for general budget recommendations."
        ),
        "examples": [
            "Paneer tikka kitne ka hai?",
            "What is the price of Butter Chicken?",
            "Cold coffee ka price batao.",
            "Bhai iska rate kya hai?",
        ],
        "entities": [
            "menu_item_name",
        ],
    },

    "MENU_AVAILABILITY_INQUIRY": {
        "description": (
            "Customer wants to know whether a specific food or drink "
            "item is currently available. NOT for general menu browsing."
        ),
        "examples": [
            "Aaj Hakka Noodles available hain?",
            "Do you have Cold Coffee right now?",
            "Pizza milega kya abhi?",
            "Butter chicken hai kya aaj?",
        ],
        "entities": [
            "menu_item_name",
        ],
    },

    "MENU_ITEM_DETAILS": {
        "description": (
            "Customer asks about details of a specific dish such as "
            "ingredients, veg/non-veg status, spice level, allergens, "
            "calories, portion size, customization, or preparation. "
            "NOT for price or availability."
        ),
        "examples": [
            "Kya Dal Makhani veg hai?",
            "Pizza mein extra cheese hota hai kya?",
            "Is dish mein garlic hai?",
            "Kitna spicy hai ye paneer tikka?",
            "Kya is dish mein nuts hain?",
        ],
        "entities": [
            "menu_item_name",
            "detail_type",
        ],
    },

    "MENU_CATEGORY_LISTING": {
        "description": (
            "Customer wants to browse items under a category such as "
            "starters, drinks, desserts, or wants to see the full menu."
        ),
        "examples": [
            "Aapke paas desserts mein kya kya hai?",
            "Starters me kya kya hai.",
            "Full menu dikhao.",
            "Kya kya milta hai yahan?",
        ],
        "entities": [
            "category_name",
        ],
    },

    "FOOD_RECOMMENDATION": {
        "description": (
            "Customer wants food or drink recommendations based on "
            "taste preference, diet, budget, meal type, or occasion."
        ),
        "examples": [
            "Kuch spicy suggest karo.",
            "₹200 ke under koi acha snack batao.",
            "Dinner ke liye kya best rahega?",
            "Koi light veg option hai?",
            "What should I try for lunch?",
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
            "Customer asks for the most ordered, most popular, "
            "highly rated, or signature dishes. This is about what "
            "is famous at the restaurant, not a personal recommendation."
        ),
        "examples": [
            "Aapke cafe ki sabse best dish konsi hai?",
            "Top 3 most ordered items batao.",
            "Signature dish kya hai aapki?",
            "What's your specialty?",
        ],
        "entities": [],
    },

    "ORDER_CREATE": {
        "description": (
            "Customer wants to place a new order or add food/drink "
            "items to the current order for delivery, takeaway, or dine-in."
        ),
        "examples": [
            "2 Plate Butter Naan aur 1 Kadhai Paneer pack kar do.",
            "Ek Cold Coffee order kar do.",
            "Mujhe 1 Cheese Pizza chahiye delivery ke liye.",
            "Dal makhani aur naan lena hai.",
        ],
        "entities": [
            "order_items",
            "quantity",
            "order_type",
        ],
    },

    "ORDER_STATUS_INQUIRY": {
        "description": (
            "Customer asks about the current status, progress, "
            "or estimated time of an existing order."
        ),
        "examples": [
            "Mera order kaha tak pahucha?",
            "Kitna time aur lagega food aane mein?",
            "Is my pizza order ready?",
            "Kab tak deliver hoga?",
        ],
        "entities": [
            "order_id",
            "customer_phone",
        ],
    },

    "ORDER_CANCEL": {
        "description": (
            "Customer wants to cancel an active order or remove "
            "a specific item from an order."
        ),
        "examples": [
            "Mera order cancel kar do.",
            "Mujhe Cold Coffee cancel karni hai.",
            "Please cancel my order.",
            "Order rok do abhi.",
        ],
        "entities": [
            "order_id",
            "item_name",
        ],
    },

    "TABLE_BOOKING_CREATE": {
        "description": (
            "Customer wants to reserve or book a restaurant table. "
            "Date, time, and guest count may be missing; the workflow "
            "will collect missing information later."
        ),
        "examples": [
            "Aaj raat 8 baje 4 logon ke liye table book kar do.",
            "Can I reserve a table for 2 people tomorrow?",
            "Table booking karni hai kal sham ko.",
            "Aaj ke liye table chahiye.",
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
            "for a specific time, date, or number of guests."
        ),
        "examples": [
            "Kya 7 baje table khaali milegi?",
            "Do you have space for 6 people tonight?",
            "Aaj table milegi kya?",
        ],
        "entities": [
            "guests_count",
            "time",
            "date",
        ],
    },

    "TABLE_BOOKING_CANCEL": {
        "description": (
            "Customer wants to cancel an existing table reservation."
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

    "COMPLAINT_FEEDBACK": {
        "description": (
            "Customer is expressing dissatisfaction or reporting "
            "a problem such as delayed food, wrong items, cold food, "
            "bad food quality, or poor service."
        ),
        "examples": [
            "Khana thanda aaya tha.",
            "Order bohot late ho gaya.",
            "Aapne galat item bhej diya.",
            "Food quality theek nahi thi.",
        ],
        "entities": [
            "complaint_text",
            "order_id",
            "item_name",
        ],
    },

    "RESTAURANT_INFORMATION": {
        "description": (
            "Customer asks for factual information about the restaurant "
            "such as WiFi password, address, opening hours, closing hours, "
            "delivery area, parking, contact number, or home delivery."
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