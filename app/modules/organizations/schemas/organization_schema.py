from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class AddressSchema(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None


class Organization(BaseModel):
    id: Optional[str] = None
    owner_id: str                    # ref → User (auto from token)
    business_platform_id: str        # ref → BusinessPlatform
    business_type_id: str            # ref → BusinessType
    tenant_id: str                   # auto-generated unique workspace ID
    name: str
    slug: str                        # auto-generated from name
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[AddressSchema] = None
    did_number: Optional[str] = None          # Vobiz DID number assigned to this org
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class CreateOrganizationRequest(BaseModel):
    business_platform_id: str
    business_type_id: str
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[AddressSchema] = None
    did_number: Optional[str] = None          # Vobiz DID number


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    business_platform_id: Optional[str] = None
    business_type_id: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[AddressSchema] = None
    did_number: Optional[str] = None          # Vobiz DID number
    is_active: Optional[bool] = None


class OrganizationResponse(BaseModel):
    id: str
    owner_id: str
    business_platform_id: str
    business_type_id: Optional[str] = None
    tenant_id: str
    name: str
    slug: str
    description: Optional[str]
    logo_url: Optional[str]
    website: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[AddressSchema]
    did_number: Optional[str] = None          # Vobiz DID number
    is_active: bool
    created_at: datetime
    updated_at: datetime
