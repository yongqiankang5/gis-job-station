# GIS 遥感就业情报站

一个面向 GIS、遥感、测绘与空间信息从业者的招聘情报基础项目。项目统一存储多平台岗位和事业单位招录记录，提供组合筛选、城市空间分布、技能热度与岗位类型统计，并预留真实抓取器的扩展接口。

## 技术组成

- 后端：Python 3.10+、FastAPI、Uvicorn
- 数据层：SQLAlchemy 2 ORM、SQLite（可迁移至 PostgreSQL）
- 数据分析：pandas
- 前端：静态 HTML、CSS、原生 JavaScript、ECharts、Leaflet
- 配置：pydantic-settings、python-dotenv
- 中文分词：jieba（技能复合词识别）

## 目录结构

```text
gis-job-tracker/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 环境配置
│   ├── database.py          # 数据库连接与会话
│   ├── models.py            # ORM 数据模型
│   ├── schemas.py           # API 响应结构
│   ├── routers/             # 岗位、统计、事业单位 API
│   ├── services/            # 抓取、清洗与分析服务
│   └── utils/keywords.py    # GIS / 遥感关键词词典
├── data/raw/                # 原始抓取数据
├── data/processed/          # 清洗后数据
├── static/                  # 静态首页资源
├── requirements.txt
└── .env.example
```

## 安装

以下命令在项目根目录执行。

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

请在正式使用前修改 `.env` 中的 `SECRET_KEY`。`CORS_ORIGINS` 使用 JSON 数组格式。
如需启用 5 分钟统计缓存，可将 `REDIS_URL` 配置为 `redis://localhost:6379/0`；留空时自动使用数据库实时统计。

## 运行

### Windows 一键启动

依赖已安装时，直接双击项目根目录中的 `启动小程序.bat`。程序会自动打开浏览器，关闭命令窗口即可停止服务。

如果需要先载入界面演示数据，可执行：

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
```

演示数据使用 `demo` 来源标识，所有姓名和链接均为虚构示例，便于在真实抓取数据尚未导入时体验完整功能。

### 命令行启动

```bash
uvicorn app.main:app --reload
```

打开以下地址：

- 首页：<http://127.0.0.1:8000/>
- 交互式 API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

应用首次启动时会自动创建 `data/gis_jobs.db` 及所需数据表。初始数据库为空，因此页面会显示空状态。

### 数据清洗

```bash
# 默认：仅清洗未处理岗位，然后执行去重和质量评分
python scripts/run_clean.py

# 重新清洗所有岗位
python scripts/run_clean.py --all

# 只执行去重或评分
python scripts/run_clean.py --dedup
python scripts/run_clean.py --score
```

首次清洗会把原始字段保存到 `jobs.raw_data`，重复岗位仅标记为无效，不会删除。

### BOSS 登录后抓取

当浏览器没有登录、登录状态过期，或岗位接口返回验证页面时，使用可见浏览器登录模式：

```powershell
.\.venv\Scripts\python.exe scripts\run_boss_scraper.py --login-first --keywords "GIS" --cities "北京" --max-pages 1
```

程序会打开并最大化 BOSS 官方登录页。完成登录后回到终端按回车，程序才会开始抓取。登录或验证期间不要使用 `--headless`。

## 主要 API

- `GET /api/jobs`：按关键词、省市、学历、经验、岗位类型、最低薪资、最低质量分和技能筛选岗位
- `GET /api/jobs/{job_id}`：岗位详情
- `GET /api/stats/overview`：首页概览
- `GET /api/stats/skills`：技能需求频次
- `GET /api/stats/job-types`：岗位类型分布
- `GET /api/stats/cities`：城市岗位排行
- `GET /api/stats/map`：地图用省市聚合数据
- `GET /api/stats/city-distribution`：城市、省份、平均薪资与岗位密度
- `GET /api/stats/salary-distribution`：薪资区间及分组平均薪资
- `GET /api/stats/skill-analysis`：技能频次、共现和薪资溢价
- `GET /api/stats/requirement-analysis`：学历与经验要求分析
- `GET /api/stats/company-analysis`：公司需求和公司类型对比
- `GET /api/stats/official-analysis`：事业单位招录综合分析
- `GET /api/stats/trend`：近 12 个月岗位、薪资和技能趋势
- `GET /api/official`：事业单位招录记录筛选与分页
- `GET /api/jobs/export`：按当前岗位筛选条件导出 CSV

## 后续扩展

1. 在 `app/services/scraper.py` 的 `BaseScraper` 基础上为各来源实现独立抓取器。
2. 抓取结果先保存到 `data/raw/`，通过 `DataCleaner` 标准化、去重并评分。
3. 为城市补充经纬度字段或独立行政区划表，替换前端的基础城市坐标表。
4. 迁移 PostgreSQL 时修改 `DATABASE_URL` 并安装对应驱动；生产项目建议再引入 Alembic 管理数据库版本。

> 请遵守招聘平台服务条款、robots 协议、访问频率限制及个人信息保护相关规定。本项目的抓取模块仅提供接口骨架。
