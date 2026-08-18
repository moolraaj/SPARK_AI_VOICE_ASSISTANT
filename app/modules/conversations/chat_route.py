from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.chat_schema import SendChatMessageRequest, BulkDeleteConversationsRequest
from .chat_service import ChatService


chat_service = ChatService()

# ── Router Definitions ───────────────────────────────────────────────────────

chat_router          = APIRouter(prefix="/ai-employee", tags=["AI Employee Chat"])
conversations_router = APIRouter(prefix="/conversations", tags=["Conversations"])
conversation_router  = APIRouter(prefix="/conversation", tags=["Conversation"])


# ─── Public Chat Endpoint ────────────────────────────────────────────────────

@chat_router.post("/{employee_id}/chat")
async def chat_with_ai_employee(
    employee_id: str,
    request: SendChatMessageRequest
):
    """
    FREE / PUBLIC: AI Employee Chat Endpoint (For Telephony Voice Sessions / Public Customer Chat Widgets).
    """
    return await chat_service.chat_with_employee(
        employee_id=employee_id,
        user_message=request.message,
        session_id=request.session_id,
        customer_phone_number=request.customer_phone_number,
        customer_name=request.customer_name
    )


# ─── Conversations (Plural List Routes) ──────────────────────────────────────

@conversations_router.get("/my-history")
@chat_router.get("/conversations/my-history")
async def get_my_conversations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get conversation history logs for the logged-in business owner.
    """
    return await chat_service.get_owner_conversations(current_user=current_user, page=page, limit=limit)


@conversations_router.get("/by-phone/{phone_number}")
@chat_router.get("/conversations/by-phone/{phone_number}")
async def get_conversations_by_phone(
    phone_number: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get full conversation & call history by customer phone number.
    """
    return await chat_service.get_conversations_by_phone(phone_number=phone_number, page=page, limit=limit)


@conversations_router.post("/bulk-remove")
@chat_router.post("/conversations/bulk-remove")
@conversations_router.post("/bulk-delete")
@chat_router.post("/conversations/bulk-delete")
async def bulk_delete_conversations(
    request: BulkDeleteConversationsRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Bulk delete multiple conversation records at once by array of _ids.
    """
    return await chat_service.bulk_delete_conversations(request.conversation_ids, current_user)


# ─── Conversation (Singular Resource Routes) ──────────────────────────────────

@conversation_router.get("/get-by-id/{conversation_id}")
@chat_router.get("/conversations/get-by-id/{conversation_id}")
async def get_single_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Get single conversation record by MongoDB _id.
    """
    return await chat_service.get_conversation_by_id(conversation_id, current_user)


@conversation_router.delete("/remove/{conversation_id}")
@conversations_router.delete("/remove/{conversation_id}")
@conversations_router.delete("/{conversation_id}")
@chat_router.delete("/conversations/{conversation_id}")
async def delete_single_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    PROTECTED: Delete a single conversation record by MongoDB _id.
    """
    return await chat_service.delete_conversation(conversation_id, current_user)
