from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class UploadedDocument(BaseModel):
    id: Optional[str] = None          # MongoDB _id (string)
    owner_id: str
    business_type_id: Optional[str] = None
    file_name: str
    file_type: str                    # "pdf", "xlsx", "xls", "csv"
    file_size_bytes: int
    storage_path: str
    status: str = "ACTIVE"            # "ACTIVE", "PROCESSED", "DELETED"
    detected_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentUploadDataResponse(BaseModel):
    id: str                           # MongoDB _id — use this for all subsequent API calls
    owner_id: str
    business_type_id: Optional[str] = None
    file_name: str
    file_type: str
    file_size_bytes: int
    storage_path: str
    status: str
    detected_type: Optional[str] = None
    created_at: datetime


class UploadDocumentResponse(BaseModel):
    success: bool
    message: str
    data: DocumentUploadDataResponse


class DocumentListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[DocumentUploadDataResponse]
