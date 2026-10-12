"""岗位与事业单位数据手动导入命令行工具。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine, ensure_job_cleaning_columns  # noqa: E402
from app.services.importer import DataImporter  # noqa: E402


def configure_console() -> None:
    """在 Windows 等环境中统一使用 UTF-8，避免中文或特殊分隔符打印失败。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    """构建导入工具参数解析器。"""

    parser = argparse.ArgumentParser(
        description="从 Excel、CSV 或 JSON 导入岗位，或导入事业单位招录记录。"
    )
    parser.add_argument("--file", help="待导入文件路径，支持 xlsx、xls、csv、json。")
    parser.add_argument("--source", default="manual", help="岗位来源标记，默认 manual。")
    parser.add_argument(
        "--type", choices=("job", "official"), default="job",
        help="导入类型：job 或 official，默认 job。",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只校验、去重并预览，不写入业务数据。"
    )
    parser.add_argument(
        "--template", nargs="?", const="data/templates/岗位导入模板.xlsx",
        help="生成标准 Excel 模板；可省略路径使用默认位置。",
    )
    return parser


def print_preview(report: dict[str, object]) -> None:
    """以容易核对的格式打印列映射和前五行预览。"""

    print("\n列名映射：")
    print(json.dumps(report.get("column_mapping", {}), ensure_ascii=False, indent=2, default=str))
    print("\n前 5 行预览：")
    print(json.dumps(report.get("preview", []), ensure_ascii=False, indent=2, default=str))


def main() -> int:
    """初始化数据库、执行指定导入任务并打印详细报告。"""

    configure_console()
    args = build_parser().parse_args()
    if not args.file and not args.template:
        print("错误：请使用 --file 指定导入文件，或使用 --template 生成模板。")
        return 2
    if args.file and args.template:
        print("错误：--file 与 --template 不能同时使用。")
        return 2

    Base.metadata.create_all(bind=engine)
    ensure_job_cleaning_columns(engine)
    db_session = SessionLocal()
    try:
        importer = DataImporter(db_session)
        if args.template:
            output = importer.generate_template(args.template)
            print(f"导入模板已生成：{output}")
            return 0

        path = Path(args.file).expanduser().resolve()
        if args.type == "official":
            if path.suffix.lower() == ".json":
                print("错误：事业单位数据请使用 xlsx、xls 或 csv 文件。")
                return 2
            report = importer.import_official_from_file(path, dry_run=args.dry_run)
        elif path.suffix.lower() == ".json":
            report = importer.import_from_json(path, source=args.source, dry_run=args.dry_run)
        else:
            report = importer.import_from_file(path, source=args.source, dry_run=args.dry_run)

        print_preview(report)
        print("\n导入报告：")
        report_without_preview = dict(report)
        report_without_preview.pop("preview", None)
        report_without_preview.pop("column_mapping", None)
        print(json.dumps(report_without_preview, ensure_ascii=False, indent=2, default=str))
        if report.get("error_file"):
            print(f"\n失败行已保存：{report['error_file']}")
        return 0 if int(report.get("failed", 0)) == 0 else 2
    except (FileNotFoundError, ValueError, TypeError) as exc:
        db_session.rollback()
        print(f"导入参数或数据错误：{exc}")
        return 2
    except Exception as exc:
        db_session.rollback()
        print(f"导入失败：{type(exc).__name__}: {exc}")
        return 1
    finally:
        db_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
