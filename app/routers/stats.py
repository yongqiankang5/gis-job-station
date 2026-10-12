"""岗位、薪资、技能、公司、事业单位与趋势统计分析 API。"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache, wraps
from typing import Any, Callable, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job
from app.schemas import (
    CityDistributionResponse,
    CompanyAnalysisResponse,
    MapPoint,
    NamedValue,
    OfficialAnalysisResponse,
    OverviewStats,
    RequirementAnalysisResponse,
    SalaryDistributionResponse,
    SkillAnalysisResponse,
    TrendResponse,
)
from app.services.analyzer import JobAnalyzer

try:
    import redis
except ImportError:  # pragma: no cover - 允许用户不启用 Redis 时以最小依赖运行。
    redis = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stats", tags=["统计分析"])
FunctionType = TypeVar("FunctionType", bound=Callable[..., Any])


@lru_cache(maxsize=1)
def _redis_client() -> Any | None:
    """按配置创建同步 Redis 客户端；未配置或缺少依赖时返回 None。"""

    if not settings.redis_url or redis is None:
        return None
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def cache_statistics(ttl_seconds: int = 300) -> Callable[[FunctionType], FunctionType]:
    """为同步统计端点添加可选 Redis 缓存，故障时静默回退实时查询。"""

    def decorator(function: FunctionType) -> FunctionType:
        """包装统计端点并保留 FastAPI 所需的原函数签名。"""

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """读取缓存或执行原统计函数，并在成功后缓存五分钟。"""

            client = _redis_client()
            if client is None:
                return function(*args, **kwargs)
            key_parts = {
                key: value
                for key, value in kwargs.items()
                if key != "db" and isinstance(value, (str, int, float, bool, type(None)))
            }
            raw_key = json.dumps(key_parts, ensure_ascii=False, sort_keys=True)
            digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:20]
            cache_key = f"gis-job-tracker:stats:{function.__name__}:{digest}"
            try:
                cached = client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as exc:  # Redis 不应成为接口的单点故障。
                logger.warning("读取统计缓存失败，回退数据库：%s", exc)
            result = function(*args, **kwargs)
            try:
                client.setex(
                    cache_key,
                    ttl_seconds,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                )
            except Exception as exc:
                logger.warning("写入统计缓存失败：%s", exc)
            return result

        return cast(FunctionType, wrapper)

    return decorator


def _internal_error(label: str, exc: Exception) -> HTTPException:
    """把分析异常转换为带上下文的 HTTP 500。"""

    logger.exception("%s失败", label)
    return HTTPException(status_code=500, detail=f"{label}失败：{type(exc).__name__}: {exc}")


@router.get("/overview", response_model=OverviewStats)
@cache_statistics()
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    """返回岗位数量、覆盖范围、薪资和近期新增概览。"""

    try:
        return JobAnalyzer(db).get_overview()
    except Exception as exc:
        raise _internal_error("岗位概览统计", exc) from exc


@router.get("/city-distribution", response_model=CityDistributionResponse)
@cache_statistics()
def city_distribution_analysis(
    top_n: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回 Top 城市、省份及岗位密度指数。"""

    try:
        return JobAnalyzer(db).get_city_distribution(top_n)
    except Exception as exc:
        raise _internal_error("城市分布统计", exc) from exc


@router.get("/salary-distribution", response_model=SalaryDistributionResponse)
@cache_statistics()
def salary_distribution(db: Session = Depends(get_db)) -> dict[str, Any]:
    """返回薪资区间和多维平均薪资。"""

    try:
        return JobAnalyzer(db).get_salary_distribution()
    except Exception as exc:
        raise _internal_error("薪资分布统计", exc) from exc


@router.get("/skill-analysis", response_model=SkillAnalysisResponse)
@cache_statistics()
def skill_analysis(
    top_n: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回技能频次、共现、类型偏好和薪资溢价。"""

    try:
        return JobAnalyzer(db).get_skill_analysis(top_n)
    except Exception as exc:
        raise _internal_error("技能需求分析", exc) from exc


@router.get("/requirement-analysis", response_model=RequirementAnalysisResponse)
@cache_statistics()
def requirement_analysis(db: Session = Depends(get_db)) -> dict[str, Any]:
    """返回学历和经验要求差异。"""

    try:
        return JobAnalyzer(db).get_requirement_analysis()
    except Exception as exc:
        raise _internal_error("学历经验分析", exc) from exc


@router.get("/company-analysis", response_model=CompanyAnalysisResponse)
@cache_statistics()
def company_analysis(
    top_n: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回公司招聘需求、类型分布和薪资对比。"""

    try:
        return JobAnalyzer(db).get_company_analysis(top_n)
    except Exception as exc:
        raise _internal_error("公司分析", exc) from exc


@router.get("/official-analysis", response_model=OfficialAnalysisResponse)
@cache_statistics()
def official_analysis(db: Session = Depends(get_db)) -> dict[str, Any]:
    """返回事业单位招录兑现率、省份和拟聘人员背景统计。"""

    try:
        return JobAnalyzer(db).get_official_analysis()
    except Exception as exc:
        raise _internal_error("事业单位分析", exc) from exc


@router.get("/trend", response_model=TrendResponse)
@cache_statistics()
def trend_analysis(
    months: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回近月岗位薪资趋势和技能年度对比。"""

    try:
        return JobAnalyzer(db).get_trend(months)
    except Exception as exc:
        raise _internal_error("趋势分析", exc) from exc


# 以下端点兼容现有静态首页，继续提供轻量结构。
@router.get("/skills", response_model=list[NamedValue])
def skill_demand(
    limit: int = Query(default=15, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """返回旧版首页使用的技能频次列表。"""

    skills = db.scalars(select(Job.skills).where(Job.is_valid.is_(True), Job.source != "demo")).all()
    return JobAnalyzer.skill_frequency(skills, limit)


@router.get("/job-types", response_model=list[NamedValue])
def job_type_distribution(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """返回旧版首页使用的岗位类型频次。"""

    values = db.scalars(select(Job.job_type).where(Job.is_valid.is_(True), Job.source != "demo")).all()
    return JobAnalyzer.value_counts(values)


@router.get("/cities", response_model=list[NamedValue])
def city_frequency(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """返回旧版首页使用的城市岗位频次。"""

    values = db.scalars(select(Job.city).where(Job.is_valid.is_(True), Job.source != "demo")).all()
    return JobAnalyzer.value_counts(values, limit)


@router.get("/map", response_model=list[MapPoint])
def map_distribution(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """按省市聚合岗位数量供现有地图使用。"""

    rows = db.execute(
        select(Job.province, Job.city).where(Job.is_valid.is_(True), Job.source != "demo")
    ).all()
    return JobAnalyzer.location_counts(rows)
