"""Excel、CSV、JSON 招聘数据及事业单位数据导入服务。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tqdm.auto import tqdm

from app.models import CrawlLog, Job, OfficialRecord
from app.services.cleaner import DataCleaner


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ERROR_DIR = PROJECT_ROOT / "data" / "raw" / "import_errors"
TEMPLATE_DIR = PROJECT_ROOT / "data" / "templates"


class DataImporter:
    """将外部表格或 JSON 数据安全导入当前 SQLAlchemy 数据库。"""

    COLUMN_MAPPING = {
        # 中文列名映射。
        "职位名称": "job_title", "岗位名称": "job_title",
        "公司名称": "company_name", "单位名称": "company_name",
        "城市": "city", "工作城市": "city", "工作地点": "city",
        "薪资": "salary_note", "工资": "salary_note", "薪水": "salary_note",
        "学历要求": "education", "学历": "education",
        "经验要求": "experience", "工作经验": "experience", "经验": "experience",
        "岗位类型": "job_type", "职位类型": "job_type",
        "公司类型": "company_type", "单位类型": "company_type",
        "职位描述": "job_description", "岗位描述": "job_description", "JD": "job_description",
        "技能标签": "skills", "技能要求": "skills", "技能": "skills",
        "发布日期": "publish_date", "发布时间": "publish_date",
        "来源链接": "url", "链接": "url", "URL": "url",
        "省份": "province", "省": "province",
        "区县": "district", "区": "district",
        "来源ID": "source_id", "原始ID": "source_id",
        # 英文字段同时支持大小写、空格和连字符差异。
        "job_title": "job_title", "title": "job_title",
        "company_name": "company_name", "company": "company_name",
        "city": "city", "salary": "salary_note", "salary_note": "salary_note",
        "education": "education", "experience": "experience",
        "job_type": "job_type", "company_type": "company_type",
        "job_description": "job_description", "description": "job_description",
        "skills": "skills", "publish_date": "publish_date", "url": "url",
        "province": "province", "district": "district", "source_id": "source_id",
        "salary_min": "salary_min", "salary_max": "salary_max",
        "note": "note", "is_valid": "is_valid",
    }

    OFFICIAL_COLUMN_MAPPING = {
        "单位名称": "unit_name", "unit_name": "unit_name",
        "单位级别": "unit_level", "unit_level": "unit_level",
        "省份": "province", "省": "province", "province": "province",
        "城市": "city", "city": "city",
        "岗位名称": "job_title", "职位名称": "job_title", "job_title": "job_title",
        "计划招录人数": "planned_count", "招聘人数": "planned_count",
        "planned_count": "planned_count",
        "实际拟聘人数": "actual_count", "拟聘人数": "actual_count",
        "actual_count": "actual_count",
        "专业要求": "major_requirement", "major_requirement": "major_requirement",
        "学历要求": "education", "学历": "education", "education": "education",
        "拟聘人员信息": "hired_candidates", "拟聘人员": "hired_candidates",
        "hired_candidates": "hired_candidates",
        "年份": "year", "年度": "year", "year": "year",
        "来源链接": "source_url", "链接": "source_url", "URL": "source_url",
        "source_url": "source_url",
    }

    CANDIDATE_COLUMN_MAPPING = {
        "单位名称": "unit_name", "unit_name": "unit_name",
        "岗位名称": "job_title", "职位名称": "job_title", "job_title": "job_title",
        "年份": "year", "年度": "year", "year": "year",
        "姓名": "name", "name": "name",
        "学校": "school", "毕业院校": "school", "院校": "school", "school": "school",
        "专业": "major", "所学专业": "major", "major": "major",
    }

    REQUIRED_JOB_FIELDS = ("job_title", "company_name", "city")
    REQUIRED_OFFICIAL_FIELDS = ("unit_name", "job_title", "year")

    def __init__(self, db_session: Session):
        """保存数据库会话并初始化复用的数据清洗器。"""

        self.db = db_session
        self.cleaner = DataCleaner(db_session)

    def import_from_file(
        self, file_path: str | Path, source: str = "manual", dry_run: bool = False
    ) -> dict[str, Any]:
        """从 Excel/CSV 导入岗位；dry_run=True 时只校验和预览。"""

        path = self._require_file(file_path, {".xlsx", ".xls", ".csv"})
        try:
            frame = self._read_tabular_file(path)
            return self._import_job_frame(frame, source, dry_run, path.name)
        except Exception as exc:
            self.db.rollback()
            self._record_log(source, "手动岗位导入", path.name, 0, 0, "failed", str(exc))
            raise

    def import_from_json(
        self, json_path: str | Path, source: str = "manual", dry_run: bool = False
    ) -> dict[str, Any]:
        """从字段名与 jobs 表对应的 JSON 数组导入岗位数据。"""

        path = self._require_file(json_path, {".json"})
        try:
            with path.open("r", encoding="utf-8-sig") as stream:
                payload = json.load(stream)
            if not isinstance(payload, list):
                raise ValueError("JSON 顶层必须是岗位对象数组")
            if any(not isinstance(item, dict) for item in payload):
                raise ValueError("JSON 数组中的每一项都必须是对象")
            frame = pd.DataFrame(payload)
            return self._import_job_frame(frame, source, dry_run, path.name)
        except Exception as exc:
            self.db.rollback()
            self._record_log(source, "JSON岗位导入", path.name, 0, 0, "failed", str(exc))
            raise

    def add_single(self, job_data: dict[str, Any], source: str = "manual") -> dict[str, Any]:
        """验证、清洗并添加单条岗位；重复岗位不会再次保存。"""

        if not isinstance(job_data, dict):
            raise TypeError("job_data 必须是字典")
        frame = self._normalize_columns(pd.DataFrame([job_data]))
        missing = [field for field in self.REQUIRED_JOB_FIELDS if field not in frame.columns]
        if missing:
            raise ValueError(f"缺少必填字段：{', '.join(missing)}")
        row = self._row_to_dict(frame.iloc[0])
        valid, error = self._validate_row(row)
        if not valid:
            raise ValueError(error)

        try:
            job, explicit_skills = self._build_job(row, source)
            self.cleaner.clean_one(job)
            job.skills = self._merge_skills(explicit_skills, job.skills)
            duplicate = self._find_duplicate_job(job)
            if duplicate:
                self._record_log(source, "单条手动添加", job.city, 1, 0, "skipped", "重复岗位")
                return {
                    "success": False,
                    "skipped": True,
                    "reason": "数据库中已存在相同公司、职位和城市的岗位",
                    "existing_job_id": duplicate.id,
                }

            with self.db.begin_nested():
                self.db.add(job)
                self.db.flush()
            self._record_log(source, "单条手动添加", job.city, 1, 1, "success", None, commit=False)
            self.db.commit()
            return {
                "success": True,
                "skipped": False,
                "job_id": job.id,
                "job": self._job_summary(job),
            }
        except Exception as exc:
            self.db.rollback()
            self._record_log(source, "单条手动添加", str(row.get("city", "")), 1, 0, "failed", str(exc))
            raise

    def import_official_from_file(
        self, file_path: str | Path, dry_run: bool = False
    ) -> dict[str, Any]:
        """从 Excel/CSV 导入事业单位招录记录及可选拟聘人员 Sheet。"""

        path = self._require_file(file_path, {".xlsx", ".xls", ".csv"})
        source = "official_manual"
        try:
            main_frame, candidates_frame = self._read_official_workbook(path)
            frame = self._normalize_columns(main_frame, self.OFFICIAL_COLUMN_MAPPING)
            mapping = self._mapping_report(main_frame.columns, self.OFFICIAL_COLUMN_MAPPING)
            missing = [field for field in self.REQUIRED_OFFICIAL_FIELDS if field not in frame.columns]
            if missing:
                raise ValueError(f"事业单位文件缺少必填列：{', '.join(missing)}")

            candidate_lookup = self._build_candidate_lookup(candidates_frame)
            preview = self._preview(frame)
            total = len(frame)
            success = skipped = failed = 0
            failures: list[dict[str, Any]] = []
            seen: set[tuple[str, str, int]] = set()

            for position, (_, series) in enumerate(
                tqdm(frame.iterrows(), total=total, desc="导入事业单位数据", unit="行"), start=2
            ):
                row = self._row_to_dict(series)
                try:
                    record = self._build_official_record(row, candidate_lookup)
                    key = (record.unit_name.casefold(), record.job_title.casefold(), record.year)
                    exists = self.db.scalar(
                        select(OfficialRecord.id).where(
                            func.lower(OfficialRecord.unit_name) == record.unit_name.casefold(),
                            func.lower(OfficialRecord.job_title) == record.job_title.casefold(),
                            OfficialRecord.year == record.year,
                        ).limit(1)
                    )
                    if key in seen or exists is not None:
                        skipped += 1
                        continue
                    seen.add(key)
                    if not dry_run:
                        with self.db.begin_nested():
                            self.db.add(record)
                            self.db.flush()
                    success += 1
                except Exception as exc:
                    failed += 1
                    failures.append({"row": position, "reason": str(exc), "data": row})

            error_file = self._save_error_rows(failures, "official")
            status = "dry_run" if dry_run else ("partial" if failed else "success")
            self._record_log(
                source, "事业单位手动导入", path.name, total, 0 if dry_run else success,
                status, self._failure_summary(failures), commit=False,
            )
            self.db.commit()
            return self._report(
                total, success, skipped, failed, failures, preview, mapping,
                error_file, dry_run,
            )
        except Exception as exc:
            self.db.rollback()
            self._record_log(source, "事业单位手动导入", path.name, 0, 0, "failed", str(exc))
            raise

    def generate_template(self, output_path: str | Path | None = None) -> str:
        """生成含岗位、事业单位、拟聘人员和字段说明的标准 Excel 模板。"""

        path = Path(output_path) if output_path else TEMPLATE_DIR / "岗位导入模板.xlsx"
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        job_example = pd.DataFrame([{
            "职位名称": "WebGIS 开发工程师", "公司名称": "示例地理信息公司",
            "城市": "北京·朝阳区", "薪资": "15-25K·14薪", "学历要求": "本科及以上",
            "经验要求": "3-5年", "岗位类型": "开发", "公司类型": "民营",
            "职位描述": "负责 WebGIS 平台开发，熟悉 Python、JavaScript、Leaflet 和 PostGIS。",
            "技能标签": "Python,JavaScript,Leaflet,PostGIS", "发布日期": date.today().isoformat(),
            "来源链接": "https://example.com/jobs/1", "省份": "北京", "区县": "朝阳区",
        }])
        official_example = pd.DataFrame([{
            "单位名称": "示例地理信息中心", "单位级别": "省", "省份": "陕西",
            "城市": "西安", "岗位名称": "遥感监测岗", "计划招录人数": 2,
            "实际拟聘人数": 1, "专业要求": "摄影测量与遥感、地理信息科学",
            "学历要求": "硕士", "年份": date.today().year,
            "来源链接": "https://example.gov.cn/notice/1", "拟聘人员信息": "[]",
        }])
        candidate_example = pd.DataFrame([{
            "单位名称": "示例地理信息中心", "岗位名称": "遥感监测岗",
            "年份": date.today().year, "姓名": "示例姓名", "学校": "示例大学", "专业": "遥感科学与技术",
        }])
        descriptions = pd.DataFrame([
            {"字段": "职位名称/公司名称/城市", "是否必填": "是", "说明": "岗位导入的三个唯一性判断字段"},
            {"字段": "薪资", "是否必填": "否", "说明": "支持 15-25K、15K以上、15-25万/年、面议等"},
            {"字段": "技能标签", "是否必填": "否", "说明": "可用中英文逗号、分号或空格分隔"},
            {"字段": "职位描述", "是否必填": "否", "说明": "会自动从标题和描述中提取技能"},
            {"字段": "单位名称/岗位名称/年份", "是否必填": "是", "说明": "事业单位记录的去重字段"},
            {"字段": "拟聘人员信息", "是否必填": "否", "说明": "JSON 数组；也可填入“拟聘人员”Sheet，仅保留姓名、学校、专业"},
        ])

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            job_example.to_excel(writer, sheet_name="岗位数据", index=False)
            official_example.to_excel(writer, sheet_name="事业单位数据", index=False)
            candidate_example.to_excel(writer, sheet_name="拟聘人员", index=False)
            descriptions.to_excel(writer, sheet_name="字段说明", index=False)
            self._style_workbook(writer.book)
        return str(path)

    def _normalize_columns(
        self, df: pd.DataFrame, mapping: dict[str, str] | None = None
    ) -> pd.DataFrame:
        """将 DataFrame 列名映射为标准字段，并合并映射后重名的列。"""

        selected = mapping or self.COLUMN_MAPPING
        normalized_lookup = {self._column_key(key): value for key, value in selected.items()}
        result = pd.DataFrame(index=df.index)
        for original in df.columns:
            clean_name = str(original).replace("\ufeff", "").strip()
            target = normalized_lookup.get(self._column_key(clean_name), clean_name)
            values = df[original]
            if target in result.columns:
                result[target] = result[target].combine_first(values)
            else:
                result[target] = values
        return result

    def _validate_row(self, row_data: dict[str, Any]) -> tuple[bool, str]:
        """验证岗位单行必填字段，返回“是否有效、错误信息”。"""

        missing = [
            field for field in self.REQUIRED_JOB_FIELDS
            if not self._clean_value(row_data.get(field))
        ]
        if missing:
            labels = {"job_title": "职位名称", "company_name": "公司名称", "city": "城市"}
            return False, f"缺少必填值：{', '.join(labels.get(item, item) for item in missing)}"
        return True, ""

    def _import_job_frame(
        self, frame: pd.DataFrame, source: str, dry_run: bool, origin_name: str
    ) -> dict[str, Any]:
        """执行岗位 DataFrame 的共享校验、清洗、去重和保存流程。"""

        if frame.empty:
            raise ValueError("导入文件没有数据行")
        normalized = self._normalize_columns(frame)
        mapping = self._mapping_report(frame.columns, self.COLUMN_MAPPING)
        missing = [field for field in self.REQUIRED_JOB_FIELDS if field not in normalized.columns]
        if missing:
            raise ValueError(f"文件缺少必填列：{', '.join(missing)}")

        total = len(normalized)
        success = skipped = failed = 0
        failures: list[dict[str, Any]] = []
        preview = self._preview(normalized)
        seen: set[tuple[str, str, str]] = set()

        for position, (_, series) in enumerate(
            tqdm(normalized.iterrows(), total=total, desc="导入岗位数据", unit="行"), start=2
        ):
            row = self._row_to_dict(series)
            valid, error = self._validate_row(row)
            if not valid:
                failed += 1
                failures.append({"row": position, "reason": error, "data": row})
                continue
            try:
                job, explicit_skills = self._build_job(row, source)
                self.cleaner.clean_one(job)
                job.skills = self._merge_skills(explicit_skills, job.skills)
                key = self._job_key(job)
                if key in seen or self._find_duplicate_job(job) is not None:
                    skipped += 1
                    continue
                seen.add(key)
                if not dry_run:
                    with self.db.begin_nested():
                        self.db.add(job)
                        self.db.flush()
                success += 1
            except Exception as exc:
                failed += 1
                failures.append({"row": position, "reason": str(exc), "data": row})

        error_file = self._save_error_rows(failures, "jobs")
        status = "dry_run" if dry_run else ("partial" if failed else "success")
        self._record_log(
            source, "手动岗位导入", origin_name, total, 0 if dry_run else success,
            status, self._failure_summary(failures), commit=False,
        )
        self.db.commit()
        return self._report(
            total, success, skipped, failed, failures, preview, mapping,
            error_file, dry_run,
        )

    def _build_job(self, row: dict[str, Any], source: str) -> tuple[Job, list[str]]:
        """将已验证行转换为 Job，并返回用户显式提供的技能列表。"""

        source_name = self._clean_value(source) or "manual"
        title = self._clean_value(row.get("job_title"))
        company = self._clean_value(row.get("company_name"))
        city = self._clean_value(row.get("city"))
        explicit_skills = self._parse_skills(row.get("skills"))
        source_id = self._clean_value(row.get("source_id")) or self._manual_source_id(
            source_name, company, title, city
        )
        job = Job(
            source=source_name[:32], source_id=source_id[:128],
            job_title=title, company_name=company,
            company_type=self._clean_value(row.get("company_type")) or "其他",
            city=city, province=self._clean_value(row.get("province")) or "未知",
            district=self._clean_value(row.get("district")) or None,
            salary_min=self._optional_float(row.get("salary_min")),
            salary_max=self._optional_float(row.get("salary_max")),
            salary_note=self._clean_value(row.get("salary_note")) or None,
            education=self._clean_value(row.get("education")) or "不限",
            experience=self._clean_value(row.get("experience")) or "不限",
            job_type=self._clean_value(row.get("job_type")) or "其他",
            job_description=self._clean_value(row.get("job_description")),
            skills=explicit_skills,
            publish_date=self._parse_date(row.get("publish_date")),
            crawl_date=date.today(), url=self._clean_value(row.get("url")),
            is_valid=self._parse_bool(row.get("is_valid"), default=True),
            note=self._clean_value(row.get("note")) or None,
        )
        return job, explicit_skills

    def _build_official_record(
        self,
        row: dict[str, Any],
        candidate_lookup: dict[tuple[str, str, int], list[dict[str, str]]],
    ) -> OfficialRecord:
        """将事业单位数据行转换为 ORM 记录，仅保留非敏感拟聘字段。"""

        unit = self._clean_value(row.get("unit_name"))
        title = self._clean_value(row.get("job_title"))
        year = self._optional_int(row.get("year"))
        if not unit or not title or year is None:
            raise ValueError("单位名称、岗位名称和年份均不能为空")
        inline_candidates = self._parse_candidates(row.get("hired_candidates"))
        extra_candidates = candidate_lookup.get((unit.casefold(), title.casefold(), year), [])
        candidates = self._unique_candidates([*inline_candidates, *extra_candidates])
        return OfficialRecord(
            unit_name=unit, unit_level=self._clean_value(row.get("unit_level")) or "其他",
            province=self._clean_value(row.get("province")) or "未知",
            city=self._clean_value(row.get("city")) or "未知", job_title=title,
            planned_count=self._optional_int(row.get("planned_count")),
            actual_count=self._optional_int(row.get("actual_count")),
            major_requirement=self._clean_value(row.get("major_requirement")),
            education=self.cleaner.normalize_education(self._clean_value(row.get("education"))),
            hired_candidates=candidates, year=year,
            source_url=self._clean_value(row.get("source_url")),
        )

    def _find_duplicate_job(self, job: Job) -> Job | None:
        """按公司名、职位名和标准城市名查找已有岗位。"""

        return self.db.scalar(
            select(Job).where(
                func.lower(Job.company_name) == job.company_name.casefold(),
                func.lower(Job.job_title) == job.job_title.casefold(),
                func.lower(Job.city) == job.city.casefold(),
            ).limit(1)
        )

    def _read_tabular_file(self, path: Path) -> pd.DataFrame:
        """根据扩展名读取 Excel 或自动尝试常见编码的 CSV。"""

        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        errors: list[str] = []
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError as exc:
                errors.append(str(exc))
        raise ValueError(f"CSV 编码无法识别：{'；'.join(errors)}")

    def _read_official_workbook(self, path: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        """读取事业单位主表，并自动发现可选的拟聘人员 Sheet。"""

        if path.suffix.lower() == ".csv":
            return self._read_tabular_file(path), None
        workbook = pd.ExcelFile(path)
        main_sheet = next(
            (name for name in workbook.sheet_names if "事业" in name or "招录" in name),
            workbook.sheet_names[0],
        )
        candidate_sheet = next(
            (name for name in workbook.sheet_names if "拟聘" in name or "人员" in name), None
        )
        main = pd.read_excel(workbook, sheet_name=main_sheet)
        candidates = pd.read_excel(workbook, sheet_name=candidate_sheet) if candidate_sheet else None
        return main, candidates

    def _build_candidate_lookup(
        self, frame: pd.DataFrame | None
    ) -> dict[tuple[str, str, int], list[dict[str, str]]]:
        """将拟聘人员 Sheet 转换为按单位、岗位、年份索引的安全字段字典。"""

        result: dict[tuple[str, str, int], list[dict[str, str]]] = {}
        if frame is None or frame.empty:
            return result
        normalized = self._normalize_columns(frame, self.CANDIDATE_COLUMN_MAPPING)
        required = {"unit_name", "job_title", "year"}
        if not required.issubset(normalized.columns):
            return result
        for _, series in normalized.iterrows():
            row = self._row_to_dict(series)
            unit = self._clean_value(row.get("unit_name"))
            title = self._clean_value(row.get("job_title"))
            year = self._optional_int(row.get("year"))
            if not unit or not title or year is None:
                continue
            candidate = {
                "name": self._clean_value(row.get("name")),
                "school": self._clean_value(row.get("school")),
                "major": self._clean_value(row.get("major")),
            }
            if any(candidate.values()):
                result.setdefault((unit.casefold(), title.casefold(), year), []).append(candidate)
        return result

    def _parse_candidates(self, value: Any) -> list[dict[str, str]]:
        """解析 JSON 拟聘人员列，并丢弃姓名、学校、专业之外的字段。"""

        if self._is_empty(value):
            return []
        payload = value
        if isinstance(value, str):
            try:
                payload = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("拟聘人员信息必须是合法 JSON 数组") from exc
        if not isinstance(payload, list):
            raise ValueError("拟聘人员信息必须是 JSON 数组")
        result: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            candidate = {
                "name": self._clean_value(item.get("name", item.get("姓名"))),
                "school": self._clean_value(item.get("school", item.get("学校"))),
                "major": self._clean_value(item.get("major", item.get("专业"))),
            }
            if any(candidate.values()):
                result.append(candidate)
        return result

    def _record_log(
        self, source: str, keyword: str, city: str, total: int, new: int,
        status: str, error: str | None, commit: bool = True,
    ) -> None:
        """写入 crawl_logs；日志失败不掩盖原始导入结果。"""

        try:
            self.db.add(CrawlLog(
                source=(self._clean_value(source) or "manual")[:32],
                keyword=keyword[:128], city=self._clean_value(city)[:64],
                total_fetched=int(total), total_new=int(new), status=status[:32],
                error_msg=error,
            ))
            if commit:
                self.db.commit()
        except Exception:
            self.db.rollback()

    def _save_error_rows(self, failures: list[dict[str, Any]], prefix: str) -> str | None:
        """把失败行及原因保存为 UTF-8 CSV，返回绝对路径。"""

        if not failures:
            return None
        ERROR_DIR.mkdir(parents=True, exist_ok=True)
        path = ERROR_DIR / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
        flat_rows: list[dict[str, Any]] = []
        for failure in failures:
            data = dict(failure.get("data") or {})
            flat_rows.append({"原始行号": failure.get("row"), "失败原因": failure.get("reason"), **data})
        pd.DataFrame(flat_rows).to_csv(path, index=False, encoding="utf-8-sig")
        return str(path.resolve())

    @classmethod
    def _parse_skills(cls, value: Any) -> list[str]:
        """将数组或逗号、分号、空格分隔文本解析为去重技能列表。"""

        if cls._is_empty(value):
            return []
        if isinstance(value, (list, tuple, set)):
            parts: Iterable[Any] = value
        else:
            text = str(value).strip()
            if text.startswith("["):
                try:
                    decoded = json.loads(text)
                    parts = decoded if isinstance(decoded, list) else [text]
                except json.JSONDecodeError:
                    parts = re.split(r"[,，;；\s]+", text)
            else:
                parts = re.split(r"[,，;；\s]+", text)
        result: list[str] = []
        seen: set[str] = set()
        for part in parts:
            skill = cls._clean_value(part)
            folded = skill.casefold()
            if skill and folded not in seen:
                result.append(skill)
                seen.add(folded)
        return result

    @staticmethod
    def _merge_skills(primary: list[str], secondary: list[str]) -> list[str]:
        """按显式技能优先顺序合并清洗器提取结果。"""

        result: list[str] = []
        seen: set[str] = set()
        for skill in [*primary, *secondary]:
            folded = str(skill).casefold()
            if folded and folded not in seen:
                result.append(str(skill))
                seen.add(folded)
        return result

    @staticmethod
    def _manual_source_id(source: str, company: str, title: str, city: str) -> str:
        """根据稳定业务键生成可重复的手工导入 source_id。"""

        raw = "|".join((source.casefold(), company.casefold(), title.casefold(), city.casefold()))
        return f"manual-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"

    @classmethod
    def _parse_date(cls, value: Any) -> date | None:
        """兼容日期对象、Excel 时间和常见日期字符串。"""

        if cls._is_empty(value):
            return None
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"发布日期无法解析：{value}")
        return parsed.date()

    @classmethod
    def _optional_int(cls, value: Any) -> int | None:
        """从数字或“2人”等文本中提取非负整数。"""

        if cls._is_empty(value):
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if not match:
            return None
        number = int(float(match.group()))
        return number if number >= 0 else None

    @classmethod
    def _optional_float(cls, value: Any) -> float | None:
        """安全解析可空浮点值。"""

        if cls._is_empty(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"数值无法解析：{value}") from exc

    @classmethod
    def _parse_bool(cls, value: Any, default: bool = True) -> bool:
        """将中英文真假值转换为布尔值。"""

        if cls._is_empty(value):
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().casefold()
        if text in {"0", "false", "否", "无效", "n", "no"}:
            return False
        if text in {"1", "true", "是", "有效", "y", "yes"}:
            return True
        return default

    @classmethod
    def _row_to_dict(cls, row: pd.Series) -> dict[str, Any]:
        """把 pandas 行转换为可序列化字典并清除 NaN/NaT。"""

        result: dict[str, Any] = {}
        for key, value in row.items():
            if cls._is_empty(value):
                result[str(key)] = None
            elif isinstance(value, (pd.Timestamp, datetime, date)):
                result[str(key)] = value.isoformat()
            else:
                result[str(key)] = value.item() if hasattr(value, "item") else value
        return result

    @classmethod
    def _preview(cls, frame: pd.DataFrame) -> list[dict[str, Any]]:
        """返回前五行 JSON 安全预览。"""

        return [cls._row_to_dict(row) for _, row in frame.head(5).iterrows()]

    @classmethod
    def _mapping_report(
        cls, columns: Iterable[Any], mapping: dict[str, str]
    ) -> dict[str, str]:
        """返回原始列到标准字段的映射，便于导入前人工确认。"""

        lookup = {cls._column_key(key): value for key, value in mapping.items()}
        return {
            str(column): lookup.get(cls._column_key(str(column)), str(column).strip())
            for column in columns
        }

    @staticmethod
    def _column_key(value: Any) -> str:
        """标准化列名以支持大小写、空格和连字符差异。"""

        return re.sub(r"[\s\-]+", "_", str(value).replace("\ufeff", "").strip()).casefold()

    @classmethod
    def _clean_value(cls, value: Any) -> str:
        """将空值转换为空字符串并合并多余空白。"""

        if cls._is_empty(value):
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _is_empty(value: Any) -> bool:
        """判断 None、NaN、NaT 和空字符串。"""

        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        try:
            result = pd.isna(value)
            return bool(result) if not isinstance(result, (list, tuple)) else False
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _require_file(file_path: str | Path, allowed: set[str]) -> Path:
        """验证输入文件存在且扩展名受支持。"""

        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在：{path}")
        if path.suffix.lower() not in allowed:
            raise ValueError(f"不支持的文件格式：{path.suffix}")
        return path

    @staticmethod
    def _job_key(job: Job) -> tuple[str, str, str]:
        """返回岗位跨来源去重键。"""

        return job.company_name.casefold(), job.job_title.casefold(), job.city.casefold()

    @staticmethod
    def _unique_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        """按姓名、学校、专业组合去除重复拟聘人员。"""

        result: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidates:
            key = tuple(str(candidate.get(field, "")).casefold() for field in ("name", "school", "major"))
            if key not in seen:
                result.append(candidate)
                seen.add(key)
        return result

    @staticmethod
    def _failure_summary(failures: list[dict[str, Any]]) -> str | None:
        """生成适合 crawl_logs 的简短失败摘要。"""

        if not failures:
            return None
        samples = [f"第{item['row']}行：{item['reason']}" for item in failures[:10]]
        suffix = f"；另有{len(failures) - 10}条" if len(failures) > 10 else ""
        return "；".join(samples) + suffix

    @staticmethod
    def _report(
        total: int, success: int, skipped: int, failed: int,
        failures: list[dict[str, Any]], preview: list[dict[str, Any]],
        mapping: dict[str, str], error_file: str | None, dry_run: bool,
    ) -> dict[str, Any]:
        """构造统一导入统计结果。"""

        return {
            "total": total, "success": success, "skipped": skipped,
            "failed": failed, "dry_run": dry_run,
            "message": "预览完成，未写入业务数据" if dry_run else "导入完成",
            "column_mapping": mapping, "preview": preview,
            "failures": failures, "error_file": error_file,
        }

    @staticmethod
    def _job_summary(job: Job) -> dict[str, Any]:
        """返回适合命令行确认的岗位摘要。"""

        return {
            "job_title": job.job_title, "company_name": job.company_name,
            "city": job.city, "province": job.province, "district": job.district,
            "salary_min": job.salary_min, "salary_max": job.salary_max,
            "education": job.education, "experience": job.experience,
            "job_type": job.job_type, "skills": job.skills,
        }

    @staticmethod
    def _style_workbook(workbook: Any) -> None:
        """为模板添加表头、筛选、冻结窗格和易读列宽。"""

        from openpyxl.styles import Alignment, Font, PatternFill

        fill = PatternFill("solid", fgColor="2C5F8F")
        font = Font(color="FFFFFF", bold=True)
        for sheet in workbook.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.fill = fill
                cell.font = font
                cell.alignment = Alignment(horizontal="center")
            for column_cells in sheet.columns:
                letter = column_cells[0].column_letter
                width = max(len(str(cell.value or "")) for cell in column_cells[:20]) + 2
                sheet.column_dimensions[letter].width = min(max(width, 12), 40)
