"""SQLite 数据库在线备份、gzip 压缩和历史备份清理工具。"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402


DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backups"


def configure_console() -> None:
    """在 Windows 等环境中使用 UTF-8 输出中文备份结果。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def resolve_sqlite_path(database_url: str | None = None) -> Path:
    """从 SQLAlchemy URL 解析本地 SQLite 文件绝对路径。"""

    url = make_url(database_url or settings.database_url)
    if not url.drivername.startswith("sqlite"):
        raise ValueError("backup.py 仅支持 SQLite；PostgreSQL 请使用 pg_dump")
    database = url.database
    if not database or database == ":memory:":
        raise ValueError("内存 SQLite 数据库无法执行文件备份")
    path = Path(database)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def prune_backups(
    backup_dir: str | Path = DEFAULT_BACKUP_DIR, retention_days: int = 30
) -> list[str]:
    """删除修改时间早于保留期限的本工具备份，并返回删除文件名。"""

    directory = Path(backup_dir).resolve()
    if not directory.exists():
        return []
    cutoff = datetime.now().timestamp() - timedelta(days=max(retention_days, 1)).total_seconds()
    removed: list[str] = []
    for path in directory.glob("db_*.db.gz"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path.name)
    return removed


def create_backup(
    database_url: str | None = None,
    output_dir: str | Path = DEFAULT_BACKUP_DIR,
    retention_days: int = 30,
) -> dict[str, Any]:
    """使用 SQLite 在线备份 API 生成一致性副本并压缩为 gzip。"""

    source_path = resolve_sqlite_path(database_url)
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite 数据库不存在：{source_path}")
    backup_dir = Path(output_dir)
    if not backup_dir.is_absolute():
        backup_dir = PROJECT_ROOT / backup_dir
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = backup_dir / f"db_{timestamp}.db.gz"
    # 临时数据库与目标文件位于同一目录，replace 操作在同一文件系统内是原子的。
    with tempfile.NamedTemporaryFile(
        prefix="sqlite_backup_", suffix=".db", dir=backup_dir, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    compressed_temp = output_path.with_suffix(output_path.suffix + ".tmp")

    try:
        source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        destination = sqlite3.connect(temporary_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        with temporary_path.open("rb") as source_file, gzip.open(
            compressed_temp, "wb", compresslevel=6
        ) as target_file:
            shutil.copyfileobj(source_file, target_file, length=1024 * 1024)
        compressed_temp.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
        compressed_temp.unlink(missing_ok=True)

    removed = prune_backups(backup_dir, retention_days)
    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "size_mb": round(output_path.stat().st_size / 1024 / 1024, 2),
        "source": str(source_path),
        "retention_days": retention_days,
        "removed_old_backups": removed,
        "created_at": datetime.now().astimezone().isoformat(),
    }


def build_parser() -> argparse.ArgumentParser:
    """构建数据库备份命令行参数。"""

    parser = argparse.ArgumentParser(description="备份并压缩 GIS 就业情报站 SQLite 数据库。")
    parser.add_argument("--output-dir", default=str(DEFAULT_BACKUP_DIR), help="备份目录。")
    parser.add_argument("--retention-days", type=int, default=30, help="备份保留天数，默认 30。")
    return parser


def main() -> int:
    """执行备份并打印文件大小和路径。"""

    configure_console()
    args = build_parser().parse_args()
    try:
        result = create_backup(
            output_dir=args.output_dir, retention_days=max(args.retention_days, 1)
        )
        print(f"数据库备份完成：{result['path']}")
        print(f"压缩后大小：{result['size_mb']} MB（{result['size_bytes']} 字节）")
        if result["removed_old_backups"]:
            print(f"已清理 {len(result['removed_old_backups'])} 个过期备份。")
        return 0
    except Exception as exc:
        print(f"数据库备份失败：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
