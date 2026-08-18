from bson import ObjectId

from app.core.datetime import timestamps
from app.core.security import hash_password
from app.database.mongodb import mongodb
from app.common.constants.constant import SUPER_ADMIN_EMAIL,SUPER_ADMIN_PASSWORD,SUPER_ADMIN_NAME,SUPER_ADMIN_PHONE_NUMBER


async def seed_super_admin():

    users = mongodb.database["users"]

    existing = await users.find_one(
        {"email": SUPER_ADMIN_EMAIL}
    )

    if existing:
        print("✅ Super Admin already exists.")
        return

    super_admin = {
        "_id": ObjectId(),
        "name": SUPER_ADMIN_NAME,
        "email": SUPER_ADMIN_EMAIL,
        "phone_number":SUPER_ADMIN_PHONE_NUMBER,
        "password": hash_password(SUPER_ADMIN_PASSWORD),
        "role": "SUPER_ADMIN",
        "is_active": True,
        "is_verified": True,
        **timestamps(),
    }

    await users.insert_one(super_admin)

    print("✅ Super Admin created successfully.")