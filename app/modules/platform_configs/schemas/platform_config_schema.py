from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ─── Base Model ───────────────────────────────────────────────────────────────

class PlatformConfig(BaseModel):
    id: Optional[str] = None
    business_type_id: str
    instructions: str
    rules: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


# ─── Create Request ───────────────────────────────────────────────────────────

class CreatePlatformConfigRequest(BaseModel):
    business_type_id: str = Field(..., description="Business Type ID (ObjectId)")
    instructions: str = Field(..., min_length=1)
    rules: str = Field(..., min_length=1)
    is_active: bool = True


# ─── Update Request ───────────────────────────────────────────────────────────

class UpdatePlatformConfigRequest(BaseModel):
    instructions: Optional[str] = Field(None, min_length=1)
    rules: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


# ─── Response Schema ──────────────────────────────────────────────────────────

class PlatformConfigResponse(BaseModel):
    id: str
    business_type_id: str
    instructions: str
    rules: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
