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
    title: str = ""
    dept: str = ""
    avatar_hue: int = 212
    team_roles: list[dict] = Field(default_factory=list)  # [{team_id, team_name, role}]


class UserBrief(BaseModel):
    """邀请候选用户 (不含敏感字段)."""
    id: int
    name: str
    email: str
    title: str = ""
    dept: str = ""
    avatar_hue: int = 212


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
    # 解析任务扩展 (witty 接入)
    name: str = ""
    parser_type: str = ""
    asset_id: int | None = None
    log_size: int = 0
    event_count: int = 0
    # 关联展示字段 (路由层填充)
    creator_name: str = ""
    asset_name: str = ""


class UploadResponse(BaseModel):
    task_id: UUID
    status: TaskStatus


class PrecheckRequest(BaseModel):
    parser_type: str
    text: str = Field(max_length=512 * 1024)  # 前端只传前 512KB 切片


class PrecheckResponse(BaseModel):
    count: int
    sample: list[str] = Field(default_factory=list)


class TextUploadRequest(BaseModel):
    """向导粘贴文本直传 (≤10MB), 免落盘走临时文件."""
    name: str = Field(max_length=128)
    parser_type: str
    asset_id: int
    text: str = Field(max_length=10 * 1024 * 1024)
    filename: str = "pasted.log"


# ---------- Team ----------
class TeamCreate(BaseModel):
    name: str = Field(max_length=64)
    desc: str = Field(default="", max_length=255)


class TeamUpdate(BaseModel):
    name: str = Field(max_length=64)
    desc: str = Field(default="", max_length=255)


class MemberInfo(BaseModel):
    user_id: int
    name: str
    email: str = ""
    title: str = ""
    dept: str = ""
    avatar_hue: int = 212
    role: str


class TeamInfo(BaseModel):
    id: int
    name: str
    desc: str
    owner_user_id: int
    created_at: datetime
    my_role: str | None = None
    member_count: int = 0
    asset_count: int = 0
    task_count: int = 0


class TeamDetail(TeamInfo):
    members: list[MemberInfo] = Field(default_factory=list)
    assets: list["AssetInfo"] = Field(default_factory=list)
    pending_applies: list["NoticeInfo"] = Field(default_factory=list)


class InviteRequest(BaseModel):
    user_id: int
    role: str = "member"  # member / team_admin


class MemberRoleUpdate(BaseModel):
    role: str  # member / team_admin


class NoticeInfo(BaseModel):
    id: int
    type: str                     # invite / apply
    team_id: int
    team_name: str = ""
    from_user_id: int
    from_user_name: str = ""
    to_user_id: int
    to_user_name: str = ""
    role: str = "member"
    status: str
    created_at: datetime


class NoticeResolve(BaseModel):
    accept: bool


# ---------- Asset ----------
class AssetCreate(BaseModel):
    name: str = Field(max_length=64)
    desc: str = Field(default="", max_length=255)
    ip_range: str = Field(default="", max_length=128)


class AssetUpdate(AssetCreate):
    pass


class AssetInfo(BaseModel):
    id: int
    team_id: int
    name: str
    desc: str
    ip_range: str
    created_at: datetime
    task_count: int = 0


class TaskListPage(BaseModel):
    total: int
    items: list[TaskInfo] = Field(default_factory=list)
    sparks: dict[str, list[dict]] = Field(default_factory=dict)  # task_id -> 16 桶 spark


# ---------- Analysis (witty 结果页) ----------
class AnalyzeEvent(BaseModel):
    id: int
    ts: int
    source_ip: str
    severity: str
    category: str
    error_code: str
    raw: str
    fields: dict = Field(default_factory=dict)


class EventsPage(BaseModel):
    total: int
    items: list[AnalyzeEvent] = Field(default_factory=list)


class StatsResponse(BaseModel):
    kpi: dict
    time_buckets: list[dict]
    categories: list[dict]
    codes: list[dict]
    ips: list[dict]


class LlmStartResponse(BaseModel):
    run_id: str


class ReportInfo(BaseModel):
    task_id: UUID
    health_score: int | None = None
    summary: str
    sections: list[dict] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    llm: bool = False
    created_at: datetime | None = None


# ---------- Audit ----------
class AuditRecordOut(BaseModel):
    id: int
    created_at: datetime
    user_name: str
    action: str
    team_id: int | None = None
    team_name: str = ""
    target: str
    success: bool


class AuditPage(BaseModel):
    total: int
    items: list[AuditRecordOut] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


# ---------- Dashboard ----------
class DashboardResponse(BaseModel):
    teams: int
    assets: int
    tasks: int
    kpi: dict
    recent_tasks: list[TaskInfo] = Field(default_factory=list)
    top_codes: list[dict] = Field(default_factory=list)


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
