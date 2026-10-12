"""BOSS、事业单位、清洗去重与评分的一键全量更新脚本。"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine, ensure_job_cleaning_columns  # noqa: E402
from app.models import Job, OfficialRecord  # noqa: E402
from app.services.cleaner import DataCleaner  # noqa: E402
from app.services.scheduler import TaskAlreadyRunning, task_lock  # noqa: E402
from app.services.scraper_boss import BossScraper  # noqa: E402
from app.services.scraper_official import OfficialScraper  # noqa: E402


LOG_DIR = PROJECT_ROOT / "data" / "logs"


class TeeStream:
    """把 print 和第三方库输出同时写入终端与更新日志。"""

    def __init__(self, *streams: TextIO):
        """保存所有需要同步写入的文本流。"""

        self.streams = streams

    def write(self, text: str) -> int:
        """向所有目标流写入相同文本并立即刷新。"""

        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        """刷新所有目标流。"""

        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        """返回 False，避免进度组件输出终端控制字符。"""

        return False


def parse_cities(value: str) -> list[str]:
    """解析中英文逗号分隔的城市列表。"""

    cities = [item.strip() for item in re.split(r"[,，]", value) if item.strip()]
    if not cities:
        raise argparse.ArgumentTypeError("至少指定一个城市")
    return list(dict.fromkeys(cities))


def parse_max_pages(value: str) -> int:
    """校验 BOSS 最大页数范围为 1—10。"""

    try:
        pages = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("最大页数必须是整数") from exc
    if not 1 <= pages <= 10:
        raise argparse.ArgumentTypeError("最大页数必须在 1 到 10 之间")
    return pages


def build_parser() -> argparse.ArgumentParser:
    """构建一键更新脚本参数。"""

    parser = argparse.ArgumentParser(description="一键更新全部招聘和事业单位数据。")
    parser.add_argument("--skip-boss", action="store_true", help="跳过 BOSS 抓取。")
    parser.add_argument("--skip-official", action="store_true", help="跳过事业单位抓取。")
    parser.add_argument("--cities", type=parse_cities, help="指定 BOSS 城市，中英文逗号分隔。")
    parser.add_argument("--max-pages", type=parse_max_pages, default=10, help="每个组合最大页数。")
    parser.add_argument("--headless", action="store_true", help="无头运行 Chromium，适用于服务器。")
    return parser


def database_counts() -> dict[str, int]:
    """查询当前岗位与事业单位记录总量。"""

    session = SessionLocal()
    try:
        return {
            "jobs": int(session.scalar(select(func.count(Job.id))) or 0),
            "valid_jobs": int(
                session.scalar(select(func.count(Job.id)).where(Job.is_valid.is_(True))) or 0
            ),
            "official_records": int(session.scalar(select(func.count(OfficialRecord.id))) or 0),
        }
    finally:
        session.close()


def run_update(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """顺序执行各更新阶段，单阶段失败后继续后续清洗并汇总报告。"""

    Base.metadata.create_all(bind=engine)
    ensure_job_cleaning_columns(engine)
    before = database_counts()
    report: dict[str, Any] = {
        "started_at": datetime.now().astimezone().isoformat(),
        "before": before,
        "boss": {"skipped": args.skip_boss},
        "official": {"skipped": args.skip_official},
        "cleaning": {},
        "errors": [],
    }

    with task_lock("crawl"):
        if not args.skip_boss:
            print("\n[1/3] 开始 BOSS 全量抓取……")
            session = SessionLocal()
            scraper: BossScraper | None = None
            try:
                scraper = BossScraper(session, headless=args.headless)
                report["boss"] = scraper.crawl(
                    cities=args.cities, max_pages=args.max_pages
                )
            except Exception as exc:
                logging.exception("BOSS 抓取阶段失败")
                report["errors"].append(f"BOSS: {type(exc).__name__}: {exc}")
                report["boss"] = {"status": "failed", "error": str(exc)}
            finally:
                if scraper is not None:
                    try:
                        scraper.close()
                    except Exception:
                        logging.exception("关闭 BOSS 浏览器失败")
                session.close()

        if not args.skip_official:
            print("\n[2/3] 开始事业单位数据更新……")
            session = SessionLocal()
            scraper = OfficialScraper(session)
            try:
                current_year = datetime.now().year
                report["official"] = scraper.crawl_all(
                    (current_year - 2, current_year - 1, current_year)
                )
                if int(report["official"].get("errors", 0)):
                    report["errors"].append(
                        f"事业单位: {report['official']['errors']} 个来源执行失败"
                    )
            except Exception as exc:
                logging.exception("事业单位抓取阶段失败")
                report["errors"].append(f"事业单位: {type(exc).__name__}: {exc}")
                report["official"] = {"status": "failed", "error": str(exc)}
            finally:
                scraper.close()
                session.close()

        print("\n[3/3] 开始数据清洗、去重和质量评分……")
        with task_lock("data_maintenance"):
            session = SessionLocal()
            try:
                cleaner = DataCleaner(session)
                report["cleaning"] = {
                    "clean": cleaner.clean_all(only_unprocessed=True),
                    "deduplicate": cleaner.deduplicate(),
                    "quality": cleaner.compute_quality_scores(),
                    "stats": cleaner.get_stats(),
                }
            except Exception as exc:
                session.rollback()
                logging.exception("数据清洗阶段失败")
                report["errors"].append(f"清洗: {type(exc).__name__}: {exc}")
                report["cleaning"] = {"status": "failed", "error": str(exc)}
            finally:
                session.close()

    after = database_counts()
    boss_data = report.get("boss") if isinstance(report.get("boss"), dict) else {}
    official_data = report.get("official") if isinstance(report.get("official"), dict) else {}
    report.update({
        "finished_at": datetime.now().astimezone().isoformat(),
        "after": after,
        "summary": {
            "new_jobs": int(boss_data.get("total_new", 0)),
            "updated_jobs": int(boss_data.get("total_updated", 0)),
            "new_official_records": int(official_data.get("new", 0)),
            "updated_official_records": int(official_data.get("updated", 0)),
            "job_total_change": after["jobs"] - before["jobs"],
            "official_total_change": after["official_records"] - before["official_records"],
            "total_jobs": after["jobs"],
            "valid_jobs": after["valid_jobs"],
        },
    })
    return report, 0 if not report["errors"] else 2


def configure_console() -> None:
    """在支持的终端中启用 UTF-8，防止中文日志编码失败。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """创建带时间戳日志、执行更新并打印最终 JSON 报告。"""

    configure_console()
    args = build_parser().parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"update_{datetime.now():%Y%m%d_%H%M%S}.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        stdout_tee = TeeStream(sys.stdout, log_file)
        stderr_tee = TeeStream(sys.stderr, log_file)
        with redirect_stdout(stdout_tee), redirect_stderr(stderr_tee):
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                force=True,
            )
            print(f"更新日志：{log_path}")
            try:
                report, exit_code = run_update(args)
                print("\n更新报告：")
                print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
                return exit_code
            except TaskAlreadyRunning as exc:
                print(f"更新未启动：{exc}")
                return 3
            except Exception as exc:
                logging.exception("一键更新发生未处理异常")
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
