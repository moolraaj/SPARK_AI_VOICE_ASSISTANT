from app.database.mongodb import mongodb
from bson import ObjectId
from bson.errors import InvalidId


class AuthRepository:

    @property
    def users(self):
        return mongodb.database["users"]

    @property
    def reset_otps(self):
        return mongodb.database["reset_password_otps"]

    async def get_user_by_email(self, email: str):
        return await self.users.find_one({"email": email})

    async def get_user_by_id(self, user_id: str):

        if not user_id:
            return None

        try:
            object_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            return None

        return await self.users.find_one({"_id": object_id})
    
    async def get_user_by_phone(self, phone_number: str):
        return await self.users.find_one({"phone_number": phone_number})
    
    async def create_user(self, user: dict):
        result = await self.users.insert_one(user)
        return str(result.inserted_id)

    async def delete_user(self, user_id: ObjectId):
        try:
            return await self.users.delete_one({"_id": user_id})
        except (InvalidId, TypeError):
            return None

    async def update_user(
        self,
        object_id: ObjectId,
        update_data: dict
    ):
        return await self.users.update_one(
            {"_id": object_id},
            {"$set": update_data}
        )

    async def get_all_users(self, skip: int, limit: int):
        return await self.users.find().skip(skip).limit(limit).to_list(length=limit)

    async def count_users(self):
        return await self.users.count_documents({})

    async def delete_password_reset_otp(self, email: str):
        return await self.reset_otps.delete_one({"email": email})

    async def save_password_reset_otp(self, otp_data: dict):
        return await self.reset_otps.insert_one(otp_data)

    async def get_password_reset_otp(self, email: str):
        return await self.reset_otps.find_one({"email": email})