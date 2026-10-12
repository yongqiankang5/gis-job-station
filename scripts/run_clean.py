"""招聘数据清洗、去重和质量评分命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 支持从项目根目录直接运行 scripts/run_clean.py。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import (  # noqa: E402
    Base,
    SessionLocal,
    engine,
    ensure_job_cleaning_columns,
)
from app.services.cleaner import DataCleaner  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """构建数据清洗命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="标准化招聘岗位、提取技能、合并重复项并计算质量分。"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="重新清洗全部岗位；默认只清洗尚未处理的岗位。",
    )
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="仅执行重复数据合并；可与 --score 同时使用。",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="仅重新计算质量分；可与 --dedup 同时使用。",
    )
    return parser


def main() -> int:
    """执行所选清洗任务并打印 JSON 格式统计报告。"""

    args = build_parser().parse_args()
    Base.metadata.create_all(bind=engine)
    ensure_job_cleaning_columns(engine)
    db_session = SessionLocal()
    try:
        cleaner = DataCleaner(db_session)
        report: dict[str, object] = {}
        special_mode = args.dedup or args.score

        if not special_mode:
            report["清洗"] = cleaner.clean_all(only_unprocessed=not args.all)
            report["去重"] = cleaner.deduplicate()
            report["评分"] = cleaner.compute_quality_scores()
        else:
            if args.dedup:
                report["去重"] = cleaner.deduplicate()
            if args.score:
                report["评分"] = cleaner.compute_quality_scores()

        report["最终统计"] = cleaner.get_stats()
        print("招聘数据处理完成：")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        db_session.rollback()
        print(f"数据处理失败：{type(exc).__name__}: {exc}")
        return 1
    finally:
        db_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
