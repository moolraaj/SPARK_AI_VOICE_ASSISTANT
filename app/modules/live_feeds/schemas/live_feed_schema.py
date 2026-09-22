from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LiveFeedType(str, Enum):
    GENERAL = "general"
    SPECIAL = "special"


class LiveFeed(BaseModel):
    id: Optional[str] = None
    org_id: str
    user_id: str
    type: LiveFeedType
    title: str
    message: str
    valid_from: datetime
    valid_until: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class CreateLiveFeedRequest(BaseModel):
    org_id: Optional[str] = Field(default=None, description="Organization ID (e.g. Hotel, Hospital)")
    type: LiveFeedType = Field(default=LiveFeedType.GENERAL)
    title: str = Field(..., min_length=1, max_length=250)
    message: str = Field(..., min_length=1)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: bool = True


class UpdateLiveFeedRequest(BaseModel):
    type: Optional[LiveFeedType] = None
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    message: Optional[str] = Field(None, min_length=1)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: Optional[bool] = None


class LiveFeedResponse(BaseModel):
    id: str
    org_id: str
    user_id: str
    type: LiveFeedType
    title: str
    message: str
    valid_from: datetime
    valid_until: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
