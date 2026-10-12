"""GIS 招聘岗位与事业单位招录数据统计分析服务。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, OfficialRecord


CITY_LEVEL_WEIGHTS: dict[str, float] = {
    "一线": 5.0,
    "新一线": 4.0,
    "二线": 3.0,
    "三线": 2.0,
    "其他": 1.0,
}
EDUCATION_ORDER = ("不限", "大专", "本科", "硕士", "博士")
EXPERIENCE_ORDER = ("不限", "应届", "1-3年", "3-5年", "5-10年", "10年以上")
SALARY_BANDS: tuple[tuple[str, float, float | None], ...] = (
    ("0-5K", 0, 5),
    ("5-10K", 5, 10),
    ("10-15K", 10, 15),
    ("15-20K", 15, 20),
    ("20-30K", 20, 30),
    ("30-50K", 30, 50),
    ("50K+", 50, None),
)


class JobAnalyzer:
    """通过 SQLAlchemy 读取数据并返回可直接 JSON 序列化的统计字典。"""

    def __init__(self, db_session: Session):
        """保存当前数据库会话。"""

        self.db = db_session

    def get_overview(self) -> dict[str, Any]:
        """返回岗位总量、覆盖范围、薪资、近期新增和事业招录概览。"""

        # 生产统计默认排除演示数据
        base_filter = [Job.is_valid.is_(True), Job.source != "demo"]
        total_jobs = self.db.scalar(select(func.count(Job.id)).where(*base_filter)) or 0
        valid_jobs = total_jobs
        active_cities = self.db.scalar(
            select(func.count(func.distinct(Job.city))).where(*base_filter)
        ) or 0
        active_companies = self.db.scalar(
            select(func.count(func.distinct(Job.company_name))).where(*base_filter)
        ) or 0
        salaries = self._salary_values(
            self.db.scalars(
                select(Job.salary_mid).where(
                    *base_filter, Job.salary_mid.is_not(None)
                )
            ).all()
        )
        recent_start = date.today() - timedelta(days=30)
        recent_jobs = self.db.scalar(
            select(func.count(Job.id)).where(
                *base_filter, Job.publish_date >= recent_start
            )
        ) or 0
        # 数据更新时间：取最新的抓取日期
        last_crawl_date = self.db.scalar(
            select(func.max(Job.crawl_date)).where(*base_filter)
        )
        official_records = self.db.scalar(select(func.count(OfficialRecord.id))) or 0
        official_planned = self.db.scalar(
            select(func.coalesce(func.sum(OfficialRecord.planned_count), 0))
        ) or 0
        return {
            "total_jobs": int(total_jobs),
            "valid_jobs": int(valid_jobs),
            "active_cities": int(active_cities),
            "active_companies": int(active_companies),
            "average_salary": self._average(salaries),
            "median_salary": round(float(median(salaries)), 2) if salaries else None,
            "new_jobs_30d": int(recent_jobs),
            "data_updated_at": str(last_crawl_date) if last_crawl_date else None,
            "official_planned_count": int(official_planned),
            # 保留旧首页字段，值为事业单位记录条数。
            "official_records": int(official_records),
        }

    def get_city_distribution(self, top_n: int = 20) -> dict[str, Any]:
        """返回城市、省份聚合结果及按城市等级校正的岗位密度指数。"""

        rows = self.db.execute(
            select(
                Job.province,
                Job.city,
                Job.city_level,
                Job.company_name,
                Job.salary_mid,
            ).where(Job.is_valid.is_(True), Job.source != "demo")
        ).all()
        city_groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
        province_groups: dict[str, list[Any]] = defaultdict(list)
        for row in rows:
            city_groups[(row.province or "未知", row.city or "未知")].append(row)
            province_groups[row.province or "未知"].append(row)

        cities: list[dict[str, Any]] = []
        for (province, city), group in city_groups.items():
            levels = Counter((row.city_level or "其他") for row in group)
            level = levels.most_common(1)[0][0]
            weight = CITY_LEVEL_WEIGHTS.get(level, 1.0)
            salaries = self._salary_values(row.salary_mid for row in group)
            cities.append(
                {
                    "province": province,
                    "city": city,
                    "job_count": len(group),
                    "average_salary": self._average(salaries),
                    "company_count": len({row.company_name for row in group if row.company_name}),
                    "city_level": level,
                    "level_weight": weight,
                    "density_index": round(len(group) / weight, 2),
                }
            )
        cities.sort(key=lambda item: (-item["job_count"], item["city"]))

        provinces: list[dict[str, Any]] = []
        for province, group in province_groups.items():
            salaries = self._salary_values(row.salary_mid for row in group)
            provinces.append(
                {
                    "province": province,
                    "job_count": len(group),
                    "city_count": len({row.city for row in group if row.city}),
                    "company_count": len({row.company_name for row in group if row.company_name}),
                    "average_salary": self._average(salaries),
                }
            )
        provinces.sort(key=lambda item: (-item["job_count"], item["province"]))
        return {
            "cities": cities[:top_n],
            "provinces": provinces,
            "city_level_weights": CITY_LEVEL_WEIGHTS,
        }

    def get_salary_distribution(self) -> dict[str, Any]:
        """统计薪资区间及学历、经验、岗位类型和城市的平均薪资。"""

        rows = self.db.execute(
            select(
                Job.salary_mid,
                Job.education,
                Job.experience,
                Job.job_type,
                Job.city,
            ).where(Job.is_valid.is_(True), Job.source != "demo")
        ).all()
        distribution = {label: 0 for label, _, _ in SALARY_BANDS}
        missing_count = 0
        for row in rows:
            if row.salary_mid is None:
                missing_count += 1
                continue
            salary = float(row.salary_mid)
            for label, lower, upper in SALARY_BANDS:
                if salary >= lower and (upper is None or salary < upper):
                    distribution[label] += 1
                    break

        education = self._group_average(
            rows, "education", allowed=("本科", "硕士", "博士")
        )
        experience = self._group_average(rows, "experience", allowed=EXPERIENCE_ORDER)
        job_types = self._group_average(rows, "job_type")
        cities = self._group_average(rows, "city")
        cities.sort(
            key=lambda item: (
                item["average_salary"] is None,
                -(item["average_salary"] or 0),
                item["name"],
            )
        )
        return {
            "salary_ranges": [
                {"name": label, "count": count} for label, count in distribution.items()
            ],
            "missing_salary_count": missing_count,
            "by_education": education,
            "by_experience": experience,
            "by_job_type": job_types,
            "top_salary_cities": cities[:10],
        }

    def get_skill_analysis(self, top_n: int = 30) -> dict[str, Any]:
        """统计技能频次、共现、岗位类型偏好和薪资溢价。"""

        rows = self.db.execute(
            select(Job.skills, Job.job_type, Job.salary_mid).where(
                Job.is_valid.is_(True), Job.source != "demo"
            )
        ).all()
        frequency: Counter[str] = Counter()
        for row in rows:
            frequency.update(set(row.skills or []))
        ranked = sorted(frequency.items(), key=lambda item: (-item[1], item[0]))
        top_skills = [
            {"name": name, "count": int(count)} for name, count in ranked[:top_n]
        ]

        co_skills = [name for name, _ in ranked[:15]]
        co_index = {skill: index for index, skill in enumerate(co_skills)}
        matrix = [[0 for _ in co_skills] for _ in co_skills]
        for row in rows:
            present = sorted(set(row.skills or []).intersection(co_index))
            for left_index, left in enumerate(present):
                matrix[co_index[left]][co_index[left]] += 1
                for right in present[left_index + 1 :]:
                    matrix[co_index[left]][co_index[right]] += 1
                    matrix[co_index[right]][co_index[left]] += 1
        links = [
            {"source": co_skills[i], "target": co_skills[j], "value": matrix[i][j]}
            for i in range(len(co_skills))
            for j in range(i + 1, len(co_skills))
            if matrix[i][j] > 0
        ]

        type_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            type_counts[row.job_type or "其他"].update(set(row.skills or []))
        by_job_type = []
        for job_type, counts in sorted(type_counts.items()):
            skills = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
            by_job_type.append(
                {
                    "job_type": job_type,
                    "skills": [{"name": name, "count": count} for name, count in skills],
                }
            )

        all_salaries = self._salary_values(row.salary_mid for row in rows)
        overall_average = self._average(all_salaries)
        skill_salaries: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row.salary_mid is None:
                continue
            for skill in set(row.skills or []):
                skill_salaries[skill].append(float(row.salary_mid))
        correlations: list[dict[str, Any]] = []
        for skill, salaries in skill_salaries.items():
            average = self._average(salaries)
            premium = (
                round(((average - overall_average) / overall_average) * 100, 2)
                if average is not None and overall_average not in (None, 0)
                else None
            )
            correlations.append(
                {
                    "skill": skill,
                    "job_count": len(salaries),
                    "average_salary": average,
                    "overall_average_salary": overall_average,
                    "premium_rate": premium,
                }
            )
        correlations.sort(
            key=lambda item: (
                item["premium_rate"] is None,
                -(item["premium_rate"] or 0),
                item["skill"],
            )
        )
        # 按技术体系分类统计
        from app.utils.keywords import SKILL_CATEGORIES
        category_stats = []
        for category, skills in SKILL_CATEGORIES.items():
            count = sum(frequency.get(skill, 0) for skill in skills)
            category_stats.append({"name": category, "count": count, "skills": [
                {"name": skill, "count": frequency.get(skill, 0)}
                for skill in skills if frequency.get(skill, 0) > 0
            ]})

        return {
            "top_skills": top_skills,
            "cooccurrence": {"skills": co_skills, "matrix": matrix, "links": links},
            "by_job_type": by_job_type,
            "category_stats": category_stats,
            "overall_average_salary": overall_average,
            "salary_correlation": correlations,
            "high_premium_skills": [
                item for item in correlations if (item["premium_rate"] or 0) > 20
            ],
        }

    def get_requirement_analysis(self) -> dict[str, Any]:
        """分析学历、经验、城市等级和事业单位/企业要求差异。"""

        rows = self.db.execute(
            select(Job.education, Job.experience, Job.city_level, Job.company_type).where(
                Job.is_valid.is_(True), Job.source != "demo"
            )
        ).all()
        education = self._distribution((row.education for row in rows), EDUCATION_ORDER)
        experience = self._distribution((row.experience for row in rows), EXPERIENCE_ORDER)

        level_groups: dict[str, list[str]] = {"一线": [], "二线": []}
        organization_groups: dict[str, list[str]] = {"事业单位": [], "企业": []}
        for row in rows:
            if row.city_level in level_groups:
                level_groups[row.city_level].append(row.education or "不限")
            organization = "事业单位" if row.company_type == "事业单位" else "企业"
            organization_groups[organization].append(row.education or "不限")
        return {
            "education_distribution": education,
            "experience_distribution": experience,
            "education_by_city_level": [
                {"group": group, "distribution": self._distribution(values, EDUCATION_ORDER)}
                for group, values in level_groups.items()
            ],
            "official_vs_enterprise": [
                {"group": group, "distribution": self._distribution(values, EDUCATION_ORDER)}
                for group, values in organization_groups.items()
            ],
        }

    def get_company_analysis(self, top_n: int = 20) -> dict[str, Any]:
        """分析招聘公司排行、公司性质分布及不同所有制薪资。"""

        rows = self.db.execute(
            select(Job.company_name, Job.company_type, Job.salary_mid, Job.city).where(
                Job.is_valid.is_(True), Job.source != "demo"
            )
        ).all()
        company_groups: dict[str, list[Any]] = defaultdict(list)
        for row in rows:
            company_groups[row.company_name or "未知公司"].append(row)
        companies = []
        for company, group in company_groups.items():
            companies.append(
                {
                    "company_name": company,
                    "job_count": len(group),
                    "average_salary": self._average(
                        self._salary_values(row.salary_mid for row in group)
                    ),
                    "city_count": len({row.city for row in group if row.city}),
                    "company_type": Counter(
                        (row.company_type or "其他") for row in group
                    ).most_common(1)[0][0],
                }
            )
        companies.sort(key=lambda item: (-item["job_count"], item["company_name"]))
        company_types = self._distribution(
            (row.company_type or "其他" for row in rows),
            ("国企", "民营", "上市公司", "事业单位", "外资", "合资", "其他"),
        )

        comparison = {"国企/事业单位": [], "民营/上市公司": []}
        for row in rows:
            if row.salary_mid is None:
                continue
            if row.company_type in ("国企", "事业单位"):
                comparison["国企/事业单位"].append(float(row.salary_mid))
            elif row.company_type in ("民营", "上市公司"):
                comparison["民营/上市公司"].append(float(row.salary_mid))
        return {
            "top_companies": companies[:top_n],
            "company_type_distribution": company_types,
            "salary_comparison": [
                {"name": name, "count": len(values), "average_salary": self._average(values)}
                for name, values in comparison.items()
            ],
        }

    def get_official_analysis(self, year: int | None = None) -> dict[str, Any]:
        """分析事业单位年度招录、单位兑现率、省份分布及拟聘人员背景。"""

        statement = select(OfficialRecord)
        if year is not None:
            statement = statement.where(OfficialRecord.year == year)
        records = list(self.db.scalars(statement))

        year_groups: dict[int, list[OfficialRecord]] = defaultdict(list)
        unit_groups: dict[str, list[OfficialRecord]] = defaultdict(list)
        province_groups: dict[str, list[OfficialRecord]] = defaultdict(list)
        schools: Counter[str] = Counter()
        majors: Counter[str] = Counter()
        for record in records:
            year_groups[record.year].append(record)
            unit_groups[record.unit_name].append(record)
            province_groups[record.province or "未知"].append(record)
            for candidate in record.hired_candidates or []:
                school = str(candidate.get("school") or "").strip()
                major = str(candidate.get("major") or "").strip()
                if school:
                    schools[school] += 1
                if major:
                    majors[major] += 1

        by_year = []
        for item_year, group in sorted(year_groups.items()):
            planned = sum(record.planned_count or 0 for record in group)
            actual = sum(record.actual_count or 0 for record in group)
            by_year.append(
                {
                    "year": item_year,
                    "planned_count": planned,
                    "actual_count": actual,
                    "fulfillment_rate": self._rate(actual, planned),
                }
            )
        by_unit = []
        for unit, group in unit_groups.items():
            planned = sum(record.planned_count or 0 for record in group)
            actual = sum(record.actual_count or 0 for record in group)
            by_unit.append(
                {
                    "unit_name": unit,
                    "planned_count": planned,
                    "actual_count": actual,
                    "fulfillment_rate": self._rate(actual, planned),
                }
            )
        by_unit.sort(key=lambda item: (-item["planned_count"], item["unit_name"]))
        by_province = [
            {
                "province": province,
                "planned_count": sum(record.planned_count or 0 for record in group),
                "actual_count": sum(record.actual_count or 0 for record in group),
            }
            for province, group in province_groups.items()
        ]
        by_province.sort(key=lambda item: (-item["planned_count"], item["province"]))
        return {
            "record_count": len(records),
            "by_year": by_year,
            "by_unit": by_unit,
            "by_province": by_province,
            "top_schools": self._counter_items(schools, 20),
            "major_distribution": self._counter_items(majors, None),
        }

    def get_trend(self, months: int = 12) -> dict[str, Any]:
        """返回近若干月岗位与薪资趋势，以及 2024—2026 技能年度对比。"""

        month_keys = self._recent_months(months)
        first_year, first_month = map(int, month_keys[0].split("-"))
        start_date = date(first_year, first_month, 1)
        rows = self.db.execute(
            select(Job.publish_date, Job.salary_mid, Job.skills).where(
                Job.is_valid.is_(True), Job.source != "demo", Job.publish_date >= start_date
            )
        ).all()
        monthly: dict[str, list[Any]] = {key: [] for key in month_keys}
        for row in rows:
            key = row.publish_date.strftime("%Y-%m")
            if key in monthly:
                monthly[key].append(row)
        monthly_trend = [
            {
                "month": key,
                "job_count": len(group),
                "average_salary": self._average(
                    self._salary_values(row.salary_mid for row in group)
                ),
            }
            for key, group in monthly.items()
        ]

        annual_rows = self.db.execute(
            select(Job.publish_date, Job.skills).where(
                Job.is_valid.is_(True),
                Job.source != "demo",
                Job.publish_date >= date(2024, 1, 1),
                Job.publish_date < date(2027, 1, 1),
            )
        ).all()
        annual: dict[int, Counter[str]] = {2024: Counter(), 2025: Counter(), 2026: Counter()}
        for row in annual_rows:
            annual[row.publish_date.year].update(set(row.skills or []))
        skill_year_comparison = [
            {
                "year": year,
                "skills": [
                    {"name": name, "count": count}
                    for name, count in sorted(
                        counts.items(), key=lambda item: (-item[1], item[0])
                    )[:30]
                ],
            }
            for year, counts in annual.items()
        ]
        return {
            "monthly": monthly_trend,
            "skill_year_comparison": skill_year_comparison,
        }

    @staticmethod
    def _salary_values(values: Iterable[float | None]) -> list[float]:
        """移除空薪资并转换为普通 float。"""

        return [float(value) for value in values if value is not None]

    @staticmethod
    def _average(values: Sequence[float]) -> float | None:
        """计算平均值并保留两位小数，空序列返回 None。"""

        return round(sum(values) / len(values), 2) if values else None

    @classmethod
    def _group_average(
        cls,
        rows: Iterable[Any],
        field: str,
        allowed: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按指定字段统计有薪资岗位数量与平均薪资。"""

        groups: dict[str, list[float]] = defaultdict(list)
        total_counts: Counter[str] = Counter()
        for row in rows:
            name = str(getattr(row, field) or "不限")
            if allowed is not None and name not in allowed:
                continue
            total_counts[name] += 1
            if row.salary_mid is not None:
                groups[name].append(float(row.salary_mid))
        names = list(allowed) if allowed is not None else sorted(total_counts)
        return [
            {
                "name": name,
                "count": int(total_counts.get(name, 0)),
                "average_salary": cls._average(groups.get(name, [])),
            }
            for name in names
        ]

    @staticmethod
    def _distribution(
        values: Iterable[str | None], ordered_names: Sequence[str]
    ) -> list[dict[str, Any]]:
        """计算分类字段数量和百分比，并按指定顺序返回。"""

        clean_values = [str(value or "不限") for value in values]
        counts = Counter(clean_values)
        total = len(clean_values)
        extras = sorted(set(counts).difference(ordered_names))
        return [
            {
                "name": name,
                "count": int(counts.get(name, 0)),
                "percentage": round(counts.get(name, 0) / total * 100, 2) if total else 0.0,
            }
            for name in [*ordered_names, *extras]
        ]

    @staticmethod
    def _counter_items(counter: Counter[str], limit: int | None) -> list[dict[str, Any]]:
        """将 Counter 转为稳定排序的名称/数量列表。"""

        items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if limit is not None:
            items = items[:limit]
        return [{"name": name, "count": int(count)} for name, count in items]

    @staticmethod
    def _rate(actual: int, planned: int) -> float | None:
        """计算招录兑现率百分比，计划数为零时返回 None。"""

        return round(actual / planned * 100, 2) if planned else None

    @staticmethod
    def _recent_months(months: int) -> list[str]:
        """生成包含当前月在内的连续月份键。"""

        current = date.today().replace(day=1)
        result = []
        year, month = current.year, current.month
        for offset in range(months - 1, -1, -1):
            total_month = year * 12 + month - 1 - offset
            item_year, zero_based_month = divmod(total_month, 12)
            result.append(f"{item_year:04d}-{zero_based_month + 1:02d}")
        return result

    # 以下静态方法保留旧版统计路由兼容性。
    @staticmethod
    def skill_frequency(
        skill_groups: Iterable[list[str] | None], limit: int = 15
    ) -> list[dict[str, Any]]:
        """兼容旧接口：返回技能名称及频次。"""

        counts: Counter[str] = Counter()
        for group in skill_groups:
            counts.update(group or [])
        return [
            {"name": name, "value": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    @staticmethod
    def value_counts(
        values: Iterable[str | None], limit: int | None = None
    ) -> list[dict[str, Any]]:
        """兼容旧接口：返回分类值频次。"""

        counts = Counter(value for value in values if value)
        items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if limit is not None:
            items = items[:limit]
        return [{"name": name, "value": count} for name, count in items]

    @staticmethod
    def location_counts(rows: Iterable[Any]) -> list[dict[str, Any]]:
        """兼容地图接口：按省市聚合岗位数量。"""

        counts = Counter((row[0], row[1]) for row in rows)
        return [
            {
                "province": province,
                "city": city,
                "count": count,
                "longitude": None,
                "latitude": None,
            }
            for (province, city), count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
