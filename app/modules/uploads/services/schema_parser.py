import re
import json
from openai import AsyncOpenAI
from app.core.config import settings
from .token_calculator import calculate_openai_cost


def clean_price_value(val) -> int | float:
    """Strip currency strings like PKR, (PKR), Rs, ₹, $, etc., leaving numeric price."""
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    s = re.sub(r'(?i)\(?(?:PKR|Rs\.?|INR|USD|\$|₹)\)?', '', s).strip()
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except Exception:
        m = re.search(r'\d+(?:\.\d+)?', s)
        if m:
            v = m.group(0)
            return float(v) if '.' in v else int(v)
        return 0


async def extract_categorized_items_with_ai(
    raw_text: str,
    business_type_name: str,
    file_name: str
) -> tuple[dict, dict | None]:
    """
    AI-Powered Full Document Item Extractor:
    Uses gpt-4o-mini to extract items and categories from multi-line, multi-column, or tabular text.
    Strips currency tokens (PKR, Rs, etc.), leaving purely numeric prices.
    """
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        prompt = f"""You are an expert document data extractor for a {business_type_name} business catalog.
Extract all menu/catalog items from the provided text and group them by Category.

Rules:
1. Extract Category name, Item name, and Price.
2. Price MUST be a pure number (e.g. 240, 290). Remove any currency symbols or currency codes like PKR, (PKR), Rs, INR, $.
3. Set is_veg boolean (true if vegetarian, false if contains chicken, mutton, fish, egg, pork, meat, etc.).
4. If a subcategory exists (like VEG, CHICKEN, MUTTON under MOMOS), combine it into the item_name or keep category name clear.

Text:
---
{raw_text[:12000]}
---

Return ONLY valid JSON in this exact structure:
{{
  "categories": {{
    "Category Name": [
      {{"item_name": "Item Name", "price": 240, "is_veg": true}}
    ]
  }}
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )

        usage = None
        if response.usage:
            usage = calculate_openai_cost(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                model="gpt-4o-mini"
            )
            print(f"💰 [LLM LOG - Full AI Document Extraction] Tokens: {usage['total_tokens']} | Cost: {usage['formatted_cost']}")

        parsed = json.loads(response.choices[0].message.content.strip())
        raw_cats = parsed.get("categories", {})

        cleaned_cats = {}
        total_count = 0
        for cat_name, item_list in raw_cats.items():
            if not isinstance(item_list, list):
                continue
            cleaned_items = []
            for item in item_list:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("item_name", "")).strip()
                if not name:
                    continue
                cleaned_price = clean_price_value(item.get("price", 0))
                cleaned_items.append({
                    "item_name": name,
                    "price": cleaned_price,
                    "is_veg": bool(item.get("is_veg", True)),
                    "metadata_source": {
                        "item_name": "source_extracted",
                        "price": "source_extracted",
                        "is_veg": "system_inferred"
                    }
                })
                total_count += 1
            if cleaned_items:
                cleaned_cats[cat_name] = cleaned_items

        if cleaned_cats:
            return {
                "document_info": {
                    "file_name": file_name,
                    "business_type": business_type_name,
                    "parsed_by": "ai_full_document_extraction",
                    "total_categories_count": len(cleaned_cats),
                    "total_items_count": total_count,
                    "llm_usage": usage
                },
                "categories": cleaned_cats
            }, usage

        return {}, usage
    except Exception as e:
        print(f"⚠️ AI full document extraction failed: {e}")
        return {}, None


async def analyze_document_schema_with_ai(sample_text: str, business_type_name: str) -> tuple[list, dict | None]:
    """
    AI Schema Analyzer (Low Tokens ~150 max):
    Analyzes document text sample and extracts top-level categories.
    """
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = f"""You are an AI document structure analyzer for a {business_type_name} business platform.

Read this document sample and extract all top-level category names:
---
{sample_text[:3000]}
---

Return ONLY JSON format:
{{"categories": ["MOMOS (8 PCS)", "SOUPS", "SALADS & RAITA", "STARTERS", "INDIAN MAIN COURSE", "BREADS", "RICE", "DESSERTS", "MEALS"]}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"}
        )

        usage = None
        if response.usage:
            usage = calculate_openai_cost(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                model="gpt-4o-mini"
            )
            print(f"💰 [LLM LOG - AI Schema Analysis] Tokens: {usage['total_tokens']} | Cost: {usage['formatted_cost']}")

        result_text = response.choices[0].message.content.strip()
        parsed = json.loads(result_text)
        cats = parsed.get("categories", [])
        return cats, usage
    except Exception:
        default_cats = ["Starters", "Cold Beverages", "Hot Beverages", "Soups", "Salads", "Paneer", "Vegetable", "Meals", "Roti", "Rice", "Thali", "Beverages", "Desserts"]
        return default_cats, None


