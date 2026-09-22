from fastapi import APIRouter, UploadFile, File, Depends, Query
from app.middleware.auth import get_current_user
from .upload_service import UploadService

service = UploadService()

upload_router = APIRouter(prefix="/upload", tags=["Upload Documents"])
uploads_router = APIRouter(prefix="/uploads", tags=["Upload Documents"])


@upload_router.post("/document")
@upload_router.post("/pdf")
async def upload_document(
    file: UploadFile = File(...),
    organization_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload PDF, Excel (.xlsx, .xls), or CSV (.csv) document.
    """
    return await service.upload_and_process(file=file, current_user=current_user, organization_id=organization_id)


@upload_router.get("/preview/{doc_id}")
async def get_preview(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch the extracted preview data from Redis.
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
    """
    return await service.update_preview(doc_id=doc_id, payload=payload, current_user=current_user)


@upload_router.post("/confirm/{doc_id}")
@upload_router.post("/confirm")
async def confirm_and_save(
    doc_id: str | None = None,
    organization_id: str | None = Query(default=None),
    payload: dict | None = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Confirm and permanently save extracted menu data to MongoDB & Qdrant vector store.
    """
    target_doc_id = doc_id
    target_org_id = organization_id
    if payload and isinstance(payload, dict):
        if not target_doc_id:
            target_doc_id = payload.get("document_id")
        if not target_org_id:
            target_org_id = payload.get("organization_id")

    if not target_doc_id:
        return {"success": False, "message": "document_id is required to confirm catalog save."}

    # If items are passed directly in body, save via create_structured_data if Redis draft is unavailable
    result = await service.confirm_and_save(doc_id=target_doc_id, current_user=current_user, organization_id=target_org_id)
    if not result.get("success") and payload and "items" in payload:
        return await service.create_structured_data(doc_id=target_doc_id, payload=payload, current_user=current_user)
    return result


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