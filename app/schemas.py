"""API 请求与响应使用的 Pydantic 数据结构。"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobResponse(BaseModel):
    """单条招聘岗位响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    job_title: str
    company_name: str
    company_type: str
    city: str
    province: str
    district: str | None
    city_level: str | None
    salary_min: float | None
    salary_max: float | None
    salary_mid: float | None
    salary_note: str | None
    education: str
    experience: str
    job_type: str
    job_description: str
    skills: list[str] = Field(default_factory=list)
    publish_date: date | None
    crawl_date: date
    url: str
    is_valid: bool
    quality_score: int
    note: str | None
    is_cleaned: bool
    cleaned_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    """带分页信息的岗位列表响应。"""

    items: list[JobResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CandidateInfo(BaseModel):
    """事业单位拟聘人员信息。"""

    name: str
    school: str | None = None
    major: str | None = None


class OfficialRecordResponse(BaseModel):
    """事业单位招录记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    unit_name: str
    unit_level: str
    province: str
    city: str
    job_title: str
    planned_count: int | None
    actual_count: int | None
    major_requirement: str
    education: str
    hired_candidates: list[CandidateInfo] = Field(default_factory=list)
    year: int
    source_url: str
    created_at: datetime


class OfficialListResponse(BaseModel):
    """带分页信息的事业单位记录列表响应。"""

    items: list[OfficialRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int


class OverviewStats(BaseModel):
    """岗位与事业单位招录概览响应。"""

    total_jobs: int
    valid_jobs: int
    active_cities: int
    active_companies: int
    average_salary: float | None
    median_salary: float | None
    new_jobs_30d: int
    official_planned_count: int
    official_records: int


class NameCount(BaseModel):
    """名称与数量通用统计项。"""

    name: str
    count: int


class DistributionItem(NameCount):
    """带百分比的分类分布项。"""

    percentage: float


class AverageSalaryItem(NameCount):
    """带平均薪资的分组统计项。"""

    average_salary: float | None


class CityDistributionItem(BaseModel):
    """单个城市岗位聚合项。"""

    province: str
    city: str
    job_count: int
    average_salary: float | None
    company_count: int
    city_level: str
    level_weight: float
    density_index: float


class ProvinceDistributionItem(BaseModel):
    """单个省份岗位聚合项。"""

    province: str
    job_count: int
    city_count: int
    company_count: int
    average_salary: float | None


class CityDistributionResponse(BaseModel):
    """城市和省份岗位分布响应。"""

    cities: list[CityDistributionItem]
    provinces: list[ProvinceDistributionItem]
    city_level_weights: dict[str, float]


class SalaryRangeItem(BaseModel):
    """薪资区间岗位数量项。"""

    name: str
    count: int


class SalaryDistributionResponse(BaseModel):
    """薪资区间与多维平均薪资响应。"""

    salary_ranges: list[SalaryRangeItem]
    missing_salary_count: int
    by_education: list[AverageSalaryItem]
    by_experience: list[AverageSalaryItem]
    by_job_type: list[AverageSalaryItem]
    top_salary_cities: list[AverageSalaryItem]


class SkillCooccurrenceLink(BaseModel):
    """技能共现关系边。"""

    source: str
    target: str
    value: int


class SkillCooccurrence(BaseModel):
    """Top 技能共现矩阵及关系边。"""

    skills: list[str]
    matrix: list[list[int]]
    links: list[SkillCooccurrenceLink]


class JobTypeSkillGroup(BaseModel):
    """某岗位类型的高频技能。"""

    job_type: str
    skills: list[NameCount]


class SkillSalaryItem(BaseModel):
    """技能薪资与相对总体薪资溢价项。"""

    skill: str
    job_count: int
    average_salary: float | None
    overall_average_salary: float | None
    premium_rate: float | None


class SkillAnalysisResponse(BaseModel):
    """技能需求、共现和薪资溢价分析响应。"""

    top_skills: list[NameCount]
    cooccurrence: SkillCooccurrence
    by_job_type: list[JobTypeSkillGroup]
    overall_average_salary: float | None
    salary_correlation: list[SkillSalaryItem]
    high_premium_skills: list[SkillSalaryItem]


class GroupDistribution(BaseModel):
    """指定群体内部的分类分布。"""

    group: str
    distribution: list[DistributionItem]


class RequirementAnalysisResponse(BaseModel):
    """学历与经验要求分析响应。"""

    education_distribution: list[DistributionItem]
    experience_distribution: list[DistributionItem]
    education_by_city_level: list[GroupDistribution]
    official_vs_enterprise: list[GroupDistribution]


class CompanyDemandItem(BaseModel):
    """公司招聘需求聚合项。"""

    company_name: str
    job_count: int
    average_salary: float | None
    city_count: int
    company_type: str


class CompanyAnalysisResponse(BaseModel):
    """公司需求、类型和薪资对比响应。"""

    top_companies: list[CompanyDemandItem]
    company_type_distribution: list[DistributionItem]
    salary_comparison: list[AverageSalaryItem]


class OfficialYearItem(BaseModel):
    """事业单位年度招录统计项。"""

    year: int
    planned_count: int
    actual_count: int
    fulfillment_rate: float | None


class OfficialUnitItem(BaseModel):
    """事业单位招录兑现率统计项。"""

    unit_name: str
    planned_count: int
    actual_count: int
    fulfillment_rate: float | None


class OfficialProvinceItem(BaseModel):
    """省份事业单位招录统计项。"""

    province: str
    planned_count: int
    actual_count: int


class OfficialAnalysisResponse(BaseModel):
    """事业单位招录综合分析响应。"""

    record_count: int
    by_year: list[OfficialYearItem]
    by_unit: list[OfficialUnitItem]
    by_province: list[OfficialProvinceItem]
    top_schools: list[NameCount]
    major_distribution: list[NameCount]


class MonthlyTrendItem(BaseModel):
    """单月岗位数量和薪资趋势项。"""

    month: str
    job_count: int
    average_salary: float | None


class YearSkillGroup(BaseModel):
    """单年度高频技能统计。"""

    year: int
    skills: list[NameCount]


class TrendResponse(BaseModel):
    """近月岗位趋势与技能年度对比响应。"""

    monthly: list[MonthlyTrendItem]
    skill_year_comparison: list[YearSkillGroup]


class NamedValue(BaseModel):
    """图表常用名称与数值响应。"""

    name: str
    value: int | float


class MapPoint(BaseModel):
    """岗位城市聚合地图点响应。"""

    province: str
    city: str
    count: int
    longitude: float | None = None
    latitude: float | None = None


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    app: str
