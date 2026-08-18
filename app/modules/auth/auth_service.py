from datetime import timedelta
import asyncio
from .repository import AuthRepository
from .schemas.user_schema import (
    LoginRequest,
    RegisterRequest,
    ChangePasswordRequest
)
from app.core.security import create_access_token, hash_password, verify_password, hash_otp, verify_otp
from app.core.datetime import timestamps, utc_now
from .mapper import user_response
from app.core.config import ACCESS_TOKEN_EXPIRE_DAYS
from bson import ObjectId
from .schemas.forgot_password_schema import ForgotPasswordRequest
import random
from ...utils.email.email_service import EmailService
from ...utils.email.email_templates import forgot_password_template
from ...common.constants.constant import FORGET_PASSWORD_EMAIL_OTP_TIME
from .schemas.reset_password_schema import ResetPasswordRequest


class AuthService:

    def __init__(self):
        self.repository = AuthRepository()

    async def register(self, request: RegisterRequest):

        user, phone = await asyncio.gather(
            self.repository.get_user_by_email(request.email),
            self.repository.get_user_by_phone(request.phone_number)
        )

        if phone:
            return {
                "success": False,
                "message": "phone number already exists."
            }
        if user:
            return {
                "success": False,
                "message": "Email already exists."
            }
        hashed_password = hash_password(request.password)
        new_user = {
            "name": request.name,
            "email": request.email,
            "phone_number": request.phone_number,
            "password": hashed_password,
            "role": "CUSTOMER",
            "is_active": True,
            "is_verified": False,
            **timestamps(),
        }
        user_id = await self.repository.create_user(new_user)
        return {
            "success": True,
            "message": "User Registered Successfully",
            "data": {
                "id": user_id,
                "name": request.name,
                "email": request.email,
                "phone_number": request.phone_number,
            },
        }
    
    #login handler
    async def login(self, request: LoginRequest):

        user = await self.repository.get_user_by_email(request.email)

        if not user or not verify_password(request.password, user["password"]):
            return {
                "success": False,
                "message": "Invalid email or password."
            }

        access_token = create_access_token({
            "sub": str(user["_id"]),
            "role": user["role"]
        })
        expires_at = utc_now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        
        return {
            "success": True,
            "message": "Login successful.",
            "data": {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_at": expires_at.isoformat(),
                "user": user_response(user)["user"]
            }
        }
    

    # chnage password handler
    async def change_password(
        self,
        current_user: dict,
        request: ChangePasswordRequest
    ):
        user_id = current_user["_id"]
        user = await self.repository.get_user_by_id(user_id)
        if not user:
            return {
                "success": False,
                "message": "User not found."
            }
        if not verify_password(
            request.current_password,
            user["password"]
        ):
            return {
                "success": False,
                "message": "Current password is incorrect."
            }

        if request.current_password == request.new_password:
            return {
                "success": False,
                "message": "New password must be different from current password."
            }

        hashed_password = hash_password(request.new_password)
        result = await self.repository.update_user(
            ObjectId(user_id),
            {
                "password": hashed_password,
                "updated_at": utc_now()
            }
        )
        if result.modified_count == 0:
            return {
                "success": False,
                "message": "Password could not be updated."
            }
        return {
            "success": True,
            "message": "Password changed successfully."
        }

    async def forgot_password(
        self,
        request: ForgotPasswordRequest
    ):

        user = await self.repository.get_user_by_email(
            request.email
        )
        if not user:
            return {
                "success": False,
                "message": "If this email is registered, an OTP has been sent."
            }

        await self.repository.delete_password_reset_otp(
            request.email
        )
        otp = str(
            random.randint(
                100000,
                999999
            )
        )
        hashed_otp = hash_otp(otp)
        otp_data = {
            "user_id": user["_id"],
            "email": user["email"],
            "otp_hash": hashed_otp,
            "expires_at": utc_now() + timedelta(minutes=FORGET_PASSWORD_EMAIL_OTP_TIME),
            "created_at": utc_now()
        }
        await self.repository.save_password_reset_otp(
            otp_data
        )
        try:
            EmailService.send_email(
                receiver_email=user["email"],
                subject="Reset Your Password",
                body=forgot_password_template(
                    user["name"],
                    otp,
                    FORGET_PASSWORD_EMAIL_OTP_TIME
                )
            )
        except Exception:
            await self.repository.delete_password_reset_otp(request.email)
            return {
                "success": False,
                "message": "Failed to send OTP email. Please try again."
            }
        return {
            "success": True,
            "message": "OTP sent successfully to your email."
        }


    async def reset_password(
        self,
        request: ResetPasswordRequest
    ):
        otp_record = await self.repository.get_password_reset_otp(
            request.email
        )
        if not otp_record:
            return {
                "success": False,
                "message": "Invalid or expired OTP."
            }
        if otp_record["expires_at"] < utc_now():
            await self.repository.delete_password_reset_otp(
                request.email
            )
            return {
                "success": False,
                "message": "OTP has expired."
            }

        if not verify_otp(
            request.otp,
            otp_record["otp_hash"]
        ):
            return {
                "success": False,
                "message": "Invalid OTP."
            }

        user = await self.repository.get_user_by_id(
            otp_record["user_id"]
        )

        if not user:
            return {
                "success": False,
                "message": "User not found."
            }

        if verify_password(
            request.new_password,
            user["password"]
        ):
            return {
                "success": False,
                "message": "New password cannot be the same as the current password."
            }
        hashed_password = hash_password(request.new_password)
        result = await self.repository.update_user(
            otp_record["user_id"],
            {
                "password": hashed_password,
                "updated_at": utc_now()
            }
        )
        if result.modified_count == 0:
            return {
                "success": False,
                "message": "Password could not be updated."
            }
        await self.repository.delete_password_reset_otp(
            request.email
        )
        return {
            "success": True,
            "message": "Password reset successfully."
        }