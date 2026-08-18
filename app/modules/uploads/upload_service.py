import os
import json
from fastapi import UploadFile

from app.core.datetime import timestamps
from app.database.redis import redis_client
from .upload_repository import UploadRepository
from .services.text_extractor import extract_raw_text_from_bytes, SCANNED_PDF_MARKER
from .services.domain_classifier import check_domain_relevance_with_ai
from .services.schema_parser import (
    analyze_document_schema_with_ai,
    python_execute_categorized_parsing,
    convert_txt_to_categorized_json_with_ai
)

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}


class UploadService:

    def __init__(self):
        self.repository = UploadRepository()

    async def upload_and_process(self, file: UploadFile, current_user: dict) -> dict:
        filename = file.filename or "file"
        _, ext = os.path.splitext(filename.lower())

        # 1. Early Exit: File Extension Gate
        if ext not in ALLOWED_EXTENSIONS:
            return {
                "success": False,
                "message": f"Invalid file type '{ext}'. Only PDF (.pdf), Excel (.xlsx, .xls), and CSV (.csv) files are allowed."
            }

        # 2. Extract owner_id from JWT Auth Token
        owner_id = str(current_user["_id"])

        # 3. Auto-resolve Business Type from Owner's Organization
        bt_id, bt_name = await self.repository.get_business_type_for_owner(owner_id)

        if not bt_id or not bt_name:
            return {
                "success": False,
                "message": "No registered organization found for your account. Please set up your business organization before uploading documents."
            }

        # Read file bytes in memory
        file_bytes = await file.read()
        file_size = len(file_bytes)

        # 4. Extract Text for AI Domain Check
        raw_text = extract_raw_text_from_bytes(file_bytes, ext)

        # 5. Scanned PDF Early Rejection
        if raw_text == SCANNED_PDF_MARKER:
            return {
                "success": False,
                "message": "Only digital PDF, Excel (.xlsx, .xls), and CSV (.csv) files are accepted. Scanned or image-based PDFs are not supported."
            }

        # 6. AI-Powered Domain Relevance Check
        is_matched, match_reason = await check_domain_relevance_with_ai(raw_text, bt_name)

        if not is_matched:
            return {
                "success": False,
                "message": match_reason
            }

        # Save File to specific folder structure (/uploads/{pdfs|excels|csvs}/{owner_id}/)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../uploads"))

        if ext == ".pdf":
            subfolder = "pdfs"
        elif ext in [".xlsx", ".xls"]:
            subfolder = "excels"
        else:
            subfolder = "csvs"

        target_dir = os.path.join(base_dir, subfolder, owner_id)
        os.makedirs(target_dir, exist_ok=True)

        target_filepath = os.path.join(target_dir, filename)
        with open(target_filepath, "wb") as f:
            f.write(file_bytes)

        # Extract Raw JSON items for Frontend Editable Table View
        categories_list, llm_usage = await analyze_document_schema_with_ai(raw_text, bt_name)
        raw_parsed_data = python_execute_categorized_parsing(raw_text, categories_list, bt_name, filename, llm_usage)

        flat_raw_items = []
        for cat_name, items_list in raw_parsed_data.get("categories", {}).items():
            for item_obj in items_list:
                flat_raw_items.append({
                    "category": cat_name,
                    "item_name": item_obj.get("item_name"),
                    "price": item_obj.get("price"),
                    "is_veg": item_obj.get("is_veg", True)
                })

        base_filename = os.path.splitext(filename)[0]
        raw_json_filename = f"{base_filename}_raw.json"
        raw_json_filepath = os.path.join(target_dir, raw_json_filename)
        with open(raw_json_filepath, "w", encoding="utf-8") as f:
            json.dump(flat_raw_items, f, ensure_ascii=False, indent=2, default=str)

        # Insert Document Metadata in MongoDB
        doc_data = {
            "owner_id": owner_id,
            "business_type_id": bt_id,
            "file_name": filename,
            "file_type": ext.lstrip("."),
            "file_size_bytes": file_size,
            "storage_path": target_filepath,
            "raw_json_path": raw_json_filepath,
            "status": "ACTIVE",
            "detected_type": bt_name.upper(),
            **timestamps()
        }

        mongo_id = await self.repository.create(doc_data)

        # Save extracted preview to Redis (2hr TTL) — survives page refresh
        unique_categories = list(dict.fromkeys(item["category"] for item in flat_raw_items))
        await redis_client.save_preview(mongo_id, {
            "doc_id": mongo_id,
            "owner_id": owner_id,
            "file_name": filename,
            "detected_type": bt_name.upper(),
            "categories": unique_categories,
            "items": flat_raw_items,
        })

        return {
            "success": True,
            "message": f"Document uploaded and processed. {len(flat_raw_items)} items extracted.",
            "data": {
                "id": mongo_id,
                "owner_id": owner_id,
                "file_name": filename,
                "file_type": ext.lstrip("."),
                "file_size_bytes": file_size,
                "status": "ACTIVE",
                "detected_type": bt_name.upper(),
                "created_at": doc_data["created_at"],
                "total_items_count": len(flat_raw_items),
                "preview_ttl_seconds": 7200,
                "raw_items": flat_raw_items
            }
        }

    async def get_preview(self, doc_id: str, current_user: dict) -> dict:
        """Read extracted preview data from Redis."""
        owner_id = str(current_user["_id"])
        data = await redis_client.get_preview(doc_id)

        if data is None:
            return {
                "success": False,
                "message": "Preview not found or expired (2hr TTL). Please upload the document again."
            }

        # Ownership check
        if data.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to view this preview."}

        return {
            "success": True,
            "message": "Preview fetched from Redis.",
            "data": data
        }

    async def update_preview(self, doc_id: str, payload: dict, current_user: dict) -> dict:
        """Overwrite preview data in Redis with user's edits. Resets TTL."""
        owner_id = str(current_user["_id"])

        existing = await redis_client.get_preview(doc_id)
        if existing is None:
            return {
                "success": False,
                "message": "Preview not found or expired. Please upload the document again."
            }

        if existing.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to update this preview."}

        items = payload.get("items")
        if not isinstance(items, list):
            return {"success": False, "message": "Invalid payload. Expected { 'items': [...] }."}

        # Rebuild categories list from updated items
        unique_categories = list(dict.fromkeys(
            item.get("category", "General") for item in items
        ))

        updated_data = {
            **existing,
            "categories": unique_categories,
            "items": items,
        }

        await redis_client.update_preview(doc_id, updated_data)

        return {
            "success": True,
            "message": f"Preview updated in Redis. {len(items)} items, {len(unique_categories)} categories.",
            "data": {
                "doc_id": doc_id,
                "total_items": len(items),
                "categories": unique_categories,
            }
        }

    async def confirm_and_save(self, doc_id: str, current_user: dict) -> dict:
        """
        Confirm: Redis → MongoDB (menu_categories + menu_items) + Qdrant vector store.
        Clears Redis key after successful save.
        """
        owner_id = str(current_user["_id"])

        # 1. Fetch preview from Redis
        preview_data = await redis_client.get_preview(doc_id)
        if preview_data is None:
            return {
                "success": False,
                "message": "Preview not found or expired. Please upload the document again."
            }

        if preview_data.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to confirm this upload."}

        # 2. Save to MongoDB + Qdrant via CatalogService
        from app.modules.catalogs.catalog_service import CatalogService
        catalog_service = CatalogService()
        result = await catalog_service.confirm_and_save(
            owner_id=owner_id,
            document_id=doc_id,
            preview_data=preview_data
        )

        if not result.get("success"):
            return result

        # 3. Update uploaded_documents status → PROCESSED
        await self.repository.update(doc_id, {
            "status": "PROCESSED",
            "updated_at": timestamps()["updated_at"]
        })

        # 4. Clear Redis key
        await redis_client.delete_preview(doc_id)

        return {
            "success": True,
            "message": "Catalog saved to database and vector store. Redis cleared.",
            "data": result["data"]
        }

    async def create_structured_data(self, doc_id: str, payload: dict, current_user: dict) -> dict:

        """
        Creates and saves final structured JSON & records to DB after Frontend review.
        """
        owner_id = str(current_user["_id"])

        doc = await self.repository.get_by_id(doc_id)
        if not doc:
            return {"success": False, "message": "Document not found."}

        if doc.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to edit this document."}

        items_input = payload.get("items") if isinstance(payload, dict) else payload
        if not items_input or not isinstance(items_input, list):
            return {"success": False, "message": "Invalid payload format. Expected list of items under 'items'."}

        bt_id, bt_name = await self.repository.get_business_type_for_owner(owner_id)
        bt_name = bt_name or doc.get("detected_type", "Business")
        filename = doc.get("file_name", "document.pdf")
        target_dir = os.path.dirname(doc.get("storage_path"))

        categories_dict = {}
        total_items = 0
        non_veg_keywords = ["chicken", "mutton", "fish", "egg", "prawn", "lamb", "buff", "keema", "pork"]

        for item in items_input:
            cat = str(item.get("category", "General")).strip()
            name = str(item.get("item_name", "")).strip()
            if not name:
                continue

            raw_price = item.get("price", 0)
            try:
                price_val = float(raw_price) if "." in str(raw_price) else int(raw_price)
            except Exception:
                price_val = str(raw_price)

            is_veg = item.get("is_veg")
            if is_veg is None:
                is_veg = not any(kw in name.lower() for kw in non_veg_keywords)

            if cat not in categories_dict:
                categories_dict[cat] = []

            categories_dict[cat].append({
                "item_name": name,
                "price": price_val,
                "is_veg": is_veg,
                "metadata_source": {
                    "item_name": "user_reviewed" if item.get("name_edited") else "source_extracted",
                    "price": "user_reviewed" if item.get("price_edited") else "source_extracted",
                    "is_veg": "user_reviewed" if item.get("veg_edited") else "system_inferred"
                }
            })
            total_items += 1

        final_structured_data = {
            "document_info": {
                "file_name": filename,
                "business_type": bt_name,
                "parsed_by": "user_reviewed_and_saved_table",
                "total_categories_count": len(categories_dict),
                "total_items_count": total_items,
                "updated_at": timestamps()["updated_at"].isoformat()
            },
            "categories": categories_dict
        }

        base_filename = os.path.splitext(filename)[0]
        json_filename = f"{base_filename}.json"
        json_filepath = os.path.join(target_dir, json_filename)

        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(final_structured_data, f, ensure_ascii=False, indent=2, default=str)

        await self.repository.update(doc_id, {
            "json_path": json_filepath,
            "status": "PROCESSED",
            "total_items_count": total_items,
            "updated_at": timestamps()["updated_at"]
        })

        # Save to MongoDB catalog_categories, catalog_items collections & Qdrant vector store
        try:
            from app.modules.catalogs.catalog_service import CatalogService
            catalog_service = CatalogService()
            unique_categories = list(dict.fromkeys(item.get("category", "General") for item in items_input))
            await catalog_service.confirm_and_save(
                owner_id=owner_id,
                document_id=doc_id,
                preview_data={
                    "doc_id": doc_id,
                    "owner_id": owner_id,
                    "file_name": filename,
                    "categories": unique_categories,
                    "items": items_input
                }
            )
            await redis_client.delete_preview(doc_id)
        except Exception as e:
            print(f"⚠️  Warning: Failed to save to catalog collections/vectorstore: {e}")

        return {
            "success": True,
            "message": "Structured data created and saved to database successfully.",
            "data": {
                "id": doc_id,
                "file_name": filename,
                "json_path": json_filepath,
                "status": "PROCESSED",
                "total_items_count": total_items,
                "structured_data": final_structured_data
            }
        }

    async def convert_document_to_json(self, doc_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])

        doc = await self.repository.get_by_id(doc_id)
        if not doc:
            return {"success": False, "message": "Document not found."}

        if doc.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to process this document."}

        raw_json_path = doc.get("raw_json_path")
        if not raw_json_path or not os.path.exists(raw_json_path):
            return {"success": False, "message": "Extracted raw JSON file not found on disk. Please upload document again."}

        with open(raw_json_path, "r", encoding="utf-8") as f:
            raw_items = json.load(f)

        bt_id, bt_name = await self.repository.get_business_type_for_owner(owner_id)
        bt_name = bt_name or doc.get("detected_type", "Business")
        filename = doc.get("file_name", "document")

        structured_json = await convert_txt_to_categorized_json_with_ai(
            raw_text=json.dumps(raw_items),
            business_type_name=bt_name,
            file_name=filename
        )

        target_dir = os.path.dirname(raw_json_path)
        base_filename = os.path.splitext(filename)[0]
        json_filename = f"{base_filename}.json"
        json_filepath = os.path.join(target_dir, json_filename)

        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(structured_json, f, ensure_ascii=False, indent=2, default=str)

        await self.repository.update(doc_id, {
            "json_path": json_filepath,
            "status": "PROCESSED",
            "updated_at": timestamps()["updated_at"]
        })

        return {
            "success": True,
            "message": "Document converted to categorized JSON successfully.",
            "data": {
                "id": doc_id,
                "file_name": filename,
                "json_path": json_filepath,
                "status": "PROCESSED",
                "structured_data": structured_json
            }
        }

    async def get_my_uploaded_documents(self, current_user: dict, page: int, limit: int) -> dict:
        owner_id = str(current_user["_id"])
        skip = (page - 1) * limit
        docs = await self.repository.get_by_owner(owner_id=owner_id, skip=skip, limit=limit)
        total = await self.repository.count_by_owner(owner_id=owner_id)

        formatted_docs = []
        for d in docs:
            formatted_docs.append({
                "id": str(d["_id"]),
                "file_name": d.get("file_name"),
                "file_type": d.get("file_type"),
                "file_size_bytes": d.get("file_size_bytes"),
                "status": d.get("status"),
                "detected_type": d.get("detected_type"),
                "storage_path": d.get("storage_path"),
                "json_path": d.get("json_path"),
                "created_at": d.get("created_at")
            })

        return {
            "success": True,
            "message": "Documents fetched successfully.",
            "data": {
                "documents": formatted_docs,
                "total": total,
                "page": page,
                "limit": limit
            }
        }

    async def delete_document(self, doc_id: str, current_user: dict) -> dict:
        owner_id = str(current_user["_id"])
        doc = await self.repository.get_by_id(doc_id)
        if not doc:
            return {"success": False, "message": "Document not found."}

        if doc.get("owner_id") != owner_id and current_user.get("role") != "SUPER_ADMIN":
            return {"success": False, "message": "You are not authorized to delete this document."}

        paths_to_delete = [
            doc.get("storage_path"),
            doc.get("raw_json_path"),
            doc.get("json_path")
        ]

        for fpath in paths_to_delete:
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        await self.repository.delete(doc_id)
        return {"success": True, "message": "Document deleted successfully."}
