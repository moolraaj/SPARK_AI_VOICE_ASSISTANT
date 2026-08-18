from fastapi import APIRouter

from app.modules.auth.auth_route import router as auth_router
from app.modules.auth.user_route import user_router, users_router
from app.modules.businesses.business_type.business_type_route import (
    business_type_router,
    business_types_router,
)
from app.modules.businesses.business_platform.business_platform_route import (
    business_platform_router,
    business_platforms_router,
)
from app.modules.organizations.organization_route import (
    organization_router,
    organizations_router,
)
from app.modules.ai_employees.ai_employee_route import (
    ai_employee_router,
    ai_employees_router,
)
from app.modules.uploads.upload_route import (
    upload_router,
    uploads_router,
)
from app.modules.catalogs.catalog_route import (
    catalog_categories_router,
    catalog_category_router,
    catalog_items_router,
    catalog_item_router,
)
from app.modules.conversations.chat_route import (
    chat_router,
    conversations_router,
    conversation_router,
)
from app.modules.customers.customer_route import customers_router, customer_router


api_router = APIRouter(prefix="/api/v1")


api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(users_router)

api_router.include_router(business_types_router)
api_router.include_router(business_type_router)

api_router.include_router(business_platforms_router)
api_router.include_router(business_platform_router)

api_router.include_router(organizations_router)
api_router.include_router(organization_router)

api_router.include_router(ai_employees_router)
api_router.include_router(ai_employee_router)

api_router.include_router(upload_router)
api_router.include_router(uploads_router)

api_router.include_router(catalog_categories_router)
api_router.include_router(catalog_category_router)
api_router.include_router(catalog_items_router)
api_router.include_router(catalog_item_router)

api_router.include_router(chat_router)
api_router.include_router(conversations_router)
api_router.include_router(conversation_router)

api_router.include_router(customers_router)
api_router.include_router(customer_router)
