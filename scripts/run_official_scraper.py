"""事业单位 GIS、遥感与测绘招录采集器命令行入口。"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# 支持从项目根目录直接运行 scripts/run_official_scraper.py。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services.scraper_official import OfficialScraper  # noqa: E402
from app.utils.province_sites import PROVINCE_SITES  # noqa: E402


def parse_years(value: str) -> tuple[int, ...]:
    """解析中英文逗号分隔年份并验证合理范围。"""

    parts = [part.strip() for part in re.split(r"[,，]", value) if part.strip()]
    try:
        years = tuple(sorted({int(part) for part in parts}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("年份必须是整数并用逗号分隔") from exc
    if not years or any(year < 2000 or year > 2100 for year in years):
        raise argparse.ArgumentTypeError("年份必须位于 2000 到 2100 之间")
    return years


def build_parser() -> argparse.ArgumentParser:
    """构建事业单位采集器命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="低频采集公开政府网站中的 GIS、遥感和测绘事业单位招录数据。"
    )
    parser.add_argument(
        "--years",
        type=parse_years,
        default=(2024, 2025, 2026),
        help="指定年份，中英文逗号分隔，默认 2024,2025,2026。",
    )
    parser.add_argument(
        "--source",
        choices=("mnr", "mohrss", "province", "all"),
        default="all",
        help="指定来源：mnr、mohrss、province 或 all，默认 all。",
    )
    parser.add_argument(
        "--province",
        choices=tuple(PROVINCE_SITES),
        help="指定省份，仅在 --source province 时有效。",
    )
    return parser


def main() -> int:
    """初始化数据库，执行所选来源并输出 JSON 统计。"""

    args = build_parser().parse_args()
    if args.source == "province" and not args.province:
        print("错误：使用 --source province 时必须同时指定 --province。")
        return 2
    if args.source != "province" and args.province:
        print("提示：--province 仅在 --source province 时生效，本次将忽略。")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    print("开始采集公开政府招录信息，请保持低频运行并遵守网站使用规范。")
    print("候选人信息仅保存姓名、学校和专业，不采集身份证号、手机号等敏感信息。")

    Base.metadata.create_all(bind=engine)
    db_session = SessionLocal()
    scraper = OfficialScraper(db_session)
    try:
        if args.source == "mnr":
            result = scraper.crawl_mnr(args.years)
        elif args.source == "mohrss":
            result = scraper.crawl_mohrss(args.years)
        elif args.source == "province":
            config = PROVINCE_SITES[args.province]
            result = scraper.crawl_province(
                args.province,
                config["list_url"],
                args.years,
            )
        else:
            result = scraper.crawl_all(args.years)
        print("\n采集任务完成：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if int(result.get("errors", 0)) == 0 else 2
    except KeyboardInterrupt:
        print("\n用户已中断采集，已提交的数据和原始摘要仍然保留。")
        return 130
    except Exception as exc:
        logging.exception("采集任务失败")
        print(f"采集任务失败：{type(exc).__name__}: {exc}")
        return 1
    finally:
        scraper.close()
        db_session.close()


if __name__ == "__main__":
    raise SystemExit(main())

