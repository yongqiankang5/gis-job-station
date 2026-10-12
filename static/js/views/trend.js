/** 近 12 个月岗位、平均薪资和技能年度趋势视图。 */

import { api } from "../api.js";
import { axisStyle, createChart, emptyChart, palette } from "../utils.js";

export const title = "趋势分析";

/** 从年度技能数据挑选跨年度总频次最高的十项技能。 */
function commonTopSkills(groups) {
  const totals = {};
  groups.forEach((group) => group.skills.forEach((item) => { totals[item.name] = (totals[item.name] || 0) + item.count; }));
  return Object.entries(totals).sort((left, right) => right[1] - left[1]).slice(0, 10).map(([name]) => name);
}

/** 加载并渲染趋势分析。 */
export async function render(root) {
  const data = await api.trend(12);
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">趋势分析</h1><p class="view-subtitle">追踪岗位发布、平均薪资与核心技能的时间变化</p></div></header>
    <section class="panel"><div class="panel-header"><h2 class="panel-title">近 12 个月岗位与薪资变化</h2><span class="panel-note">双 Y 轴</span></div><div id="trend-monthly" class="chart tall"></div></section>
    <section class="panel" style="margin-top:16px"><div class="panel-header"><h2 class="panel-title">年度技能需求对比</h2><span class="panel-note">2024 / 2025 / 2026</span></div><div id="trend-skills" class="chart tall"></div></section>
    <p class="notice">基于抓取数据统计，可能存在样本偏差；趋势仅反映当前已收录数据，不代表完整就业市场。</p>`;

  const monthlyChart = createChart("trend-monthly");
  const hasMonthly = data.monthly.some((item) => item.job_count || item.average_salary != null);
  if (!hasMonthly) emptyChart(monthlyChart);
  else monthlyChart.setOption({
    color: [palette(0), palette(6)], tooltip: { trigger: "axis" }, legend: { bottom: 0 },
    grid: { left: 50, right: 55, top: 26, bottom: 52 },
    xAxis: { ...axisStyle(), type: "category", boundaryGap: false, data: data.monthly.map((item) => item.month) },
    yAxis: [{ ...axisStyle(), type: "value", name: "岗位数", minInterval: 1 }, { ...axisStyle(), type: "value", name: "K/月" }],
    series: [
      { name: "发布岗位数", type: "line", smooth: true, symbolSize: 7, areaStyle: { opacity: .1 }, data: data.monthly.map((item) => item.job_count) },
      { name: "平均薪资", type: "line", yAxisIndex: 1, smooth: true, symbolSize: 7, data: data.monthly.map((item) => item.average_salary) },
    ],
  });

  const skills = commonTopSkills(data.skill_year_comparison);
  const skillChart = createChart("trend-skills");
  if (!skills.length) emptyChart(skillChart);
  else skillChart.setOption({
    color: data.skill_year_comparison.map((_, index) => palette(index)), tooltip: { trigger: "axis" }, legend: { bottom: 0 },
    grid: { left: 48, right: 18, top: 25, bottom: 80 },
    xAxis: { ...axisStyle(), type: "category", data: skills, axisLabel: { rotate: 35 } }, yAxis: { ...axisStyle(), type: "value", minInterval: 1 },
    series: data.skill_year_comparison.map((group) => {
      const counts = Object.fromEntries(group.skills.map((item) => [item.name, item.count]));
      return { name: String(group.year), type: "bar", data: skills.map((skill) => counts[skill] || 0) };
    }),
  });
}
