"""招聘数据标准化、技能提取、重复合并与质量评分服务。"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable

import jieba
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import ensure_job_cleaning_columns
from app.models import Job
from app.utils.city_province_map import find_city, normalize_province
from app.utils.keywords import SKILL_KEYWORDS


# 清洗规则集中在模块顶部，后续调整无需修改流程代码。
GENERAL_PROGRAMMING_SKILLS = ["Python", "Java", "C++", "JavaScript", "R", "SQL"]
ALL_SKILL_KEYWORDS = list(dict.fromkeys([*SKILL_KEYWORDS, *GENERAL_PROGRAMMING_SKILLS]))

JOB_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("销售", ("销售", "市场", "客户经理", "区域经理")),
    ("算法", ("算法", "ai", "深度学习", "机器学习", "图像识别")),
    ("数据处理", ("数据处理", "内业", "制图", "解译", "遥感处理")),
    ("分析", ("分析", "规划", "咨询", "研究员")),
    ("开发", ("开发", "工程师", "前端", "后端", "webgis", "三维")),
)
OFFICIAL_TITLE_KEYWORDS = ("管理", "调查", "监测")

COMPANY_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("事业单位", ("事业单位", "事业编", "研究院所", "公益一类", "公益二类")),
    ("国企", ("国企", "国有", "央企", "地方国资", "国资委")),
    ("上市公司", ("上市公司", "已上市", "上市企业", "a股", "港股", "美股")),
    ("外资", ("外资", "外商独资", "外企")),
    ("合资", ("合资", "中外合资")),
    ("民营", ("民营", "私营", "民企")),
)

SNAPSHOT_FIELDS = (
    "source", "source_id", "job_title", "company_name", "company_type",
    "city", "province", "district", "salary_min", "salary_max", "salary_note",
    "education", "experience", "job_type", "job_description", "skills",
    "publish_date", "crawl_date", "url", "is_valid",
)


class DataCleaner:
    """对 SQLAlchemy Job 对象执行可重复、可回溯的数据清洗。"""

    def __init__(self, db_session: Session):
        """保存数据库会话，并确保旧数据库具备清洗所需增量字段。"""

        self.db = db_session
        ensure_job_cleaning_columns(self.db.get_bind())
        # 将专业词加入 jieba 词典，避免中文复合技能在辅助分词时被拆散。
        for keyword in ALL_SKILL_KEYWORDS:
            if re.search(r"[\u4e00-\u9fff]", keyword):
                jieba.add_word(keyword)

    def clean_all(self, only_unprocessed: bool = True) -> dict[str, Any]:
        """清洗全部或尚未处理的岗位，并返回包含处理数量的统计信息。"""

        statement = select(Job)
        if only_unprocessed:
            statement = statement.where(
                or_(Job.is_cleaned.is_(False), Job.is_cleaned.is_(None))
            )
        jobs = list(self.db.scalars(statement.order_by(Job.id)))
        for job in jobs:
            self.clean_one(job)
        self.db.commit()
        stats = self.get_stats()
        stats["本次清洗数"] = len(jobs)
        return stats

    def clean_one(self, job: Job) -> Job:
        """清洗单条岗位并返回原 ORM 对象；调用方负责提交事务。"""

        if not job.raw_data:
            job.raw_data = self._make_snapshot(job)

        job.job_title = self._clean_text(job.job_title)
        job.company_name = self._clean_text(job.company_name)
        job.job_description = str(job.job_description or "").strip()

        city, parsed_district, mapped_province, city_level = find_city(job.city)
        job.city = city or self._clean_text(job.city)
        job.district = self._normalize_district(job.district or parsed_district)
        job.province = mapped_province or normalize_province(job.province) or "未知"
        job.city_level = city_level or "其他"

        salary_min, salary_max = self.parse_salary(job.salary_note)
        if salary_min is not None or salary_max is not None or self._is_negotiable(job.salary_note):
            job.salary_min, job.salary_max = salary_min, salary_max
        else:
            job.salary_min = self._positive_number(job.salary_min)
            job.salary_max = self._positive_number(job.salary_max)
        job.salary_mid = self._salary_mid(job.salary_min, job.salary_max)

        combined_text = f"{job.job_title}\n{job.job_description}"
        education = self.normalize_education(job.education)
        if education == "不限":
            education = self.extract_education(combined_text)
        job.education = education

        experience = self.normalize_experience(job.experience)
        if experience == "不限":
            experience = self.extract_experience(combined_text)
        job.experience = experience

        job.company_type = self.normalize_company_type(job.company_type)
        job.skills = self.extract_skills(combined_text)
        job.job_type = self.classify_job_type(
            job.job_title, job.job_description, job.company_type
        )
        job.is_cleaned = True
        job.cleaned_at = datetime.now(timezone.utc)
        return job

    def extract_skills(self, text: str | None) -> list[str]:
        """从标题和 JD 中不区分大小写提取技能，按词典顺序返回去重列表。"""

        content = str(text or "")
        if not content:
            return []
        normalized = content.casefold()
        # jieba 结果用于强化中文复合词识别；子串匹配则兼容“熟悉ArcGIS软件”等写法。
        tokens = {token.casefold() for token in jieba.lcut(content, cut_all=False)}
        found: list[str] = []
        for skill in ALL_SKILL_KEYWORDS:
            folded = skill.casefold()
            if self._contains_skill(normalized, folded) or folded in tokens:
                found.append(skill)
        return found

    def classify_job_type(
        self, title: str | None, description: str | None, company_type: str | None
    ) -> str:
        """根据标题、JD 和公司性质判断岗位类型，优先采用更具体的类别。"""

        title_text = str(title or "").casefold()
        content = f"{title or ''} {description or ''}".casefold()
        company = str(company_type or "")
        if (
            ("事业单位" in company or "国企" in company)
            and any(keyword in title_text for keyword in OFFICIAL_TITLE_KEYWORDS)
        ):
            return "事业单位"
        # 标题比 JD 描述更能代表岗位主职能；先匹配标题中的具体类别。
        for job_type, keywords in JOB_TYPE_RULES:
            if any(keyword in title_text for keyword in keywords):
                return job_type
        # 标题没有有效信号时，再使用 JD 作为补充判断。
        for job_type, keywords in JOB_TYPE_RULES:
            if any(keyword in content for keyword in keywords):
                return job_type
        return "其他"

    def deduplicate(self) -> dict[str, int]:
        """按公司、职位和城市合并跨平台重复项，保留信息最完整的有效记录。"""

        active_jobs = list(
            self.db.scalars(select(Job).where(Job.is_valid.is_(True)).order_by(Job.id))
        )
        groups: dict[tuple[str, str, str], list[Job]] = defaultdict(list)
        for job in active_jobs:
            key = (
                self._clean_text(job.company_name).casefold(),
                self._clean_text(job.job_title).casefold(),
                self._clean_text(job.city).casefold(),
            )
            if all(key):
                groups[key].append(job)

        merged_groups = 0
        invalidated = 0
        for candidates in groups.values():
            if len(candidates) < 2:
                continue
            winner = max(candidates, key=self._completeness_key)
            sources = sorted({job.source for job in candidates if job.source})
            merge_message = f"合并自 {','.join(sources)}"
            winner.note = self._append_note(winner.note, merge_message)
            for duplicate in candidates:
                if duplicate.id == winner.id:
                    continue
                duplicate.is_valid = False
                duplicate.note = self._append_note(
                    duplicate.note, f"已合并至岗位 #{winner.id}；{merge_message}"
                )
                invalidated += 1
            merged_groups += 1
        self.db.commit()
        return {"合并组数": merged_groups, "标记无效数": invalidated}

    def compute_quality_scores(self) -> dict[str, float | int]:
        """按照多维分档规则计算所有岗位的 0—100 数据质量分。"""

        jobs = list(self.db.scalars(select(Job)))
        today = date.today()
        for job in jobs:
            score = 0

            # 1. 薪资完整度（20分）：有上下限满分，只有下限半分
            if job.salary_min is not None and job.salary_max is not None:
                score += 20
            elif job.salary_min is not None:
                score += 10

            # 2. JD完整度（20分）：分三档，越长分越高
            jd_length = len(str(job.job_description or "").strip())
            if jd_length > 500:
                score += 20
            elif jd_length > 200:
                score += 12
            elif jd_length > 100:
                score += 6

            # 3. 技能数量（15分）：分三档，技能越多分越高
            skill_count = len(job.skills or [])
            if skill_count >= 5:
                score += 15
            elif skill_count >= 3:
                score += 10
            elif skill_count >= 1:
                score += 5

            # 4. 学历明确度（10分）
            if job.education and job.education != "不限":
                score += 10

            # 5. 经验明确度（10分）
            if job.experience and job.experience != "不限":
                score += 10

            # 6. 公司类型明确度（10分）
            if job.company_type and job.company_type != "其他":
                score += 10

            # 7. 岗位新鲜度（15分）：越新分越高
            if job.publish_date is not None:
                age_days = (today - job.publish_date).days
                if 0 <= age_days <= 30:
                    score += 15
                elif age_days <= 90:
                    score += 10
                elif age_days <= 180:
                    score += 5

            job.quality_score = score
        self.db.commit()
        average = sum(job.quality_score for job in jobs) / len(jobs) if jobs else 0.0
        return {"评分岗位数": len(jobs), "平均质量分": round(average, 2)}

    def get_stats(self) -> dict[str, Any]:
        """返回总数、有效数、各岗位类型数量和有效岗位平均质量分。"""

        total = self.db.scalar(select(func.count(Job.id))) or 0
        valid = self.db.scalar(
            select(func.count(Job.id)).where(Job.is_valid.is_(True))
        ) or 0
        type_rows = self.db.execute(
            select(Job.job_type, func.count(Job.id))
            .where(Job.is_valid.is_(True))
            .group_by(Job.job_type)
            .order_by(Job.job_type)
        ).all()
        average = self.db.scalar(
            select(func.avg(Job.quality_score)).where(Job.is_valid.is_(True))
        )
        return {
            "总数": int(total),
            "有效数": int(valid),
            "各类型数量": {str(name or "其他"): int(count) for name, count in type_rows},
            "平均质量分": round(float(average or 0), 2),
        }

    @classmethod
    def parse_salary(
        cls, salary_text: str | None
    ) -> tuple[float | None, float | None]:
        """将常见月薪、年薪描述转换成 K/月的上下限。"""

        text = cls._clean_text(salary_text).replace("／", "/")
        if not text or cls._is_negotiable(text):
            return None, None
        normalized = (
            text.replace("・", "·").replace("—", "-").replace("–", "-")
            .replace("~", "-").replace("至", "-")
        )
        annual = re.search(
            r"(?P<min>\d+(?:\.\d+)?)\s*-\s*(?P<max>\d+(?:\.\d+)?)\s*万\s*/?\s*年",
            normalized, flags=re.I,
        )
        if annual:
            factor = 10 / 12
            return (
                round(float(annual.group("min")) * factor, 2),
                round(float(annual.group("max")) * factor, 2),
            )
        range_match = re.search(
            r"(?P<min>\d+(?:\.\d+)?)\s*(?:[kK]\s*)?-\s*"
            r"(?P<max>\d+(?:\.\d+)?)\s*[kK](?:\s*/?\s*月)?",
            normalized,
        )
        if range_match:
            return float(range_match.group("min")), float(range_match.group("max"))
        above = re.search(
            r"(?P<min>\d+(?:\.\d+)?)\s*[kK]\s*(?:以上|起)", normalized
        )
        if above:
            return float(above.group("min")), None
        monthly_wan = re.search(
            r"(?P<min>\d+(?:\.\d+)?)\s*-\s*(?P<max>\d+(?:\.\d+)?)\s*万\s*/?\s*月",
            normalized,
        )
        if monthly_wan:
            return (
                float(monthly_wan.group("min")) * 10,
                float(monthly_wan.group("max")) * 10,
            )
        return None, None

    @staticmethod
    def normalize_education(value: str | None) -> str:
        """将学历文本映射为不限、大专、本科、硕士或博士。"""

        text = str(value or "").strip().casefold()
        if not text:
            return "不限"
        if any(keyword in text for keyword in ("博士", "phd")):
            return "博士"
        if any(keyword in text for keyword in ("硕士", "研究生", "master")):
            return "硕士"
        if any(keyword in text for keyword in ("本科", "学士", "bachelor")):
            return "本科"
        if any(keyword in text for keyword in ("大专", "专科", "高职")):
            return "大专"
        if any(keyword in text for keyword in ("不限", "无要求", "不要求")):
            return "不限"
        return "不限"

    @classmethod
    def extract_education(cls, text: str | None) -> str:
        """从职位标题和 JD 中提取最高优先级的明确学历层次。"""

        return cls.normalize_education(text)

    @staticmethod
    def normalize_experience(value: str | None) -> str:
        """将工作经验文本映射到六个统一档位。"""

        text = re.sub(r"\s+", "", str(value or "")).casefold()
        if not text:
            return "不限"
        if any(keyword in text for keyword in ("应届", "在校", "毕业生", "实习生")):
            return "应届"
        if re.search(r"10(?:年)?以上|十年(?:以上)?", text):
            return "10年以上"
        match = re.search(r"(\d+)\s*[-~至]\s*(\d+)年", text)
        if match:
            lower, upper = int(match.group(1)), int(match.group(2))
            if lower >= 10:
                return "10年以上"
            if lower >= 5 or upper > 5:
                return "5-10年"
            if lower >= 3 or upper > 3:
                return "3-5年"
            return "1-3年"
        single = re.search(r"(\d+)年(?:以上|经验|工作)?", text)
        if single:
            years = int(single.group(1))
            if years >= 10:
                return "10年以上"
            if years >= 5:
                return "5-10年"
            if years >= 3:
                return "3-5年"
            return "1-3年"
        if any(keyword in text for keyword in ("不限", "无要求", "不要求", "无经验")):
            return "不限"
        return "不限"

    @classmethod
    def extract_experience(cls, text: str | None) -> str:
        """从职位标题和 JD 中提取统一经验档位。"""

        return cls.normalize_experience(text)

    @staticmethod
    def normalize_company_type(value: str | None) -> str:
        """从公司性质描述中提取六类标准公司类型。"""

        text = str(value or "").casefold()
        for standard, keywords in COMPANY_TYPE_RULES:
            if any(keyword in text for keyword in keywords):
                return standard
        return "其他"

    @staticmethod
    def _contains_skill(normalized_text: str, folded_skill: str) -> bool:
        """执行技能匹配，并为英文短词添加边界以降低误报。"""

        if re.fullmatch(r"[a-z0-9+#. ]+", folded_skill):
            pattern = rf"(?<![a-z0-9+#.]){re.escape(folded_skill)}(?![a-z0-9+#.])"
            return re.search(pattern, normalized_text) is not None
        return folded_skill in normalized_text

    @staticmethod
    def _make_snapshot(job: Job) -> dict[str, Any]:
        """创建可 JSON 序列化的首次清洗快照。"""

        snapshot: dict[str, Any] = {}
        for field in SNAPSHOT_FIELDS:
            value = getattr(job, field, None)
            if isinstance(value, (date, datetime)):
                snapshot[field] = value.isoformat()
            else:
                snapshot[field] = json.loads(json.dumps(value, ensure_ascii=False))
        return snapshot

    @staticmethod
    def _normalize_district(value: str | None) -> str | None:
        """清理区县字段两侧分隔符并保留行政区后缀。"""

        district = str(value or "").strip(" \t\r\n·・•/|,，:：-")
        return district or None

    @staticmethod
    def _positive_number(value: Any) -> float | None:
        """将非负薪资转换为 float，空值、非法值和负数返回 None。"""

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number >= 0 else None

    @staticmethod
    def _salary_mid(minimum: float | None, maximum: float | None) -> float | None:
        """仅在上下限均存在时计算月薪中位估计值。"""

        if minimum is None or maximum is None:
            return None
        return round((minimum + maximum) / 2, 2)

    @staticmethod
    def _is_negotiable(value: str | None) -> bool:
        """判断薪资是否明确标注为面议。"""

        return "面议" in str(value or "")

    @staticmethod
    def _clean_text(value: Any) -> str:
        """合并多余空白并返回安全字符串。"""

        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _completeness_key(job: Job) -> tuple[int, int, int]:
        """生成重复岗位优选键：完整度、JD 长度、主键。"""

        values: Iterable[Any] = (
            job.salary_min, job.salary_max, job.salary_note, job.education,
            job.experience, job.company_type, job.district, job.publish_date,
            job.url, job.skills,
        )
        score = sum(
            1 for value in values if value not in (None, "", [], "不限", "其他")
        )
        return score, len(str(job.job_description or "")), -int(job.id or 0)

    @staticmethod
    def _append_note(existing: str | None, message: str) -> str:
        """追加不重复的审计备注。"""

        current = str(existing or "").strip()
        if not current:
            return message
        if message in current:
            return current
        return f"{current}；{message}"


# 兼容项目早期可能存在的 JobCleaner 导入，新代码应使用 DataCleaner。
JobCleaner = DataCleaner
