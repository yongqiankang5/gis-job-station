"""为本地演示环境生成 GIS / 遥感招聘与事业单位样例数据。"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

# 支持直接运行 ``python scripts/seed_demo_data.py``。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine, ensure_job_cleaning_columns  # noqa: E402
from app.models import Job, OfficialRecord  # noqa: E402
from app.services.cleaner import DataCleaner  # noqa: E402


CITIES = (
    ("北京", "北京", 1.35),
    ("上海", "上海", 1.32),
    ("深圳", "广东", 1.30),
    ("广州", "广东", 1.20),
    ("杭州", "浙江", 1.18),
    ("南京", "江苏", 1.12),
    ("武汉", "湖北", 1.00),
    ("成都", "四川", 1.02),
    ("西安", "陕西", 0.96),
    ("重庆", "重庆", 0.98),
    ("长沙", "湖南", 0.94),
    ("苏州", "江苏", 1.08),
)

JOB_TEMPLATES = (
    {
        "title": "WebGIS 开发工程师",
        "company": "星图空间科技有限公司",
        "company_type": "上市公司",
        "salary": (14, 24),
        "education": "本科及以上",
        "experience": "1-3年经验",
        "description": (
            "负责 WebGIS 平台的功能设计、前后端开发和性能优化，参与地图服务发布与空间数据库建设。"
            "要求熟悉 JavaScript、Leaflet、OpenLayers 或 Cesium，掌握 PostGIS、PostgreSQL 与 SQL，"
            "能够使用 Python、GDAL 和 GeoPandas 完成地理数据处理；理解 REST API、Linux 部署及常见投影坐标系。"
        ),
    },
    {
        "title": "遥感算法工程师",
        "company": "天巡遥感技术有限公司",
        "company_type": "民营",
        "salary": (18, 32),
        "education": "硕士研究生",
        "experience": "3-5年经验",
        "description": (
            "面向卫星影像开展地物分类、变化检测和目标识别算法研发，负责样本构建、模型训练、精度评价与工程化。"
            "要求熟练使用 Python、PyTorch、TensorFlow、Rasterio、GDAL 和 ENVI，理解深度学习、机器学习、"
            "随机森林与遥感成像原理；有 Google Earth Engine（GEE）或大规模栅格并行处理经验者优先。"
        ),
    },
    {
        "title": "GIS 数据处理工程师",
        "company": "经纬地理信息有限公司",
        "company_type": "民营",
        "salary": (8, 15),
        "education": "大专及以上",
        "experience": "1-3年",
        "description": (
            "承担基础地理数据入库、质量检查、空间拓扑处理和专题制图，配合完成自然资源调查成果整理。"
            "要求熟练使用 ArcGIS、QGIS、FME、GeoPandas、Shapely 和 SQL，了解 GDAL、Python 自动化脚本；"
            "能够独立处理矢量、栅格和坐标转换问题，具备严谨的数据质量意识和项目文档编写能力。"
        ),
    },
    {
        "title": "国土空间规划分析师",
        "company": "城市空间规划研究院",
        "company_type": "事业单位",
        "salary": (10, 18),
        "education": "硕士及以上",
        "experience": "应届/在校",
        "description": (
            "参与国土空间总体规划、用途管制和自然资源评价项目，开展空间分析、指标测算、成果制图与专题研究。"
            "要求掌握 ArcGIS、QGIS、Python、GeoPandas 和空间分析方法，了解土地资源管理、城市规划及生态评价；"
            "具备良好的研究报告写作、沟通汇报和跨专业协作能力，能够阅读政策文件与技术规程。"
        ),
    },
    {
        "title": "InSAR 形变监测工程师",
        "company": "自然资源调查监测集团",
        "company_type": "国企",
        "salary": (13, 23),
        "education": "本科",
        "experience": "3-5年",
        "description": (
            "负责 Sentinel-1 等 SAR 数据的干涉处理、时序形变反演和地质灾害监测，完成结果验证与报告编制。"
            "要求理解 InSAR 原理，熟悉 SNAP、ENVI、MATLAB、Python、Linux 和 Shell，能够处理轨道、DEM、"
            "相位解缠及大气误差问题；有矿区沉降、滑坡或城市地面沉降项目经验者优先。"
        ),
    },
    {
        "title": "三维 GIS / 点云算法工程师",
        "company": "云境数字孪生科技有限公司",
        "company_type": "民营",
        "salary": (16, 28),
        "education": "本科及以上",
        "experience": "3-5年经验",
        "description": (
            "负责 LiDAR 点云处理、三维场景重建和数字孪生可视化模块研发，建设城市级三维空间数据生产流程。"
            "要求掌握 C++、Python、JavaScript、Cesium、Three.js、WebGL 与点云算法，熟悉 GDAL、PostGIS、"
            "Linux 环境和常见三维格式；具备目标分割、配准、模型轻量化或 GPU 并行经验者优先。"
        ),
    },
)

OFFICIAL_UNITS = (
    ("自然资源部第一地理信息制图院", "中央", "陕西", "西安"),
    ("国家卫星海洋应用中心", "中央", "北京", "北京"),
    ("湖北省测绘工程院", "省", "湖北", "武汉"),
    ("四川省国土空间规划研究院", "省", "四川", "成都"),
    ("广东省国土资源测绘院", "省", "广东", "广州"),
    ("浙江省自然资源调查登记中心", "省", "浙江", "杭州"),
    ("江苏省测绘工程院", "省", "江苏", "南京"),
    ("山东省国土测绘院", "省", "山东", "济南"),
)


def _add_demo_jobs() -> int:
    """插入确定性的演示岗位，返回新增数量。"""

    today = date.today()
    created = 0
    with SessionLocal() as db:
        existing = db.scalar(select(func.count(Job.id)).where(Job.source == "demo")) or 0
        if existing:
            print(f"演示岗位已存在 {existing} 条，跳过重复生成。")
            return 0

        for city_index, (city, province, multiplier) in enumerate(CITIES):
            for template_index, template in enumerate(JOB_TEMPLATES):
                salary_min, salary_max = template["salary"]
                # 主样本覆盖近 12 个月，以便趋势图打开即有数据。
                age_days = (city_index * 23 + template_index * 11) % 350
                publish_date = today - timedelta(days=age_days)
                minimum = round(salary_min * multiplier, 1)
                maximum = round(salary_max * multiplier, 1)
                source_id = f"demo-{city_index:02d}-{template_index:02d}"
                db.add(
                    Job(
                        source="demo",
                        source_id=source_id,
                        job_title=str(template["title"]),
                        company_name=str(template["company"]),
                        company_type=str(template["company_type"]),
                        city=city,
                        province=province,
                        district=None,
                        salary_min=minimum,
                        salary_max=maximum,
                        salary_note=f"{minimum:g}-{maximum:g}K·13薪",
                        education=str(template["education"]),
                        experience=str(template["experience"]),
                        job_type="其他",
                        job_description=str(template["description"]),
                        skills=[],
                        publish_date=publish_date,
                        crawl_date=today,
                        url=f"https://example.com/gis-job/{source_id}",
                        is_valid=True,
                        note="演示数据：用于本地界面与接口验证，不代表真实招聘岗位。",
                    )
                )
                created += 1

        # 追加 2024—2025 年历史样本，为年度技能对比提供基线。
        for history_index in range(24):
            template = JOB_TEMPLATES[history_index % len(JOB_TEMPLATES)]
            city, province, multiplier = CITIES[history_index % len(CITIES)]
            year = 2024 if history_index < 12 else 2025
            month = history_index % 12 + 1
            salary_min, salary_max = template["salary"]
            source_id = f"demo-history-{history_index:02d}"
            minimum = round(salary_min * multiplier, 1)
            maximum = round(salary_max * multiplier, 1)
            db.add(
                Job(
                    source="demo",
                    source_id=source_id,
                    job_title=f"{template['title']}（历史样本）",
                    company_name=f"{template['company']}历史样本",
                    company_type=str(template["company_type"]),
                    city=city,
                    province=province,
                    salary_min=minimum,
                    salary_max=maximum,
                    salary_note=f"{minimum:g}-{maximum:g}K",
                    education=str(template["education"]),
                    experience=str(template["experience"]),
                    job_type="其他",
                    job_description=str(template["description"]),
                    skills=[],
                    publish_date=date(year, month, min(8 + history_index, 28)),
                    crawl_date=today,
                    url=f"https://example.com/gis-job/{source_id}",
                    is_valid=True,
                    note="演示历史数据：仅用于年度趋势展示。",
                )
            )
            created += 1

        db.commit()
        cleaner = DataCleaner(db)
        cleaner.clean_all(only_unprocessed=True)
        cleaner.deduplicate()
        cleaner.compute_quality_scores()
    return created


def _add_demo_official_records() -> int:
    """插入事业单位演示记录，返回新增数量。"""

    created = 0
    with SessionLocal() as db:
        existing = db.scalar(
            select(func.count(OfficialRecord.id)).where(
                OfficialRecord.source_url.like("https://example.com/official-demo/%")
            )
        ) or 0
        if existing:
            print(f"演示招录记录已存在 {existing} 条，跳过重复生成。")
            return 0

        for year in (2024, 2025, 2026):
            for index, (unit, level, province, city) in enumerate(OFFICIAL_UNITS):
                planned = 2 + (index + year) % 5
                actual = max(1, planned - ((index + year) % 2))
                candidates = [
                    {
                        "name": f"示例人员{year % 100:02d}{index:02d}{number:02d}",
                        "school": ("武汉大学", "中国地质大学", "南京师范大学", "中南大学")[
                            (index + number) % 4
                        ],
                        "major": ("地图学与地理信息系统", "摄影测量与遥感", "测绘工程")[
                            (index + number) % 3
                        ],
                    }
                    for number in range(actual)
                ]
                db.add(
                    OfficialRecord(
                        unit_name=unit,
                        unit_level=level,
                        province=province,
                        city=city,
                        job_title=("遥感监测技术岗", "地理信息管理岗", "测绘成果质检岗")[index % 3],
                        planned_count=planned,
                        actual_count=actual,
                        major_requirement="地图学与地理信息系统、摄影测量与遥感、测绘工程等相关专业",
                        education="硕士" if index % 3 == 0 else "本科",
                        hired_candidates=candidates,
                        year=year,
                        source_url=f"https://example.com/official-demo/{year}/{index}",
                    )
                )
                created += 1
        db.commit()
    return created


def main() -> int:
    """初始化数据库、生成演示数据并输出结果。"""

    Base.metadata.create_all(bind=engine)
    ensure_job_cleaning_columns(engine)
    jobs = _add_demo_jobs()
    official = _add_demo_official_records()
    print(f"演示数据准备完成：新增岗位 {jobs} 条，事业单位记录 {official} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
