from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import MONGODB_URI, DATABASE_NAME


class MongoDB:

    def __init__(self):
        self.client = None
        self.database = None

    async def connect(self):
        self.client = AsyncIOMotorClient(
            MONGODB_URI,
            tz_aware=True
        )

        self.database = self.client[DATABASE_NAME]

        print("✅ MongoDB Connected")

    async def disconnect(self):
        if self.client:
            self.client.close()
            print("❌ MongoDB Disconnected")
    


mongodb = MongoDB()