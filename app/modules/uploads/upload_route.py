from fastapi import APIRouter, UploadFile, File, Depends, Query
from app.middleware.auth import get_current_user
from .upload_service import UploadService

service = UploadService()

upload_router = APIRouter(prefix="/upload", tags=["Upload Documents"])
uploads_router = APIRouter(prefix="/uploads", tags=["Upload Documents"])


@upload_router.post("/document")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload PDF, Excel (.xlsx, .xls), or CSV (.csv) document.

    Automated Behavior:
    - owner_id auto-extracted from JWT.
    - Business Type auto-resolved from Organization.
    - AI extracts items → saved to Redis (2hr TTL).
    - Returns MongoDB _id as 'id'. Use it for all subsequent calls.
    """
    return await service.upload_and_process(file=file, current_user=current_user)


@upload_router.get("/preview/{doc_id}")
async def get_preview(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch the extracted preview data from Redis.
    Call this after upload to populate the editable table on the frontend.
    Returns 404 if the preview has expired (2hr TTL).
    """
    return await service.get_preview(doc_id=doc_id, current_user=current_user)


@upload_router.put("/preview/{doc_id}")
async def update_preview(
    doc_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Save user's edits back to Redis.
    Payload: { "items": [...], "categories": [...] }
    Resets the 2hr TTL on each save.
    """
    return await service.update_preview(doc_id=doc_id, payload=payload, current_user=current_user)


@upload_router.post("/confirm/{doc_id}")
async def confirm_and_save(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Confirm and permanently save extracted menu data.
    - Reads items from Redis.
    - Saves categories to menu_categories collection.
    - Saves items to menu_items collection.
    - Embeds items into Qdrant vector store.
    - Clears Redis preview key.
    - Updates uploaded_documents status = PROCESSED.
    """
    return await service.confirm_and_save(doc_id=doc_id, current_user=current_user)


@uploads_router.get("/my-documents")
async def get_my_uploaded_documents(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch all uploaded documents for the logged-in owner. Newest first.
    """
    return await service.get_my_uploaded_documents(current_user=current_user, page=page, limit=limit)


@upload_router.post("/convert-to-json/{doc_id}")
async def convert_to_json(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Re-run AI conversion on already-uploaded document raw JSON.
    """
    return await service.convert_document_to_json(doc_id=doc_id, current_user=current_user)


@upload_router.post("/create-structured-data/{doc_id}")
async def create_structured_data(
    doc_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Legacy: Save reviewed items directly as structured JSON (disk + MongoDB).
    Prefer using /confirm/{doc_id} for the full Redis → MongoDB + Qdrant flow.
    """
    return await service.create_structured_data(doc_id=doc_id, payload=payload, current_user=current_user)


@upload_router.delete("/remove/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete document by MongoDB _id — removes from MongoDB, disk files, and Redis.
    """
    return await service.delete_document(doc_id=doc_id, current_user=current_user)
