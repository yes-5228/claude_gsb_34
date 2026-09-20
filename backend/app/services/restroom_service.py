"""公厕台账业务逻辑。"""

from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import OPEN_ISSUE_STATUSES, IssueStatus
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models import Inspection, Issue, RectificationRecord, Restroom, RestroomDeleteAudit
from app.schemas.restroom import (
    IssueStatusCount,
    RestroomCreate,
    RestroomDeleteImpact,
    RestroomDetail,
    RestroomOut,
    RestroomUpdate,
)

SORTABLE_FIELDS = {
    "code": Restroom.code,
    "name": Restroom.name,
    "district": Restroom.district,
    "created_at": Restroom.created_at,
    "updated_at": Restroom.updated_at,
}

RETAINED_WHEN_ARCHIVED = [
    "巡查记录及检查项打分明细",
    "问题记录、整改流水与处理说明",
    "问题附件链接（不删除外部文件）",
    "历史统计、月度报表与问题分类/状态分布",
]

REMOVED_FROM_ACTIVE_VIEWS = [
    "公厕台账列表和新增业务下拉选项",
    "公厕详情、编辑及新增巡查/问题入口",
    "当前运行看板的公厕数量、区域公厕数和重点公厕排行",
]


def _next_code(db: Session) -> str:
    """生成形如 WC-0007 的公厕编号。"""
    seq = (db.scalar(select(func.count()).select_from(Restroom)) or 0) + 1
    while True:
        code = f"WC-{seq:04d}"
        if not db.scalar(select(Restroom.id).where(Restroom.code == code)):
            return code
        seq += 1


def get_restroom(db: Session, restroom_id: int, *, include_archived: bool = False) -> Restroom:
    restroom = db.get(Restroom, restroom_id)
    if restroom is None or (restroom.deleted_at is not None and not include_archived):
        raise NotFoundError(f"公厕 {restroom_id} 不存在")
    return restroom


def list_restrooms(
    db: Session,
    *,
    keyword: str | None = None,
    district: str | None = None,
    status: str | None = None,
    grade: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "created_at",
    order: str = "desc",
) -> tuple[list[Restroom], int]:
    stmt = select(Restroom).where(Restroom.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Restroom.name.like(like),
                Restroom.code.like(like),
                Restroom.address.like(like),
                Restroom.manager.like(like),
            )
        )
    if district:
        stmt = stmt.where(Restroom.district == district)
    if status:
        stmt = stmt.where(Restroom.status == status)
    if grade:
        stmt = stmt.where(Restroom.grade == grade)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE_FIELDS.get(sort_by, Restroom.created_at)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), Restroom.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def list_districts(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Restroom.district)
            .where(Restroom.deleted_at.is_(None))
            .distinct()
            .order_by(Restroom.district)
        )
    )


def create_restroom(db: Session, payload: RestroomCreate) -> Restroom:
    data = payload.model_dump()
    code = (data.pop("code") or "").strip() or _next_code(db)
    if db.scalar(select(Restroom.id).where(Restroom.code == code)):
        raise DomainError(f"公厕编号 {code} 已存在")
    data = {key: (value.value if hasattr(value, "value") else value) for key, value in data.items()}
    restroom = Restroom(code=code, **data)
    db.add(restroom)
    db.commit()
    db.refresh(restroom)
    return restroom


