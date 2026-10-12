"""导出微信小程序静态快照数据：分片岗位列表 + 统计JSON。

用法：
    python scripts/export_miniprogram_data.py

输出到 miniprogram/data/ 目录：
    - overview.json        总览统计
    - cities.json          城市分布
    - salary.json          薪资分布
    - skills.json          技能分析
    - trend.json           趋势数据
    - official.json        事业单位数据
    - jobs_0.json, jobs_1.json...  岗位分片，每500条一个文件
    - manifest.json        数据清单（总条数、分片数、更新时间）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 把项目根目录加入模块搜索路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.analyzer import JobAnalyzer
from app.models import Job
from sqlalchemy import select


PAGE_SIZE = 500  # 每个分片文件最多岗位数


def export_jobs(db, output_dir: Path) -> dict:
    """导出岗位列表为分片JSON，返回清单信息。"""
    jobs = list(db.scalars(
        select(Job)
        .where(Job.is_valid.is_(True), Job.source != "demo")
        .order_by(Job.publish_date.desc().nullslast(), Job.id.desc())
    ))

    total = len(jobs)
    chunks = [jobs[i:i+PAGE_SIZE] for i in range(0, total, PAGE_SIZE)]

    for idx, chunk in enumerate(chunks):
        items = []
        for job in chunk:
            items.append({
                "id": job.id,
                "title": job.job_title,
                "company": job.company_name,
                "city": job.city,
                "province": job.province,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_note": job.salary_note,
                "education": job.education,
                "experience": job.experience,
                "job_type": job.job_type,
                "skills": job.skills or [],
                "publish_date": str(job.publish_date) if job.publish_date else None,
                "url": job.url,
                "quality_score": job.quality_score,
            })
        with open(output_dir / f"jobs_{idx}.json", "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, separators=(",", ":"))

    return {
        "total_jobs": total,
        "chunk_count": len(chunks),
        "chunk_size": PAGE_SIZE,
    }


def export_stats(db, output_dir: Path) -> None:
    """导出所有统计数据为独立JSON文件。"""
    analyzer = JobAnalyzer(db)

    # 总览
    overview = analyzer.get_overview()
    with open(output_dir / "overview.json", "w", encoding="utf-8") as f:
        json.dump(overview, f, ensure_ascii=False, separators=(",", ":"))

    # 城市分布
    cities = analyzer.get_city_distribution(50)
    with open(output_dir / "cities.json", "w", encoding="utf-8") as f:
        json.dump(cities, f, ensure_ascii=False, separators=(",", ":"))

    # 薪资分布
    salary = analyzer.get_salary_distribution()
    with open(output_dir / "salary.json", "w", encoding="utf-8") as f:
        json.dump(salary, f, ensure_ascii=False, separators=(",", ":"))

    # 技能分析
    skills = analyzer.get_skill_analysis(30)
    with open(output_dir / "skills.json", "w", encoding="utf-8") as f:
        json.dump(skills, f, ensure_ascii=False, separators=(",", ":"))

    # 趋势
    trend = analyzer.get_trend(12)
    with open(output_dir / "trend.json", "w", encoding="utf-8") as f:
        json.dump(trend, f, ensure_ascii=False, separators=(",", ":"))

    # 事业单位分析
    official = analyzer.get_official_analysis()
    with open(output_dir / "official.json", "w", encoding="utf-8") as f:
        json.dump(official, f, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    output_dir = ROOT / "miniprogram" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        print("导出统计数据...")
        export_stats(db, output_dir)

        print("导出岗位分片...")
        job_info = export_jobs(db, output_dir)

        # 生成manifest清单
        manifest = {
            **job_info,
            "data_updated_at": None,
        }
        # 从overview里拿更新时间
        with open(output_dir / "overview.json", "r", encoding="utf-8") as f:
            overview = json.load(f)
            manifest["data_updated_at"] = overview.get("data_updated_at")

        with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        print(f"导出完成：{job_info['total_jobs']} 条岗位，分成 {job_info['chunk_count']} 个文件")
        print(f"输出目录：{output_dir}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
