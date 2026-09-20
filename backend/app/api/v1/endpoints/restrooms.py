"""公厕台账接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep, build_meta
from app.core.database import get_db
from app.schemas.common import Page
from app.schemas.restroom import (
    RestroomCreate,
    RestroomDeleteImpact,
    RestroomDeleteResult,
    RestroomDetail,
    RestroomOut,
    RestroomUpdate,
)
from app.services import restroom_service

router = APIRouter(prefix="/restrooms", tags=["公厕台账"])


@router.get("/meta/districts", response_model=list[str], summary="区域列表")
def list_districts(db: Annotated[Session, Depends(get_db)]) -> list[str]:
    return restroom_service.list_districts(db)


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


@router.get(
    "/{restroom_id}/delete-impact",
    response_model=RestroomDeleteImpact,
    summary="删除公厕前的影响面评估",
)
def get_restroom_delete_impact(
    restroom_id: int, db: Annotated[Session, Depends(get_db)]
) -> RestroomDeleteImpact:
    return restroom_service.build_delete_impact(db, restroom_id)


@router.get("/{restroom_id}", response_model=RestroomDetail, summary="公厕详情")
def get_restroom(restroom_id: int, db: Annotated[Session, Depends(get_db)]) -> RestroomDetail:
    return restroom_service.get_restroom_detail(db, restroom_id)


@router.patch("/{restroom_id}", response_model=RestroomOut, summary="更新公厕")
def update_restroom(
    restroom_id: int, payload: RestroomUpdate, db: Annotated[Session, Depends(get_db)]
) -> RestroomOut:
    return RestroomOut.model_validate(restroom_service.update_restroom(db, restroom_id, payload))


@router.delete("/{restroom_id}", response_model=RestroomDeleteResult, summary="删除或归档公厕")
def delete_restroom(
    restroom_id: int,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query(description="存在已闭环历史数据时，true 表示确认归档并保留历史")] = False,
    reason: Annotated[str | None, Query(max_length=500, description="删除或归档原因")] = None,
    operator: Annotated[str, Query(max_length=60, description="操作人")] = "",
) -> RestroomDeleteResult:
    action, impact, audit_id = restroom_service.delete_restroom(
        db, restroom_id, force=force, reason=reason, operator=operator
    )
    message = "删除成功" if action == "delete" else "已归档公厕，巡查、问题、整改流水和附件均已保留"
    return RestroomDeleteResult(action=action, message=message, audit_id=audit_id, impact=impact)
