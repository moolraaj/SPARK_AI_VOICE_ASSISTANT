import uuid
from bson import ObjectId
from bson.errors import InvalidId
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .conversation_repository import ConversationRepository
from app.modules.ai_employees.ai_employee_repository import AIEmployeeRepository
from app.modules.organizations.organization_repository import OrganizationRepository
from app.modules.customers.customer_repository import CustomerRepository
from app.core.datetime import timestamps, utc_now
from app.ai.graph.graph import RestaurantAgentGraph
from app.ai.prompts.restaurant_prompt import build_system_prompt

# Simple TTL for employee cache entries (seconds)
_EMP_CACHE_TTL = 300  # 5 minutes


class ChatService:

    def __init__(self):
        self.conversation_repo = ConversationRepository()
        self.ai_employee_repo = AIEmployeeRepository()
        self.org_repo = OrganizationRepository()
        self.customer_repo = CustomerRepository()
        # Employee cache: key → {employee, owner_id, org_name, cached_at}
        # Invalidated after _EMP_CACHE_TTL seconds so dashboard updates are reflected.
        self._emp_cache: dict[str, dict] = {}
        self._cust_cache: dict[str, str] = {}
        # LangGraph agent — shared instance (built once, reused across all requests)
        # NOTE: MemorySaver inside the graph already tracks full conversation history
        # per thread_id. We do NOT need a separate history cache here.
        agent = RestaurantAgentGraph()
        self._graph = agent.build()

    async def chat_with_employee(
        self,
        employee_id: str,
        user_message: str,
        session_id: str | None = None,
        customer_phone_number: str | None = None,
        customer_name: str | None = None
    ) -> dict:
        # Employee cache with TTL — re-fetch from DB if cache is stale
        # This ensures dashboard updates (name, persona, system_prompt) are reflected.
        import time as _time
        cached_info = self._emp_cache.get(employee_id)
        cache_age = _time.time() - cached_info.get("cached_at", 0) if cached_info else _EMP_CACHE_TTL + 1

        if cached_info and cache_age < _EMP_CACHE_TTL:
            employee = cached_info["employee"]
            owner_id = cached_info["owner_id"]
        else:
            try:
                emp_obj_id = ObjectId(employee_id)
            except InvalidId:
                return {"success": False, "message": "Invalid AI employee ID format."}

            employee = await self.ai_employee_repo.get_by_id(emp_obj_id)
            if not employee:
                return {"success": False, "message": "AI employee not found."}

            try:
                org_obj_id = ObjectId(employee["org_id"])
                org = await self.org_repo.get_by_id(org_obj_id)
                biz_name = org.get("name", "") if org else ""
                owner_id = org.get("owner_id", "") if org else ""
            except Exception:
                biz_name = ""
                owner_id = ""

            if not owner_id:
                return {"success": False, "message": "Could not resolve owner organization for this AI employee."}

            org_id_val = str(employee.get("org_id")) if employee.get("org_id") else ""
            self._emp_cache[employee_id] = {
                "employee":  employee,
                "owner_id":  owner_id,
                "org_id":    org_id_val,
                "org_name":  biz_name or "",
                "cached_at": _time.time(),
            }

        # Auto-upsert customer record (cached per session/phone to avoid repeated queries)
        customer_id = None
        clean_phone = customer_phone_number.strip() if customer_phone_number else None
        if clean_phone:
            cust_cache_key = f"{owner_id}_{clean_phone}"
            customer_id = self._cust_cache.get(cust_cache_key)
            if not customer_id:
                existing_customer = await self.customer_repo.get_by_phone(owner_id, clean_phone)
                if existing_customer:
                    customer_id = str(existing_customer["_id"])
                    if customer_name and customer_name.strip() and not existing_customer.get("name"):
                        await self.customer_repo.update_customer(customer_id, {"name": customer_name.strip()})
                else:
                    name_to_set = customer_name.strip() if customer_name and customer_name.strip() else None
                    new_customer = {
                        "owner_id": owner_id,
                        "name": name_to_set,
                        "phone_number": clean_phone,
                        "role": "CUSTOMER",
                        "total_conversations": 1,
                        **timestamps()
                    }
                    customer_id = await self.customer_repo.create_customer(new_customer)
                if customer_id:
                    self._cust_cache[cust_cache_key] = customer_id

        # Generate or reuse session_id (Auto-attach to recent active session if session_id is omitted)
        active_session_id = session_id
        if not active_session_id and customer_id:
            recent_convs = await self.conversation_repo.get_by_customer_id(customer_id, skip=0, limit=1)
            if recent_convs:
                latest_conv = recent_convs[0]
                last_updated = latest_conv.get("updated_at")
                if last_updated:
                    try:
                        now = utc_now()
                        if hasattr(last_updated, "tzinfo") and last_updated.tzinfo is None:
                            from datetime import timezone
                            last_updated = last_updated.replace(tzinfo=timezone.utc)
                        diff = abs((now - last_updated).total_seconds())
                        if diff < 1800:  # 30 minutes active call/chat session window
                            active_session_id = latest_conv.get("session_id")
                    except Exception as e:
                        print(f"⚠️ Session resolution error: {e}")

        if not active_session_id:
            active_session_id = f"session_{uuid.uuid4().hex[:12]}"

        # ── LangGraph Agent Pipeline ─────────────────────────────────────────
        # FIXED: Only send the NEW user message to the graph.
        # LangGraph's MemorySaver checkpointer already holds the full conversation
        # history for this thread_id. Sending the complete history again causes
        # the add_messages reducer to produce DUPLICATES on every turn:
        # Turn 5 → MemorySaver has T1-T4, we'd send T1-T4 again + T5 = T1-T4 appear twice.
        # This was doubling token counts and causing context drift.
        cached_emp_info = self._emp_cache.get(employee_id, {})
        cached_emp     = cached_emp_info.get("employee", {})
        org_name       = cached_emp_info.get("org_name", "")

        # First turn of a session: inject SystemMessage so the graph initialises
        # with the correct employee persona. On subsequent turns MemorySaver already
        # has it — but injecting it again is harmless because nodes.py checks for
        # an existing SystemMessage before prepending a new one.
        #
        # Enrich active_emp with restaurant_name so {restaurant_name} placeholder
        # resolves correctly inside build_system_prompt (both custom & fallback paths).
        base_emp    = cached_emp if cached_emp else employee
        active_emp  = {**base_emp, "restaurant_name": org_name or base_emp.get("restaurant_name", "")}
        system_prompt = build_system_prompt(active_emp)

        new_user_message = HumanMessage(content=user_message)

        try:
            graph_output = await self._graph.ainvoke(
                {
                    # Only the new message — history lives in MemorySaver (thread_id)
                    "messages":       [SystemMessage(content=system_prompt), new_user_message],
                    "owner_id":       owner_id,
                    "business_type":  employee.get("business_type", "RESTAURANT"),
                    "ai_employee_id": employee_id,
                    "ai_employee":    active_emp,
                },
                config={"configurable": {"thread_id": active_session_id}},
            )
            # Extract last AI message as the reply
            output_messages = graph_output.get("messages", [])
            reply = ""
            for msg in reversed(output_messages):
                if isinstance(msg, AIMessage) and msg.content and isinstance(msg.content, str):
                    reply = msg.content.strip()
                    break
            if not reply:
                reply = "Kuch problem ho gayi, please dobara try karein."
        except Exception as graph_err:
            print(f"❌ Graph Error in chat_service: {graph_err}")
            reply = "Abhi kuch technical issue hai, thodi der mein try karein."

        result = {
            "reply": reply,
            "cart": [],
            "retrieved_items": []
        }

        reply = result["reply"]
        cart = result["cart"]
        retrieved_items = result["retrieved_items"]

        current_org_id = cached_emp_info.get("org_id") or str(employee.get("org_id", ""))
        # Persist conversation and updated messages in MongoDB (using customer_id & org_id references)
        await self.conversation_repo.save_message(
            session_id=active_session_id,
            owner_id=owner_id,
            org_id=current_org_id,
            employee_id=employee_id,
            user_message=user_message,
            assistant_reply=reply,
            cart=cart,
            customer_id=customer_id
        )

        # NOTE: No in-memory history cache needed here.
        # LangGraph MemorySaver (thread_id) is the single source of truth for
        # conversation state during an active session. MongoDB is the persistence
        # layer for analytics/display — not for feeding the LLM.

        return {
            "success": True,
            "data": {
                "session_id": active_session_id,
                "customer_phone_number": clean_phone,
                "customer_id": customer_id,
                "reply": reply,
                "cart": cart,
                "retrieved_items": retrieved_items,
                "llm_time": result.get("llm_time", 0.0),
                "llm_cost_inr": result.get("llm_cost_inr", 0.0),
                "qdrant_time": result.get("qdrant_time", 0.0),
                "in_tokens": result.get("in_tokens", 0),
                "out_tokens": result.get("out_tokens", 0),
            }
        }

    async def get_owner_conversations(self, current_user: dict, page: int = 1, limit: int = 20) -> dict:
        owner_id = str(current_user["_id"])
        skip = (page - 1) * limit
        conversations = await self.conversation_repo.get_by_owner(owner_id, skip=skip, limit=limit)
        total_records = await self.conversation_repo.count_by_owner(owner_id)

        # Batch resolve customer details (phone_number, name) from customers collection
        customer_ids = list({doc.get("customer_id") for doc in conversations if doc.get("customer_id")})
        cust_map = {}
        if customer_ids:
            cust_docs = await self.customer_repo.get_by_ids(customer_ids)
            cust_map = {str(c["_id"]): c for c in cust_docs}

        clean_docs = []
        for doc in conversations:
            cid = doc.get("customer_id")
            c_info = cust_map.get(cid, {}) if cid else {}
            clean_docs.append({
                "id": str(doc["_id"]),
                "session_id": doc["session_id"],
                "owner_id": doc["owner_id"],
                "employee_id": doc["employee_id"],
                "customer_id": cid,
                "customer_phone_number": c_info.get("phone_number"),
                "customer_name": c_info.get("name"),
                "message_count": len(doc.get("messages", [])),
                "messages": doc.get("messages", []),
                "latest_cart": doc.get("latest_cart", []),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            })

        return {
            "success": True,
            "data": clean_docs,
            "total": total_records,
            "page": page,
            "limit": limit
        }

    async def delete_conversation(self, conversation_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        deleted = await self.conversation_repo.delete_by_id(conversation_id, owner_id)
        if not deleted:
            return {"success": False, "message": "Conversation not found or unauthorized."}
        return {"success": True, "message": "Conversation deleted successfully."}

    async def bulk_delete_conversations(self, conversation_ids: list[str], current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        if not conversation_ids:
            return {"success": False, "message": "No conversation IDs provided for deletion."}
        count = await self.conversation_repo.delete_by_ids(conversation_ids, owner_id)
        return {
            "success": True,
            "message": f"Successfully deleted {count} conversation(s).",
            "deleted_count": count
        }

    async def get_conversation_by_id(self, conversation_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        conv = await self.conversation_repo.get_by_id(conversation_id)
        if not conv:
            return {"success": False, "message": "Conversation not found."}
        if conv.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to view this conversation."}

        cid = conv.get("customer_id")
        c_info = {}
        if cid:
            c_doc = await self.customer_repo.get_by_id(cid)
            if c_doc:
                c_info = c_doc

        return {
            "success": True,
            "data": {
                "id": str(conv["_id"]),
                "session_id": conv["session_id"],
                "owner_id": conv["owner_id"],
                "employee_id": conv["employee_id"],
                "customer_id": cid,
                "customer_phone_number": c_info.get("phone_number"),
                "customer_name": c_info.get("name"),
                "message_count": len(conv.get("messages", [])),
                "messages": conv.get("messages", []),
                "latest_cart": conv.get("latest_cart", []),
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
            }
        }

    async def get_conversations_by_phone(
        self,
        phone_number: str,
        org_id: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        phone_clean = phone_number.strip()
        from bson import ObjectId
        from bson.errors import InvalidId

        customer = await self.customer_repo.customers.find_one({"phone_number": phone_clean})
        if not customer:
            try:
                customer = await self.customer_repo.customers.find_one({"_id": ObjectId(phone_clean)})
            except (InvalidId, TypeError):
                customer = None

        query_conditions = []
        if customer:
            c_id = str(customer["_id"])
            c_phone = customer.get("phone_number", "")
            query_conditions.append({"customer_id": c_id})
            if c_phone:
                query_conditions.append({"session_id": {"$regex": c_phone}})
        else:
            query_conditions.append({"customer_id": phone_clean})
            query_conditions.append({"session_id": {"$regex": phone_clean}})

        filter_query: dict[str, Any] = {"$or": query_conditions}
        if org_id:
            filter_query = {
                "$and": [
                    {"$or": query_conditions},
                    {"$or": [{"org_id": org_id}, {"org_id": {"$exists": False}}]}
                ]
            }

        skip = (page - 1) * limit
        conversations = await self.conversation_repo.conversations.find(filter_query)\
            .sort("updated_at", -1).skip(skip).limit(limit).to_list(length=limit)
        total_records = await self.conversation_repo.conversations.count_documents(filter_query)

        clean_docs = []
        for doc in conversations:
            clean_docs.append({
                "id": str(doc["_id"]),
                "session_id": doc["session_id"],
                "owner_id": doc["owner_id"],
                "org_id": doc.get("org_id"),
                "employee_id": doc.get("employee_id"),
                "customer_id": doc.get("customer_id"),
                "customer_phone_number": customer.get("phone_number") if customer else phone_clean,
                "customer_name": customer.get("name") if customer else None,
                "message_count": len(doc.get("messages", [])),
                "messages": doc.get("messages", []),
                "latest_cart": doc.get("latest_cart", []),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            })

        return {
            "success": True,
            "data": clean_docs,
            "total": total_records,
            "page": page,
            "limit": limit
        }

