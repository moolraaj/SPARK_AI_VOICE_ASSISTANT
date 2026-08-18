from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    BUSINESS_OWNER = "BUSINESS_OWNER"
    CUSTOMER = "GUEST"


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    phone_number: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    @field_validator("confirm_password")
    @classmethod
    def validate_password(cls, confirm_password: str, values):
        password = values.data.get("password")
        if password != confirm_password:
            raise ValueError("Passwords do not match.")
        return confirm_password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

class UpdateUserRequest(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=100)
    email: EmailStr | None = None
    phone_number: str | None = Field(None, min_length=10, max_length=15)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirm password do not match.")
        return self