import asyncio

from app.ai.planner.intent_router import IntentRouter


async def main():

    router = IntentRouter()

    print("=" * 70)
    print("        RESTAURANT INTENT ROUTER TEST")
    print("=" * 70)
    print("Type your customer message.")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 70)

    while True:

        try:
            user_message = input("\nYou: ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break

        if not user_message:
            continue

        if user_message.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        try:

            result = await router.classify(
                user_message=user_message,
                business_type="RESTAURANT",
            )

            print("\n--- Router Result ---")
            print(f"Intent   : {result.intent}")
            print(f"Entities : {result.entities}")
            print("---------------------")

        except Exception as error:

            print("\n❌ Router Error:")
            print(error)


if __name__ == "__main__":
    asyncio.run(main())