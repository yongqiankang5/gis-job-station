"""事业单位招录记录分页筛选、详情与汇总统计 API。"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OfficialRecord
from app.schemas import (
    OfficialAnalysisResponse,
    OfficialListResponse,
    OfficialRecordResponse,
)
from app.services.analyzer import JobAnalyzer


router = APIRouter(prefix="/official", tags=["事业单位招录"])


@router.get("", response_model=OfficialListResponse)
def list_official_records(
    keyword: str | None = Query(default=None, description="单位、岗位或专业关键词"),
    province: str | None = Query(default=None, description="省份"),
    unit_level: str | None = Query(default=None, description="单位级别"),
    year: int | None = Query(default=None, ge=2000, le=2100, description="年份"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OfficialListResponse:
    """动态筛选事业单位招录记录并返回分页结果。"""

    statement = select(OfficialRecord)
    if keyword:
        fuzzy = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                OfficialRecord.unit_name.ilike(fuzzy),
                OfficialRecord.job_title.ilike(fuzzy),
                OfficialRecord.major_requirement.ilike(fuzzy),
            )
        )
    if province:
        statement = statement.where(OfficialRecord.province == province.strip())
    if unit_level:
        statement = statement.where(OfficialRecord.unit_level == unit_level.strip())
    if year is not None:
        statement = statement.where(OfficialRecord.year == year)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = db.scalars(
        statement.order_by(OfficialRecord.year.desc(), OfficialRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return OfficialListResponse(
        items=[OfficialRecordResponse.model_validate(record) for record in records],
        total=int(total),
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/stats", response_model=OfficialAnalysisResponse)
def official_stats(
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """返回全部年份或指定年份的事业单位招录统计。"""

    try:
        return JobAnalyzer(db).get_official_analysis(year)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"事业单位招录统计失败：{type(exc).__name__}: {exc}",
        ) from exc


@router.get("/{record_id}", response_model=OfficialRecordResponse)
def get_official_record(
    record_id: int, db: Session = Depends(get_db)
) -> OfficialRecordResponse:
    """按主键查询单条事业单位招录详情。"""

    record = db.get(OfficialRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="事业单位招录记录不存在")
    return OfficialRecordResponse.model_validate(record)
