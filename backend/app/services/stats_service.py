"""统计看板业务逻辑。"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    OPEN_ISSUE_STATUSES,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomStatus,
)
from app.models import Inspection, Issue, RectificationRecord, Restroom, RestroomDeleteAudit
from app.schemas.stats import (
    CategoryStat,
    DashboardStats,
    DistrictStat,
    MonthlyReport,
    MonthlyArchiveItem,
    NameValue,
    OverviewStats,
    RestroomRankItem,
    TrendPoint,
)
from app.services import inspection_service, issue_service


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(*conditions)
    return db.scalar(stmt) or 0


def _month_bounds(month: str) -> tuple[datetime, datetime, date]:
    try:
        year_text, month_text = month.split("-", 1)
        year = int(year_text)
        month_number = int(month_text)
        first = date(year, month_number, 1)
    except (ValueError, TypeError) as exc:
        from app.core.exceptions import DomainError

        raise DomainError("月份格式必须为 YYYY-MM") from exc
    if month_number == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month_number + 1, 1)
    return datetime.combine(first, time.min), datetime.combine(next_first, time.min), first


def overview(db: Session) -> OverviewStats:
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    week_start = today_start - timedelta(days=6)
    month_start = datetime.combine(date(now.year, now.month, 1), time.min)

    issue_total = _count(db, Issue)
    issue_open = _count(
        db,
        Issue,
        Issue.status.in_(OPEN_ISSUE_STATUSES),
        Issue.restroom_id.in_(select(Restroom.id).where(Restroom.deleted_at.is_(None))),
    )
    issue_overdue = _count(
        db,
        Issue,
        Issue.deadline.is_not(None),
        Issue.deadline < now,
        Issue.status.in_(OPEN_ISSUE_STATUSES),
        Issue.restroom_id.in_(select(Restroom.id).where(Restroom.deleted_at.is_(None))),
    )
    done_count = _count(db, Issue, Issue.status == IssueStatus.DONE.value)
    closed_count = _count(db, Issue, Issue.status == IssueStatus.CLOSED.value)
    finished = done_count + closed_count
    archived_restroom_count = _count(db, Restroom, Restroom.deleted_at.is_not(None))
    retained_inspection_count = (
        db.scalar(
            select(func.count())
            .select_from(Inspection)
            .join(Restroom, Restroom.id == Inspection.restroom_id)
            .where(Restroom.deleted_at.is_not(None))
        )
        or 0
    )
    retained_issue_count = (
        db.scalar(
            select(func.count())
            .select_from(Issue)
            .join(Restroom, Restroom.id == Issue.restroom_id)
            .where(Restroom.deleted_at.is_not(None))
        )
        or 0
    )
    retained_record_count = (
        db.scalar(
            select(func.count())
            .select_from(RectificationRecord)
            .join(Issue, Issue.id == RectificationRecord.issue_id)
            .join(Restroom, Restroom.id == Issue.restroom_id)
            .where(Restroom.deleted_at.is_not(None))
        )
        or 0
    )
    retained_issues = db.scalars(
        select(Issue)
        .join(Restroom, Restroom.id == Issue.restroom_id)
        .where(Restroom.deleted_at.is_not(None))
    ).all()
    retained_attachment_count = sum(len(issue.images or []) for issue in retained_issues)

    return OverviewStats(
        restroom_total=_count(db, Restroom, Restroom.deleted_at.is_(None)),
        restroom_open=_count(
            db,
            Restroom,
            Restroom.status == RestroomStatus.NORMAL.value,
            Restroom.deleted_at.is_(None),
        ),
        restroom_maintenance=_count(
            db,
            Restroom,
            Restroom.status == RestroomStatus.MAINTENANCE.value,
            Restroom.deleted_at.is_(None),
        ),
        inspection_total=_count(db, Inspection),
        inspection_today=_count(
            db,
            Inspection,
            Inspection.inspect_time >= today_start,
            Inspection.restroom_id.in_(select(Restroom.id).where(Restroom.deleted_at.is_(None))),
        ),
        inspection_week=_count(
            db,
            Inspection,
            Inspection.inspect_time >= week_start,
            Inspection.restroom_id.in_(select(Restroom.id).where(Restroom.deleted_at.is_(None))),
        ),
        avg_score_week=round(
            float(
                db.scalar(
                    select(func.avg(Inspection.score))
                    .join(Restroom, Restroom.id == Inspection.restroom_id)
                    .where(
                        Inspection.inspect_time >= week_start,
                        Restroom.deleted_at.is_(None),
                    )
                )
                or 0.0
            ),
            1,
        ),
        issue_total=issue_total,
        issue_open=issue_open,
        issue_overdue=issue_overdue,
        issue_done_this_month=_count(
            db,
            Issue,
            Issue.status == IssueStatus.DONE.value,
            Issue.updated_at >= month_start,
            Issue.restroom_id.in_(select(Restroom.id).where(Restroom.deleted_at.is_(None))),
        ),
        archived_restroom_count=archived_restroom_count,
        retained_inspection_count=retained_inspection_count,
        retained_issue_count=retained_issue_count,
        retained_record_count=retained_record_count,
        retained_attachment_count=int(retained_attachment_count or 0),
        rectification_rate=round(finished / issue_total * 100, 1) if issue_total else 0.0,
    )


def issue_by_status(db: Session) -> list[NameValue]:
    rows = dict(
        db.execute(select(Issue.status, func.count()).group_by(Issue.status)).all()  # type: ignore[arg-type]
    )
    ordered = list(IssueStatus)
    return [NameValue(name=status.value, value=float(rows.get(status.value, 0))) for status in ordered]


def issue_by_severity(db: Session) -> list[NameValue]:
    rows = dict(db.execute(select(Issue.severity, func.count()).group_by(Issue.severity)).all())
    return [
        NameValue(name=severity.value, value=float(rows.get(severity.value, 0)))
        for severity in IssueSeverity
    ]


def issue_by_category(db: Session) -> list[CategoryStat]:
    rows = db.execute(
        select(Issue.category, func.count()).group_by(Issue.category)
    ).all()
    totals = {category: int(count) for category, count in rows}
    open_rows = db.execute(
        select(Issue.category, func.count())
        .where(Issue.status.in_(OPEN_ISSUE_STATUSES))
        .group_by(Issue.category)
    ).all()
    opens = {category: int(count) for category, count in open_rows}
    result: list[CategoryStat] = []
    for category in IssueCategory:
        total = totals.get(category.value, 0)
        open_count = opens.get(category.value, 0)
        result.append(
            CategoryStat(
                category=category.value, total=total, open=open_count, closed=total - open_count
            )
        )
    return result


def inspection_trend(db: Session, days: int = 14) -> list[TrendPoint]:
    days = max(3, min(days, 60))
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min)

    inspection_rows = db.execute(
        select(Inspection.inspect_time, Inspection.score)
        .join(Restroom, Restroom.id == Inspection.restroom_id)
        .where(Inspection.inspect_time >= start_dt, Restroom.deleted_at.is_(None))
    ).all()
    issue_rows = db.execute(
        select(Issue.report_time).where(Issue.report_time >= start_dt)
    ).all()

    buckets: dict[str, dict[str, float]] = {}
    for offset in range(days):
        key = (start + timedelta(days=offset)).isoformat()
        buckets[key] = {"inspections": 0, "issues": 0, "score_sum": 0.0}
    for inspect_time, score in inspection_rows:
        key = inspect_time.date().isoformat()
        if key in buckets:
            buckets[key]["inspections"] += 1
            buckets[key]["score_sum"] += float(score or 0)
    for (report_time,) in issue_rows:
        key = report_time.date().isoformat()
        if key in buckets:
            buckets[key]["issues"] += 1

    points: list[TrendPoint] = []
    for key, bucket in buckets.items():
        count = int(bucket["inspections"])
        points.append(
            TrendPoint(
                date=key,
                inspections=count,
                issues=int(bucket["issues"]),
                avg_score=round(bucket["score_sum"] / count, 1) if count else 0.0,
            )
        )
    return points


def district_stats(db: Session) -> list[DistrictStat]:
    restroom_rows = db.execute(
        select(Restroom.district, func.count())
        .where(Restroom.deleted_at.is_(None))
        .group_by(Restroom.district)
    ).all()
    counts = {district: int(count) for district, count in restroom_rows}
    open_rows = db.execute(
        select(Restroom.district, func.count(Issue.id))
        .join(Issue, Issue.restroom_id == Restroom.id)
        .where(Issue.status.in_(OPEN_ISSUE_STATUSES), Restroom.deleted_at.is_(None))
        .group_by(Restroom.district)
    ).all()
    opens = {district: int(count) for district, count in open_rows}
    retained_rows = db.execute(
        select(Restroom.district, func.count(Issue.id))
        .join(Issue, Issue.restroom_id == Restroom.id)
        .where(Restroom.deleted_at.is_not(None))
        .group_by(Restroom.district)
    ).all()
    retained = {district: int(count) for district, count in retained_rows}
    score_rows = db.execute(
        select(Restroom.district, func.avg(Inspection.score))
        .join(Inspection, Inspection.restroom_id == Restroom.id)
        .where(Restroom.deleted_at.is_(None))
        .group_by(Restroom.district)
    ).all()
    scores = {district: float(avg or 0) for district, avg in score_rows}

    districts = set(counts) | set(retained)
    return sorted(
        [
            DistrictStat(
                district=district,
                restroom_count=counts.get(district, 0),
                issue_open=opens.get(district, 0),
                retained_issue_count=retained.get(district, 0),
                avg_score=round(scores.get(district, 0.0), 1),
            )
            for district in districts
        ],
        key=lambda item: (item.issue_open, -item.avg_score),
        reverse=True,
    )


def restroom_ranking(db: Session, limit: int = 8) -> list[RestroomRankItem]:
    inspections = db.execute(
        select(
            Inspection.restroom_id,
            func.count(Inspection.id),
            func.avg(Inspection.score),
        )
        .join(Restroom, Restroom.id == Inspection.restroom_id)
        .where(Restroom.deleted_at.is_(None))
        .group_by(Inspection.restroom_id)
    ).all()
    stats = {
        rid: {"count": int(count), "avg": round(float(avg or 0), 1)} for rid, count, avg in inspections
    }
    open_rows = db.execute(
        select(Issue.restroom_id, func.count())
        .join(Restroom, Restroom.id == Issue.restroom_id)
        .where(Issue.status.in_(OPEN_ISSUE_STATUSES), Restroom.deleted_at.is_(None))
        .group_by(Issue.restroom_id)
    ).all()
    opens = {rid: int(count) for rid, count in open_rows}

    ranking: list[RestroomRankItem] = []
    for restroom in db.scalars(select(Restroom).where(Restroom.deleted_at.is_(None))):
        stat = stats.get(restroom.id, {"count": 0, "avg": 0.0})
        ranking.append(
            RestroomRankItem(
                restroom_id=restroom.id,
                code=restroom.code,
                name=restroom.name,
                district=restroom.district,
                inspection_count=stat["count"],
                avg_score=stat["avg"],
                open_issues=opens.get(restroom.id, 0),
            )
        )
    ranking.sort(key=lambda item: (-item.open_issues, item.avg_score, -item.inspection_count))
    return ranking[:limit]


def monthly_report(db: Session, month: str | None = None) -> MonthlyReport:
    """生成月度历史口径报表，并单列当月归档公厕对当前运行看板的影响。"""
    if month is None:
        now = datetime.now()
        month = f"{now.year:04d}-{now.month:02d}"
    start, end, _ = _month_bounds(month)

    inspection_count = _count(
        db, Inspection, Inspection.inspect_time >= start, Inspection.inspect_time < end
    )
    issue_reported_count = _count(
        db, Issue, Issue.report_time >= start, Issue.report_time < end
    )
    issue_closed_count = _count(
        db,
        Issue,
        Issue.closed_at.is_not(None),
        Issue.closed_at >= start,
        Issue.closed_at < end,
    )
    month_end = min(end, datetime.now())
    issue_open_at_month_end = (
        db.scalar(
            select(func.count())
            .select_from(Issue)
            .where(Issue.report_time < month_end)
            .where(
                (Issue.status.in_(OPEN_ISSUE_STATUSES))
                | (Issue.closed_at >= month_end)
                | (
                    (Issue.status == IssueStatus.DONE.value)
                    & (Issue.updated_at >= month_end)
                )
            )
        )
        or 0
    )

    audits = list(
        db.scalars(
            select(RestroomDeleteAudit)
            .where(
                RestroomDeleteAudit.deleted_at >= start,
                RestroomDeleteAudit.deleted_at < end,
            )
            .order_by(RestroomDeleteAudit.deleted_at.desc(), RestroomDeleteAudit.id.desc())
        )
    )
    archived_restroom_count = len(audits)
    retained_inspection_count = sum(item.inspection_count for item in audits)
    retained_issue_count = sum(item.issue_count for item in audits)
    retained_record_count = sum(item.rectification_record_count for item in audits)
    retained_attachment_count = sum(item.attachment_count for item in audits)
    removed_active_restroom_count = archived_restroom_count
    archive_items = [
        MonthlyArchiveItem(
            audit_id=item.id,
            restroom_id=item.restroom_id,
            code=item.restroom_code,
            name=item.restroom_name,
            district=item.district,
            reason=item.reason,
            operator=item.operator,
            archived_at=item.deleted_at,
            inspection_count=item.inspection_count,
            issue_count=item.issue_count,
            rectification_record_count=item.rectification_record_count,
            attachment_count=item.attachment_count,
        )
        for item in audits
    ]

    note = (
        f"{month} 月报采用历史口径：巡查 {inspection_count} 条、上报问题 {issue_reported_count} 条均保留；"
        f"当月归档公厕 {archived_restroom_count} 座，仅从当前运行台账移除，"
        f"其 {retained_inspection_count} 条巡查、{retained_issue_count} 条问题、"
        f"{retained_record_count} 条整改流水和 {retained_attachment_count} 个附件仍用于历史追溯。"
    )
    return MonthlyReport(
        month=month,
        inspection_count=inspection_count,
        issue_reported_count=issue_reported_count,
        issue_closed_count=issue_closed_count,
        issue_open_at_month_end=issue_open_at_month_end,
        archived_restroom_count=archived_restroom_count,
        retained_inspection_count=retained_inspection_count,
        retained_issue_count=retained_issue_count,
        retained_record_count=retained_record_count,
        retained_attachment_count=retained_attachment_count,
        removed_active_restroom_count=removed_active_restroom_count,
        archives=archive_items,
        reconciliation_note=note,
    )


def dashboard(db: Session, trend_days: int = 14) -> DashboardStats:
    recent_issues, _ = issue_service.list_issues(
        db, page=1, page_size=5, sort_by="report_time", include_archived=False
    )
    recent_inspections, _ = inspection_service.list_inspections(
        db, page=1, page_size=5, sort_by="inspect_time"
    )
    return DashboardStats(
        overview=overview(db),
        issue_by_status=issue_by_status(db),
        issue_by_category=issue_by_category(db),
        issue_by_severity=issue_by_severity(db),
        inspection_trend=inspection_trend(db, days=trend_days),
        districts=district_stats(db),
        top_restrooms=restroom_ranking(db),
        recent_issues=[issue_service.to_out(issue) for issue in recent_issues],
        recent_inspections=[inspection_service.to_out(item) for item in recent_inspections],
    )