def python_execute_categorized_parsing(raw_text: str, categories_list: list, business_type_name: str, file_name: str, llm_usage: dict | None) -> dict:
    """
    Python Execution Parser (Zero/Low LLM Tokens Fallback):
    Handles single-line, multi-line, dot-separated, and PKR/currency formats.
    Strips PKR, Rs., and currency labels from prices.
    """
    lines = [
        line.strip() for line in raw_text.splitlines() 
        if line.strip() and not re.search(r'(?i)^(category|subcategory|item name|price)', line.strip())
    ]

    non_veg_keywords = ["chicken", "mutton", "fish", "egg", "prawn", "lamb", "buff", "keema", "pork", "murg", "ghosht"]
    result_cats = {}
    total_items = 0

    current_category = "General"

    # 1. Single-Line & Dot Pattern Matching
    for line in lines:
        matched_cat = None
        remainder = None

        for cat in sorted(categories_list, key=len, reverse=True):
            if line.upper() == cat.upper() or line.startswith(cat + " "):
                matched_cat = cat
                remainder = line[len(cat):].strip() if line.startswith(cat + " ") else ""
                current_category = cat
                break

        if not matched_cat:
            match = re.match(
                r"^([A-Za-z\s&/-]+?)\s+([A-Za-z0-9\s&()'/.-]+?)\s+((?:(?:PKR|Rs\.?|INR|\$|₹)\s*)?[\d\/]+(?:\s+Extra)?|\d+)$",
                line,
                re.IGNORECASE,
            )
            if match:
                matched_cat, item, price = match.groups()
                matched_cat = matched_cat.strip()
                remainder = f"{item.strip()} {price.strip()}"

        if (matched_cat or current_category) and remainder:
            cat_to_use = matched_cat or current_category
            price_match = re.search(r'((?:(?:PKR|Rs\.?|INR|\$|₹)\s*)?[\d\/]+(?:\s+Extra)?|\d+)$', remainder, re.IGNORECASE)
            if price_match:
                raw_price = price_match.group(1).strip()
                item_str = remainder[:price_match.start()].strip()
                item_str = re.sub(r'^[•\-\*\s]+', '', item_str).strip()

                p_val = clean_price_value(raw_price)
                is_veg = not any(kw in item_str.lower() for kw in non_veg_keywords)

                if cat_to_use not in result_cats:
                    result_cats[cat_to_use] = []

                result_cats[cat_to_use].append({
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

    # 2. Multi-Line Fallback (e.g. Category / Subcategory / Item Name / Price on separate lines)
    if total_items == 0:
        idx = 0
        current_cat = "General"
        while idx < len(lines):
            line = lines[idx]
            cleaned_num = clean_price_value(line)
            is_pure_num = line.isdigit() or bool(re.match(r'^\d+(?:\.\d+)?$', line.strip()))

            if is_pure_num and cleaned_num > 0:
                if idx >= 1:
                    item_name = lines[idx - 1]
                    cat = current_cat

                    if idx >= 3 and lines[idx-2].isupper() and len(lines[idx-2].split()) <= 4 and lines[idx-3].isupper():
                        cat = lines[idx-3]
                        subcat = lines[idx-2]
                        item_name = f"{item_name} ({subcat})"
                    elif idx >= 2 and lines[idx-2].isupper() and len(lines[idx-2].split()) <= 4:
                        cat = lines[idx-2]

                    current_cat = cat
                    is_veg = not any(kw in item_name.lower() for kw in non_veg_keywords)

                    if current_cat not in result_cats:
                        result_cats[current_cat] = []

                    if not any(it["item_name"] == item_name and it["price"] == cleaned_num for it in result_cats[current_cat]):
                        result_cats[current_cat].append({
                            "item_name": item_name,
                            "price": cleaned_num,
                            "is_veg": is_veg,
                            "metadata_source": {
                                "item_name": "source_extracted",
                                "price": "source_extracted",
                                "is_veg": "system_inferred"
                            }
                        })
                        total_items += 1
            idx += 1

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
    Full AI Document Extractor with Fallback to Python Parser.
    """
    ai_result, _ = await extract_categorized_items_with_ai(raw_text, business_type_name, file_name)
    if ai_result and ai_result.get("categories"):
        return ai_result
    categories_list, llm_usage = await analyze_document_schema_with_ai(raw_text, business_type_name)
    return python_execute_categorized_parsing(raw_text, categories_list, business_type_name, file_name, llm_usage)