from fastapi import APIRouter, Query, Depends

from app.middleware.auth import get_current_user
from .schemas.ai_employee_schema import (
    CreateAIEmployeeRequest,
    UpdateAIEmployeeRequest,
)
from .ai_employee_service import AIEmployeeService


service = AIEmployeeService()

# Plural — list routes
ai_employees_router = APIRouter(prefix="/ai-employees", tags=["AI Employees"])

# Singular — resource routes
ai_employee_router = APIRouter(prefix="/ai-employee", tags=["AI Employee"])


# ─── Admin: All AI Employees ──────────────────────────────────────────────────

@ai_employees_router.get("")
async def get_all_ai_employees(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user = Depends(get_current_user),
):
    return await service.get_all(page, limit, current_user)


# ─── Get by Org ───────────────────────────────────────────────────────────────

@ai_employees_router.get("/by-org/{org_id}")
async def get_ai_employees_by_org(
    org_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user = Depends(get_current_user),
):
    return await service.get_by_org(org_id, page, limit, current_user)


# ─── Get by ID ────────────────────────────────────────────────────────────────

@ai_employee_router.get("/get-by-id/{ai_employee_id}")
async def get_ai_employee_by_id(
    ai_employee_id: str,
    current_user = Depends(get_current_user),
):
    return await service.get_by_id(ai_employee_id, current_user)


# ─── Create ───────────────────────────────────────────────────────────────────

@ai_employee_router.post("/create")
async def create_ai_employee(
    request: CreateAIEmployeeRequest,
    current_user = Depends(get_current_user),
):
    return await service.create(request, current_user)


# ─── Update ───────────────────────────────────────────────────────────────────

@ai_employee_router.put("/update/{ai_employee_id}")
async def update_ai_employee(
    ai_employee_id: str,
    request: UpdateAIEmployeeRequest,
    current_user = Depends(get_current_user),
):
    return await service.update(ai_employee_id, request, current_user)


# ─── Delete ───────────────────────────────────────────────────────────────────

@ai_employee_router.delete("/remove/{ai_employee_id}")
async def delete_ai_employee(
    ai_employee_id: str,
    current_user = Depends(get_current_user),
):
    return await service.delete(ai_employee_id, current_user)
