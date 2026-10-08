import asyncio
import time
import uuid

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

from app.ai.graph.graph import SparkAgentGraph
from app.ai.context.session_context_resolver import SessionContextResolver
from app.ai.prompts.prompt_builder import RuntimePromptBuilder

from app.database.mongodb import mongodb
from app.modules.conversations.conversation_repository import ConversationRepository



# ============================================================
# CONFIG
# ============================================================
session_id = str(uuid.uuid4())   # ek hi conversation ke liye fixed rahega

# Owner ka phone number = org ka DID number (same thing)
# Jab customer yeh number call karta hai → org identify hoti hai
OWNER_PHONE    = "7807224726"    # Owner's phone = DID number
CUSTOMER_PHONE = "6230097248"    # Actual caller (customer)

DID_NUMBER = OWNER_PHONE         # same number — no separate field needed

# Unique session per call
SESSION_UUID = uuid.uuid4().hex[:8]
SESSION_ID   = f"SESSION_{DID_NUMBER}_{CUSTOMER_PHONE}_{SESSION_UUID}"

# Legacy constant (kept for backward compatibility)
OWNER_ID      = "6a69cc543c715f070a74bff3"
BUSINESS_TYPE = "RESTAURANT"


# ============================================================
# MESSAGE PRINTER
# ============================================================

def print_message(message):

    # ========================================================
    # HUMAN MESSAGE
    # ========================================================

    if isinstance(message, HumanMessage):

        print("\n👤 YOU")
        print("-" * 60)
        print(message.content)

    # ========================================================
    # AI MESSAGE
    # ========================================================

    elif isinstance(message, AIMessage):

        # ----------------------------------------------------
        # TOOL CALL
        # ----------------------------------------------------

        if message.tool_calls:

            for tool_call in message.tool_calls:

                print("\n🔧 TOOL CALL")
                print("-" * 60)

                print(
                    f"Tool : {tool_call['name']}"
                )

                print(
                    f"Args : {tool_call['args']}"
                )

        # ----------------------------------------------------
        # NORMAL AI RESPONSE
        # ----------------------------------------------------

        else:

            content = message.content

            if isinstance(content, str):

                if content.strip():

                    print("\n🤖 AI")
                    print("-" * 60)
                    print(content)

            elif isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "text"
                    ):
                        text = block.get("text")
                        if text and text.strip():
                            print("\n🤖 AI")
                            print("-" * 60)
                            print(text)
    # ========================================================
    # TOOL RESULT
    # ========================================================

    elif isinstance(message, ToolMessage):

        print("\n🔧 TOOL RESULT")
        print("-" * 60)

        print(message.content)

    # ========================================================
    # SYSTEM MESSAGE
    # ========================================================

    elif isinstance(message, SystemMessage):

        print("\n⚙️ SYSTEM")
        print("-" * 60)

        print(message.content)


# ============================================================
# RESOLVE SESSION CONTEXT (DID → Org → AI Employee → Platform Config)
# ============================================================

async def resolve_session_context():
    """
    Resolve the full session context using SessionContextResolver.
    OWNER_PHONE = DID number (same thing) → resolves org → ai_employee → platform_config.
    """
    resolver = SessionContextResolver()

    print(f"\n🔍 Resolving session: DID={DID_NUMBER} | Caller={CUSTOMER_PHONE}")

    ctx = await resolver.resolve(
        did_number   = DID_NUMBER,      # OWNER_PHONE is the DID number
        caller_phone = CUSTOMER_PHONE or None,
    )

    return ctx


# ============================================================
# RESOLVE ORGANIZATION NAME (required by RuntimePromptBuilder)
# ============================================================

async def resolve_organization_name(ctx) -> str:
    """
    Get the real organization/business name for the greeting layer.

    Priority:
    1. If SessionContextResolver already attached a name on ctx (org_name /
       organization_name), reuse it — no extra DB hit.
    2. Otherwise, look it up directly from the `organizations` collection
       using ctx.org_id.

    Raises:
        ValueError: if no name can be resolved — this must fail loudly,
        RuntimePromptBuilder.build() will not accept a missing name either.
    """

    # 1. Already resolved on ctx? (adjust attribute name if your resolver
    #    uses a different field — check SessionContextResolver's return type)
    name = getattr(ctx, "org_name", None) or getattr(ctx, "organization_name", None)
    if name and str(name).strip():
        return str(name).strip()

    # 2. Fallback: fetch directly from MongoDB using org_id
    if not ctx.org_id:
        raise ValueError("Cannot resolve organization name — ctx.org_id is missing.")

    org_doc = await mongodb.database["organizations"].find_one({"_id": ctx.org_id})

    # org_id might be stored as a string in ctx but ObjectId in Mongo — retry if needed
    if not org_doc:
        try:
            from bson import ObjectId
            org_doc = await mongodb.database["organizations"].find_one(
                {"_id": ObjectId(ctx.org_id)}
            )
        except Exception:
            org_doc = None

    if not org_doc or not org_doc.get("name"):
        raise ValueError(
            f"Organization name not found in DB for org_id={ctx.org_id}. "
            "Check the 'organizations' collection and field name ('name')."
        )

    return org_doc["name"].strip()


