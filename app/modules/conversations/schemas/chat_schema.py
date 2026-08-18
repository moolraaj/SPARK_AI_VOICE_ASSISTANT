from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SendChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message content")
    session_id: Optional[str] = Field(None, description="Optional conversation session ID (UUID/MongoDB ID)")
    customer_phone_number: Optional[str] = Field(None, description="Caller / Customer phone number")
    customer_name: Optional[str] = Field(None, description="Caller name if known")


class ChatMessageResponse(BaseModel):
    session_id: str
    reply: str
    cart: List[Dict[str, Any]] = []
    retrieved_items: List[Dict[str, Any]] = []


class BulkDeleteConversationsRequest(BaseModel):
    conversation_ids: List[str] = Field(..., min_length=1, description="List of conversation _id strings to delete")
