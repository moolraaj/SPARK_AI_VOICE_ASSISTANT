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
    owner_id: str
    business_platform_id: str
    business_type_id: str
    tenant_id: str
    name: str
    slug: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[AddressSchema] = None
    hardware_device_id: Optional[str] = None
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
    hardware_device_id: Optional[str] = None


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
    hardware_device_id: Optional[str] = None
    is_active: Optional[bool] = None


class LinkDeviceRequest(BaseModel):
    """Request body for linking a hardware device to an organization."""
    device_id: str = Field(..., min_length=3, max_length=64, description="Hardware device ID (e.g. SPARK-F89A4E40C86C)")


class UnlinkDeviceRequest(BaseModel):
    """Request body for unlinking a hardware device from an organization."""
    device_id: str = Field(..., min_length=3, max_length=64)


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
    hardware_device_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime