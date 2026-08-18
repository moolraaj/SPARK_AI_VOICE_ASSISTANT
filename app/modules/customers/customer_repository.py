from bson import ObjectId
from bson.errors import InvalidId
from app.database.mongodb import mongodb
from app.core.datetime import utc_now, timestamps


class CustomerRepository:

    @property
    def customers(self):
        return mongodb.database["customers"]

    async def get_by_phone(self, owner_id: str, phone_number: str) -> dict | None:
        """Find customer by owner_id and phone_number."""
        return await self.customers.find_one({
            "owner_id": owner_id,
            "phone_number": phone_number
        })

    async def get_by_id(self, customer_id: str) -> dict | None:
        try:
            return await self.customers.find_one({"_id": ObjectId(customer_id)})
        except (InvalidId, TypeError):
            return None

    async def get_by_ids(self, customer_ids: list[str]) -> list[dict]:
        obj_ids = []
        for cid in customer_ids:
            try:
                obj_ids.append(ObjectId(cid))
            except (InvalidId, TypeError):
                pass
        if not obj_ids:
            return []
        return await self.customers.find({"_id": {"$in": obj_ids}}).to_list(length=len(obj_ids))

    async def ensure_indexes(self):
        """Ensure unique compound index on (owner_id, phone_number)."""
        try:
            await self.customers.create_index(
                [("owner_id", 1), ("phone_number", 1)],
                unique=True,
                name="unique_owner_customer_phone"
            )
        except Exception:
            pass

    async def create_customer(self, customer_data: dict) -> str:
        """Create new customer record in customers collection with unique index safeguard."""
        await self.ensure_indexes()
        customer_data["role"] = "CUSTOMER"
        customer_data["total_conversations"] = customer_data.get("total_conversations", 1)
        if "created_at" not in customer_data:
            customer_data.update(timestamps())

        try:
            result = await self.customers.insert_one(customer_data)
            return str(result.inserted_id)
        except Exception:
            # Handle duplicate phone key race condition gracefully
            existing = await self.get_by_phone(customer_data["owner_id"], customer_data["phone_number"])
            if existing:
                return str(existing["_id"])
            raise

    async def update_customer(self, customer_id: str, update_data: dict):
        update_data["updated_at"] = utc_now()
        try:
            return await self.customers.update_one(
                {"_id": ObjectId(customer_id)},
                {"$set": update_data, "$inc": {"total_conversations": 1}}
            )
        except (InvalidId, TypeError):
            return None

    async def get_by_owner(self, owner_id: str, skip: int = 0, limit: int = 20) -> list[dict]:
        docs = await self.customers.find({"owner_id": owner_id}).sort("updated_at", -1).skip(skip).limit(limit).to_list(length=limit)
        return [
            {
                "id": str(d["_id"]),
                "owner_id": d.get("owner_id"),
                "name": d.get("name"),
                "phone_number": d.get("phone_number"),
                "role": d.get("role", "CUSTOMER"),
                "total_conversations": d.get("total_conversations", 1),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
            for d in docs
        ]

    async def count_by_owner(self, owner_id: str) -> int:
        return await self.customers.count_documents({"owner_id": owner_id})
