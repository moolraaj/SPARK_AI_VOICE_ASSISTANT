import json
from openai import AsyncOpenAI
from app.core.config import settings
from .token_calculator import calculate_openai_cost


async def check_domain_relevance_with_ai(
    raw_text: str,
    business_type_name: str
) -> tuple[bool, str]:
    """
    AI-Powered Domain Relevance Gate using OpenAI.
    Checks if the document content matches the owner's registered Business Type.
    No hardcoded keywords — fully AI-driven classification.
    """
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Use only first 1500 chars for fast/cheap classification call
        sample_text = raw_text[:1500].strip()

        if not sample_text:
            return False, "Document appears to be empty or unreadable."

        prompt = f"""You are a document domain classifier for a multi-business AI platform.

A business owner has registered their business as: "{business_type_name}"
They uploaded a document. Below is a sample of the document's extracted text:

---
{sample_text}
---

Your task:
1. Determine if this document is relevant to the business type "{business_type_name}".
2. A document is RELEVANT if it contains information that a "{business_type_name}" business would use (e.g. menus, prices, policies, schedules, product lists, FAQs, rules, guidelines related to that business).
3. A document is IRRELEVANT if it belongs to a completely different domain (e.g. a school textbook uploaded for a restaurant, a hospital manual uploaded for a hotel shop).

Respond ONLY in this exact JSON format (no explanation, no markdown):
{{"is_relevant": true, "reason": "Brief reason why it matches or not"}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=120,
        )

        if response.usage:
            usage = calculate_openai_cost(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                model="gpt-4o-mini"
            )
            print(f"💰 [LLM LOG - Domain Check] Tokens: {usage['total_tokens']} (Prompt: {usage['prompt_tokens']}, Completion: {usage['completion_tokens']}) | Cost: {usage['formatted_cost']}")

        result_text = response.choices[0].message.content.strip()

        # Strip markdown fences if any
        if result_text.startswith("```"):
            result_text = result_text.strip("`").strip()
            if result_text.startswith("json"):
                result_text = result_text[4:].strip()

        result = json.loads(result_text)
        is_relevant = result.get("is_relevant", True)
        reason = result.get("reason", "")

        if not is_relevant:
            return False, f"Upload Rejected: {reason}"

        return True, "Accepted"

    except Exception as e:
        # If AI check fails for any reason, allow the upload (fail-open strategy)
        return True, "Accepted (AI check skipped)"
