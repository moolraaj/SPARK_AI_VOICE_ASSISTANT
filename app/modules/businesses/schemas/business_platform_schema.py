from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"


# ─── Pricing ───────────────────────────────────────────────────────────────────

class PricingSchema(BaseModel):
    base_price: float = Field(..., ge=0)      # SuperAdmin cost price
    selling_price: float = Field(..., ge=0)   # Customer pays
    currency: Currency = Currency.INR


# ─── BusinessPlatform Schemas ──────────────────────────────────────────────────

class BusinessPlatform(BaseModel):
    id: Optional[str] = None
    business_type_id: str
    name: str
    description: Optional[str] = None
    features: List[str] = []               # ["AI Chat", "Voice Support", ...]
    duration: int = 1                       # plan duration in months (1, 3, 6, 12)
    pricing: PricingSchema
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class CreateBusinessPlatformRequest(BaseModel):
    business_type_id: str
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    features: List[str] = []
    duration: int = Field(default=1, ge=1)   # in months e.g. 1, 3, 6, 12
    pricing: PricingSchema


class UpdateBusinessPlatformRequest(BaseModel):
    business_type_id: Optional[str] = None
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    features: Optional[List[str]] = None
    duration: Optional[int] = None
    pricing: Optional[PricingSchema] = None
    is_active: Optional[bool] = None


class BusinessPlatformResponse(BaseModel):
    id: str
    business_type_id: str
    name: str
    description: Optional[str]
    features: List[str]
    duration: int
    pricing: PricingSchema
    is_active: bool
    created_at: datetime
    updated_at: datetime