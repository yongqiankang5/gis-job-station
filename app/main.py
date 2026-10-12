"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine, ensure_job_cleaning_columns
from app.routers import jobs, official, stats
from app.schemas import HealthResponse
from app.services.scheduler import JobScheduler, TaskAlreadyRunning

# 以项目目录为基准定位静态资源，避免从其他目录启动时报错。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """初始化数据库和可选调度器，并在退出时释放后台资源。"""

    Base.metadata.create_all(bind=engine)
    ensure_job_cleaning_columns(engine)
    job_scheduler = JobScheduler()
    application.state.job_scheduler = job_scheduler
    application.state.scheduler_started = False
    if settings.enable_scheduler:
        application.state.scheduler_started = job_scheduler.start()
    try:
        yield
    finally:
        job_scheduler.shutdown()


app = FastAPI(
    title=settings.app_name,
    description="GIS 与遥感招聘信息聚合、筛选和需求分析 API",
    version="0.1.0",
    lifespan=lifespan,
)

# 允许配置中的前端来源访问 API。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(official.router, prefix="/api")


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    """将根路径重定向到静态首页。"""

    return RedirectResponse(url="/index.html")


@app.get("/api/health", response_model=HealthResponse, tags=["系统"])
def health() -> HealthResponse:
    """返回应用健康状态。"""

    return HealthResponse(status="ok", app=settings.app_name)


def _scheduler_from_request(request: Request) -> JobScheduler:
    """从应用状态取得调度服务，缺失时返回可读的 503 错误。"""

    scheduler = getattr(request.app.state, "job_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="调度服务尚未初始化")
    return scheduler


@app.post("/api/admin/run-scraper", tags=["管理"])
def run_scraper(
    request: Request,
    source: Literal["boss", "official", "all"] = Query(
        default="all", description="抓取来源：boss、official 或 all"
    ),
) -> dict[str, Any]:
    """后台触发指定来源抓取；跨进程锁会阻止重复执行。"""

    task_ids = {
        "boss": "boss_incremental",
        "official": "official_update",
        "all": "scraper_all",
    }
    try:
        return _scheduler_from_request(request).run_job_now(task_ids[source])
    except TaskAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/scheduler-status", tags=["管理"])
def scheduler_status(request: Request) -> dict[str, Any]:
    """返回周期任务、下次运行时间和最近一次手动或定时执行结果。"""

    result = _scheduler_from_request(request).get_job_status()
    result["configured_enabled"] = settings.enable_scheduler
    return result


@app.post("/api/admin/clean", tags=["管理"])
def run_clean(request: Request) -> dict[str, Any]:
    """后台触发岗位清洗、重复合并和质量评分。"""

    try:
        return _scheduler_from_request(request).run_job_now("clean_data")
    except TaskAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# 必须在 API 路由之后挂载，避免静态路由吞掉 API 请求。
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
