"""BOSS 直聘抓取器命令行入口。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 允许直接执行 scripts/run_boss_scraper.py 时正确导入项目 app 包。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services.scraper_boss import BossScraper  # noqa: E402


def parse_csv_argument(value: str) -> list[str]:
    """将中英文逗号分隔的命令行参数转换为非空列表。"""

    values = [item.strip() for item in re.split(r"[,，]", value) if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("至少需要提供一个非空值")
    return values


def parse_page_count(value: str) -> int:
    """验证最大页数必须处于 1 到 10 之间。"""

    try:
        page_count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("最大页数必须是整数") from exc
    if not 1 <= page_count <= 10:
        raise argparse.ArgumentTypeError("最大页数必须在 1 到 10 之间")
    return page_count


def build_parser() -> argparse.ArgumentParser:
    """创建 BOSS 抓取器命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="通过真实 Chromium 正常访问并监听 BOSS 直聘岗位列表响应。"
    )
    parser.add_argument(
        "--keywords",
        type=parse_csv_argument,
        help="指定关键词，中英文逗号分隔；不传则使用默认 8 个关键词。",
    )
    parser.add_argument(
        "--cities",
        type=parse_csv_argument,
        help="指定城市，中英文逗号分隔；不传则使用默认 10 个城市。",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="使用无头模式；首次登录或可能触发验证时不建议启用。",
    )
    parser.add_argument(
        "--login-first",
        action="store_true",
        help="抓取前打开 BOSS 官方登录页，并等待手动确认登录完成。",
    )
    parser.add_argument(
        "--max-pages",
        type=parse_page_count,
        default=10,
        help="每个关键词与城市组合的最大页数，范围 1～10，默认 10。",
    )
    parser.add_argument(
        "--proxy",
        help="浏览器代理，例如 http://127.0.0.1:7890。",
    )
    return parser


def main() -> int:
    """初始化数据库和抓取器，执行任务并返回进程退出码。"""

    args = build_parser().parse_args()
    print("请确保已在浏览器中登录 BOSS 直聘账号，否则可能只能看到有限数据")
    print("请遵守网站服务条款并保持低频访问；程序不会破解任何验证或加密。")

    # 与 Web 应用一致：首次运行时自动创建缺失的数据表。
    Base.metadata.create_all(bind=engine)
    db_session = SessionLocal()
    scraper: BossScraper | None = None
    try:
        scraper = BossScraper(
            db_session=db_session,
            headless=args.headless,
            proxy=args.proxy,
        )
        if args.login_first:
            scraper.prepare_login()
        stats = scraper.crawl(
            keywords=args.keywords,
            cities=args.cities,
            max_pages=args.max_pages,
        )
        print("\n抓取任务完成：")
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0 if stats["failed"] == 0 else 2
    except KeyboardInterrupt:
        print("\n用户已中断抓取，已完成页面的数据仍保存在数据库中。")
        return 130
    except Exception as exc:
        print(f"\n抓取器启动或执行失败：{type(exc).__name__}: {exc}")
        return 1
    finally:
        if scraper is not None:
            try:
                scraper.close()
            except Exception as close_error:
                print(f"关闭浏览器时出现错误：{close_error}")
        db_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
