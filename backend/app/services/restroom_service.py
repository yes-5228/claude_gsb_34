"""公厕台账业务逻辑。"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import OPEN_ISSUE_STATUSES
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models import Inspection, Issue, RectificationRecord, Restroom, RestroomDeletionLog
from app.schemas.restroom import (
    DeletionImpact,
    RestroomCreate,
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


def _next_code(db: Session) -> str:
    """生成形如 WC-0007 的公厕编号。"""
    seq = (db.scalar(select(func.count()).select_from(Restroom)) or 0) + 1
    while True:
        code = f"WC-{seq:04d}"
        if not db.scalar(select(Restroom.id).where(Restroom.code == code)):
            return code
        seq += 1


def get_restroom(db: Session, restroom_id: int) -> Restroom:
    restroom = db.get(Restroom, restroom_id)
    if restroom is None:
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
    stmt = select(Restroom)
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
    return list(db.scalars(select(Restroom.district).distinct().order_by(Restroom.district)))


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


def _collect_impact(db: Session, restroom_id: int) -> dict:
    """汇总删除一座公厕会牵连的数据量，供影响面评估与删除审计共用。"""
    inspection_count = db.scalar(
        select(func.count()).select_from(Inspection).where(Inspection.restroom_id == restroom_id)
    ) or 0
    issues = list(
        db.scalars(select(Issue).where(Issue.restroom_id == restroom_id)).all()
    )
    issue_by_status: dict[str, int] = {}
    issue_by_category: dict[str, int] = {}
    open_issue_count = 0
    attachment_count = 0
    for issue in issues:
        issue_by_status[issue.status] = issue_by_status.get(issue.status, 0) + 1
        issue_by_category[issue.category] = issue_by_category.get(issue.category, 0) + 1
        if issue.status in OPEN_ISSUE_STATUSES:
            open_issue_count += 1
        attachment_count += len(issue.images or [])
    rectification_count = db.scalar(
        select(func.count())
        .select_from(RectificationRecord)
        .join(Issue, Issue.id == RectificationRecord.issue_id)
        .where(Issue.restroom_id == restroom_id)
    ) or 0
    return {
        "inspection_count": inspection_count,
        "issue_count": len(issues),
        "open_issue_count": open_issue_count,
        "rectification_count": rectification_count,
        "attachment_count": attachment_count,
        "issue_by_status": issue_by_status,
        "issue_by_category": issue_by_category,
    }


def get_deletion_impact(db: Session, restroom_id: int) -> DeletionImpact:
    """删除前的影响面评估：随删数据规模 + 是否被未闭环问题阻断。"""
    restroom = get_restroom(db, restroom_id)
    impact = _collect_impact(db, restroom_id)
    blocking_reasons: list[str] = []
    if impact["open_issue_count"]:
        blocking_reasons.append(
            f"存在 {impact['open_issue_count']} 条未闭环问题（待整改/整改中/待验收），"
            "进行中的整改工单不允许随删除清除，请先完成整改闭环或关闭问题"
        )
    return DeletionImpact(
        restroom_id=restroom.id,
        code=restroom.code,
        name=restroom.name,
        requires_force=bool(impact["inspection_count"] or impact["issue_count"]),
        deletable=not blocking_reasons,
        blocking_reasons=blocking_reasons,
        **impact,
    )


def _restroom_snapshot(restroom: Restroom) -> dict:
    """留存公厕档案关键字段，删除后仍能解释历史统计口径。"""
    return {
        "code": restroom.code,
        "name": restroom.name,
        "district": restroom.district,
        "address": restroom.address,
        "grade": restroom.grade,
        "status": restroom.status,
        "manager": restroom.manager,
        "manager_phone": restroom.manager_phone,
        "open_hours": restroom.open_hours,
        "stall_count": restroom.stall_count,
        "basin_count": restroom.basin_count,
        "has_accessible": restroom.has_accessible,
        "created_at": restroom.created_at.isoformat() if restroom.created_at else None,
    }


def delete_restroom(
    db: Session,
    restroom_id: int,
    *,
    force: bool = False,
    operator: str = "",
    reason: str | None = None,
) -> RestroomDeletionLog:
    """删除公厕。

    边界约定：
    - 公厕档案、巡查记录、已闭环问题及其整改流水与附件随公厕一并删除；
    - 未闭环问题（待整改/整改中/待验收）属于进行中的整改工单，必须先闭环或关闭，
      否则即使 force=true 也拒绝删除；
    - 删除前把随删数据的规模与分布写入删除审计，审计写入与级联删除在同一事务，
      任一步失败整体回退。
    """
    restroom = get_restroom(db, restroom_id)
    impact = _collect_impact(db, restroom_id)
    if (impact["inspection_count"] or impact["issue_count"]) and not force:
        raise ConflictError(
            f"该公厕已有 {impact['inspection_count']} 条巡查记录、{impact['issue_count']} 条问题记录"
            f"（含整改流水 {impact['rectification_count']} 条、附件 {impact['attachment_count']} 个），"
            "确需删除请使用 force=true"
        )
    if impact["open_issue_count"]:
        raise ConflictError(
            f"该公厕还有 {impact['open_issue_count']} 条未闭环问题（待整改/整改中/待验收），"
            "强制删除也不能清除进行中的整改工单，请先完成整改闭环或关闭问题"
        )

    log = RestroomDeletionLog(
        restroom_id=restroom.id,
        code=restroom.code,
        name=restroom.name,
        district=restroom.district,
        inspection_count=impact["inspection_count"],
        issue_count=impact["issue_count"],
        rectification_count=impact["rectification_count"],
        attachment_count=impact["attachment_count"],
        issue_by_status=impact["issue_by_status"],
        issue_by_category=impact["issue_by_category"],
        restroom_snapshot=_restroom_snapshot(restroom),
        operator=operator,
        reason=reason,
    )
    try:
        db.add(log)
        db.delete(restroom)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return log


def list_deletion_logs(
    db: Session, *, page: int = 1, page_size: int = 10
) -> tuple[list[RestroomDeletionLog], int]:
    """删除审计分页查询，用于解释看板与报表中消失的数据。"""
    total = db.scalar(select(func.count()).select_from(RestroomDeletionLog)) or 0
    rows = list(
        db.scalars(
            select(RestroomDeletionLog)
            .order_by(RestroomDeletionLog.created_at.desc(), RestroomDeletionLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


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
    open_issue_count = db.scalar(
        select(func.count())
        .select_from(Issue)
        .where(Issue.restroom_id == restroom_id, Issue.status.in_(OPEN_ISSUE_STATUSES))
    ) or 0
    total_issue_count = db.scalar(
        select(func.count()).select_from(Issue).where(Issue.restroom_id == restroom_id)
    ) or 0

    base = RestroomOut.model_validate(restroom).model_dump()
    return RestroomDetail(
        **base,
        inspection_count=inspection_count,
        latest_inspection_time=latest.inspect_time if latest else None,
        latest_inspection_score=latest.score if latest else None,
        avg_score=round(float(avg_score), 1) if avg_score is not None else None,
        open_issue_count=open_issue_count,
        total_issue_count=total_issue_count,
    )


def touch(db: Session, restroom_id: int) -> None:
    """巡查或问题变更后刷新台账更新时间。"""
    restroom = db.get(Restroom, restroom_id)
    if restroom is not None:
        restroom.updated_at = datetime.now()
        db.commit()
