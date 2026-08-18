from fastapi import APIRouter,Depends
from app.middleware.auth import get_current_user
from .schemas.user_schema import (
    LoginRequest,
    RegisterRequest,
    ChangePasswordRequest,
)
from .schemas.forgot_password_schema import ForgotPasswordRequest
from .schemas.reset_password_schema import ResetPasswordRequest
from .auth_service import AuthService
from .mapper import user_response
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

service = AuthService()


@router.post("/register")
async def register(request: RegisterRequest):
    return await service.register(request)


@router.post("/login")
async def login(
    request: LoginRequest,
):
    return await service.login(request)

@router.get("/profile")
async def get_profile(
    current_user=Depends(get_current_user)
):
    return user_response(current_user)


@router.put("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user=Depends(get_current_user)
):
    return await service.change_password(
        current_user=current_user,
        request=request
    )

@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest
):
    return await service.forgot_password(request)

@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest
):
    return await service.reset_password(request)

 

 




