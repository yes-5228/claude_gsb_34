"""公厕台账删除审计模型。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RestroomDeleteAudit(Base):
    """公厕档案归档时的影响面快照，用于报表追溯与差异解释。"""

    __tablename__ = "restroom_delete_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restroom_id: Mapped[int] = mapped_column(Integer, index=True, comment="被归档公厕 ID")
    restroom_code: Mapped[str] = mapped_column(String(32), index=True, comment="公厕编号快照")
    restroom_name: Mapped[str] = mapped_column(String(120), comment="公厕名称快照")
    district: Mapped[str] = mapped_column(String(60), index=True, comment="所属区域快照")
    inspection_count: Mapped[int] = mapped_column(Integer, default=0, comment="保留巡查数")
    issue_count: Mapped[int] = mapped_column(Integer, default=0, comment="保留问题数")
    open_issue_count: Mapped[int] = mapped_column(Integer, default=0, comment="未闭环问题数")
    closed_issue_count: Mapped[int] = mapped_column(Integer, default=0, comment="已闭环问题数")
    rectification_record_count: Mapped[int] = mapped_column(Integer, default=0, comment="保留整改流水数")
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, comment="保留附件数")
    impact: Mapped[dict] = mapped_column(JSON, default=dict, comment="删除前完整影响面")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="删除/归档原因")
    operator: Mapped[str] = mapped_column(String(60), default="", comment="操作人")
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="归档时间"
    )
