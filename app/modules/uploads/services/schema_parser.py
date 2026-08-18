import re
import json
from openai import AsyncOpenAI
from app.core.config import settings
from .token_calculator import calculate_openai_cost


async def analyze_document_schema_with_ai(sample_text: str, business_type_name: str) -> tuple[list, dict | None]:
    """
    AI Schema Analyzer (Low Tokens ~150 max):
    Analyzes document text sample and extracts top-level categories.
    Outputs ~100 tokens max ($0.00003 / <1 paise cost).
    """
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = f"""You are an AI document structure analyzer for a {business_type_name} business platform.

Read this document sample and extract all top-level category names:
---
{sample_text[:1500]}
---

Return ONLY JSON format:
{{"categories": ["Starters", "Cold Beverages", "Soups", "Salads", "Paneer", "Vegetable", "Meals", "Roti", "Rice", "Thali", "Beverages", "Desserts"]}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"}
        )

        usage = None
        if response.usage:
            usage = calculate_openai_cost(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                model="gpt-4o-mini"
            )
            print(f"💰 [LLM LOG - AI Schema Analysis] Tokens: {usage['total_tokens']} (Prompt: {usage['prompt_tokens']}, Completion: {usage['completion_tokens']}) | Cost: {usage['formatted_cost']}")

        result_text = response.choices[0].message.content.strip()
        parsed = json.loads(result_text)
        cats = parsed.get("categories", [])
        return cats, usage
    except Exception:
        default_cats = ["Starters", "Cold Beverages", "Hot Beverages", "Soups", "Salads", "Paneer", "Vegetable", "Meals", "Roti", "Rice", "Thali", "Beverages", "Desserts"]
        return default_cats, None


def python_execute_categorized_parsing(raw_text: str, categories_list: list, business_type_name: str, file_name: str, llm_usage: dict | None) -> dict:
    """
    Python Execution Parser (Zero LLM Tokens):
    Parses all lines, expands multi-option items, tags meal times, and constructs final JSON.
    """
    lines = [
        line.strip() for line in raw_text.splitlines() 
        if line.strip() and not line.strip().lower().startswith("category item price")
    ]

    non_veg_keywords = ["chicken", "mutton", "fish", "egg", "prawn", "lamb", "buff", "keema", "pork"]
    result_cats = {}
    total_items = 0

    for line in lines:
        matched_cat = None
        remainder = None

        # 1. Match category from AI extracted category list
        for cat in sorted(categories_list, key=len, reverse=True):
            if line.startswith(cat + " "):
                matched_cat = cat
                remainder = line[len(cat):].strip()
                break

        # 2. Fallback regex match if category is not in list
        if not matched_cat:
            match = re.match(
                r"^([A-Za-z\s&/-]+?)\s+([A-Za-z0-9\s&()'/.-]+?)\s+((?:Rs\.\s*)?[\d\/]+(?:\s+Extra)?|\d+)$",
                line,
                re.IGNORECASE,
            )
            if match:
                matched_cat, item, price = match.groups()
                matched_cat = matched_cat.strip()
                remainder = f"{item.strip()} {price.strip()}"

        if matched_cat and remainder:
            price_match = re.search(r'((?:Rs\.\s*)?[\d\/]+(?:\s+Extra)?|\d+)$', remainder, re.IGNORECASE)
            if price_match:
                raw_price = price_match.group(1).strip()
                item_str = remainder[:price_match.start()].strip()

                # Expand Multi-Option Items e.g. (Regular/Grilled) 260/280 or (Pineapple/Watermelon/Sweet Lime) 210
                opt_match = re.search(r'\((.*?)\)', item_str)
                prices_split = [p.strip() for p in raw_price.split("/")]

                if opt_match and "/" in opt_match.group(1):
                    options = [o.strip() for o in opt_match.group(1).split("/")]
                    prefix = item_str[:opt_match.start()].strip()
                    suffix = item_str[opt_match.end():].strip()

                    for idx, opt in enumerate(options):
                        name = f"{prefix} {opt} {suffix}".strip() if prefix else f"{opt} {suffix}".strip()
                        p_val = prices_split[idx] if idx < len(prices_split) else prices_split[0]
                        try:
                            p_val = int(p_val)
                        except Exception:
                            pass

                        is_veg = not any(kw in name.lower() for kw in non_veg_keywords)

                        # Determine meal_time tag
                        cat_lower = matched_cat.lower()
                        item_lower = name.lower()
                        if any(k in item_lower or k in cat_lower for k in ["idli", "puri", "dahi vada", "tea", "coffee", "paratha", "poha", "upma"]):
                            meal_time = ["breakfast", "lunch", "dinner"] if "paratha" in item_lower or "puri" in item_lower else ["breakfast"]
                        elif any(k in cat_lower for k in ["paneer", "vegetable", "meals", "roti", "rice", "thali", "soups"]):
                            meal_time = ["lunch", "dinner"]
                        else:
                            meal_time = ["all"]

                        if matched_cat not in result_cats:
                            result_cats[matched_cat] = []

                        result_cats[matched_cat].append({
                            "item_name": name,
                            "price": p_val,
                            "is_veg": is_veg,
                            "metadata_source": {
                                "item_name": "source_extracted",
                                "price": "source_extracted",
                                "is_veg": "system_inferred"
                            }
                        })
                        total_items += 1
                elif "/" in item_str:
                    sub_items = [s.strip() for s in item_str.split("/") if s.strip()]
                    for idx, sub_name in enumerate(sub_items):
                        p_val = prices_split[idx] if idx < len(prices_split) else prices_split[0]
                        try:
                            p_val = int(p_val)
                        except Exception:
                            pass

                        is_veg = not any(kw in sub_name.lower() for kw in non_veg_keywords)

                        if matched_cat not in result_cats:
                            result_cats[matched_cat] = []

                        result_cats[matched_cat].append({
                            "item_name": sub_name,
                            "price": p_val,
                            "is_veg": is_veg,
                            "metadata_source": {
                                "item_name": "source_extracted",
                                "price": "source_extracted",
                                "is_veg": "system_inferred"
                            }
                        })
                        total_items += 1
                else:
                    try:
                        p_val = int(raw_price)
                    except Exception:
                        p_val = raw_price

                    is_veg = not any(kw in item_str.lower() for kw in non_veg_keywords)

                    if matched_cat not in result_cats:
                        result_cats[matched_cat] = []

                    result_cats[matched_cat].append({
                        "item_name": item_str,
                        "price": p_val,
                        "is_veg": is_veg,
                        "metadata_source": {
                            "item_name": "source_extracted",
                            "price": "source_extracted",
                            "is_veg": "system_inferred"
                        }
                    })
                    total_items += 1

    doc_info = {
        "file_name": file_name,
        "business_type": business_type_name,
        "parsed_by": "ai_schema_analysis_plus_python_execution",
        "total_categories_count": len(result_cats),
        "total_items_count": total_items
    }
    if llm_usage:
        doc_info["llm_usage"] = llm_usage

    return {
        "document_info": doc_info,
        "categories": result_cats
    }


async def convert_txt_to_categorized_json_with_ai(
    raw_text: str,
    business_type_name: str,
    file_name: str
) -> dict:
    """
    AI Schema Analysis + Python Execution Parser:
    1. AI analyzes text sample to extract categories (~150 tokens max, <1 paise).
    2. Python executes item expansion, meal_time tagging, and builds JSON (0 LLM tokens).
    """
    categories_list, llm_usage = await analyze_document_schema_with_ai(raw_text, business_type_name)
    return python_execute_categorized_parsing(raw_text, categories_list, business_type_name, file_name, llm_usage)
