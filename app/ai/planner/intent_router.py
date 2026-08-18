from openai import AsyncOpenAI

from app.core.config import OPENAI_API_KEY
from app.ai.models.intent_output import IntentRouterOutput

from app.ai.prompts.common_prompt import COMMON_INTENT_PROMPT
from app.ai.prompts.restaurant_prompt import RESTAURANT_INTENT_PROMPT


class IntentRouter:

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY
        )

        self.domain_prompts = {
            "RESTAURANT": RESTAURANT_INTENT_PROMPT,
        }

    async def classify(
        self,
        user_message: str,
        business_type: str,
    ) -> IntentRouterOutput:

        business_type = business_type.upper().strip()

        domain_prompt = self.domain_prompts.get(business_type)

        if not domain_prompt:
            raise ValueError(
                f"No intent configuration found for business type: "
                f"{business_type}"
            )

        system_prompt = f"""
You are the Intent Router for an AI Employee.

Your ONLY job is to classify the customer's message.

You MUST:

1. Select exactly one intent.
2. Extract entities explicitly present in the message.
3. Return only the required structured output.
4. Never answer the customer.
5. Never invent information.
6. Never invent entities.
7. Use the business-specific intent definitions provided below.

CURRENT BUSINESS TYPE:
{business_type}

{COMMON_INTENT_PROMPT}

{domain_prompt}
"""

        user_prompt = f"""
CUSTOMER MESSAGE:

{user_message}
"""

        response = await self.client.responses.parse(
            model="gpt-5.6",
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            text_format=IntentRouterOutput,
        )

        if response.output_parsed is None:
            raise ValueError(
                "Intent Router returned no structured output."
            )

        return response.output_parsed