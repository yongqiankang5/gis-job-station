# GIS 遥感就业情报站：AI 继续开发交接说明

> 交接日期：2026-09-08  
> 项目状态：本地 Web 版可运行，尚未转换为原生微信小程序。

## 1. 项目目标

本项目聚合 GIS、遥感、测绘、空间信息和自然资源领域的招聘信息，提供岗位筛选、城市空间分布、技能需求、薪资、学历经验、企业和事业单位招录分析。

## 2. 当前数据快照

| 指标 | 当前值 |
|---|---:|
| 岗位总数 | 2259 |
| 有效岗位 | 2237 |
| BOSS 来源岗位 | 2163 |
| 演示岗位 | 96 |
| 有效岗位覆盖城市 | 34 |
| 事业单位记录 | 24 |
| 事业单位真实结构化记录 | 0 |
| 原数据库抓取日志 | 243 |
| 最近岗位抓取日期 | 2026-09-01 |

重要说明：事业单位采集器已经保存了大量政府网站原始页面到 `data/raw/official/`，但当前结构化入库的 24 条记录仍全部是演示数据。AI 交接包为降低隐私和噪声，不附带全部原始网页，也会清空数据快照中的 `crawl_logs`。

## 3. 技术架构

```text
BOSS / 政府公开网站 / Excel、CSV、JSON
                 │
                 ▼
        抓取器与手动导入工具
                 │
                 ▼
      清洗、标准化、去重、质量评分
                 │
                 ▼
        SQLAlchemy ORM + SQLite
                 │
                 ▼
              FastAPI
                 │
                 ▼
 原生 HTML/CSS/JavaScript + ECharts + Leaflet
```

后端使用 Python 3.10+、FastAPI、Uvicorn、SQLAlchemy、pandas 和 pydantic-settings。SQLite 可通过修改 `DATABASE_URL` 迁移到 PostgreSQL。前端为无构建工具的单页应用。

## 4. 主要目录

```text
app/
├── main.py                  FastAPI 入口、静态文件和管理接口
├── config.py                环境配置
├── database.py              数据库连接及兼容性补列
├── models.py                Job、OfficialRecord、CrawlLog
├── schemas.py               Pydantic 响应结构
├── routers/
│   ├── jobs.py              岗位筛选、详情、CSV 导出
│   ├── stats.py             统计分析接口
│   └── official.py          事业单位接口
├── services/
│   ├── scraper_boss.py      DrissionPage BOSS 抓取器
│   ├── scraper_official.py  政府网站采集器
│   ├── cleaner.py           清洗、技能提取、去重、评分
│   ├── analyzer.py          统计分析服务
│   ├── importer.py          Excel/CSV/JSON 导入
│   └── scheduler.py         APScheduler 定时任务
└── utils/                   关键词、城市、省厅配置

static/
├── index.html
├── css/style.css
└── js/
    ├── app.js、api.js、utils.js、city_coords.js
    └── views/               首页、岗位、地图、技能、薪资、事业、趋势

scripts/
├── run_boss_scraper.py
├── run_official_scraper.py
├── run_clean.py
├── import_data.py
├── add_job.py
├── update_all.py
├── backup.py
└── seed_demo_data.py
```

## 5. 已完成功能

### 数据采集与处理

- BOSS 可见 Chromium 浏览器抓取，监听正常岗位接口；
- 支持 `--login-first`，登录失效或非 JSON 响应时暂停等待人工验证；
- 36 个 BOSS 城市编码；
- 政府网站列表页发现、详情页和 HTML 表格解析；
- Excel、CSV、JSON 岗位导入和事业单位 Excel 导入；
- 城市、省份、薪资、学历、经验和公司类型标准化；
- 技能标签提取、跨平台去重和 0～100 质量评分；
- 数据备份、定时任务和更新脚本。

### API

- `GET /api/jobs`：分页与组合筛选；
- `GET /api/jobs/export`：筛选结果 CSV；
- `GET /api/jobs/{id}`：岗位详情；
- `GET /api/stats/overview`；
- `GET /api/stats/city-distribution`；
- `GET /api/stats/salary-distribution`；
- `GET /api/stats/skill-analysis`；
- `GET /api/stats/requirement-analysis`；
- `GET /api/stats/company-analysis`；
- `GET /api/stats/official-analysis`；
- `GET /api/stats/trend`；
- `GET /api/official`、`/api/official/stats`、`/api/official/{id}`；
- `/api/admin/*`：抓取、清洗和调度状态。

### 前端

- 首页统计大盘；
- 岗位查询、筛选、分页和详情展开；
- Leaflet 城市岗位地图；
- 技能词云、共现、溢价和类型热力图；
- 薪资分布、学历、经验和高薪城市分析；
- 事业单位统计和列表；
- 近 12 个月趋势分析；
- 响应式布局、加载状态、空状态和错误提示。

## 6. 快速运行

Windows 首次使用：双击 `首次安装并启动.bat`。后续使用：双击 `启动小程序.bat`。

