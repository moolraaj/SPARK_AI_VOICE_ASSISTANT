from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class AIEmployeeRole(str, Enum):
    SALES        = "SALES"
    SUPPORT      = "SUPPORT"
    RECEPTIONIST = "RECEPTIONIST"
    GENERAL      = "GENERAL"


class AIEmployeePersona(str, Enum):
    FRIENDLY     = "FRIENDLY"
    FORMAL       = "FORMAL"
    CASUAL       = "CASUAL"
    PROFESSIONAL = "PROFESSIONAL"


# ─── Full Model (internal use) ─────────────────────────────────────────────────

class AIEmployee(BaseModel):
    id:               Optional[str] = None
    org_id:           str                    # ref → Organization
    business_type_id: str                    # ref → BusinessType
    name:             str
    role:             AIEmployeeRole
    persona:          AIEmployeePersona
    language:         str
    greeting_message: Optional[str] = None
    voice_id:         Optional[str] = None
    is_active:        bool = True
    created_at:       datetime
    updated_at:       datetime


# ─── Create Request ───────────────────────────────────────────────────────────

class CreateAIEmployeeRequest(BaseModel):
    org_id:           str
    name:             str = Field(..., min_length=2, max_length=100)
    role:             AIEmployeeRole
    persona:          AIEmployeePersona
    language:         str = Field(default="en")
    greeting_message: Optional[str] = None
    voice_id:         Optional[str] = None


# ─── Update Request ───────────────────────────────────────────────────────────

class UpdateAIEmployeeRequest(BaseModel):
    name:             Optional[str]              = Field(None, min_length=2, max_length=100)
    role:             Optional[AIEmployeeRole]   = None
    persona:          Optional[AIEmployeePersona] = None
    language:         Optional[str]              = None
    greeting_message: Optional[str]              = None
    voice_id:         Optional[str]              = None
    is_active:        Optional[bool]             = None


# ─── Response ─────────────────────────────────────────────────────────────────

class AIEmployeeResponse(BaseModel):
    id:               str
    org_id:           str
    business_type_id: str
    name:             str
    role:             AIEmployeeRole
    persona:          AIEmployeePersona
    language:         str
    greeting_message: Optional[str]
    voice_id:         Optional[str]
    is_active:        bool
    created_at:       datetime
    updated_at:       datetime
