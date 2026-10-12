/** 首页大盘视图。 */

import { api } from "../api.js";
import { axisStyle, createChart, emptyChart, formatNumber, palette } from "../utils.js";

export const title = "首页大盘";

/** 计算本月岗位数相对上月变化。 */
function monthChange(monthly) {
  if (!monthly || monthly.length < 2) return { text: "暂无上月对比", neutral: true };
  const previous = monthly.at(-2).job_count;
  const current = monthly.at(-1).job_count;
  if (!previous) return { text: current ? `本月新增 ${current} 条` : "本月暂无新增", neutral: !current };
  const rate = ((current - previous) / previous) * 100;
  return { text: `较上月 ${rate >= 0 ? "+" : ""}${rate.toFixed(1)}%`, neutral: false };
}

/** 渲染首页四类图表。 */
function renderCharts(cityData, salaryData, requirementData) {
  const cityChart = createChart("home-city-chart");
  if (!cityData.cities.length) emptyChart(cityChart);
  else cityChart.setOption({
    color: ["#2c5f8f"], tooltip: { trigger: "axis" }, grid: { left: 45, right: 14, top: 15, bottom: 55 },
    xAxis: { ...axisStyle(), type: "category", data: cityData.cities.map((item) => item.city), axisLabel: { ...axisStyle().axisLabel, rotate: 38 } },
    yAxis: { ...axisStyle(), type: "value", minInterval: 1 },
    series: [{ type: "bar", barMaxWidth: 26, data: cityData.cities.map((item) => item.job_count), itemStyle: { borderRadius: [5, 5, 0, 0] } }],
  });

  const typeChart = createChart("home-type-chart");
  const typeData = salaryData.by_job_type.filter((item) => item.count > 0).map((item) => ({ name: item.name, value: item.count }));
  if (!typeData.length) emptyChart(typeChart);
  else typeChart.setOption({
    color: typeData.map((_, index) => palette(index)), tooltip: { trigger: "item", formatter: "{b}<br>{c} 个岗位（{d}%）" },
    legend: { bottom: 0, textStyle: { color: "#637482", fontSize: 11 } },
    series: [{ type: "pie", radius: ["34%", "68%"], center: ["50%", "44%"], label: { formatter: "{b}\n{d}%", fontSize: 10 }, data: typeData }],
  });

  const salaryChart = createChart("home-salary-chart");
  const rangeTotal = salaryData.salary_ranges.reduce((sum, item) => sum + item.count, 0);
  if (!rangeTotal) emptyChart(salaryChart);
  else salaryChart.setOption({
    color: ["#4d89b7"], tooltip: { trigger: "axis" }, grid: { left: 45, right: 15, top: 15, bottom: 40 },
    xAxis: { ...axisStyle(), type: "category", data: salaryData.salary_ranges.map((item) => item.name) },
    yAxis: { ...axisStyle(), type: "value", minInterval: 1 },
    series: [{ type: "bar", data: salaryData.salary_ranges.map((item) => item.count), itemStyle: { borderRadius: [5, 5, 0, 0] } }],
  });

  const educationChart = createChart("home-education-chart");
  const education = requirementData.education_distribution.filter((item) => item.count > 0).map((item) => ({ name: item.name, value: item.count }));
  if (!education.length) emptyChart(educationChart);
  else educationChart.setOption({
    color: education.map((_, index) => palette(index)), tooltip: { trigger: "item", formatter: "{b}<br>{c} 个（{d}%）" },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{ name: "学历要求", type: "pie", radius: ["45%", "70%"], center: ["50%", "44%"], label: { formatter: "{b} {d}%", fontSize: 10 }, data: education }],
  });
}

/** 加载首页数据并渲染视图。 */
export async function render(root) {
  const [overview, cities, salary, requirements, trend] = await Promise.all([
    api.overview(), api.cityDistribution(15), api.salaryDistribution(), api.requirementAnalysis(), api.trend(2),
  ]);
  const change = monthChange(trend.monthly);
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">首页大盘</h1><p class="view-subtitle">快速了解 GIS、遥感与测绘就业市场的核心信号 · 数据更新至 ${overview.data_updated_at || '未知'}</p></div></header>
    <section class="metric-grid">
      <article class="metric-card"><span class="metric-label">有效岗位总数</span><strong class="metric-value">${formatNumber(overview.valid_jobs)}</strong><small class="metric-change ${change.neutral ? "neutral" : ""}">${change.text}</small></article>
      <article class="metric-card"><span class="metric-label">平均月薪</span><strong class="metric-value">${formatNumber(overview.average_salary, 1)}<em class="metric-unit">K / 月</em></strong><small class="metric-change neutral">中位数 ${formatNumber(overview.median_salary, 1)}K</small></article>
      <article class="metric-card"><span class="metric-label">覆盖城市</span><strong class="metric-value">${formatNumber(overview.active_cities)}</strong><small class="metric-change neutral">覆盖 ${formatNumber(overview.active_companies)} 家公司</small></article>
      <article class="metric-card"><span class="metric-label">事业单位计划招录</span><strong class="metric-value">${formatNumber(overview.official_planned_count)}</strong><small class="metric-change neutral">公开记录 ${formatNumber(overview.official_records)} 条</small></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><h2 class="panel-title">岗位城市分布 Top15</h2><span class="panel-note">按有效岗位数</span></div><div id="home-city-chart" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">岗位类型结构</h2><span class="panel-note">职能分类占比</span></div><div id="home-type-chart" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">薪资分布</h2><span class="panel-note">K / 月</span></div><div id="home-salary-chart" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">学历要求</h2><span class="panel-note">有效岗位占比</span></div><div id="home-education-chart" class="chart"></div></article>
    </section>`;
  renderCharts(cities, salary, requirements);
}