命令行方式：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问：

- 首页：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

## 7. 数据更新命令

先登录再做小范围 BOSS 测试：

```powershell
.\.venv\Scripts\python.exe scripts\run_boss_scraper.py --login-first --keywords "GIS" --cities "北京" --max-pages 1
```

扩大范围时应分批、低频执行，不要绕过验证码、加密或访问限制。

事业单位采集：

```powershell
.\.venv\Scripts\python.exe scripts\run_official_scraper.py --source all --years "2024,2025,2026"
```

清洗、去重和评分：

```powershell
.\.venv\Scripts\python.exe scripts\run_clean.py
```

## 8. 已知问题与风险

### P0：公开部署前必须处理

1. `/api/admin/*` 当前没有身份认证，部署公网前必须增加管理员鉴权、CSRF/重放保护和访问审计。
2. 当前没有 Alembic 数据库迁移，仍通过启动时补列兼容；应补迁移基线。
3. 缺少自动化测试和持续集成；至少需要服务层单元测试、API 集成测试和前端烟雾测试。
4. 正式环境必须使用新的 `SECRET_KEY`，不得提交 `.env`。
5. BOSS 页面和接口随时可能变化；仅允许使用真实浏览器正常访问和人工验证，不应绕过反爬措施。
6. 招聘数据再分发、公开发布及小程序类目可能涉及平台条款、著作权、个人信息和人力资源服务资质，应在上线前完成合规评估。

### P1：数据质量

1. 96 条 `source=demo` 岗位需要在生产数据中移除或默认隐藏。
2. 事业单位原始网页很多，但表格识别和字段映射未形成真实入库结果；应针对附件 Excel、Word、PDF 建立解析管线。
3. BOSS 列表接口通常没有完整 JD，导致技能提取和质量评分偏弱；可在遵守访问频率的前提下补充详情，但不能扩大为高频抓取。
4. 公司类型从规模和阶段推断，准确性有限。
5. 部分发布日期为空，应区分“未提供”和“抓取日期”。

### P2：工程与体验

1. ECharts、wordcloud、Leaflet 使用外部 CDN，离线或网络受限时图表可能不可用；建议改为本地静态依赖。
2. SQLite 适合单机，公开多实例部署建议 PostgreSQL。
3. Redis 是可选缓存，目前未配置时直接查询数据库。
4. 调度器默认关闭；多进程部署时不能在每个 Web worker 内重复启动调度任务。
5. 建议增加岗位收藏、失效反馈、筛选条件保存、数据更新时间和来源可信度展示。

## 9. 建议的开发路线图

### 第一里程碑：可信数据版

- 增加测试和 Alembic；
- 增加管理员鉴权；
- 生产视图排除演示数据；
- 修复事业单位真实数据入库；
- 增加数据源、抓取批次和失败原因仪表板；
- 为岗位增加 `last_seen_at` 和失效判断。

验收标准：所有核心 API 测试通过，首页统计只使用真实有效数据，事业单位至少有一个真实来源可稳定入库。

### 第二里程碑：分享与部署版

- 前端第三方依赖本地化；
- PostgreSQL + Alembic；
- Nginx/HTTPS 或受管平台部署；
- 管理接口仅内网或管理员可用；
- 日志脱敏、备份恢复演练、健康检查和限流。

验收标准：全新环境一键启动，连续运行 7 天，无重复调度和数据损坏，备份可恢复。

### 第三里程碑：微信小程序版

若不购买服务器，推荐“静态快照版”：

```text
本地抓取和清洗 → 导出精简 JSON → 原生微信小程序读取本地 JSON → 更新时重新提交版本
```

首版页面建议：

- 首页；
- 岗位列表与详情；
- 城市地图；
- 事业单位；
- 综合分析。

不要直接把 FastAPI、SQLite 或抓取器放入小程序客户端。小程序只承载展示数据；抓取仍在授权电脑上低频运行。

## 10. 交给下一个模型时的工作约束

- 先完整阅读本文件、`README.md`、`app/models.py` 和相关模块；
- 不删除或覆盖现有数据库，修改前先生成 SQLite 备份；
- 工作目录可能没有 Git，不得假设可以回滚；
- 不提交 `.env`、Cookie、浏览器用户目录或真实密钥；
- 保持中文注释和函数 docstring；
- 所有修改必须执行编译检查和与风险相称的运行验证；
- 不把演示数据描述为真实招聘数据；
- 不尝试破解验证码、加密参数或其他反爬措施；
- 不把 Docker 作为默认前置条件，除非用户明确要求。

## 11. 推荐下一步

优先完成“真实数据可信版”，再制作原生微信小程序。具体顺序：

1. 建立测试基线；
2. 隐藏或移除演示数据；
3. 修复事业单位附件解析和真实入库；
4. 增加管理员鉴权；
5. 导出适合微信小程序包体的精简 JSON；
6. 创建 `miniprogram/` 原生前端骨架。

