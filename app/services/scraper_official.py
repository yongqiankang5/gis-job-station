"""公开政府网站 GIS、遥感与测绘事业单位招录数据采集器。"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
import warnings
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from app.models import CrawlLog, OfficialRecord
from app.utils.keywords import JOB_KEYWORDS, MAJOR_KEYWORDS
from app.utils.province_sites import PROVINCE_SITES, ProvinceSiteConfig

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_OFFICIAL_DIR = PROJECT_ROOT / "data" / "raw" / "official"

MNR_CONFIG: dict[str, Any] = {
    "name": "自然资源部",
    "list_url": "https://www.mnr.gov.cn/gk/tzgg/",
    "item_selector": ".list li a, .main_list li a, .contentList li a, li a[href]",
    "next_page": {
        "type": "selector",
        "selector": "a[title*='下一页'], a.next, .pagination a.next",
        "max_pages": 6,
    },
}

MOHRSS_CONFIG: dict[str, Any] = {
    "name": "人力资源和社会保障部事业单位招聘专栏",
    "list_url": (
        "https://www.mohrss.gov.cn/SYrlzyhshbzb/fwyd/SYkaoshizhaopin/"
        "zyhgjjgsydwgkzp/"
    ),
    "item_selector": ".serviceMainList li a, .list li a, .news-list li a, li a[href]",
    "next_page": {
        "type": "selector",
        "selector": "a[title*='下一页'], a.next, .pagination a.next",
        "max_pages": 8,
    },
}

DISCOVERY_KEYWORDS = ("招聘", "招录", "拟聘", "公示", "录用", "事业单位")
EMPLOYMENT_KEYWORDS = ("招聘", "招录", "拟聘", "聘用", "录用", "事业单位")
UNIT_KEYWORDS = (
    "测绘",
    "地理信息",
    "遥感",
    "地图",
    "自然资源",
    "地质调查",
    "海洋",
    "规划院",
    "勘测",
    "国土",
    "空间信息",
    "卫星",
)
GEO_KEYWORDS = tuple(
    dict.fromkeys((*UNIT_KEYWORDS, *JOB_KEYWORDS, *MAJOR_KEYWORDS, "GIS", "地质"))
)

# 省级来源缺少明确城市字段时使用省会作为保守的默认工作地。
PROVINCE_CAPITALS = {
    "陕西": "西安",
    "湖北": "武汉",
    "四川": "成都",
    "广东": "广州",
    "浙江": "杭州",
    "江苏": "南京",
    "北京": "北京",
    "山东": "济南",
}

JOB_COLUMN_ALIASES = {
    "unit": ("招聘单位", "用人单位", "单位名称", "单位", "部门名称"),
    "job": ("招聘岗位", "岗位名称", "职位名称", "岗位", "职位"),
    "count": ("招聘人数", "计划人数", "招聘数量", "需求人数", "人数", "名额"),
    "major": ("专业要求", "所需专业", "专业", "学科专业", "专业条件"),
    "education": ("学历要求", "学历学位", "学历/学位", "学历", "学位"),
    "city": ("工作地点", "所在地", "城市", "地区"),
}

HIRED_COLUMN_ALIASES = {
    "unit": ("招聘单位", "聘用单位", "用人单位", "单位名称", "单位"),
    "job": ("招聘岗位", "拟聘岗位", "岗位名称", "职位名称", "岗位", "职位"),
    "name": ("姓名", "拟聘人员", "拟聘人选", "拟录用人员", "拟聘用人员"),
    "school": ("毕业院校", "毕业学校", "学校", "院校"),
    "major": ("所学专业", "毕业专业", "专业"),
    "education": ("学历学位", "学历/学位", "学历", "学位"),
    "city": ("工作地点", "所在地", "城市", "地区"),
}


class OfficialScraper:
    """以低频请求采集公开政府页面中的事业单位招录表格。"""

    def __init__(self, db_session: Session) -> None:
        """初始化数据库会话、HTTP 会话和公开页面请求头。"""

        self.db = db_session
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36 GISJobTracker/0.1"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._last_request_at = 0.0
        self._current_context: dict[str, Any] = {}

    def crawl_all(
        self, years: Sequence[int] = (2024, 2025, 2026)
    ) -> dict[str, Any]:
        """采集自然资源部、人社部和全部已配置省级数据源。"""

        normalized_years = self._normalize_years(years)
        summary = self._empty_summary()
        summary["sources"] = {}

        source_tasks = [
            ("mnr", lambda: self.crawl_mnr(normalized_years)),
            ("mohrss", lambda: self.crawl_mohrss(normalized_years)),
        ]
        source_tasks.extend(
            (
                f"province:{province}",
                lambda province=province, config=config: self.crawl_province(
                    province,
                    config["list_url"],
                    normalized_years,
                ),
            )
            for province, config in PROVINCE_SITES.items()
        )

        for source_key, task in source_tasks:
            try:
                result = task()
            except Exception as exc:
                logger.exception("来源 %s 采集失败", source_key)
                self._write_log(
                    source=source_key,
                    keyword="source",
                    city="-",
                    total_fetched=0,
                    total_new=0,
                    status="failed",
                    error_msg=f"{type(exc).__name__}: {exc}",
                )
                result = self._empty_summary()
                result["errors"] = 1
            summary["sources"][source_key] = result
            self._merge_summary(summary, result)
        return summary

    def crawl_mnr(self, years: Sequence[int]) -> dict[str, int]:
        """采集自然资源部通知公告栏目。"""

        return self._crawl_site(
            config=MNR_CONFIG,
            years=self._normalize_years(years),
            source_key="official_mnr",
            province="北京",
            city="北京",
            unit_level="中央",
            require_geo_in_title=False,
        )

    def crawl_mohrss(self, years: Sequence[int]) -> dict[str, int]:
        """采集人社部中央和国家机关事业单位招聘专栏。"""

        return self._crawl_site(
            config=MOHRSS_CONFIG,
            years=self._normalize_years(years),
            source_key="official_mohrss",
            province="北京",
            city="北京",
            unit_level="中央",
            # 人社部栏目覆盖各行业，只保留标题中包含自然资源相关信号的文章。
            require_geo_in_title=True,
        )

    def crawl_province(
        self,
        province_name: str,
        list_url: str,
        years: Sequence[int],
    ) -> dict[str, int]:
        """使用省厅配置的通用模板采集单个省自然资源厅。"""

        if province_name not in PROVINCE_SITES:
            raise ValueError(f"未配置省份：{province_name}")
        config: dict[str, Any] = dict(PROVINCE_SITES[province_name])
        config["list_url"] = list_url
        return self._crawl_site(
            config=config,
            years=self._normalize_years(years),
            source_key=f"official_{province_name}",
            province=province_name,
            city=PROVINCE_CAPITALS.get(province_name, province_name),
            unit_level="省",
            require_geo_in_title=False,
        )

    def _crawl_site(
        self,
        config: dict[str, Any],
        years: tuple[int, ...],
        source_key: str,
        province: str,
        city: str,
        unit_level: str,
        require_geo_in_title: bool,
    ) -> dict[str, int]:
        """完成一个站点的列表发现、详情解析、保存和日志记录。"""

        result = self._empty_summary()
        try:
            articles = self._discover_articles(config, years, require_geo_in_title)
            result["discovered"] = len(articles)
        except Exception as exc:
            self._write_log(
                source=source_key,
                keyword="list",
                city=city,
                total_fetched=0,
                total_new=0,
                status="failed",
                error_msg=f"列表页发现失败：{type(exc).__name__}: {exc}",
            )
            raise

        for article in articles:
            try:
                article_result = self._process_article(
                    article=article,
                    source_key=source_key,
                    province=province,
                    city=city,
                    unit_level=unit_level,
                    source_name=str(
                        config.get("name")
                        or config.get("agency_name")
                        or f"{province}自然资源主管部门"
                    ),
                )
                result["visited"] += 1
                result["tables"] += article_result["tables"]
                result["records"] += article_result["records"]
                result["new"] += article_result["new"]
                result["updated"] += article_result["updated"]
            except Exception as exc:
                result["errors"] += 1
                logger.exception("解析政府文章失败：%s", article["url"])
                self._write_log(
                    source=source_key,
                    keyword=str(article["title"])[:128],
                    city=city,
                    total_fetched=0,
                    total_new=0,
                    status="failed",
                    error_msg=f"{article['url']} | {type(exc).__name__}: {exc}",
                )

        self._write_log(
            source=source_key,
            keyword="summary",
            city=city,
            total_fetched=result["records"],
            total_new=result["new"],
            status="success" if result["errors"] == 0 else "partial",
            error_msg=(f"{result['errors']} 篇文章解析失败" if result["errors"] else None),
        )
        return result

    def _discover_articles(
        self,
        config: dict[str, Any],
        years: tuple[int, ...],
        require_geo_in_title: bool,
    ) -> list[dict[str, Any]]:
        """遍历栏目分页并发现指定年份的潜在招聘或拟聘文章。"""

        current_url = str(config["list_url"])
        selector = str(config.get("item_selector") or "a[href]")
        next_rule = config.get("next_page") or {}
        max_pages = max(1, int(next_rule.get("max_pages", 5)))
        visited_pages: set[str] = set()
        found: dict[str, dict[str, Any]] = {}

        for _ in range(max_pages):
            if current_url in visited_pages:
                break
            visited_pages.add(current_url)
            soup = self._fetch_page(current_url)
            anchors = soup.select(selector)
            if not anchors:
                anchors = soup.select("a[href]")

            for anchor in anchors:
                if not isinstance(anchor, Tag):
                    continue
                title = self._clean_text(anchor.get("title") or anchor.get_text(" "))
                href = str(anchor.get("href") or "").strip()
                if not title or not href:
                    continue
                article_url = urljoin(current_url, href)
                if not self._is_html_page(article_url):
                    continue
                context_text = self._clean_text(
                    anchor.parent.get_text(" ") if anchor.parent else title
                )
                year = self._extract_year(f"{title} {context_text} {article_url}")
                if year not in years:
                    continue
                if not self._is_recruitment_title(title):
                    continue
                if require_geo_in_title and not self._contains_geo_keyword(title):
                    continue
                found[article_url] = {
                    "title": title,
                    "url": article_url,
                    "year": year,
                }

            next_url = self._find_next_page(soup, current_url, next_rule)
            if not next_url or next_url in visited_pages:
                break
            current_url = next_url

        return list(found.values())

    def _process_article(
        self,
        article: dict[str, Any],
        source_key: str,
        province: str,
        city: str,
        unit_level: str,
        source_name: str,
    ) -> dict[str, int]:
        """解析单篇详情页表格并保存招聘或拟聘记录。"""

        soup = self._fetch_page(str(article["url"]))
        title = str(article["title"])
        year = int(article["year"])
        unit_name = self._infer_unit_name(title, soup, source_name)
        self._current_context = {
            "source_key": source_key,
            "source_url": article["url"],
            "province": province,
            "city": city,
            "unit_level": unit_level,
            "title": title,
        }
        tables = self._extract_tables(soup)
        parsed_records: list[dict[str, Any]] = []
        is_hired_notice = self._is_hired_notice(title)

        for frame in tables:
            if is_hired_notice:
                parsed_records.extend(self._parse_hired_table(frame, unit_name, year))
            else:
                parsed_records.extend(self._parse_job_table(frame, unit_name, year))

        saved = self._save_records(parsed_records)
        return {
            "tables": len(tables),
            "records": len(parsed_records),
            "new": saved["new"],
            "updated": saved["updated"],
        }

    def _fetch_page(self, url: str) -> BeautifulSoup:
        """礼貌请求页面、归档脱敏摘要并返回 BeautifulSoup 对象。"""

        self._polite_wait()
        response = self.session.get(url, timeout=(10, 30), allow_redirects=True)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        html = response.text
        self._last_request_at = time.monotonic()
        self._archive_page(response.url, html)
        return BeautifulSoup(html, "lxml")

    def _extract_tables(self, soup: BeautifulSoup) -> list[pd.DataFrame]:
        """从详情页正文提取所有 HTML 表格并返回 DataFrame 列表。"""

        content = self._find_article_content(soup)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                frames = pd.read_html(StringIO(str(content)), flavor="lxml")
        except ValueError:
            return []
        return [self._normalize_dataframe(frame) for frame in frames if not frame.empty]

    def _parse_job_table(
        self, df: pd.DataFrame, unit_name: str, year: int
    ) -> list[dict[str, Any]]:
        """解析招聘公告岗位表，返回适合 official_records 的记录列表。"""

        frame = self._normalize_dataframe(df)
        columns = {
            key: self._find_column(frame, aliases)
            for key, aliases in JOB_COLUMN_ALIASES.items()
        }
        if columns["job"] is None and columns["major"] is None:
            return []

        records: list[dict[str, Any]] = []
        for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
            row_unit = self._cell_text(row.get(columns["unit"])) if columns["unit"] else ""
            row_job = self._cell_text(row.get(columns["job"])) if columns["job"] else ""
            major = (
                self._cell_text(row.get(columns["major"]), preserve_whitespace=True)
                if columns["major"]
                else ""
            )
            effective_unit = row_unit or unit_name
            if not row_job and not major:
                continue
            if not self._row_is_geo_related(effective_unit, row_job, major):
                continue

            count_text = (
                self._cell_text(row.get(columns["count"])) if columns["count"] else ""
            )
            planned_count = self._parse_count(count_text)
            if planned_count is None:
                logger.warning(
                    "无法解析计划人数：url=%s table_row=%s raw=%r",
                    self._current_context.get("source_url"),
                    row_number,
                    count_text,
                )
            education = (
                self._cell_text(row.get(columns["education"]))
                if columns["education"]
                else "不限"
            )
            row_city = (
                self._cell_text(row.get(columns["city"])) if columns["city"] else ""
            )
            records.append(
                self._build_record(
                    unit_name=effective_unit,
                    job_title=row_job or "专业技术岗位",
                    year=year,
                    planned_count=planned_count,
                    actual_count=None,
                    major_requirement=major,
                    education=education or "不限",
                    hired_candidates=[],
                    city=row_city or None,
                )
            )
        return records

    def _parse_hired_table(
        self, df: pd.DataFrame, unit_name: str, year: int
    ) -> list[dict[str, Any]]:
        """解析拟聘表，仅保留姓名、学校和专业并生成可更新记录。"""

        frame = self._normalize_dataframe(df)
        columns = {
            key: self._find_column(frame, aliases)
            for key, aliases in HIRED_COLUMN_ALIASES.items()
        }
        if columns["name"] is None:
            return []

        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for _, row in frame.iterrows():
            candidate_name = self._safe_candidate_value(row.get(columns["name"]))
            # 若姓名单元格混入身份证或手机号，脱敏后只留下姓名文本本身。
            candidate_name = re.sub(
                r"\[已脱敏(?:身份证|手机号|邮箱)\]", "", candidate_name or ""
            ).strip(" ,，;；")
            if not candidate_name:
                continue
            row_unit = self._cell_text(row.get(columns["unit"])) if columns["unit"] else ""
            row_job = self._cell_text(row.get(columns["job"])) if columns["job"] else ""
            school = (
                self._safe_candidate_value(row.get(columns["school"]))
                if columns["school"]
                else None
            )
            major = (
                self._safe_candidate_value(row.get(columns["major"]))
                if columns["major"]
                else None
            )
            education = (
                self._cell_text(row.get(columns["education"]))
                if columns["education"]
                else "不限"
            )
            effective_unit = row_unit or unit_name
            effective_job = row_job or "拟聘人员"
            if not self._row_is_geo_related(effective_unit, effective_job, major or ""):
                continue

            key = (effective_unit, effective_job)
            if key not in grouped:
                row_city = (
                    self._cell_text(row.get(columns["city"]))
                    if columns["city"]
                    else ""
                )
                grouped[key] = self._build_record(
                    unit_name=effective_unit,
                    job_title=effective_job,
                    year=year,
                    planned_count=None,
                    actual_count=0,
                    major_requirement="",
                    education=education or "不限",
                    hired_candidates=[],
                    city=row_city or None,
                )
            candidate = {"name": candidate_name, "school": school, "major": major}
            if candidate not in grouped[key]["hired_candidates"]:
                grouped[key]["hired_candidates"].append(candidate)

        for record in grouped.values():
            record["actual_count"] = len(record["hired_candidates"])
        return list(grouped.values())

    def _match_unit(self, unit_name: str) -> bool:
        """模糊判断单位名是否与 GIS、遥感、测绘或自然资源相关。"""

        clean_name = self._clean_text(unit_name).casefold()
        return any(keyword.casefold() in clean_name for keyword in UNIT_KEYWORDS)

    def _save_records(self, records: list[dict[str, Any]]) -> dict[str, int]:
        """按单位名、岗位名和年份去重保存，已存在记录执行安全合并。"""

        merged: dict[tuple[str, str, int], dict[str, Any]] = {}
        for record in records:
            key = (
                str(record["unit_name"]),
                str(record["job_title"]),
                int(record["year"]),
            )
            if key not in merged:
                merged[key] = dict(record)
                merged[key]["hired_candidates"] = list(record.get("hired_candidates") or [])
                continue
            current = merged[key]
            if record.get("planned_count") is not None:
                current["planned_count"] = record["planned_count"]
            if record.get("actual_count") is not None:
                current["actual_count"] = record["actual_count"]
            for candidate in record.get("hired_candidates") or []:
                if candidate not in current["hired_candidates"]:
                    current["hired_candidates"].append(candidate)

        new_count = 0
        updated_count = 0
        try:
            for (unit_name, job_title, year), values in merged.items():
                existing = self.db.scalar(
                    select(OfficialRecord).where(
                        OfficialRecord.unit_name == unit_name,
                        OfficialRecord.job_title == job_title,
                        OfficialRecord.year == year,
                    )
                )
                if existing is None:
                    self.db.add(OfficialRecord(**values))
                    new_count += 1
                    continue

                # 招聘表和拟聘表可能分批到达：空值不覆盖先前已经解析出的信息。
                for field in (
                    "unit_level",
                    "province",
                    "city",
                    "major_requirement",
                    "education",
                    "source_url",
                ):
                    if values.get(field) not in (None, ""):
                        setattr(existing, field, values[field])
                if values.get("planned_count") is not None:
                    existing.planned_count = values["planned_count"]
                if values.get("actual_count") is not None:
                    existing.actual_count = values["actual_count"]
                incoming_candidates = values.get("hired_candidates") or []
                if incoming_candidates:
                    existing.hired_candidates = self._merge_candidates(
                        existing.hired_candidates or [], incoming_candidates
                    )
                updated_count += 1
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"new": new_count, "updated": updated_count}

    def _build_record(
        self,
        unit_name: str,
        job_title: str,
        year: int,
        planned_count: int | None,
        actual_count: int | None,
        major_requirement: str,
        education: str,
        hired_candidates: list[dict[str, str | None]],
        city: str | None,
    ) -> dict[str, Any]:
        """结合当前文章上下文构造一条标准事业单位记录。"""

        context = self._current_context
        return {
            "unit_name": self._clean_text(unit_name) or "未知单位",
            "unit_level": str(context.get("unit_level") or "省"),
            "province": str(context.get("province") or "未知"),
            "city": self._clean_text(city or context.get("city") or "未知"),
            "job_title": self._clean_text(job_title) or "未命名岗位",
            # 专业要求保留表格原文，仅去除首尾空白。
            "planned_count": planned_count,
            "actual_count": actual_count,
            "major_requirement": str(major_requirement or "").strip(),
            "education": self._clean_text(education) or "不限",
            "hired_candidates": hired_candidates,
            "year": year,
            "source_url": str(context.get("source_url") or ""),
        }

    def _find_next_page(
        self,
        soup: BeautifulSoup,
        current_url: str,
        next_rule: dict[str, Any],
    ) -> str | None:
        """按配置选择器及可见文字寻找下一页链接。"""

        selector = str(next_rule.get("selector") or "")
        candidate: Tag | None = soup.select_one(selector) if selector else None
        if candidate is None:
            for anchor in soup.select("a[href]"):
                text = self._clean_text(anchor.get_text(" "))
                title = self._clean_text(anchor.get("title") or "")
                if text in {"下一页", "下页", ">", "›"} or "下一页" in title:
                    candidate = anchor
                    break
        if candidate is None:
            return None
        href = str(candidate.get("href") or "").strip()
        if not href or href.lower().startswith("javascript:"):
            return None
        return urljoin(current_url, href)

    def _find_article_content(self, soup: BeautifulSoup) -> Tag | BeautifulSoup:
        """从常见政府网站正文容器中选择最合适的内容节点。"""

        selectors = (
            "article",
            ".TRS_Editor",
            ".article-content",
            ".article_content",
            ".pages_content",
            ".content-body",
            "#zoom",
            "#UCAP-CONTENT",
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if isinstance(node, Tag) and (node.find("table") or len(node.get_text()) > 100):
                return node
        return soup

    def _infer_unit_name(
        self, title: str, soup: BeautifulSoup, source_name: str
    ) -> str:
        """从公告标题推断发布或招聘单位名称。"""

        clean_title = self._clean_text(title).lstrip("关于")
        prefixes = re.split(
            r"(?:20\d{2}年(?:度)?|公开招聘|招聘工作人员|拟聘(?:用)?人员|拟录用人员)",
            clean_title,
            maxsplit=1,
        )
        candidate = prefixes[0].strip(" ：:，,《》") if prefixes else ""
        if len(candidate) >= 4 and self._match_unit(candidate):
            return candidate

        # 部分详情页在正文首段重复写明单位，取前 300 字做保守匹配。
        opening = self._clean_text(self._find_article_content(soup).get_text(" "))[:300]
        unit_match = re.search(
            r"([\u4e00-\u9fff]{2,30}(?:院|中心|局|厅|所|站|馆|部))",
            opening,
        )
        if unit_match and self._match_unit(unit_match.group(1)):
            return unit_match.group(1)
        return source_name

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """扁平化多层表头并清除全空行列。"""

        frame = df.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            flattened = []
            for column in frame.columns:
                parts = [
                    str(part).strip()
                    for part in column
                    if str(part).strip() and not str(part).startswith("Unnamed")
                ]
                flattened.append(" ".join(dict.fromkeys(parts)))
            frame.columns = flattened
        else:
            frame.columns = [
                "" if str(column).startswith("Unnamed") else str(column).strip()
                for column in frame.columns
            ]
        return frame.dropna(axis=0, how="all").dropna(axis=1, how="all")

    @classmethod
    def _find_column(
        cls, frame: pd.DataFrame, aliases: Iterable[str]
    ) -> str | None:
        """按常见字段别名在 DataFrame 中查找最匹配的列。"""

        normalized_aliases = [(alias, cls._normalize_header(alias)) for alias in aliases]
        columns = [(str(column), cls._normalize_header(str(column))) for column in frame.columns]
        for _, alias in normalized_aliases:
            for original, normalized in columns:
                if normalized == alias:
                    return original
        for _, alias in normalized_aliases:
            for original, normalized in columns:
                if alias and (alias in normalized or normalized in alias):
                    return original
        return None

    @staticmethod
    def _normalize_header(value: str) -> str:
        """移除表头中的空白和常见标点以增强别名匹配。"""

        return re.sub(r"[\s/\-_（）()]+", "", value).casefold()

    @staticmethod
    def _cell_text(value: Any, preserve_whitespace: bool = False) -> str:
        """安全读取表格单元格；专业原文可选择不压缩内部空白。"""

        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        return text if preserve_whitespace else re.sub(r"\s+", " ", text)

    @staticmethod
    def _parse_count(value: str) -> int | None:
        """从“2名”“计划3人”等文本解析非负招聘人数。"""

        match = re.search(r"\d+", str(value or ""))
        return int(match.group()) if match else None

    def _row_is_geo_related(self, unit: str, job: str, major: str) -> bool:
        """判断表格行的单位、岗位或专业是否属于目标领域。"""

        if self._match_unit(unit):
            return True
        return self._contains_geo_keyword(f"{job} {major}")

    @staticmethod
    def _contains_geo_keyword(text: str) -> bool:
        """判断文本是否包含 GIS、遥感、测绘或自然资源关键词。"""

        folded = str(text or "").casefold()
        return any(keyword.casefold() in folded for keyword in GEO_KEYWORDS)

    @staticmethod
    def _is_recruitment_title(title: str) -> bool:
        """过滤普通业务公示，只保留招聘、拟聘或人员录用类标题。"""

        if not any(keyword in title for keyword in DISCOVERY_KEYWORDS):
            return False
        if any(keyword in title for keyword in EMPLOYMENT_KEYWORDS):
            return True
        return "公示" in title and any(word in title for word in ("人员", "人选", "聘"))

    @staticmethod
    def _is_hired_notice(title: str) -> bool:
        """判断文章是否属于拟聘或拟录用人员公示。"""

        return any(
            signal in title
            for signal in ("拟聘", "拟录用", "拟聘用", "录用人员公示", "聘用人员公示")
        )

    @staticmethod
    def _extract_year(text: str) -> int | None:
        """从标题、上下文或 URL 中提取四位年份。"""

        match = re.search(r"(?<!\d)(20\d{2})(?!\d)", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _is_html_page(url: str) -> bool:
        """排除 PDF、Office、图片和压缩包等非 HTML 附件链接。"""

        path = urlparse(url).path.casefold()
        excluded = (
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar",
            ".jpg", ".jpeg", ".png", ".gif",
        )
        return not path.endswith(excluded)

    def _archive_page(self, url: str, html: str) -> None:
        """保存 URL、内容哈希及脱敏 HTML 摘要，便于追溯且避免敏感信息落盘。"""

        fetched_at = datetime.now().astimezone()
        day_dir = RAW_OFFICIAL_DIR / fetched_at.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        host = re.sub(r"[^a-zA-Z0-9.-]+", "_", urlparse(url).netloc)[:60]
        filename = f"{host}_{digest}.json"

        soup = BeautifulSoup(html, "lxml")
        title = self._clean_text(soup.title.get_text(" ") if soup.title else "")
        text_summary = self._redact_sensitive(self._clean_text(soup.get_text(" "))[:5000])
        html_excerpt = self._redact_sensitive(html[:12000])
        payload = {
            "url": url,
            "fetched_at": fetched_at.isoformat(),
            "sha256": hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest(),
            "title": title,
            "text_summary": text_summary,
            "html_excerpt": html_excerpt,
            "privacy_note": "身份证号、手机号和电子邮箱已脱敏；仅保存 HTML 摘要。",
        }
        (day_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _redact_sensitive(text: str) -> str:
        """从归档摘要和候选人字段中移除身份证、手机号及邮箱。"""

        # 同时覆盖政府附件转 HTML 后数字间被插入空格或连字符的情况。
        redacted = re.sub(
            r"(?<!\d)(?:\d[\s-]*){17}[\dXx](?!\d)",
            "[已脱敏身份证]",
            text,
        )
        redacted = re.sub(
            r"(?<!\d)1[3-9](?:[\s-]*\d){9}(?!\d)",
            "[已脱敏手机号]",
            redacted,
        )
        redacted = re.sub(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "[已脱敏邮箱]",
            redacted,
        )
        return redacted

    def _safe_candidate_value(self, value: Any) -> str | None:
        """读取允许保存的候选人字段并执行敏感信息脱敏。"""

        text = self._cell_text(value)
        if not text:
            return None
        # 姓名、学校或专业单元格偶尔会误带身份证、手机号等内容。
        # 删除敏感片段后也移除脱敏占位符，避免把占位符当作业务数据入库。
        redacted = self._redact_sensitive(text)
        cleaned = re.sub(r"\[已脱敏(?:身份证|手机号|邮箱)\]", "", redacted)
        cleaned = cleaned.strip(" \t\r\n,，;；:：-/")
        return cleaned or None

    @staticmethod
    def _merge_candidates(
        existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """按姓名、学校和专业合并候选人数组并保持原顺序。"""

        result = list(existing)
        seen = {
            (item.get("name"), item.get("school"), item.get("major")) for item in result
        }
        for item in incoming:
            key = (item.get("name"), item.get("school"), item.get("major"))
            if key not in seen:
                result.append(item)
                seen.add(key)
        return result

    def _polite_wait(self) -> None:
        """确保相邻政府网站请求之间随机间隔 2 到 5 秒。"""

        if self._last_request_at <= 0:
            return
        target_interval = random.uniform(2, 5)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < target_interval:
            time.sleep(target_interval - elapsed)

    def _write_log(
        self,
        source: str,
        keyword: str,
        city: str,
        total_fetched: int,
        total_new: int,
        status: str,
        error_msg: str | None,
    ) -> None:
        """把来源级状态或异常写入 crawl_logs 表。"""

        try:
            self.db.add(
                CrawlLog(
                    source=source[:32],
                    keyword=keyword[:128],
                    city=city[:64],
                    total_fetched=total_fetched,
                    total_new=total_new,
                    status=status[:32],
                    error_msg=error_msg,
                )
            )
            self.db.commit()
        except Exception as log_error:
            self.db.rollback()
            logger.error("抓取日志写入失败：%s", log_error)

    @staticmethod
    def _normalize_years(years: Sequence[int]) -> tuple[int, ...]:
        """校验、排序并去重需要采集的四位年份。"""

        normalized = tuple(sorted({int(year) for year in years}))
        if not normalized or any(year < 2000 or year > 2100 for year in normalized):
            raise ValueError("年份必须是 2000 到 2100 之间的整数")
        return normalized

    @staticmethod
    def _empty_summary() -> dict[str, int]:
        """返回一个新的来源采集统计字典。"""

        return {
            "discovered": 0,
            "visited": 0,
            "tables": 0,
            "records": 0,
            "new": 0,
            "updated": 0,
            "errors": 0,
        }

    @staticmethod
    def _merge_summary(target: dict[str, Any], source: dict[str, int]) -> None:
        """把一个来源的数值统计累加到总统计中。"""

        for key in ("discovered", "visited", "tables", "records", "new", "updated", "errors"):
            target[key] = int(target.get(key, 0)) + int(source.get(key, 0))

    @staticmethod
    def _clean_text(value: Any) -> str:
        """把页面文本整理为单空格分隔的字符串。"""

        return re.sub(r"\s+", " ", str(value or "")).strip()

    def close(self) -> None:
        """关闭复用的 HTTP 会话。"""

        self.session.close()
