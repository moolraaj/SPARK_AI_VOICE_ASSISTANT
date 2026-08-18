from fastapi import Request, HTTPException, status

from app.core.security import verify_access_token
from app.modules.auth.repository import AuthRepository


repository = AuthRepository()


async def get_current_user(request: Request):

    authorization = request.headers.get("Authorization")
     

    if not authorization:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing."
        )

    if not authorization.startswith("Bearer "):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header."
        )

    token = authorization.split(" ")[1]
     

    payload = verify_access_token(token)


    user_id = payload.get("sub")

    if not user_id:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token."
        )

    user = await repository.get_user_by_id(user_id)
    

    if not user:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found."
        )

    return user


async def require_super_admin(request: Request):
    user = await get_current_user(request)
    role = str(user.get("role", "")).upper()
    if role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Admin is authorized to perform this action."
        )
    return user