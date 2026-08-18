from typing import Optional
from pydantic import BaseModel, Field


# ── Catalog Category Schemas ──────────────────────────────────────────────────

class CreateCategoryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_order: Optional[int] = 0
    document_id: Optional[str] = None


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    display_order: Optional[int] = None
    document_id: Optional[str] = None
    status: Optional[str] = None  # "ACTIVE", "INACTIVE"


# ── Catalog Item Schemas ──────────────────────────────────────────────────────

class CreateCatalogItemRequest(BaseModel):
    category_id: str
    document_id: Optional[str] = None  # <--- Reference to uploaded document _id!
    item_name: str = Field(..., min_length=1, max_length=150)
    price: float = Field(..., ge=0)
    is_veg: Optional[bool] = True
    description: Optional[str] = None


class UpdateCatalogItemRequest(BaseModel):
    category_id: Optional[str] = None
    document_id: Optional[str] = None
    item_name: Optional[str] = Field(None, min_length=1, max_length=150)
    price: Optional[float] = Field(None, ge=0)
    is_veg: Optional[bool] = None
    description: Optional[str] = None
    status: Optional[str] = None  # "ACTIVE", "INACTIVE"
