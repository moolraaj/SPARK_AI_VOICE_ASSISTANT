from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .customer_service import CustomerService


service = CustomerService()

customers_router = APIRouter(prefix="/customers", tags=["Customers"])
customer_router = APIRouter(prefix="/customer", tags=["Customer"])


@customers_router.get("/my-customers")
async def get_my_customers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get list of all registered customers who called/chatted with the business.
    """
    return await service.get_owner_customers(current_user=current_user, page=page, limit=limit)


@customer_router.get("/{customer_id}")
async def get_customer_details(
    customer_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get detailed customer profile by ID.
    """
    return await service.get_customer_by_id(customer_id)
