from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


 

class BusinessType(BaseModel):
    id: Optional[str] = None

    name: str = Field(..., min_length=2, max_length=100)

    description: Optional[str] = None

    is_active: bool = True

    created_at: datetime

    updated_at: datetime


 

class CreateBusinessTypeRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

    description: Optional[str] = None


 

class UpdateBusinessTypeRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)

    description: Optional[str] = None

    is_active: Optional[bool] = None


 

class BusinessTypeResponse(BaseModel):
    id: str

    name: str

    description: Optional[str]

    is_active: bool

    created_at: datetime

    updated_at: datetime