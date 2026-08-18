from app.ai.intents.common_intents import COMMON_INTENTS


COMMON_INTENT_PROMPT = f"""
## COMMON INTENTS

{COMMON_INTENTS}

## COMMON CLASSIFICATION RULES

1. GREETING_CIVILITY
   Use when the customer is only greeting, thanking,
   showing courtesy, or saying goodbye.

2. OUT_OF_SCOPE
   Use when the customer request does not match any
   supported business/domain intent.

3. If a greeting is combined with a business request,
   classify the actual business request.

   Example:
   "Good morning sir, paneer tikka kitne ka hai?"
   → MENU_PRICE_INQUIRY

4. Never invent entities.

5. Extract only information explicitly present
   in the customer message.

6. Do not answer the customer.
   Only classify the request.
"""