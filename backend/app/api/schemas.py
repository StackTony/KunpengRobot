"""Schemas (Pydantic): API 请求/响应模型."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.rule import MatchType, Severity
from app.models.task import TaskStatus, TaskType


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    display_name: str
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


# ---------- Task ----------
class TaskInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: TaskType
    status: TaskStatus
    filename: str
    progress: int
    error: str
    created_at: datetime
    finished_at: datetime | None = None


class UploadResponse(BaseModel):
    task_id: UUID
    status: TaskStatus


# ---------- Rule ----------
class RuleCreate(BaseModel):
    name: str = Field(max_length=128)
    description: str = ""
    match_type: MatchType
    pattern: str = ""
    threshold: dict = Field(default_factory=dict)
    severity: Severity = Severity.warn
    log_type: str = ""
    server_type: str = ""
    enabled: bool = True
    priority: int = 100


class RuleUpdate(RuleCreate):
    pass


class RuleInfo(RuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    is_builtin: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


# ---------- Metric ----------
class MetricQuery(BaseModel):
    host: str
    metric_name: str
    start: datetime
    end: datetime
    interval_seconds: int = 0  # 0=原始点, >0=降采样窗口


class MetricSeries(BaseModel):
    host: str
    metric_name: str
    points: list[tuple[datetime, float]]


class PreferenceSave(BaseModel):
    pref_key: str
    pref_value: dict
