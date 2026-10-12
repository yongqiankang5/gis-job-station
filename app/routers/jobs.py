"""招聘岗位分页筛选、详情查询与 CSV 导出 API。"""

from __future__ import annotations

import csv
import io
import math
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.database import get_db
from app.models import Job
from app.schemas import JobListResponse, JobResponse


router = APIRouter(prefix="/jobs", tags=["招聘岗位"])


class JobFilters:
    """可同时供岗位列表和 CSV 导出复用的动态筛选参数。"""

    def __init__(
        self,
        keyword: str | None = Query(default=None, description="职位、公司或 JD 关键词"),
        city: str | None = Query(default=None, description="城市，多选用逗号分隔"),
        province: str | None = Query(default=None, description="省份"),
        job_type: str | None = Query(default=None, description="岗位类型，多选用逗号分隔"),
        education: str | None = Query(default=None, description="学历，多选用逗号分隔"),
        experience: str | None = Query(default=None, description="经验，多选用逗号分隔"),
        salary_min: float | None = Query(default=None, ge=0, description="期望薪资下限 K/月"),
        salary_max: float | None = Query(default=None, ge=0, description="期望薪资上限 K/月"),
        skills: str | None = Query(default=None, description="技能标签，多选用逗号分隔且为 AND"),
        company_type: str | None = Query(default=None, description="公司类型"),
        source: str | None = Query(default=None, description="来源平台"),
        sort: str = Query(
            default="publish_desc",
            pattern=r"^(salary_desc|salary_asc|publish_desc|quality_desc)$",
            description="排序方式",
        ),
        min_quality: int = Query(default=0, ge=0, le=100, description="最低质量分"),
    ):
        """接收并保存 FastAPI 查询参数。"""

        self.keyword = keyword
        self.city = city
        self.province = province
        self.job_type = job_type
        self.education = education
        self.experience = experience
        self.salary_min = salary_min
        self.salary_max = salary_max
        self.skills = skills
        self.company_type = company_type
        self.source = source
        self.sort = sort
        self.min_quality = min_quality


JobFiltersDependency = Annotated[JobFilters, Depends()]


def _split_values(value: str | None) -> list[str]:
    """解析中英文逗号分隔值并去重，同时保持用户输入顺序。"""

    parts = [part.strip() for part in re.split(r"[,，]", value or "") if part.strip()]
    return list(dict.fromkeys(parts))


def _filtered_statement(filters: JobFilters) -> Select[tuple[Job]]:
    """根据筛选对象动态拼接有效岗位查询。"""

    statement = select(Job).where(
        Job.is_valid.is_(True), Job.quality_score >= filters.min_quality
    )
    # 默认排除演示数据，除非用户显式指定了source
    if not filters.source:
        statement = statement.where(Job.source != "demo")
    if filters.keyword:
        fuzzy = f"%{filters.keyword.strip()}%"
        statement = statement.where(
            or_(
                Job.job_title.ilike(fuzzy),
                Job.company_name.ilike(fuzzy),
                Job.job_description.ilike(fuzzy),
            )
        )
    cities = _split_values(filters.city)
    if cities:
        statement = statement.where(Job.city.in_(cities))
    if filters.province:
        statement = statement.where(Job.province == filters.province.strip())
    job_types = _split_values(filters.job_type)
    if job_types:
        statement = statement.where(Job.job_type.in_(job_types))
    educations = _split_values(filters.education)
    if educations:
        statement = statement.where(Job.education.in_(educations))
    experiences = _split_values(filters.experience)
    if experiences:
        statement = statement.where(Job.experience.in_(experiences))
    # 采用区间重叠规则：岗位上限不低于期望下限，岗位下限不高于期望上限。
    if filters.salary_min is not None:
        statement = statement.where(Job.salary_max >= filters.salary_min)
    if filters.salary_max is not None:
        statement = statement.where(Job.salary_min <= filters.salary_max)
    for skill in _split_values(filters.skills):
        # JSON 转文本后逐个 AND 匹配，兼容 SQLite，并保留迁移 PostgreSQL 的空间。
        statement = statement.where(
            Job.skills.cast(String).ilike(f'%"{skill}"%')
        )
    company_types = _split_values(filters.company_type)
    if company_types:
        statement = statement.where(Job.company_type.in_(company_types))
    if filters.source:
        statement = statement.where(Job.source == filters.source.strip())
    return statement


def _ordered_statement(
    statement: Select[tuple[Job]], sort: str
) -> Select[tuple[Job]]:
    """为岗位查询添加稳定排序。"""

    if sort == "salary_desc":
        return statement.order_by(
            Job.salary_mid.desc().nullslast(), Job.publish_date.desc(), Job.id.desc()
        )
    if sort == "salary_asc":
        return statement.order_by(
            Job.salary_mid.asc().nullslast(), Job.publish_date.desc(), Job.id.desc()
        )
    if sort == "quality_desc":
        return statement.order_by(
            Job.quality_score.desc(), Job.publish_date.desc(), Job.id.desc()
        )
    return statement.order_by(
        Job.publish_date.desc().nullslast(), Job.created_at.desc(), Job.id.desc()
    )


@router.get("", response_model=JobListResponse)
def list_jobs(
    filters: JobFiltersDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> JobListResponse:
    """按多项条件筛选有效岗位并返回分页结果。"""

    statement = _filtered_statement(filters)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    jobs = db.scalars(
        _ordered_statement(statement, filters.sort)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return JobListResponse(
        items=[JobResponse.model_validate(job) for job in jobs],
        total=int(total),
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/export")
def export_jobs(
    filters: JobFiltersDependency,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """按当前筛选条件导出全部匹配岗位为 UTF-8 BOM CSV 附件。"""

    jobs = db.scalars(_ordered_statement(_filtered_statement(filters), filters.sort)).all()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID", "来源", "职位名称", "公司名称", "公司类型", "省份", "城市",
            "区县", "最低薪资(K/月)", "最高薪资(K/月)", "平均薪资(K/月)",
            "学历", "经验", "岗位类型", "技能", "发布日期", "质量分", "原始链接",
        ]
    )
    for job in jobs:
        writer.writerow(
            [
                job.id, job.source, job.job_title, job.company_name, job.company_type,
                job.province, job.city, job.district or "", job.salary_min,
                job.salary_max, job.salary_mid, job.education, job.experience,
                job.job_type, ";".join(job.skills or []), job.publish_date or "",
                job.quality_score, job.url,
            ]
        )
    content = "\ufeff" + buffer.getvalue()
    headers = {"Content-Disposition": 'attachment; filename="gis_jobs_export.csv"'}
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    """按主键查询单条有效岗位详情。"""

    job = db.scalar(select(Job).where(Job.id == job_id, Job.is_valid.is_(True)))
    if job is None:
        raise HTTPException(status_code=404, detail="岗位不存在或已失效")
    return JobResponse.model_validate(job)