def update_restroom(db: Session, restroom_id: int, payload: RestroomUpdate) -> Restroom:
    restroom = get_restroom(db, restroom_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(restroom, key, value.value if hasattr(value, "value") else value)
    db.commit()
    db.refresh(restroom)
    return restroom


def _issue_status_counts(issues: list[Issue]) -> list[IssueStatusCount]:
    counts = {status.value: 0 for status in IssueStatus}
    for issue in issues:
        counts[issue.status] = counts.get(issue.status, 0) + 1
    return [IssueStatusCount(status=status, count=count) for status, count in counts.items()]


def build_delete_impact(db: Session, restroom_id: int) -> RestroomDeleteImpact:
    """统计删除影响面。历史数据保留，未闭环问题必须先完成处置。"""
    restroom = get_restroom(db, restroom_id, include_archived=True)
    if restroom.deleted_at is not None:
        return RestroomDeleteImpact(
            restroom_id=restroom.id,
            code=restroom.code,
            name=restroom.name,
            district=restroom.district,
            can_delete=False,
            action="blocked",
            blockers=["该公厕已经归档，不能重复删除"],
            message="该公厕已处于归档状态",
        )

    issues = list(
        db.scalars(select(Issue).where(Issue.restroom_id == restroom_id)).all()
    )
    inspection_count = db.scalar(
        select(func.count()).select_from(Inspection).where(Inspection.restroom_id == restroom_id)
    ) or 0
    record_count = db.scalar(
        select(func.count())
        .select_from(RectificationRecord)
        .join(Issue, Issue.id == RectificationRecord.issue_id)
        .where(Issue.restroom_id == restroom_id)
    ) or 0
    attachment_count = sum(len(issue.images or []) for issue in issues)
    open_count = sum(1 for issue in issues if issue.status in OPEN_ISSUE_STATUSES)
    closed_count = len(issues) - open_count

    blockers: list[str] = []
    if open_count:
        blockers.append(f"仍有 {open_count} 条未闭环问题，请先完成整改、验收关闭或作废关闭")
    if not issues and not inspection_count:
        action = "delete"
        message = "无关联业务数据，可物理删除公厕档案"
    elif blockers:
        action = "blocked"
        message = "存在必须先处置的数据，强制删除也不会执行"
    else:
        action = "archive"
        message = "历史数据将全部保留并随公厕归档；需要 force=true 确认"

    return RestroomDeleteImpact(
        restroom_id=restroom.id,
        code=restroom.code,
        name=restroom.name,
        district=restroom.district,
        can_delete=not blockers,
        action=action,
        blockers=blockers,
        inspection_count=inspection_count,
        issue_count=len(issues),
        open_issue_count=open_count,
        closed_issue_count=closed_count,
        issue_status_counts=_issue_status_counts(issues),
        rectification_record_count=record_count,
        attachment_count=attachment_count,
        retained=RETAINED_WHEN_ARCHIVED if action == "archive" else [],
        removed_from_active_views=REMOVED_FROM_ACTIVE_VIEWS if action == "archive" else [],
        message=message,
    )


def delete_restroom(
    db: Session,
    restroom_id: int,
    *,
    force: bool = False,
    reason: str | None = None,
    operator: str = "",
) -> tuple[str, RestroomDeleteImpact, int | None]:
    impact = build_delete_impact(db, restroom_id)
    if not impact.can_delete:
        raise ConflictError("；".join(impact.blockers or [impact.message]))
    if impact.action == "archive" and not force:
        raise ConflictError(
            f"该公厕已有 {impact.inspection_count} 条巡查记录、{impact.issue_count} 条问题记录，"
            "强制操作将归档台账但保留全部历史数据；请先查看影响面并使用 force=true 确认"
        )

    restroom = get_restroom(db, restroom_id, include_archived=True)
    try:
        if impact.action == "delete":
            db.execute(delete(Restroom).where(Restroom.id == restroom.id))
            db.commit()
            return "delete", impact, None

        restroom.deleted_at = datetime.now()
        audit = RestroomDeleteAudit(
            restroom_id=restroom.id,
            restroom_code=restroom.code,
            restroom_name=restroom.name,
            district=restroom.district,
            inspection_count=impact.inspection_count,
            issue_count=impact.issue_count,
            open_issue_count=impact.open_issue_count,
            closed_issue_count=impact.closed_issue_count,
            rectification_record_count=impact.rectification_record_count,
            attachment_count=impact.attachment_count,
            impact=impact.model_dump(mode="json"),
            reason=reason,
            operator=operator,
        )
        db.add(audit)
        db.flush()
        audit_id = audit.id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return "archive", impact, audit_id


def get_restroom_detail(db: Session, restroom_id: int) -> RestroomDetail:
    restroom = get_restroom(db, restroom_id)
    inspection_count = db.scalar(
        select(func.count()).select_from(Inspection).where(Inspection.restroom_id == restroom_id)
    ) or 0
    avg_score = db.scalar(
        select(func.avg(Inspection.score)).where(Inspection.restroom_id == restroom_id)
    )
    latest = db.scalars(
        select(Inspection)
        .where(Inspection.restroom_id == restroom_id)
        .order_by(Inspection.inspect_time.desc(), Inspection.id.desc())
        .limit(1)
    ).first()
    issues = list(db.scalars(select(Issue).where(Issue.restroom_id == restroom_id)).all())
    open_issue_count = sum(1 for issue in issues if issue.status in OPEN_ISSUE_STATUSES)
    record_count = db.scalar(
        select(func.count())
        .select_from(RectificationRecord)
        .join(Issue, Issue.id == RectificationRecord.issue_id)
        .where(Issue.restroom_id == restroom_id)
    ) or 0
    attachment_count = sum(len(issue.images or []) for issue in issues)

    base = RestroomOut.model_validate(restroom).model_dump()
    return RestroomDetail(
        **base,
        inspection_count=inspection_count,
        latest_inspection_time=latest.inspect_time if latest else None,
        latest_inspection_score=latest.score if latest else None,
        avg_score=round(float(avg_score), 1) if avg_score is not None else None,
        open_issue_count=open_issue_count,
        total_issue_count=len(issues),
        rectification_record_count=record_count,
        attachment_count=attachment_count,
    )


def touch(db: Session, restroom_id: int) -> None:
    """巡查或问题变更后刷新台账更新时间。"""
    restroom = db.get(Restroom, restroom_id)
    if restroom is not None and restroom.deleted_at is None:
        restroom.updated_at = datetime.now()
        db.commit()
