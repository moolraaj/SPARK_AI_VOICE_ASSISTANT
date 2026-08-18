import asyncio

from app.ai.tools.restaurant.tools import RestaurantTools


# Static owner ID for testing
OWNER_ID = "6a69cc543c715f070a74bff3"


async def main():

    tools = RestaurantTools()

    print("=" * 70)
    print("              RESTAURANT MENU SEARCH TEST")
    print("=" * 70)
    print("Type your menu query.")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 70)

    while True:

        query = input("\nYou: ").strip()

        if query.lower() in {"exit", "quit"}:
            print("\nTest stopped.")
            break

        if not query:
            continue

        try:

            result = await tools.search_menu(
                owner_id=OWNER_ID,
                query=query,
                top_k=5,
            )

            print("\n--- Tool Result ---")
            print(f"Success : {result.get('success')}")
            print(f"Query   : {result.get('query')}")
            print(f"Count   : {result.get('count')}")

            items = result.get("items", [])

            if not items:
                print("Items   : No matching items found.")

            else:
                print("Items:")

                for index, item in enumerate(items, start=1):

                    print(
                        f"  {index}. "
                        f"{item.get('item_name')} | "
                        f"₹{item.get('price')} | "
                        f"{'Veg' if item.get('is_veg') else 'Non-Veg'} | "
                        f"Score: {item.get('score')}"
                    )

            print("---------------------")

        except Exception as exc:

            print("\n❌ Tool Error:")
            print(exc)


if __name__ == "__main__":
    asyncio.run(main())