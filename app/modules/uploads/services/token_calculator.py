def calculate_openai_cost(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o-mini") -> dict:
    """
    Calculates exact USD and estimated INR cost for OpenAI token usage.
    Rates for gpt-4o-mini:
    - Input (prompt): $0.150 / 1,000,000 tokens
    - Output (completion): $0.600 / 1,000,000 tokens
    """
    input_rate = 0.150 / 1_000_000
    output_rate = 0.600 / 1_000_000

    input_cost = prompt_tokens * input_rate
    output_cost = completion_tokens * output_rate
    total_cost_usd = input_cost + output_cost
    total_cost_inr = total_cost_usd * 83.5  # USD to INR conversion

    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(total_cost_usd, 6),
        "cost_inr": round(total_cost_inr, 4),
        "formatted_cost": f"${total_cost_usd:.6f} (~₹{total_cost_inr:.4f})"
    }
