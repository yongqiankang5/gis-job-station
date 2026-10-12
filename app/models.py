"""GIS 招聘、事业单位招录与抓取日志数据模型。"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Job(Base):
    """招聘岗位表。"""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_jobs_source_source_id"),
        Index("ix_jobs_location", "province", "city"),
        Index("ix_jobs_type_education", "job_type", "education"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_type: Mapped[str] = mapped_column(String(32), default="其他", nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    district: Mapped[str | None] = mapped_column(String(64))
    city_level: Mapped[str | None] = mapped_column(String(16), index=True)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_mid: Mapped[float | None] = mapped_column(Float, index=True)
    salary_note: Mapped[str | None] = mapped_column(String(128))
    education: Mapped[str] = mapped_column(String(32), default="不限", nullable=False)
    experience: Mapped[str] = mapped_column(String(32), default="不限", nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), default="其他", nullable=False)
    job_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # JSON 是 SQLAlchemy 的跨数据库类型，可直接迁移到 PostgreSQL。
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    publish_date: Mapped[date | None] = mapped_column(Date, index=True)
    crawl_date: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    quality_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    # 首次清洗时保存原字段快照，后续重跑清洗不会覆盖，便于审计和回溯。
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_cleaned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OfficialRecord(Base):
    """事业单位招录记录表。"""

    __tablename__ = "official_records"
    __table_args__ = (Index("ix_official_year_location", "year", "province", "city"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    unit_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    unit_level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    # 政府公告表格格式差异较大，无法可靠解析时按数据质量要求保留为空。
    planned_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_count: Mapped[int | None] = mapped_column(Integer)
    major_requirement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    education: Mapped[str] = mapped_column(String(32), default="不限", nullable=False)
    hired_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrawlLog(Base):
    """招聘信息抓取任务日志表。"""

    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    total_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_msg: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
