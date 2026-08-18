from .customer_repository import CustomerRepository


class CustomerService:

    def __init__(self):
        self.repository = CustomerRepository()

    async def get_owner_customers(self, current_user: dict, page: int = 1, limit: int = 20) -> dict:
        owner_id = str(current_user["_id"])
        skip = (page - 1) * limit
        customers = await self.repository.get_by_owner(owner_id, skip=skip, limit=limit)
        total = await self.repository.count_by_owner(owner_id)

        return {
            "success": True,
            "data": customers,
            "total": total,
            "page": page,
            "limit": limit
        }

    async def get_customer_by_id(self, customer_id: str) -> dict:
        customer = await self.repository.get_by_id(customer_id)
        if not customer:
            return {"success": False, "message": "Customer not found."}

        return {
            "success": True,
            "data": {
                "id": str(customer["_id"]),
                "owner_id": customer.get("owner_id"),
                "name": customer.get("name"),
                "phone_number": customer.get("phone_number"),
                "role": customer.get("role", "CUSTOMER"),
                "total_conversations": customer.get("total_conversations", 1),
                "created_at": customer.get("created_at"),
                "updated_at": customer.get("updated_at"),
            }
        }
