from .restaurant.langchain_tools import (
    RESTAURANT_TOOLS,
)


# ── Tool Registry — business_type → tools list ──────────────────────────────
# Add new domain tools here as new business types are supported.
# GENERAL is used as a fallback for any unknown/unsupported business type.
TOOL_REGISTRY = {
    "RESTAURANT": RESTAURANT_TOOLS,
    "HOTEL":      RESTAURANT_TOOLS,     # TODO: replace with HOTEL_TOOLS when ready
    "EDUCATION":  RESTAURANT_TOOLS,     # TODO: replace with EDUCATION_TOOLS when ready
    "CLINIC":     RESTAURANT_TOOLS,     # TODO: replace with CLINIC_TOOLS when ready
    "RETAIL":     RESTAURANT_TOOLS,     # TODO: replace with RETAIL_TOOLS when ready
    "GENERAL":    RESTAURANT_TOOLS,     # Generic fallback
}