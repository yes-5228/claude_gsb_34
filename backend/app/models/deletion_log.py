"""公厕删除审计模型。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RestroomDeletionLog(Base):
    """公厕删除审计：留存被删台账及级联数据的快照，保证统计与历史结论可解释。"""

    __tablename__ = "restroom_deletion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    restroom_id: Mapped[int] = mapped_column(Integer, index=True, comment="原公厕主键")
    code: Mapped[str] = mapped_column(String(32), index=True, comment="公厕编号快照")
    name: Mapped[str] = mapped_column(String(120), comment="公厕名称快照")
    district: Mapped[str] = mapped_column(String(60), index=True, comment="所属区域快照")
    inspection_count: Mapped[int] = mapped_column(Integer, default=0, comment="随删巡查记录数")
    issue_count: Mapped[int] = mapped_column(Integer, default=0, comment="随删问题记录数")
    rectification_count: Mapped[int] = mapped_column(Integer, default=0, comment="随删整改流水数")
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, comment="随删附件图片数")
    issue_by_status: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="随删问题的整改状态分布"
    )
    issue_by_category: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="随删问题的分类分布"
    )
    restroom_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, comment="公厕档案快照")
    operator: Mapped[str] = mapped_column(String(60), default="", comment="操作人")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="删除原因")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="删除时间"
    )
