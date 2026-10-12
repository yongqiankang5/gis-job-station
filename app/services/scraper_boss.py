"""基于 DrissionPage 浏览器网络监听的 BOSS 直聘岗位抓取器。"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from DrissionPage import Chromium, ChromiumOptions
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CrawlLog, Job
from app.utils.keywords import JOB_KEYWORDS

# BOSS 搜索页会由正常浏览器行为触发该接口，本抓取器只监听响应，不构造加密参数。
BOSS_SEARCH_URL = "https://www.zhipin.com/web/geek/jobs"
BOSS_LOGIN_URL = "https://www.zhipin.com/web/user/"
BOSS_JOB_API = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
BOSS_JOB_API_TARGET = "/wapi/zpgeek/search/joblist.json"
BOSS_JOB_DETAIL_URL = "https://www.zhipin.com/job_detail/{job_id}.html"

# 城市编码来自 BOSS 搜索页面使用的公开查询参数。
BOSS_CITY_CODES: dict[str, str] = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "南京": "101190100",
    "武汉": "101200100",
    "成都": "101270100",
    "西安": "101110100",
    "重庆": "101040100",
    "天津": "101030100",
    "苏州": "101190400",
    "长沙": "101250100",
    "郑州": "101180100",
    "青岛": "101120200",
    "大连": "101070200",
    "厦门": "101230200",
    "福州": "101230100",
    "合肥": "101220100",
    "济南": "101120100",
    "昆明": "101290100",
    "贵阳": "101260100",
    "兰州": "101160100",
    "乌鲁木齐": "101130100",
    "哈尔滨": "101050100",
    "长春": "101060100",
    "沈阳": "101070100",
    "南昌": "101240100",
    "太原": "101100100",
    "石家庄": "101090100",
    "呼和浩特": "101080100",
    "银川": "101170100",
    "西宁": "101150100",
    "拉萨": "101140100",
    "南宁": "101300100",
    "海口": "101310100",
}

# jobs.province 不允许为空，因此为内置城市补充稳定的省级行政区映射。
CITY_PROVINCES: dict[str, str] = {
    "北京": "北京",
    "上海": "上海",
    "广州": "广东",
    "深圳": "广东",
    "杭州": "浙江",
    "南京": "江苏",
    "武汉": "湖北",
    "成都": "四川",
    "西安": "陕西",
    "重庆": "重庆",
    "天津": "天津",
    "苏州": "江苏",
    "长沙": "湖南",
    "郑州": "河南",
    "青岛": "山东",
    "大连": "辽宁",
    "厦门": "福建",
    "福州": "福建",
    "合肥": "安徽",
    "济南": "山东",
    "昆明": "云南",
    "贵阳": "贵州",
    "兰州": "甘肃",
    "乌鲁木齐": "新疆",
    "哈尔滨": "黑龙江",
    "长春": "吉林",
    "沈阳": "辽宁",
    "南昌": "江西",
    "太原": "山西",
    "石家庄": "河北",
    "呼和浩特": "内蒙古",
    "银川": "宁夏",
    "西宁": "青海",
    "拉萨": "西藏",
    "南宁": "广西",
    "海口": "海南",
}

# 按需求从岗位词典选择默认关键词，若词典移除某项则不会凭空添加。
_PREFERRED_KEYWORDS = (
    "GIS",
    "地理信息",
    "遥感",
    "测绘",
    "摄影测量",
    "WebGIS",
    "国土空间规划",
    "空间分析",
)
DEFAULT_KEYWORDS = [word for word in _PREFERRED_KEYWORDS if word in JOB_KEYWORDS]
DEFAULT_CITIES = [
    "北京",
    "武汉",
    "成都",
    "西安",
    "广州",
    "深圳",
    "杭州",
    "南京",
    "上海",
    "重庆",
]


class BossVerificationRequired(RuntimeError):
    """表示页面要求用户完成验证码或登录。"""


class BossScraper:
    """低频监听 BOSS 搜索接口并把岗位写入数据库。"""

    def __init__(
        self,
        db_session: Session,
        headless: bool = False,
        proxy: str | None = None,
    ) -> None:
        """初始化抓取器。

        Args:
            db_session: SQLAlchemy 数据库会话。
            headless: 是否以无头模式启动 Chromium。
            proxy: 浏览器代理地址，例如 ``http://127.0.0.1:7890``。
        """

        self.db = db_session
        self.headless = headless
        self.proxy = proxy
        self.browser: Chromium | None = None
        self.page: Any = None

        try:
            options = ChromiumOptions()
            options.headless(headless)
            options.set_load_mode("eager")
            # Docker 中 Chromium 通常不在 DrissionPage 的默认探测位置。
            if settings.chromium_path:
                options.set_browser_path(settings.chromium_path)
            if proxy:
                options.set_proxy(proxy)
            self.browser = Chromium(options)
            self.page = self.browser.latest_tab
            if not self.headless:
                self._show_browser_window()
        except Exception as exc:
            self._write_log(
                keyword="-",
                city="-",
                total_fetched=0,
                total_new=0,
                status="failed",
                error_msg=f"浏览器初始化失败：{exc}",
            )
            raise

    def prepare_login(self) -> None:
        """在可见浏览器中打开官方登录页，并等待用户确认登录完成。"""

        if self.page is None:
            raise RuntimeError("浏览器页面尚未初始化")
        if self.headless:
            raise ValueError("--login-first 不能与 --headless 同时使用")

        self._show_browser_window()
        loaded = self.page.get(
            BOSS_LOGIN_URL,
            retry=1,
            interval=2,
            timeout=30,
            show_errmsg=True,
        )
        if loaded is False:
            raise ConnectionError("BOSS 登录页加载失败，请检查网络后重试")
        self._show_browser_window()
        print("\n" + "=" * 68)
        print("BOSS 登录页已打开，请在浏览器中完成登录。")
        print("确认能正常看到求职者首页或岗位搜索页后，再回到此终端。")
        print("=" * 68)
        try:
            input("登录完成后按回车开始抓取：")
        except EOFError as exc:
            raise RuntimeError("当前终端无法读取输入，不能等待手动登录") from exc

    def crawl(
        self,
        keywords: list[str] | None = None,
        cities: list[str] | None = None,
        max_pages: int = 10,
        published_within_days: int | None = None,
    ) -> dict[str, int]:
        """执行抓取；可仅保存最近若干天发布的岗位。"""

        crawl_keywords = self._clean_values(keywords or DEFAULT_KEYWORDS)
        crawl_cities = self._clean_values(cities or DEFAULT_CITIES)
        unknown_cities = [city for city in crawl_cities if city not in BOSS_CITY_CODES]
        if unknown_cities:
            raise ValueError(f"暂不支持以下城市：{', '.join(unknown_cities)}")
        if not crawl_keywords:
            raise ValueError("关键词列表不能为空")

        safe_max_pages = min(max(int(max_pages), 1), 10)
        stats = {
            "total_combinations": len(crawl_keywords) * len(crawl_cities),
            "succeeded": 0,
            "failed": 0,
            "total_fetched": 0,
            "total_new": 0,
            "total_updated": 0,
        }

        for combination_index, (keyword, city_name) in enumerate(
            (
                (keyword, city_name)
                for keyword in crawl_keywords
                for city_name in crawl_cities
            ),
            start=1,
        ):
            print(
                f"\n[{combination_index}/{stats['total_combinations']}] "
                f"开始抓取：{keyword} / {city_name}"
            )
            try:
                result = self._crawl_one(
                    keyword=keyword,
                    city_code=BOSS_CITY_CODES[city_name],
                    city_name=city_name,
                    max_pages=safe_max_pages,
                    published_within_days=published_within_days,
                )
                stats["succeeded"] += 1
                stats["total_fetched"] += result["fetched"]
                stats["total_new"] += result["new"]
                stats["total_updated"] += result["updated"]
                self._write_log(
                    keyword=keyword,
                    city=city_name,
                    total_fetched=result["fetched"],
                    total_new=result["new"],
                    status="success" if result["fetched"] else "empty",
                    error_msg=None,
                )
            except KeyboardInterrupt:
                self._write_log(
                    keyword=keyword,
                    city=city_name,
                    total_fetched=0,
                    total_new=0,
                    status="failed",
                    error_msg="用户中断抓取",
                )
                raise
            except Exception as exc:
                stats["failed"] += 1
                self._write_log(
                    keyword=keyword,
                    city=city_name,
                    total_fetched=0,
                    total_new=0,
                    status="failed",
                    error_msg=f"{type(exc).__name__}: {exc}",
                )
                print(f"抓取失败，已记录日志：{exc}")

            # 不并发请求；两个城市/关键词组合之间随机休息 3～8 秒。
            if combination_index < stats["total_combinations"]:
                self._sleep_random(3, 8, "组合间隔")

        return stats

    def _crawl_one(
        self,
        keyword: str,
        city_code: str,
        city_name: str,
        max_pages: int,
        published_within_days: int | None = None,
    ) -> dict[str, int]:
        """抓取单个关键词与城市组合，逐页提交数据库。"""

        result = {"fetched": 0, "new": 0, "updated": 0}
        for page_number in range(1, min(max_pages, 10) + 1):
            print(f"  正在监听第 {page_number} 页接口…")
            payload = self._fetch_page_with_retry(
                keyword=keyword,
                city_code=city_code,
                city_name=city_name,
                page_number=page_number,
            )
            raw_jobs = payload.get("jobs", [])
            if not raw_jobs:
                print("  接口返回空岗位列表，停止当前组合翻页。")
                break

            parsed_jobs = [
                parsed
                for raw_job in raw_jobs
                if (
                    parsed := self._parse_job(
                        raw_job, city_name, published_within_days=published_within_days
                    )
                ) is not None
            ]
            saved = self._save_jobs(parsed_jobs)
            result["fetched"] += len(raw_jobs)
            result["new"] += saved["new"]
            result["updated"] += saved["updated"]
            print(
                f"  第 {page_number} 页完成：获取 {len(raw_jobs)}，"
                f"新增 {saved['new']}，更新 {saved['updated']}"
            )

            if payload.get("has_more") is False:
                print("  接口标记无下一页，停止当前组合翻页。")
                break
            if page_number < min(max_pages, 10):
                self._sleep_random(5, 12, "翻页间隔")

        return result

    def _fetch_page_with_retry(
        self,
        keyword: str,
        city_code: str,
        city_name: str,
        page_number: int,
    ) -> dict[str, Any]:
        """访问搜索页并监听岗位接口，网络失败最多重试三次。"""

        verification_count = 0
        while verification_count < 5:
            for attempt in range(1, 4):
                try:
                    return self._fetch_page_once(keyword, city_code, page_number)
                except BossVerificationRequired as exc:
                    verification_count += 1
                    self._write_log(
                        keyword=keyword,
                        city=city_name,
                        total_fetched=0,
                        total_new=0,
                        status="waiting_verification",
                        error_msg=str(exc),
                    )
                    self._wait_for_manual_verification(str(exc))
                    break
                except (TimeoutError, ConnectionError) as exc:
                    if attempt >= 3:
                        raise
                    wait_seconds = attempt * 5
                    self._write_log(
                        keyword=keyword,
                        city=city_name,
                        total_fetched=0,
                        total_new=0,
                        status="retrying",
                        error_msg=f"第 {attempt} 次网络请求失败：{exc}",
                    )
                    print(
                        f"  网络请求失败（{attempt}/3）：{exc}；"
                        f"{wait_seconds} 秒后重试。"
                    )
                    time.sleep(wait_seconds)
            else:
                # 正常情况下 for 会通过 return 结束；此分支用于防御意外流程。
                raise RuntimeError("页面重试流程异常结束")

        raise RuntimeError("连续多次要求验证，已停止当前关键词与城市组合")

    def _fetch_page_once(
        self,
        keyword: str,
        city_code: str,
        page_number: int,
    ) -> dict[str, Any]:
        """执行一次浏览器访问并返回规范化的接口载荷。"""

        if self.page is None:
            raise RuntimeError("浏览器页面尚未初始化")

        query = urlencode(
            {
                "query": keyword,
                "city": city_code,
                "page": page_number,
            }
        )
        url = f"{BOSS_SEARCH_URL}?{query}"

        # 官方文档要求先启动监听再产生页面请求；重复 start 会清空旧队列。
        # BOSS 新版搜索页可能以 GET 或 POST 请求岗位接口，因此不限制请求方法；
        # 使用稳定的接口路径片段，也能兼容接口附带时间戳等查询参数的情况。
        self.page.listen.start(BOSS_JOB_API_TARGET)
        loaded = self.page.get(
            url,
            retry=0,
            interval=1,
            timeout=30,
            show_errmsg=True,
        )
        if loaded is False:
            raise ConnectionError(f"搜索页加载失败：{url}")
        if self._needs_verification():
            raise BossVerificationRequired("页面出现验证码或登录墙")

        packet = self.page.listen.wait(timeout=45, raise_err=False)
        if packet is False:
            if self._needs_verification():
                raise BossVerificationRequired("等待岗位接口时出现验证码或登录墙")
            current_url = str(getattr(self.page, "url", "") or "")
            current_title = str(getattr(self.page, "title", "") or "")
            raise TimeoutError(
                "45 秒内未监听到岗位列表接口；"
                f"当前页面：{current_title or '未知标题'}（{current_url or '未知地址'}）"
            )
        if getattr(packet, "is_failed", False):
            raise ConnectionError(f"岗位接口请求失败：{getattr(packet, 'fail_info', '')}")

        body = packet.response.body
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8", errors="replace")
        if isinstance(body, str):
            body_text = body.strip()
            if not body_text:
                raise BossVerificationRequired(
                    "岗位接口返回空内容，登录状态可能已失效或访问受到限制"
                )
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError as exc:
                # 登录失效、访问频率受限时，接口可能返回 HTML 或空白文本。
                # 不尝试绕过限制，保留浏览器并交由用户完成官方验证。
                content_type = str(
                    getattr(packet.response, "headers", {}).get("content-type", "")
                )
                raise BossVerificationRequired(
                    "岗位接口未返回 JSON，可能需要重新登录或完成安全验证"
                    f"（Content-Type: {content_type or '未知'}）"
                ) from exc
        if not isinstance(body, dict):
            raise BossVerificationRequired(
                "岗位接口响应不是 JSON 对象，可能需要重新登录或完成安全验证"
            )

        code = body.get("code", 0)
        message = str(body.get("message") or body.get("zpData") or "未知错误")
        if code not in (0, None):
            if self._looks_like_verification(message) or code in {35, 36, 37}:
                raise BossVerificationRequired(f"接口要求验证或登录：{message}")
            raise RuntimeError(f"BOSS 接口返回错误 code={code}：{message}")

        zp_data = body.get("zpData") or {}
        if not isinstance(zp_data, dict):
            raise ValueError("岗位接口缺少有效的 zpData 对象")
        jobs = zp_data.get("jobList") or []
        if not isinstance(jobs, list):
            raise ValueError("岗位接口的 jobList 不是数组")
        return {"jobs": jobs, "has_more": zp_data.get("hasMore")}

    def _parse_job(
        self,
        raw_job: dict[str, Any],
        requested_city: str,
        published_within_days: int | None = None,
    ) -> dict[str, Any] | None:
        """把 BOSS 单条岗位 JSON 转换为 jobs 表字段。"""

        source_id = str(raw_job.get("encryptJobId") or "").strip()
        if not source_id:
            print("  跳过缺少 encryptJobId 的岗位记录。")
            return None

        city, district = self._parse_city(
            str(raw_job.get("cityName") or requested_city)
        )
        district = district or self._clean_optional_text(raw_job.get("areaDistrict"))
        salary_min, salary_max, salary_note = self._parse_salary(
            raw_job.get("salaryDesc")
        )
        labels = self._normalize_labels(
            raw_job.get("jobLabels") or raw_job.get("skills") or []
        )
        job_title = str(raw_job.get("jobName") or "未命名岗位").strip()
        publish_date = self._parse_publish_date(raw_job)
        if (
            published_within_days is not None
            and publish_date is not None
            and publish_date < date.today() - timedelta(days=max(published_within_days, 0))
        ):
            return None

        return {
            "source": "boss",
            "source_id": source_id,
            "job_title": job_title,
            "company_name": str(raw_job.get("brandName") or "未知公司").strip(),
            "company_type": self._map_company_type(raw_job),
            "city": city or requested_city,
            "province": CITY_PROVINCES.get(city or requested_city, requested_city),
            "district": district,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_note": salary_note,
            "education": str(raw_job.get("jobDegree") or "不限").strip(),
            "experience": str(
                raw_job.get("workExperience")
                or raw_job.get("jobExperience")
                or "不限"
            ).strip(),
            "job_type": self._infer_job_type(job_title),
            # 详情页抓取暂未启用，若列表接口未来返回 jobDesc 则直接保存。
            "job_description": str(raw_job.get("jobDesc") or "").strip(),
            "skills": labels,
            "publish_date": publish_date,
            "crawl_date": date.today(),
            "url": BOSS_JOB_DETAIL_URL.format(job_id=source_id),
            "is_valid": True,
        }

    @staticmethod
    def _parse_publish_date(raw_job: dict[str, Any]) -> date | None:
        """解析接口中常见的时间戳、日期或“几天前”发布日期描述。"""

        raw_value = next(
            (
                raw_job.get(key)
                for key in (
                    "jobPubTime", "publishTime", "createTime",
                    "jobPubTimeDesc", "publishDate", "publishTimeDesc",
                )
                if raw_job.get(key) not in (None, "")
            ),
            None,
        )
        if raw_value is None:
            return None
        if isinstance(raw_value, (int, float)):
            timestamp = float(raw_value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            try:
                return datetime.fromtimestamp(timestamp).date()
            except (OSError, OverflowError, ValueError):
                return None

        text = str(raw_value).strip()
        today = date.today()
        if re.fullmatch(r"\d{10,13}", text):
            timestamp = float(text)
            if len(text) == 13:
                timestamp /= 1000
            try:
                return datetime.fromtimestamp(timestamp).date()
            except (OSError, OverflowError, ValueError):
                return None
        if text in {"今天", "刚刚"} or "小时前" in text or "分钟前" in text:
            return today
        if "昨天" in text:
            return today - timedelta(days=1)
        days_ago = re.search(r"(\d+)\s*天前", text)
        if days_ago:
            return today - timedelta(days=int(days_ago.group(1)))
        full_date = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
        if full_date:
            try:
                return date(*map(int, full_date.groups()))
            except ValueError:
                return None
        month_day = re.search(r"(\d{1,2})[-/.月](\d{1,2})", text)
        if month_day:
            try:
                candidate = date(today.year, int(month_day.group(1)), int(month_day.group(2)))
                return candidate.replace(year=today.year - 1) if candidate > today else candidate
            except ValueError:
                return None
        return None

    def _parse_salary(
        self, salary_str: Any
    ) -> tuple[float | None, float | None, str | None]:
        """解析薪资字符串，返回月薪 K 单位的下限、上限和原始描述。"""

        if salary_str is None:
            return None, None, None
        note = str(salary_str).strip()
        if not note or "面议" in note:
            return None, None, note or None

        # 兼容 15-25K、15K-25K、15-25K·14薪及小数薪资。
        k_match = re.search(
            r"(?P<minimum>\d+(?:\.\d+)?)\s*[kK]?\s*[-~—–至]\s*"
            r"(?P<maximum>\d+(?:\.\d+)?)\s*[kK]",
            note,
        )
        if k_match:
            return (
                float(k_match.group("minimum")),
                float(k_match.group("maximum")),
                note,
            )

        # 少量职位使用“万/月”，统一乘 10 转换为 K/月。
        ten_thousand_match = re.search(
            r"(?P<minimum>\d+(?:\.\d+)?)\s*[-~—–至]\s*"
            r"(?P<maximum>\d+(?:\.\d+)?)\s*万(?:/月)?",
            note,
        )
        if ten_thousand_match:
            return (
                float(ten_thousand_match.group("minimum")) * 10,
                float(ten_thousand_match.group("maximum")) * 10,
                note,
            )
        return None, None, note

    def _parse_city(self, city_str: Any) -> tuple[str, str | None]:
        """从“北京·朝阳区”一类字符串拆分城市与区县。"""

        text = str(city_str or "").strip()
        if not text:
            return "", None
        parts = [part.strip() for part in re.split(r"[·•]", text, maxsplit=1)]
        city = parts[0]
        district = parts[1] if len(parts) > 1 and parts[1] else None
        return city, district

    def _save_jobs(self, jobs_data: list[dict[str, Any]]) -> dict[str, int]:
        """批量保存岗位，按 boss/source_id 去重，存在则更新。"""

        # 同一页偶尔会出现重复卡片，先在内存中按 source_id 合并。
        unique_jobs = {
            str(job["source_id"]): job for job in jobs_data if job.get("source_id")
        }
        if not unique_jobs:
            return {"new": 0, "updated": 0}

        existing_jobs = self.db.scalars(
            select(Job).where(
                Job.source == "boss",
                Job.source_id.in_(list(unique_jobs)),
            )
        ).all()
        existing_by_id = {job.source_id: job for job in existing_jobs}
        new_count = 0
        updated_count = 0

        try:
            for source_id, values in unique_jobs.items():
                existing = existing_by_id.get(source_id)
                if existing is None:
                    self.db.add(Job(**values))
                    new_count += 1
                    continue
                for field, value in values.items():
                    if field not in {"source", "source_id"}:
                        setattr(existing, field, value)
                updated_count += 1
            # 每一页独立提交，使验证码暂停或意外退出时已完成进度仍然保留。
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"new": new_count, "updated": updated_count}

    def _write_log(
        self,
        keyword: str,
        city: str,
        total_fetched: int,
        total_new: int,
        status: str,
        error_msg: str | None,
    ) -> None:
        """写入一条抓取日志；日志写入失败时回滚并输出告警。"""

        try:
            self.db.add(
                CrawlLog(
                    source="boss",
                    keyword=keyword,
                    city=city,
                    total_fetched=total_fetched,
                    total_new=total_new,
                    status=status,
                    error_msg=error_msg,
                )
            )
            self.db.commit()
        except Exception as log_error:
            self.db.rollback()
            print(f"警告：抓取日志写入失败：{log_error}")

    def _needs_verification(self) -> bool:
        """根据当前 URL、标题和页面文本判断是否出现验证或登录墙。"""

        if self.page is None:
            return False
        url = str(getattr(self.page, "url", "") or "").lower()
        title = str(getattr(self.page, "title", "") or "")
        html = str(getattr(self.page, "html", "") or "")
        if any(flag in url for flag in ("/verify", "security-check", "/web/user/")):
            return True
        return self._looks_like_verification(f"{title}\n{html}")

    @staticmethod
    def _looks_like_verification(text: str) -> bool:
        """判断文本是否包含明确的验证码或强制登录提示。"""

        lowered = text.casefold()
        signals = (
            "请完成验证",
            "安全验证",
            "访问异常",
            "验证码",
            "请先登录",
            "登录后查看更多",
            "verify your identity",
        )
        return any(signal.casefold() in lowered for signal in signals)

    def _wait_for_manual_verification(self, reason: str) -> None:
        """暂停程序，等待用户在可见浏览器中手动完成验证。"""

        self._show_browser_window()
        print("\n" + "=" * 68)
        print(f"检测到 BOSS 验证码或登录墙：{reason}")
        if self.headless:
            print("当前为无头模式，无法看到验证页面；建议中断后去掉 --headless 重试。")
        print("请在浏览器中手动完成登录或验证，不要关闭浏览器。")
        print("已完成页均已保存；验证完成后回到此终端。")
        print("=" * 68)
        try:
            input("验证完成后按回车继续：")
        except EOFError as exc:
            raise RuntimeError("当前终端无法读取输入，不能等待手动验证") from exc

    def _show_browser_window(self) -> None:
        """尽量显示并最大化浏览器窗口；失败时不影响后续抓取。"""

        if self.page is None or self.headless:
            return
        try:
            self.page.set.window.show()
            self.page.set.window.max()
        except Exception as exc:
            # 窗口管理依赖操作系统能力，失败时浏览器本身仍可继续工作。
            print(f"提示：无法自动置顶浏览器窗口，请从任务栏打开 Chrome：{exc}")

    @staticmethod
    def _map_company_type(raw_job: dict[str, Any]) -> str:
        """综合公司阶段和规模字段映射项目所需的公司类型。"""

        signals = " ".join(
            str(raw_job.get(field) or "")
            for field in ("brandStageName", "brandScaleName", "companyType")
        )
        if "国企" in signals or "国有" in signals:
            return "国企"
        if "上市" in signals:
            return "上市公司"
        scale = str(raw_job.get("brandScaleName") or "").replace(" ", "")
        if scale == "0-20人":
            return "民营小公司"
        if scale in {"1000-9999人", "10000人以上"}:
            return "中大型"
        return "其他"

    @staticmethod
    def _infer_job_type(job_title: str) -> str:
        """根据岗位名称做轻量岗位类型归类。"""

        rules = (
            ("算法", ("算法", "深度学习", "机器学习", "模型")),
            ("开发", ("开发", "WebGIS", "前端", "后端", "工程师")),
            ("数据处理", ("数据处理", "制图", "测绘", "内业", "点云")),
            ("分析", ("分析", "规划", "遥感", "GIS")),
            ("销售", ("销售", "商务", "售前")),
        )
        folded_title = job_title.casefold()
        for job_type, words in rules:
            if any(word.casefold() in folded_title for word in words):
                return job_type
        return "其他"

    @staticmethod
    def _normalize_labels(value: Any) -> list[str]:
        """把接口标签字段转换为去重且非空的字符串数组。"""

        if isinstance(value, str):
            candidates = re.split(r"[,，|/]", value)
        elif isinstance(value, (list, tuple, set)):
            candidates = list(value)
        else:
            candidates = []
        labels: list[str] = []
        for candidate in candidates:
            label = str(candidate or "").strip()
            if label and label not in labels:
                labels.append(label)
        return labels

    @staticmethod
    def _clean_values(values: list[str]) -> list[str]:
        """清理列表中的空白项并保持原顺序去重。"""

        result: list[str] = []
        for value in values:
            clean_value = str(value).strip()
            if clean_value and clean_value not in result:
                result.append(clean_value)
        return result

    @staticmethod
    def _clean_optional_text(value: Any) -> str | None:
        """把可空接口字段转换为去除首尾空白的文本。"""

        clean_value = str(value or "").strip()
        return clean_value or None

    @staticmethod
    def _sleep_random(minimum: int, maximum: int, label: str) -> None:
        """按配置范围随机休眠，并打印可观察的低频提示。"""

        seconds = random.uniform(minimum, maximum)
        print(f"  {label}：休息 {seconds:.1f} 秒，降低访问频率。")
        time.sleep(seconds)

    def close(self) -> None:
        """关闭浏览器并释放 Chromium 进程。"""

        if self.browser is not None:
            self.browser.quit()
            self.browser = None
            self.page = None