# ============================================================
# MAIN
# ============================================================

async def main():

    # ========================================================
    # CONNECT MONGODB
    # ========================================================

    await mongodb.connect()

    # ========================================================
    # RESOLVE SESSION CONTEXT (DID / Phone → Org → AI Employee)
    # ========================================================

    try:
        ctx = await resolve_session_context()
    except Exception as exc:
        print("\n❌ SESSION CONTEXT RESOLUTION ERROR")
        print("-" * 60)
        print(type(exc).__name__)
        print(str(exc))
        return

    # Unpack resolved context
    owner_id        = ctx.owner_id
    org_id          = ctx.org_id
    ai_employee_id  = ctx.ai_employee_id
    ai_employee     = ctx.ai_employee
    platform_config = ctx.platform_config
    business_type   = ctx.business_type
    customer_id     = ctx.customer_id

    # ========================================================
    # RESOLVE ORGANIZATION NAME (required, no silent fallback)
    # ========================================================

    try:
        organization_name = await resolve_organization_name(ctx)
    except Exception as exc:
        print("\n❌ ORGANIZATION NAME RESOLUTION ERROR")
        print("-" * 60)
        print(type(exc).__name__)
        print(str(exc))
        return

    # ========================================================
    # BUILD DYNAMIC SYSTEM PROMPT (4 layers)
    # ========================================================

    system_prompt = RuntimePromptBuilder.build(
        ai_employee        = ai_employee,
        organization_name  = organization_name,
        platform_config    = platform_config,
    )

    # ========================================================
    # SHOW AI EMPLOYEE
    # ========================================================

    print("\n")
    print("=" * 60)
    print("👨‍💼 AI EMPLOYEE")
    print("=" * 60)

    print(
        f"Name        : {ai_employee.get('name')}"
    )

    print(
        f"Role        : {ai_employee.get('role')}"
    )

    print(
        f"Persona     : {ai_employee.get('persona')}"
    )

    print(
        f"Language    : {ai_employee.get('language')}"
    )

    print(
        f"Voice ID    : {ai_employee.get('voice_id')}"
    )

    print(
        f"Employee ID : {ai_employee_id}"
    )

    print(f"Org ID      : {org_id}")
    print(f"Org Name    : {organization_name}")
    print(f"Owner Phone : {OWNER_PHONE}")
    print(f"Customer    : {CUSTOMER_PHONE}")
    print(f"Session ID  : {SESSION_ID}")
    print("=" * 60)

    # ========================================================
    # BUILD AGENT (dynamic: business_type from resolved ctx)
    # ========================================================

    agent = SparkAgentGraph(business_type=business_type)
    graph = agent.build()

    # ========================================================
    # PRINT GRAPH
    # ========================================================

    print("\n")
    print("=" * 60)
    print("🧠 RESTAURANT AGENT GRAPH")
    print("=" * 60)

    try:

        print(
            graph.get_graph().draw_ascii()
        )

    except Exception as exc:

        print(
            "Could not render ASCII graph:"
        )

        print(exc)

        print("\nGraph structure:")

        print(
            graph.get_graph().edges
        )

    print("=" * 60)

    # ========================================================
    # ASSISTANT
    # ========================================================

    print("\n")
    print("=" * 60)
    print("🍽️ RESTAURANT AI ASSISTANT")
    print("=" * 60)

    print(
        "\nType 'exit' to quit."
    )

    # ========================================================
    # LOAD CONVERSATION HISTORY FROM MONGODB
    # (if session exists → continue, else → fresh start)
    # ========================================================

    conversation_repo = ConversationRepository()
    existing_conversation = await conversation_repo.get_by_session_id(SESSION_ID)

    if existing_conversation and existing_conversation.get("messages"):
        print(f"\n📂 Existing session found — loading {len(existing_conversation['messages'])} messages from DB...")
        db_messages = existing_conversation["messages"]
        # Convert DB format → LangChain message format
        messages = [SystemMessage(content=system_prompt)]
        for msg in db_messages:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        print(f"✅ History loaded: {len(messages) - 1} messages restored.")
    else:
        print(f"\n🆕 New session started — SESSION_ID: {SESSION_ID}")
        # Fresh start
        messages = [
            SystemMessage(
                content=system_prompt
            )
        ]

    # ========================================================
    # CHAT LOOP
    # ========================================================

    while True:

        

        # ====================================================
        # USER INPUT
        # ====================================================

        try:

            user_input = input(
                "\n👤 You: "
            ).strip()

        except (
            KeyboardInterrupt,
            EOFError,
        ):

            print(
                "\n\n👋 Goodbye!"
            )

            break

        # ====================================================
        # EMPTY INPUT
        # ====================================================

        if not user_input:

            continue

        # ====================================================
        # EXIT
        # ====================================================

        if user_input.lower() in {
            "exit",
            "quit",
            "bye",
        }:

            print(
                "\n👋 Goodbye!"
            )

            break

        # ====================================================
        # ADD USER MESSAGE
        # ====================================================

        messages.append(
            HumanMessage(
                content=user_input
            )
        )

        # ====================================================
        # SAVE MESSAGE COUNT
        # ====================================================

        previous_message_count = len(
            messages
        )

        # ====================================================
        # START TIMER & RUN LANGGRAPH STREAMING
        # ====================================================

        graph_start_time = time.perf_counter()
        first_token_time = None
        header_printed = False

        try:
            final_output_messages = None

            async for event in graph.astream_events(
                {
                    "messages":       messages,
                    "owner_id":       owner_id,
                    "org_id":         org_id,
                    "business_type":  business_type,
                    "business_type_id": ctx.business_type_id,
                    "ai_employee_id": ai_employee_id,
                    "ai_employee":    ai_employee,
                    "platform_config": platform_config,
                },
                config={"configurable": {"thread_id": SESSION_ID}},
                version="v2",
            ):
                kind = event.get("event")

                # Stream LLM tokens live as they arrive
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "")
                    if isinstance(content, str) and content:
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        if not header_printed:
                            print("\n🤖 AI (Streaming...)")
                            print("-" * 60)
                            header_printed = True
                        print(content, end="", flush=True)

                # Tool Call Triggered
                elif kind == "on_tool_start":
                    tool_name = event.get("name")
                    tool_input = event.get("data", {}).get("input")
                    print(f"\n\n🔧 TOOL CALL : {tool_name}")
                    print(f"   Args      : {tool_input}")
                    header_printed = False

                # Tool Completed
                elif kind == "on_tool_end":
                    tool_output = event.get("data", {}).get("output")
                    print(f"   Output    : {tool_output}")
                    header_printed = False

                # Capture final graph output state
                elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                    output = event.get("data", {}).get("output")
                    if isinstance(output, dict) and "messages" in output:
                        final_output_messages = output["messages"]

            print()  # Newline after stream finishes

            if final_output_messages:
                new_messages = final_output_messages
            else:
                new_messages = messages

        except Exception as exc:

            graph_end_time = time.perf_counter()

            graph_latency = (
                graph_end_time
                - graph_start_time
            )

            print("\n❌ GRAPH ERROR")
            print("-" * 60)

            print(
                type(exc).__name__
            )

            print(
                str(exc)
            )

            print(
                f"\n⏱️ Failed after: "
                f"{graph_latency:.3f}s"
            )

            messages.pop()

            continue

        # ====================================================
        # END TOTAL GRAPH TIMER
        # ====================================================

        graph_end_time = time.perf_counter()

        graph_latency = (
            graph_end_time
            - graph_start_time
        )

        ttft = (
            first_token_time - graph_start_time
            if first_token_time
            else graph_latency
        )

        # ====================================================
        # LATENCY SUMMARY
        # ====================================================

        print("\n⏱️ LATENCY BREAKDOWN")
        print("-" * 60)

        print(
            f"⚡ Time-to-First-Token (TTFT) : {ttft:.3f}s"
        )
        print(
            f"⏱️ Total Pipeline Time      : {graph_latency:.3f}s"
        )

        # ====================================================
        # SAVE TURN TO MONGODB
        # (new session → insert, existing → push messages)
        # ====================================================

        ai_reply = ""
        if new_messages:
            for msg in reversed(new_messages):
                if isinstance(msg, AIMessage) and msg.content and isinstance(msg.content, str):
                    ai_reply = msg.content.strip()
                    break

        if ai_reply:
            try:
                await conversation_repo.save_message(
                    session_id=SESSION_ID,
                    owner_id=owner_id,
                    org_id=org_id,
                    employee_id=ai_employee_id,
                    user_message=user_input,
                    assistant_reply=ai_reply,
                    cart=[],
                    customer_id=customer_id,
                )
                print(f"💾 Saved to DB → session: {SESSION_ID}")
            except Exception as save_err:
                print(f"⚠️ DB Save Error: {save_err}")

        # ====================================================
        # UPDATE COMPLETE HISTORY
        # ====================================================

        messages = new_messages


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )