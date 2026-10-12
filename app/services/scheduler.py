"""APScheduler 定时抓取、清理、快照和备份服务。"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete, select

from app.database import Base, SessionLocal, engine, ensure_job_cleaning_columns
from app.models import CrawlLog, Job
from app.services.analyzer import JobAnalyzer
from app.services.cleaner import DataCleaner
from app.services.scraper_boss import BossScraper
from app.services.scraper_official import OfficialScraper


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_DIR = PROJECT_ROOT / "data" / ".locks"
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class TaskAlreadyRunning(RuntimeError):
    """表示另一线程或进程已持有同名任务锁。"""


class InterProcessFileLock:
    """使用操作系统文件锁实现 Windows/Linux 跨进程互斥。"""

    def __init__(self, path: str | Path):
        """保存锁文件路径，锁文件本身可长期保留。"""

        self.path = Path(path)
        self._stream: Any = None

    def acquire(self, blocking: bool = False) -> bool:
        """尝试获取锁；非阻塞模式下占用时直接返回 False。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("a+b")
        self._stream.seek(0, os.SEEK_END)
        if self._stream.tell() == 0:
            self._stream.write(b"0")
            self._stream.flush()
        self._stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
                msvcrt.locking(self._stream.fileno(), mode, 1)
            else:
                import fcntl

                flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                fcntl.flock(self._stream.fileno(), flags)
            return True
        except (BlockingIOError, OSError):
            self._stream.close()
            self._stream = None
            return False

    def release(self) -> None:
        """释放当前进程持有的文件锁。"""

        if self._stream is None:
            return
        try:
            self._stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        finally:
            self._stream.close()
            self._stream = None


@contextmanager
def task_lock(name: str) -> Iterator[None]:
    """非阻塞获取任务锁，防止抓取或更新任务重复运行。"""

    lock = InterProcessFileLock(LOCK_DIR / f"{name}.lock")
    if not lock.acquire(blocking=False):
        raise TaskAlreadyRunning(f"任务 {name} 已在另一线程或进程运行")
    try:
        yield
    finally:
        lock.release()


class JobScheduler:
    """管理项目的周期任务、手动触发和最近执行状态。"""

    def __init__(self):
        """初始化上海时区后台调度器并注册全部周期任务。"""

        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai", daemon=True)
        self._leader_lock = InterProcessFileLock(LOCK_DIR / "scheduler_leader.lock")
        self._is_leader = False
        self._state_lock = threading.Lock()
        self._inflight: set[str] = set()
        self._last_runs: dict[str, dict[str, Any]] = {}
        self._task_functions: dict[str, Callable[[], dict[str, Any]]] = {
            "boss_incremental": self._boss_incremental_task,
            "official_update": self._official_update_task,
            "cleanup_expired": self._cleanup_task,
            "monthly_snapshot": self._snapshot_task,
            "daily_backup": self._backup_task,
            "clean_data": self._clean_only_task,
            "scraper_all": self._all_scrapers_task,
        }
        self._setup_jobs()

    def _setup_jobs(self) -> None:
        """配置所有定时任务及防重入、错过执行和合并策略。"""

        common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
        self.scheduler.add_job(
            lambda: self._execute_job("boss_incremental", self._boss_incremental_task),
            "cron", id="boss_incremental", name="BOSS 近7天增量抓取",
            day_of_week="mon,thu", hour=2, minute=0, replace_existing=True, **common,
        )
        self.scheduler.add_job(
            lambda: self._execute_job("official_update", self._official_update_task),
            "cron", id="official_update", name="事业单位数据更新",
            day_of_week="sun", hour=3, minute=0, replace_existing=True, **common,
        )
        self.scheduler.add_job(
            lambda: self._execute_job("cleanup_expired", self._cleanup_task),
            "cron", id="cleanup_expired", name="过期岗位与日志清理",
            hour=4, minute=0, replace_existing=True, **common,
        )
        self.scheduler.add_job(
            lambda: self._execute_job("daily_backup", self._backup_task),
            "cron", id="daily_backup", name="SQLite 每日备份",
            hour=4, minute=30, replace_existing=True, **common,
        )
        self.scheduler.add_job(
            lambda: self._execute_job("monthly_snapshot", self._snapshot_task),
            "cron", id="monthly_snapshot", name="月度统计快照",
            day=1, hour=5, minute=0, replace_existing=True, **common,
        )

    def start(self) -> bool:
        """启动调度器；多进程部署时只有获得领导锁的进程启动。"""

        if self.scheduler.running:
            return True
        if not self._leader_lock.acquire(blocking=False):
            logger.info("其他进程已启动定时调度器，本进程不重复启动")
            return False
        try:
            Base.metadata.create_all(bind=engine)
            ensure_job_cleaning_columns(engine)
            self.scheduler.start()
            self._is_leader = True
            logger.info("定时调度器已启动，共 %s 项周期任务", len(self.scheduler.get_jobs()))
            return True
        except Exception:
            self._leader_lock.release()
            raise

    def shutdown(self) -> None:
        """关闭后台调度器并释放多进程领导锁。"""

        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        finally:
            self._is_leader = False
            self._leader_lock.release()

    def run_job_now(self, job_id: str) -> dict[str, Any]:
        """在守护线程中立即执行指定任务，用于管理 API 手动触发。"""

        task = self._task_functions.get(job_id)
        if task is None:
            raise ValueError(f"未知任务：{job_id}")
        with self._state_lock:
            if job_id in self._inflight:
                raise TaskAlreadyRunning(f"任务 {job_id} 已在运行")
            self._inflight.add(job_id)
            self._last_runs[job_id] = {
                "status": "queued", "started_at": None, "finished_at": None,
                "error": None, "result": None,
            }
        thread = threading.Thread(
            target=self._execute_job,
            args=(job_id, task, True),
            name=f"manual-{job_id}",
            daemon=True,
        )
        thread.start()
        return {"accepted": True, "job_id": job_id, "message": "任务已提交后台执行"}

    def get_job_status(self) -> dict[str, Any]:
        """返回调度器状态、所有任务下次执行时间和最近运行结果。"""

        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
                "running": job.id in self._inflight,
            })
        with self._state_lock:
            last_runs = json.loads(json.dumps(self._last_runs, ensure_ascii=False, default=str))
        return {
            "running": bool(self.scheduler.running),
            "is_leader": self._is_leader,
            "timezone": "Asia/Shanghai",
            "jobs": jobs,
            "last_runs": last_runs,
        }

    def _execute_job(
        self, job_id: str, task: Callable[[], dict[str, Any]], reserved: bool = False
    ) -> dict[str, Any]:
        """统一执行任务，捕获全部异常并记录可查询状态。"""

        with self._state_lock:
            if not reserved and job_id in self._inflight:
                return {"status": "skipped", "reason": "任务已在本进程运行"}
            self._inflight.add(job_id)
            self._last_runs[job_id] = {
                "status": "running",
                "started_at": datetime.now(SHANGHAI_TZ).isoformat(),
                "finished_at": None, "error": None, "result": None,
            }
        status = "failed"
        error: str | None = "任务被异常中断"
        result: dict[str, Any] = {"status": "failed", "error": error}
        try:
            result = task()
            status = "success"
            error = None
            return result
        except TaskAlreadyRunning as exc:
            logger.warning("任务 %s 跳过：%s", job_id, exc)
            result = {"status": "skipped", "reason": str(exc)}
            status = "skipped"
            error = str(exc)
            return result
        except Exception as exc:
            logger.exception("定时任务 %s 执行失败", job_id)
            result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            status = "failed"
            error = result["error"]
            return result
        finally:
            finished_at = datetime.now(SHANGHAI_TZ).isoformat()
            with self._state_lock:
                state = self._last_runs.setdefault(job_id, {})
                state.update({
                    "status": status, "finished_at": finished_at,
                    "error": error, "result": result,
                })
                self._inflight.discard(job_id)
            self._write_task_log(job_id, status, error)

    def _boss_incremental_task(self) -> dict[str, Any]:
        """低频抓取 BOSS 最近 7 天岗位，随后清洗、去重并评分。"""

        with task_lock("crawl"):
            boss_result = self._run_boss(published_within_days=7, max_pages=3)
            with task_lock("data_maintenance"):
                cleaning = self._run_cleaning()
        return {"boss": boss_result, "cleaning": cleaning}

    def _official_update_task(self) -> dict[str, Any]:
        """更新近三年事业单位数据，随后清洗现有岗位。"""

        with task_lock("crawl"):
            official_result = self._run_official()
            with task_lock("data_maintenance"):
                cleaning = self._run_cleaning()
        return {"official": official_result, "cleaning": cleaning}

    def _all_scrapers_task(self) -> dict[str, Any]:
        """依次执行 BOSS 增量和事业单位更新，最后统一清洗。"""

        with task_lock("crawl"):
            boss_result = self._run_boss(published_within_days=7, max_pages=3)
            official_result = self._run_official()
            with task_lock("data_maintenance"):
                cleaning = self._run_cleaning()
        return {"boss": boss_result, "official": official_result, "cleaning": cleaning}

    def _clean_only_task(self) -> dict[str, Any]:
        """执行未处理岗位清洗、全量去重与质量评分。"""

        with task_lock("data_maintenance"):
            return self._run_cleaning()

    def _cleanup_task(self) -> dict[str, Any]:
        """标记 180 天未更新岗位无效，并删除 30 天前抓取日志。"""

        with task_lock("data_maintenance"):
            session = SessionLocal()
            try:
                job_cutoff = datetime.now(SHANGHAI_TZ) - timedelta(days=180)
                stale_jobs = list(session.scalars(
                    select(Job).where(Job.is_valid.is_(True), Job.updated_at < job_cutoff)
                ))
                for job in stale_jobs:
                    job.is_valid = False
                    marker = "超过180天未更新，定时标记无效"
                    job.note = marker if not job.note else (
                        job.note if marker in job.note else f"{job.note}；{marker}"
                    )
                log_cutoff = datetime.now(SHANGHAI_TZ) - timedelta(days=30)
                deleted_logs = session.execute(
                    delete(CrawlLog).where(CrawlLog.created_at < log_cutoff)
                ).rowcount or 0
                session.commit()
                return {
                    "invalidated_jobs": len(stale_jobs),
                    "deleted_logs": int(deleted_logs),
                    "job_cutoff": job_cutoff.isoformat(),
                    "log_cutoff": log_cutoff.isoformat(),
                }
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    def _snapshot_task(self) -> dict[str, Any]:
        """生成月度关键统计 JSON，并以原子替换方式保存。"""

        with task_lock("data_maintenance"):
            session = SessionLocal()
            try:
                analyzer = JobAnalyzer(session)
                payload = {
                    "generated_at": datetime.now(SHANGHAI_TZ).isoformat(),
                    "period": date.today().strftime("%Y-%m"),
                    "overview": analyzer.get_overview(),
                    "city_distribution": analyzer.get_city_distribution(top_n=20),
                    "salary_distribution": analyzer.get_salary_distribution(),
                    "skill_analysis": analyzer.get_skill_analysis(top_n=30),
                    "official_analysis": analyzer.get_official_analysis(),
                    "trend": analyzer.get_trend(months=12),
                }
            finally:
                session.close()
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            path = SNAPSHOT_DIR / f"snapshot_{date.today():%Y%m}.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            temporary.replace(path)
            return {"path": str(path), "size_bytes": path.stat().st_size}

    def _backup_task(self) -> dict[str, Any]:
        """调用共享备份函数生成每日 SQLite 压缩备份。"""

        with task_lock("data_maintenance"):
            from scripts.backup import create_backup

            return create_backup(retention_days=30)

    @staticmethod
    def _run_boss(
        published_within_days: int | None, max_pages: int
    ) -> dict[str, Any]:
        """创建独立会话执行 BOSS 抓取并确保浏览器关闭。"""

        session = SessionLocal()
        scraper: BossScraper | None = None
        try:
            scraper = BossScraper(session, headless=True)
            return scraper.crawl(
                max_pages=max_pages, published_within_days=published_within_days
            )
        finally:
            if scraper is not None:
                scraper.close()
            session.close()

    @staticmethod
    def _run_official() -> dict[str, Any]:
        """创建独立会话更新当前年份及前两年事业单位数据。"""

        session = SessionLocal()
        scraper = OfficialScraper(session)
        current_year = date.today().year
        try:
            return scraper.crawl_all((current_year - 2, current_year - 1, current_year))
        finally:
            scraper.close()
            session.close()

    @staticmethod
    def _run_cleaning() -> dict[str, Any]:
        """使用独立会话执行清洗、去重、评分并返回最终统计。"""

        session = SessionLocal()
        try:
            cleaner = DataCleaner(session)
            return {
                "clean": cleaner.clean_all(only_unprocessed=True),
                "deduplicate": cleaner.deduplicate(),
                "quality": cleaner.compute_quality_scores(),
                "stats": cleaner.get_stats(),
            }
        finally:
            session.close()

    @staticmethod
    def _write_task_log(job_id: str, status: str, error: str | None) -> None:
        """把调度任务最终状态写入 crawl_logs，写入失败只记录日志。"""

        session = SessionLocal()
        try:
            session.add(CrawlLog(
                source="scheduler", keyword=job_id, city="-",
                total_fetched=0, total_new=0, status=status,
                error_msg=error,
            ))
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("调度任务日志写入失败：%s", job_id)
        finally:
            session.close()
