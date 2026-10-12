"""数据库连接、会话及依赖注入配置。"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的声明基类。"""


# SQLite 需要关闭同线程检查；切换 PostgreSQL 时无需此参数。
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_job_cleaning_columns(target_engine: Engine = engine) -> None:
    """为旧版 jobs 表补充清洗字段；只增列，不删除或重建现有数据。"""

    inspector = inspect(target_engine)
    if "jobs" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("jobs")}
    # SQLite 与 PostgreSQL 对布尔默认值的字面量要求不同。
    boolean_default = "0" if target_engine.dialect.name == "sqlite" else "FALSE"
    definitions = {
        "city_level": "VARCHAR(16)",
        "salary_mid": "FLOAT",
        "quality_score": "INTEGER NOT NULL DEFAULT 0",
        "note": "TEXT",
        "raw_data": "JSON",
        "is_cleaned": f"BOOLEAN NOT NULL DEFAULT {boolean_default}",
        "cleaned_at": "DATETIME" if target_engine.dialect.name == "sqlite" else "TIMESTAMP WITH TIME ZONE",
    }
    with target_engine.begin() as connection:
        for column_name, definition in definitions.items():
            if column_name not in existing:
                connection.execute(
                    text(f"ALTER TABLE jobs ADD COLUMN {column_name} {definition}")
                )
        # 两个筛选字段建立索引；IF NOT EXISTS 同时受 SQLite/PostgreSQL 支持。
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_jobs_quality_score ON jobs (quality_score)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_jobs_is_cleaned ON jobs (is_cleaned)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_jobs_salary_mid ON jobs (salary_mid)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_jobs_city_level ON jobs (city_level)")
        )


def get_db() -> Generator[Session, None, None]:
    """为每次请求提供数据库会话，并在请求结束后自动关闭。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
