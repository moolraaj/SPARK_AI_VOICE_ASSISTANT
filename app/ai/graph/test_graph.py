import asyncio
import time
import uuid

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

from app.ai.graph.graph import RestaurantAgentGraph
from app.ai.prompts.restaurant_prompt import build_system_prompt
from app.database.mongodb import mongodb
from app.modules.ai_employees.ai_employee_repository import AIEmployeeRepository
from app.modules.organizations.organization_repository import OrganizationRepository
from app.modules.auth.repository import AuthRepository
from app.modules.conversations.conversation_repository import ConversationRepository
from app.modules.customers.customer_repository import CustomerRepository
from app.core.datetime import timestamps


# ============================================================
# CONFIG
# ============================================================
session_id = str(uuid.uuid4())   # ek hi conversation ke liye fixed rahega

# Phone-based resolution (Vobiz-style)
OWNER_PHONE    = "6230097248"    # Owner ka registered number (users table)
CUSTOMER_PHONE = "7018616800"    # Customer ka caller number

# Unique session per call — format: SESSION_{owner}_{customer}_{short_uuid}
# Har naye test run pe fresh session banega
SESSION_UUID = uuid.uuid4().hex[:8]   # e.g. "a3f2c1d0"
SESSION_ID   = f"SESSION_{OWNER_PHONE}_{CUSTOMER_PHONE}_{SESSION_UUID}"

# Legacy constant (kept for backward compatibility)
OWNER_ID = "6a69cc543c715f070a74bff3"

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
# LOAD AI EMPLOYEE
# ============================================================

async def load_ai_employee():

    auth_repository         = AuthRepository()
    organization_repository = OrganizationRepository()
    ai_employee_repository  = AIEmployeeRepository()

    # ========================================================
    # OWNER PHONE → USER → OWNER_ID
    # ========================================================

    owner_user = await auth_repository.get_user_by_phone(OWNER_PHONE)

    if not owner_user:
        raise RuntimeError(
            f"No user found with phone number: {OWNER_PHONE}"
        )

    resolved_owner_id = str(owner_user["_id"])

    print(f"\n✅ Owner Resolved  : {owner_user.get('name')} (ID: {resolved_owner_id})")

    # ========================================================
    # OWNER → ORGANIZATION
    # ========================================================

    organizations = await organization_repository.get_by_owner(
        resolved_owner_id,
        skip=0,
        limit=1,
    )

    if not organizations:

        raise RuntimeError(
            "No organization found for this owner."
        )

    organization = organizations[0]

    org_id = str(
        organization["_id"]
    )

    # ========================================================
    # ORGANIZATION → ACTIVE AI EMPLOYEE
    # ========================================================

    ai_employee = await ai_employee_repository.get_active_by_org(
        org_id
    )

    if not ai_employee:

        raise RuntimeError(
            "No active AI employee found for this organization."
        )

    return organization, ai_employee, resolved_owner_id


# ============================================================
# MAIN
# ============================================================

async def main():

    # ========================================================
    # MONGODB
    # ========================================================

    await mongodb.connect()

    # ========================================================
    # LOAD AI EMPLOYEE (via owner phone number)
    # ========================================================

    try:

        organization, ai_employee, resolved_owner_id = await load_ai_employee()

    except Exception as exc:

        print("\n❌ AI EMPLOYEE RESOLUTION ERROR")
        print("-" * 60)

        print(
            type(exc).__name__
        )

        print(
            str(exc)
        )

        return

    # ========================================================
    # IDS
    # ========================================================

    org_id = str(
        organization["_id"]
    )

    ai_employee_id = str(
        ai_employee["_id"]
    )

    owner_id = resolved_owner_id

    # ========================================================
    # RESOLVE / CREATE CUSTOMER RECORD
    # (so customer_id is never null in DB)
    # ========================================================

    customer_repo  = CustomerRepository()
    customer_c_uuid = f"CUSTOMER_{CUSTOMER_PHONE}_{uuid.uuid4().hex[:8]}"
    existing_customer = await customer_repo.get_by_phone(owner_id, CUSTOMER_PHONE)
    if existing_customer:
        customer_id = str(existing_customer["_id"])
        print(f"✅ Customer Found   : {CUSTOMER_PHONE} (ID: {customer_id})")
    else:
        customer_id = await customer_repo.create_customer({
            "owner_id": owner_id,
            "phone_number": CUSTOMER_PHONE,
            "customer_uuid": customer_c_uuid,   # e.g. CUSTOMER_7018616800_a3f2c1d0
            "name": None,
            "role": "CUSTOMER",
            "total_conversations": 1,
            **timestamps(),
        })
        print(f"🆕 Customer Created  : {CUSTOMER_PHONE} (customer_uuid: {customer_c_uuid})")

    # ========================================================
    # BUILD DYNAMIC SYSTEM PROMPT
    # ========================================================

    system_prompt = build_system_prompt(
        ai_employee
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
    print(f"Owner Phone : {OWNER_PHONE}")
    print(f"Customer    : {CUSTOMER_PHONE}")
    print(f"Session ID  : {SESSION_ID}")
    print("=" * 60)

    # ========================================================
    # BUILD AGENT
    # ========================================================

    agent = RestaurantAgentGraph()

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
                    "messages": messages,
                    "owner_id": owner_id,
                    "business_type": BUSINESS_TYPE,
                    "ai_employee_id": ai_employee_id,
                },
                # thread_id = checkpointer ke liye unique conversation identifier
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
                    employee_id=ai_employee_id,
                    user_message=user_input,
                    assistant_reply=ai_reply,
                    cart=[],
                    customer_id=customer_id,   # ← ab null nahi hoga
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