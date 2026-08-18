from pydantic import BaseModel, EmailStr, Field, model_validator


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6
    )
    new_password: str = Field(
        ...,
        min_length=8
    )
    confirm_password: str = Field(
        ...,
        min_length=8
    )
    @model_validator(mode="after")
    def validate_password(self):
        if self.new_password != self.confirm_password:
            raise ValueError(
                "New password and confirm password do not match."
            )
        return self