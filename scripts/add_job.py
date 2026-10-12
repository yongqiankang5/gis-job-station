"""交互式添加单条招聘岗位。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine, ensure_job_cleaning_columns  # noqa: E402
from app.services.importer import DataImporter  # noqa: E402


def configure_console() -> None:
    """在支持的终端中启用 UTF-8，确保粘贴和显示中文 JD 稳定。"""

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def prompt_required(label: str) -> str:
    """循环读取必填文本，直到用户输入非空值。"""

    while True:
        value = input(f"{label}（必填）：").strip()
        if value:
            return value
        print(f"{label}不能为空，请重新输入。")


def prompt_optional(label: str) -> str:
    """读取可选的单行文本。"""

    return input(f"{label}（可留空）：").strip()


def prompt_multiline() -> str:
    """读取可从剪贴板粘贴的多行 JD，以单独一行 END 结束。"""

    print("职位描述：可直接粘贴多行 JD；完成后另起一行输入 END。")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def collect_job_data() -> dict[str, str]:
    """按步骤收集一条岗位的用户输入。"""

    return {
        "职位名称": prompt_required("职位名称"),
        "公司名称": prompt_required("公司名称"),
        "城市": prompt_required("城市"),
        "薪资": prompt_optional("薪资，如 15-25K·14薪"),
        "学历要求": prompt_optional("学历"),
        "经验要求": prompt_optional("经验"),
        "技能标签": prompt_optional("技能标签，用逗号、分号或空格分隔"),
        "职位描述": prompt_multiline(),
    }


def main() -> int:
    """显示输入确认信息，并在用户同意后清洗和保存岗位。"""

    configure_console()
    print("GIS 遥感就业情报站 · 单条岗位添加")
    print("按提示输入岗位信息，Ctrl+C 可随时取消。\n")
    try:
        job_data = collect_job_data()
        print("\n请确认以下信息：")
        print(json.dumps(job_data, ensure_ascii=False, indent=2))
        if input("\n确认保存？输入 y 保存：").strip().casefold() not in {"y", "yes"}:
            print("已取消，未写入数据。")
            return 0

        Base.metadata.create_all(bind=engine)
        ensure_job_cleaning_columns(engine)
        db_session = SessionLocal()
        try:
            report = DataImporter(db_session).add_single(job_data, source="manual")
            if report.get("skipped"):
                print(f"未重复添加：{report.get('reason')}，已有岗位 ID={report.get('existing_job_id')}。")
                return 0
            print("岗位已保存并完成自动清洗：")
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            return 0
        finally:
            db_session.close()
    except KeyboardInterrupt:
        print("\n已取消，未写入数据。")
        return 130
    except (ValueError, TypeError) as exc:
        print(f"输入数据有误：{exc}")
        return 2
    except Exception as exc:
        print(f"保存失败：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
