/** 薪资区间、学历箱线、经验、城市和公司类型对比视图。 */

import { api, getAllJobs } from "../api.js";
import { axisStyle, boxplotValues, createChart, emptyChart, groupBy, median, palette } from "../utils.js";

export const title = "薪资分析";

/** 渲染薪资分析视图。 */
export async function render(root) {
  const [salary, cities, jobs] = await Promise.all([api.salaryDistribution(), api.cityDistribution(100), getAllJobs({}, 2000)]);
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">薪资分析</h1><p class="view-subtitle">比较不同学历、经验、城市和公司性质的薪资水平</p></div></header>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><h2 class="panel-title">薪资分布</h2><span class="panel-note">K / 月</span></div><div id="salary-range-chart" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">学历薪资箱线图</h2><span class="panel-note">最小值 / 四分位 / 中位数 / 最大值</span></div><div id="salary-education-box" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">经验薪资对比</h2><span class="panel-note">平均 K / 月</span></div><div id="salary-experience-chart" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">Top15 高薪城市</h2><span class="panel-note">城市平均薪资</span></div><div id="salary-city-chart" class="chart tall"></div></article>
      <article class="panel span-full"><div class="panel-header"><h2 class="panel-title">公司类型薪资对比</h2><span class="panel-note">平均薪资 vs 中位数</span></div><div id="salary-company-chart" class="chart"></div></article>
    </section>`;

  const range = createChart("salary-range-chart");
  if (!salary.salary_ranges.some((item) => item.count)) emptyChart(range);
  else range.setOption({
    color: ["#4d89b7"], tooltip: { trigger: "axis" }, grid: { left: 45, right: 14, top: 16, bottom: 42 },
    xAxis: { ...axisStyle(), type: "category", data: salary.salary_ranges.map((item) => item.name) }, yAxis: { ...axisStyle(), type: "value", minInterval: 1 },
    series: [{ type: "bar", data: salary.salary_ranges.map((item) => item.count), itemStyle: { borderRadius: [5, 5, 0, 0] } }],
  });

  const educationOrder = ["大专", "本科", "硕士", "博士"];
  const educationGroups = groupBy(jobs.filter((job) => job.salary_mid != null), "education");
  const boxData = educationOrder.map((name) => boxplotValues((educationGroups[name] || []).map((job) => job.salary_mid)));
  const box = createChart("salary-education-box");
  if (!boxData.some(Boolean)) emptyChart(box);
  else box.setOption({
    color: ["#2c5f8f"], tooltip: { trigger: "item" }, grid: { left: 46, right: 15, top: 20, bottom: 38 },
    xAxis: { ...axisStyle(), type: "category", data: educationOrder }, yAxis: { ...axisStyle(), type: "value", name: "K/月" },
    series: [{ type: "boxplot", data: boxData.map((item) => item || [0, 0, 0, 0, 0]) }],
  });

  const experience = createChart("salary-experience-chart");
  const expData = salary.by_experience.filter((item) => item.average_salary != null);
  if (!expData.length) emptyChart(experience);
  else experience.setOption({
    color: ["#3f8f73"], tooltip: { trigger: "axis" }, grid: { left: 48, right: 15, top: 16, bottom: 55 },
    xAxis: { ...axisStyle(), type: "category", data: expData.map((item) => item.name), axisLabel: { rotate: 30 } }, yAxis: { ...axisStyle(), type: "value", name: "K/月" },
    series: [{ type: "bar", data: expData.map((item) => item.average_salary), itemStyle: { borderRadius: [5, 5, 0, 0] } }],
  });

  const highCities = cities.cities.filter((item) => item.average_salary != null).sort((a, b) => b.average_salary - a.average_salary).slice(0, 15).reverse();
  const cityChart = createChart("salary-city-chart");
  if (!highCities.length) emptyChart(cityChart);
  else cityChart.setOption({
    color: ["#e7854d"], tooltip: { trigger: "axis" }, grid: { left: 72, right: 30, top: 15, bottom: 28 },
    xAxis: { ...axisStyle(), type: "value", name: "K/月" }, yAxis: { ...axisStyle(), type: "category", data: highCities.map((item) => item.city) },
    series: [{ type: "bar", data: highCities.map((item) => item.average_salary), itemStyle: { borderRadius: [0, 5, 5, 0] } }],
  });

  const companyTypes = ["国企", "民营", "上市公司", "事业单位"];
  const typeGroups = groupBy(jobs.filter((job) => job.salary_mid != null), "company_type");
  const companyData = companyTypes.map((name) => {
    const values = (typeGroups[name] || []).map((job) => job.salary_mid);
    return { name, average: values.length ? Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2)) : null, median: median(values) };
  });
  const company = createChart("salary-company-chart");
  if (!companyData.some((item) => item.average != null)) emptyChart(company);
  else company.setOption({
    color: [palette(0), palette(6)], tooltip: { trigger: "axis" }, legend: { bottom: 0 }, grid: { left: 48, right: 18, top: 20, bottom: 50 },
    xAxis: { ...axisStyle(), type: "category", data: companyTypes }, yAxis: { ...axisStyle(), type: "value", name: "K/月" },
    series: [{ name: "平均薪资", type: "bar", data: companyData.map((item) => item.average) }, { name: "中位数", type: "bar", data: companyData.map((item) => item.median) }],
  });
}
