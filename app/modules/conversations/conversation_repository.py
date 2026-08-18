from app.database.mongodb import mongodb
from app.core.datetime import utc_now


class ConversationRepository:

    @property
    def conversations(self):
        return mongodb.database["conversations"]

    async def get_by_session_id(self, session_id: str) -> dict | None:
        return await self.conversations.find_one({"session_id": session_id})

    async def get_by_owner(self, owner_id: str, skip: int = 0, limit: int = 20) -> list[dict]:
        return await self.conversations.find({"owner_id": owner_id}).sort("updated_at", -1).skip(skip).limit(limit).to_list(length=limit)

    async def count_by_owner(self, owner_id: str) -> int:
        return await self.conversations.count_documents({"owner_id": owner_id})

    async def get_by_customer_id(self, customer_id: str, skip: int = 0, limit: int = 20) -> list[dict]:
        return await self.conversations.find({"customer_id": customer_id}).sort("updated_at", -1).skip(skip).limit(limit).to_list(length=limit)

    async def count_by_customer_id(self, customer_id: str) -> int:
        return await self.conversations.count_documents({"customer_id": customer_id})

    async def get_by_id(self, conversation_id: str) -> dict | None:
        from bson import ObjectId
        from bson.errors import InvalidId
        try:
            return await self.conversations.find_one({"_id": ObjectId(conversation_id)})
        except (InvalidId, TypeError):
            return None

    async def delete_by_id(self, conversation_id: str, owner_id: str) -> bool:
        from bson import ObjectId
        try:
            res = await self.conversations.delete_one({
                "_id": ObjectId(conversation_id),
                "owner_id": owner_id
            })
            return res.deleted_count > 0
        except Exception:
            return False

    async def delete_by_ids(self, conversation_ids: list[str], owner_id: str) -> int:
        from bson import ObjectId
        obj_ids = []
        for cid in conversation_ids:
            try:
                obj_ids.append(ObjectId(cid))
            except Exception:
                pass
        if not obj_ids:
            return 0
        res = await self.conversations.delete_many({
            "_id": {"$in": obj_ids},
            "owner_id": owner_id
        })
        return res.deleted_count

    async def save_message(
        self,
        session_id: str,
        owner_id: str,
        employee_id: str,
        user_message: str,
        assistant_reply: str,
        cart: list[dict] | None = None,
        customer_id: str | None = None
    ) -> dict:
        now = utc_now()
        new_user_msg = {"role": "user", "content": user_message, "timestamp": now.isoformat()}
        new_assistant_msg = {"role": "assistant", "content": assistant_reply, "timestamp": now.isoformat()}
        if cart:
            new_assistant_msg["cart"] = cart

        existing = await self.get_by_session_id(session_id)
        if existing:
            set_dict = {
                "updated_at": now,
                "latest_cart": cart or existing.get("latest_cart", [])
            }
            if customer_id:
                set_dict["customer_id"] = customer_id

            await self.conversations.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": {"$each": [new_user_msg, new_assistant_msg]}},
                    "$set": set_dict
                }
            )
            updated_doc = await self.get_by_session_id(session_id)
            return updated_doc
        else:
            doc = {
                "session_id": session_id,
                "owner_id": owner_id,
                "employee_id": employee_id,
                "customer_id": customer_id,
                "messages": [new_user_msg, new_assistant_msg],
                "latest_cart": cart or [],
                "created_at": now,
                "updated_at": now,
            }
            await self.conversations.insert_one(doc)
            return doc
