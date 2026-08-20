from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import mongodb


class AIEmployeeRepository:

    @property
    def ai_employees(self):
        return mongodb.database["ai_employees"]

    # ─── Read ─────────────────────────────────────────────────────────────────

    async def get_all(self, skip: int, limit: int, query: dict | None = None):
        filter_query = query if query is not None else {}
        return await self.ai_employees.find(filter_query).skip(skip).limit(limit).to_list(length=limit)

    async def count(self, query: dict | None = None):
        filter_query = query if query is not None else {}
        return await self.ai_employees.count_documents(filter_query)

    async def get_by_org(self, org_id: str, skip: int, limit: int):
        return await self.ai_employees.find({"org_id": org_id}).skip(skip).limit(limit).to_list(length=limit)

    async def count_by_org(self, org_id: str):
        return await self.ai_employees.count_documents({"org_id": org_id})

    async def get_by_id(self, ai_employee_id: ObjectId):
        return await self.ai_employees.find_one({"_id": ai_employee_id})

    async def get_by_name_and_org(self, name: str, org_id: str):
        return await self.ai_employees.find_one({"name": name, "org_id": org_id})

    # ─── Write ────────────────────────────────────────────────────────────────

    async def create(self, data: dict):
        result = await self.ai_employees.insert_one(data)
        return str(result.inserted_id)

    async def update(self, ai_employee_id: ObjectId, data: dict):
        return await self.ai_employees.update_one(
            {"_id": ai_employee_id},
            {"$set": data}
        )

    async def delete(self, ai_employee_id: ObjectId):
        try:
            return await self.ai_employees.delete_one({"_id": ai_employee_id})
        except (InvalidId, TypeError):
            return None



    async def get_active_by_org(self, org_id: str):
        employee = await self.ai_employees.find_one({
            "org_id": org_id,
            "is_active": True,
        })
        if not employee:
            employee = await self.ai_employees.find_one({"org_id": org_id})
        return employee

