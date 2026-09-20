"""公厕台账接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep, build_meta
from app.core.database import get_db
from app.schemas.common import MessageOut, Page
from app.schemas.restroom import (
    DeletionImpact,
    DeletionLogOut,
    RestroomCreate,
    RestroomDetail,
    RestroomOut,
    RestroomUpdate,
)
from app.services import restroom_service

router = APIRouter(prefix="/restrooms", tags=["公厕台账"])


@router.get("/meta/districts", response_model=list[str], summary="区域列表")
def list_districts(db: Annotated[Session, Depends(get_db)]) -> list[str]:
    return restroom_service.list_districts(db)


@router.get("/deletion-logs", response_model=Page[DeletionLogOut], summary="公厕删除审计记录")
def list_deletion_logs(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
) -> Page[DeletionLogOut]:
    rows, total = restroom_service.list_deletion_logs(
        db, page=pagination.page, page_size=pagination.page_size
    )
    return Page[DeletionLogOut](
        items=[DeletionLogOut.model_validate(row) for row in rows],
        meta=build_meta(total, pagination),
    )


@router.get("", response_model=Page[RestroomOut], summary="公厕列表")
def list_restrooms(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    keyword: Annotated[str | None, Query(description="名称/编号/地址/责任人模糊搜索")] = None,
    district: Annotated[str | None, Query(description="所属区域")] = None,
    status: Annotated[str | None, Query(description="开放状态")] = None,
    grade: Annotated[str | None, Query(description="公厕等级")] = None,
    sort_by: Annotated[str, Query(description="排序字段")] = "created_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[RestroomOut]:
    rows, total = restroom_service.list_restrooms(
        db,
        keyword=keyword,
        district=district,
        status=status,
        grade=grade,
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        order=order,
    )
    return Page[RestroomOut](
        items=[RestroomOut.model_validate(row) for row in rows],
        meta=build_meta(total, pagination),
    )


@router.post("", response_model=RestroomOut, status_code=201, summary="新增公厕")
def create_restroom(
    payload: RestroomCreate, db: Annotated[Session, Depends(get_db)]
) -> RestroomOut:
    return RestroomOut.model_validate(restroom_service.create_restroom(db, payload))


@router.get("/{restroom_id}", response_model=RestroomDetail, summary="公厕详情")
def get_restroom(restroom_id: int, db: Annotated[Session, Depends(get_db)]) -> RestroomDetail:
    return restroom_service.get_restroom_detail(db, restroom_id)


@router.patch("/{restroom_id}", response_model=RestroomOut, summary="更新公厕")
def update_restroom(
    restroom_id: int, payload: RestroomUpdate, db: Annotated[Session, Depends(get_db)]
) -> RestroomOut:
    return RestroomOut.model_validate(restroom_service.update_restroom(db, restroom_id, payload))


@router.get("/{restroom_id}/deletion-impact", response_model=DeletionImpact, summary="删除影响面评估")
def get_deletion_impact(
    restroom_id: int, db: Annotated[Session, Depends(get_db)]
) -> DeletionImpact:
    return restroom_service.get_deletion_impact(db, restroom_id)


@router.delete("/{restroom_id}", response_model=MessageOut, summary="删除公厕")
def delete_restroom(
    restroom_id: int,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query(description="为 true 时级联删除巡查与已闭环问题记录")] = False,
    operator: Annotated[str, Query(description="操作人，写入删除审计")] = "",
    reason: Annotated[str | None, Query(description="删除原因，写入删除审计")] = None,
) -> MessageOut:
    log = restroom_service.delete_restroom(
        db, restroom_id, force=force, operator=operator, reason=reason
    )
    parts = [f"公厕「{log.name}」已删除"]
    if log.inspection_count or log.issue_count:
        parts.append(
            f"随删巡查 {log.inspection_count} 条、问题 {log.issue_count} 条、"
            f"整改流水 {log.rectification_count} 条、附件 {log.attachment_count} 个"
        )
    parts.append(f"已留存删除审计（编号 {log.id}），统计变化可追溯")
    return MessageOut(message="；".join(parts))
