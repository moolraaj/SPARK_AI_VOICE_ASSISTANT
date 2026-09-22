from fastapi import APIRouter, Depends, Query
from app.middleware.auth import get_current_user
from app.rag.vectorstore.qdrant_store import qdrant_store

vector_store_router = APIRouter(prefix="/vector-store", tags=["Vector Store"])


@vector_store_router.get("/get-vector-store-data")
@vector_store_router.get("/data")
async def get_vector_store_data(
    current_user: dict = Depends(get_current_user),
):
    """
    Get all Qdrant vector store data, including collection statistics, total record count, and payload samples.
    """
    return await qdrant_store.get_all_vector_data()


@vector_store_router.get("/org/{org_id}")
@vector_store_router.get("/data/org/{org_id}")
async def get_org_vector_store_data(
    org_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get Qdrant vector store data scoped strictly to a specific organization (owner_id / organization_id).
    """
    return await qdrant_store.get_vector_data_by_owner(owner_id=org_id)


@vector_store_router.delete("/clear/{collection_name}")
@vector_store_router.delete("/clear-collection/{collection_name}")
async def clear_vector_collection(
    collection_name: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Clear/delete all vector records from a specified Qdrant collection.
    """
    return await qdrant_store.clear_collection(collection_name=collection_name)


@vector_store_router.delete("/record/{point_id}")
async def delete_vector_record(
    point_id: str,
    collection_name: str = Query(default="catalog_items"),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a single vector record by its Point ID.
    """
    return await qdrant_store.delete_record(point_id=point_id, collection_name=collection_name)
