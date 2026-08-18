import asyncio

from app.ai.planner.intent_router import IntentRouter
from app.ai.planner.route_resolver import RouteResolver
from app.ai.tools.tool_executor import ToolExecutor
from app.database.mongodb import mongodb


# ---------------------------------------------------------
# STATIC TEST CONTEXT
# ---------------------------------------------------------

OWNER_ID = "6a69cc543c715f070a74bff3"


# ---------------------------------------------------------
# Services
# ---------------------------------------------------------

intent_router = IntentRouter()
route_resolver = RouteResolver()
tool_executor = ToolExecutor()


# ---------------------------------------------------------
# Test One Query
# ---------------------------------------------------------

async def process_query(user_message: str):

    print("\n")
    print("=" * 70)
    print("CUSTOMER QUERY")
    print("=" * 70)

    print(f"👤 Query: {user_message}")

    try:

        # =====================================================
        # 1. INTENT ROUTER
        # =====================================================

        print("\n🧠 [1] Intent Router")
        print("-" * 70)

        intent_output = await intent_router.classify(
            user_message=user_message,
            business_type="RESTAURANT",
        )

        print(f"Intent   : {intent_output.intent}")
        print(f"Entities : {intent_output.entities}")

        # =====================================================
        # 2. ROUTE RESOLVER
        # =====================================================

        print("\n🛣️ [2] Route Resolver")
        print("-" * 70)

        route = route_resolver.resolve(
            router_output=intent_output,
            business_type="RESTAURANT",
        )

        print(f"Route Type     : {route.get('route_type')}")
        print(f"Tool Name      : {route.get('tool_name')}")
        print(f"Execution Mode : {route.get('execution_mode')}")

        # =====================================================
        # 3. TOOL EXECUTOR
        # =====================================================

        print("\n🔧 [3] Tool Executor")
        print("-" * 70)

        if route.get("route_type") == "TOOL":

            context = {
                "owner_id": OWNER_ID,
            }

            print(f"Context  : {context}")
            print(f"Arguments: {route.get('entities')}")

            result = await tool_executor.execute(
                route=route,
                context=context,
            )

            print("\n✅ TOOL RESULT")
            print("-" * 70)

            print(f"Tool    : {result.get('tool_name')}")
            print(f"Success : {result.get('success')}")
            print(f"Result  : {result.get('result')}")

        else:

            print("\nℹ️ No tool required.")

            result = {
                "success": True,
                "result": None,
            }

        print("\n" + "=" * 70)
        print("PROCESS COMPLETED")
        print("=" * 70)

    except Exception as exc:

        print("\n❌ ERROR")
        print("-" * 70)
        print(type(exc).__name__)
        print(str(exc))

        print("=" * 70)


# ---------------------------------------------------------
# Interactive Test Loop
# ---------------------------------------------------------

async def main():
    await mongodb.connect()

    print("=" * 70)
    print("       RESTAURANT AI TOOL PIPELINE TEST")
    print("=" * 70)

    print("Type a customer query.")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 70)

    while True:

        user_message = input("\nYou: ").strip()

        if user_message.lower() in {"exit", "quit"}:
            print("\n👋 Test stopped.")
            break

        if not user_message:
            continue

        await process_query(user_message)


if __name__ == "__main__":
    asyncio.run(main())