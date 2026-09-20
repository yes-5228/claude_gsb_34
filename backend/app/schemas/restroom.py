"""公厕台账相关数据结构。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import RestroomGrade, RestroomStatus


class RestroomBrief(BaseModel):
    """其他模块引用公厕时的精简信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    district: str
    address: str = ""
    archived: bool = False
    archived_at: datetime | None = None


class RestroomBase(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="公厕名称")
    district: str = Field(min_length=1, max_length=60, description="所属区域")
    address: str = Field(default="", max_length=200, description="详细地址")
    grade: RestroomGrade = Field(default=RestroomGrade.SECOND, description="公厕等级")
    status: RestroomStatus = Field(default=RestroomStatus.NORMAL, description="开放状态")
    manager: str = Field(default="", max_length=60, description="保洁责任人")
    manager_phone: str = Field(default="", max_length=30, description="联系电话")
    open_hours: str = Field(default="06:00-22:00", max_length=60, description="开放时间")
    stall_count: int = Field(default=0, ge=0, description="蹲位数量")
    basin_count: int = Field(default=0, ge=0, description="洗手盆数量")
    has_accessible: bool = Field(default=True, description="是否有无障碍设施")
    longitude: float | None = Field(default=None, description="经度")
    latitude: float | None = Field(default=None, description="纬度")
    remark: str | None = Field(default=None, max_length=500, description="备注")


class RestroomCreate(RestroomBase):
    code: str | None = Field(default=None, max_length=32, description="公厕编号，留空自动生成")


class RestroomUpdate(BaseModel):
    """局部更新，仅提交需要变更的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    district: str | None = Field(default=None, min_length=1, max_length=60)
    address: str | None = Field(default=None, max_length=200)
    grade: RestroomGrade | None = None
    status: RestroomStatus | None = None
    manager: str | None = Field(default=None, max_length=60)
    manager_phone: str | None = Field(default=None, max_length=30)
    open_hours: str | None = Field(default=None, max_length=60)
    stall_count: int | None = Field(default=None, ge=0)
    basin_count: int | None = Field(default=None, ge=0)
    has_accessible: bool | None = None
    longitude: float | None = None
    latitude: float | None = None
    remark: str | None = Field(default=None, max_length=500)


class RestroomOut(RestroomBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    archived: bool = False
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RestroomDetail(RestroomOut):
    """台账详情，附带巡查与问题的汇总信息。"""

    inspection_count: int = 0
    latest_inspection_time: datetime | None = None
    latest_inspection_score: float | None = None
    avg_score: float | None = None
    open_issue_count: int = 0
    total_issue_count: int = 0
    rectification_record_count: int = 0
    attachment_count: int = 0


class IssueStatusCount(BaseModel):
    status: str
    count: int = 0


class RestroomDeleteImpact(BaseModel):
    """强制归档前返回的影响面与处置边界。"""

    restroom_id: int
    code: str
    name: str
    district: str
    can_delete: bool
    action: str = Field(description="delete=物理删除；archive=归档保留历史；blocked=需先处置")
    blockers: list[str] = Field(default_factory=list)
    inspection_count: int = 0
    issue_count: int = 0
    open_issue_count: int = 0
    closed_issue_count: int = 0
    issue_status_counts: list[IssueStatusCount] = Field(default_factory=list)
    rectification_record_count: int = 0
    attachment_count: int = 0
    retained: list[str] = Field(default_factory=list, description="归档后仍保留的数据")
    removed_from_active_views: list[str] = Field(default_factory=list, description="从当前台账/看板移除的内容")
    message: str


class RestroomDeleteResult(BaseModel):
    """删除或归档结果。"""

    action: str
    message: str
    audit_id: int | None = None
    impact: RestroomDeleteImpact
