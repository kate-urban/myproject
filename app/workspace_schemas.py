from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, UUID4, ConfigDict


class WorkspaceConfigOut(BaseModel):
    auth_enabled: bool
    edit_locks_enabled: bool
    structured_rpd_enabled: bool
    plans_auto_import: bool = True
    plans_delete_after_import: bool = True
    legacy_editor_url: str = "/"
    legacy_validation_url: str = "/validation"
    ai_assistant_enabled: bool = True
    ai_llm_configured: bool = False


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    username: str
    display_name: str


class LoginIn(BaseModel):
    username: str
    password: str = ""


class LoginOut(BaseModel):
    user: AdminUserOut
    token: str


class RegisterIn(BaseModel):
    username: str
    display_name: str
    password: str


class AuthStatusOut(BaseModel):
    auth_enabled: bool
    authenticated: bool
    can_register: bool
    users_count: int
    max_users: int
    user: Optional[AdminUserOut] = None


class WorkspaceDisciplineOut(BaseModel):
    id: UUID4
    code: str
    name: str
    credits: Optional[float] = None
    has_rpd: bool = False
    has_fos: bool = False
    program_id: Optional[UUID4] = None
    document_id: Optional[UUID4] = None
    fos_document_id: Optional[UUID4] = None
    lock_holder: Optional[str] = None
    program_kind: Optional[str] = None
    rpd_authors: list[str] = []
    passport_needs_manual: bool = False
    rpd_reapproval_years: list[int] = []


class WorkspacePlanOut(BaseModel):
    id: UUID4
    form: str
    source_file: str
    year: Optional[int] = None
    direction_code: Optional[str] = None
    direction_name: Optional[str] = None
    profile_id: Optional[UUID4] = None
    profile_name: Optional[str] = None
    disciplines: list[WorkspaceDisciplineOut] = []
    practices: list[WorkspaceDisciplineOut] = []
    gia: list[WorkspaceDisciplineOut] = []


class WorkspaceProfileOut(BaseModel):
    id: UUID4
    name: str
    plans: list[WorkspacePlanOut] = []


class WorkspaceDirectionOut(BaseModel):
    code: str
    name: str
    profiles: list[WorkspaceProfileOut] = []


class WorkspaceYearOut(BaseModel):
    year: Optional[int]
    directions: list[WorkspaceDirectionOut] = []


class EditLockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    resource_type: str
    resource_id: UUID4
    user_display_name: str
    acquired_at: datetime
    expires_at: datetime
    token: str


class AcquireLockIn(BaseModel):
    resource_type: str
    resource_id: UUID4


class LockStatusOut(BaseModel):
    locked: bool
    lock: Optional[EditLockOut] = None
    can_edit: bool = True
    message: Optional[str] = None
