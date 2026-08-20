import asyncio
import json

from .llm_tool_caller import LLMToolCaller
from app.ai.tools.tool_executor import ToolExecutor
from app.database.mongodb import mongodb


OWNER_ID = "6a69cc543c715f070a74bff3"


async def main():

    # ---------------------------------------------------------
    # Services
    # ---------------------------------------------------------

    caller = LLMToolCaller()
    executor = ToolExecutor()

    await mongodb.connect()

    llm = caller.get_llm("RESTAURANT")

    print("=" * 70)
    print("       RESTAURANT AI TOOL TEST")
    print("=" * 70)

    print("Type customer message.")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 70)

    while True:

        query = input("\nYou: ").strip()

        if not query:
            continue

        if query.lower() in {"exit", "quit"}:
            print("\nStopped.")
            break

        try:

            # =================================================
            # 1. LLM
            # =================================================

            response = await llm.ainvoke(query)

            print("\n" + "=" * 70)
            print("CUSTOMER QUERY")
            print("=" * 70)

            print(query)

            # =================================================
            # 2. TOOL CALL
            # =================================================

            tool_calls = response.tool_calls

            if not tool_calls:

                print("\n❌ NO TOOL CALL")

                print("\nLLM RESPONSE:")
                print(response.content)

                continue

            # =================================================
            # 3. EXECUTE EVERY TOOL CALL
            # =================================================

            for call in tool_calls:

                tool_name = call["name"]
                tool_args = call.get("args", {})

                print("\n" + "=" * 70)
                print("LLM TOOL CALL")
                print("=" * 70)

                print(f"Tool Name : {tool_name}")

                print("Arguments :")

                print(
                    json.dumps(
                        tool_args,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                # ---------------------------------------------
                # IMPORTANT:
                # owner_id comes from application context
                # NOT from LLM
                # ---------------------------------------------

                print("\n" + "=" * 70)
                print("EXECUTING TOOL")
                print("=" * 70)

                print(f"Owner ID  : {OWNER_ID}")
                print(f"Tool Name : {tool_name}")

                # =================================================
                # 4. TOOL EXECUTOR
                # =================================================

                result = await executor.execute(
                    business_type="RESTAURANT",
                    tool_name=tool_name,
                    arguments=tool_args,
                    context={
                        "owner_id": OWNER_ID,
                    },
                )

                # =================================================
                # 5. TOOL RESULT
                # =================================================

                print("\n" + "=" * 70)
                print("TOOL RESULT")
                print("=" * 70)

                print(
                    result.model_dump_json(
                        indent=2
                    )
                )

                print("=" * 70)

        except Exception as exc:

            print("\n❌ ERROR")
            print("=" * 70)

            print(
                type(exc).__name__
            )

            print(str(exc))


if __name__ == "__main__":
    asyncio.run(main())