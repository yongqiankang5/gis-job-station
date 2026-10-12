/** 技能词云、共现、薪资溢价和岗位类型热力图视图。 */

import { api, getAllJobs } from "../api.js";
import { axisStyle, createChart, emptyChart, palette } from "../utils.js";

export const title = "技能分析";

/** 计算岗位类型 × Top 技能的岗位出现率。 */
function heatmapData(jobs, skills) {
  const types = [...new Set(jobs.map((job) => job.job_type || "其他"))].sort();
  const data = [];
  types.forEach((type, y) => {
    const group = jobs.filter((job) => (job.job_type || "其他") === type);
    skills.forEach((skill, x) => {
      const count = group.filter((job) => (job.skills || []).includes(skill)).length;
      data.push([x, y, group.length ? Number((count / group.length * 100).toFixed(1)) : 0]);
    });
  });
  return { types, data };
}

/** 加载技能分析并渲染四类图表。 */
export async function render(root) {
  const [analysis, jobs] = await Promise.all([api.skillAnalysis(30), getAllJobs({}, 2000)]);
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">技能分析</h1><p class="view-subtitle">识别市场高频技能、技术组合和潜在薪资溢价</p></div></header>
    <section class="panel"><div class="panel-header"><h2 class="panel-title">Top30 技能词云</h2><span class="panel-note">字号代表岗位出现频次</span></div><div id="skill-wordcloud" class="chart tall"></div></section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><h2 class="panel-title">技能共现关系</h2><span class="panel-note">Top15 技能</span></div><div id="skill-graph" class="chart tall"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">高溢价技能</h2><span class="panel-note">相对总体平均薪资</span></div><div id="skill-premium" class="chart tall"></div></article>
      <article class="panel span-full"><div class="panel-header"><h2 class="panel-title">岗位类型技能需求热力图</h2><span class="panel-note">技能在该类型岗位中的出现率 %</span></div><div id="skill-heatmap" class="chart tall"></div></article>
    </section>`;

  const wordcloud = createChart("skill-wordcloud");
  if (!analysis.top_skills.length) emptyChart(wordcloud);
  else wordcloud.setOption({
    tooltip: { formatter: (item) => `${item.name}：${item.value} 个岗位` },
    series: [{ type: "wordCloud", shape: "circle", gridSize: 8, sizeRange: [15, 58], rotationRange: [-35, 35], textStyle: { color: () => palette(Math.floor(Math.random() * 9)) }, data: analysis.top_skills.map((item) => ({ name: item.name, value: item.count })) }],
  });

  const graph = createChart("skill-graph");
  if (!analysis.cooccurrence.skills.length) emptyChart(graph);
  else {
    const counts = Object.fromEntries(analysis.top_skills.map((item) => [item.name, item.count]));
    graph.setOption({
      tooltip: {},
      series: [{
        type: "graph", layout: "force", roam: true, draggable: true,
        force: { repulsion: 190, edgeLength: [55, 145], gravity: .08 },
        label: { show: true, position: "right", fontSize: 10 },
        data: analysis.cooccurrence.skills.map((name, index) => ({ name, value: counts[name] || 1, symbolSize: 14 + Math.sqrt(counts[name] || 1) * 5, itemStyle: { color: palette(index) } })),
        links: analysis.cooccurrence.links.map((link) => ({ ...link, lineStyle: { width: Math.min(8, 1 + Math.sqrt(link.value)), opacity: .4, curveness: .12 } })),
      }],
    });
  }

  const premiumChart = createChart("skill-premium");
  const premiums = (analysis.high_premium_skills.length ? analysis.high_premium_skills : analysis.salary_correlation.filter((item) => item.premium_rate > 0)).slice(0, 15).reverse();
  if (!premiums.length) emptyChart(premiumChart, "暂无正溢价技能数据");
  else premiumChart.setOption({
    color: ["#e7854d"], tooltip: { trigger: "axis", formatter: (items) => `${items[0].name}<br>溢价率 ${items[0].value}%` },
    grid: { left: 92, right: 28, top: 15, bottom: 28 }, xAxis: { ...axisStyle(), type: "value", axisLabel: { formatter: "{value}%" } },
    yAxis: { ...axisStyle(), type: "category", data: premiums.map((item) => item.skill) },
    series: [{ type: "bar", data: premiums.map((item) => item.premium_rate), itemStyle: { borderRadius: [0, 5, 5, 0] } }],
  });

  const top15 = analysis.cooccurrence.skills;
  const heat = heatmapData(jobs, top15);
  const heatmap = createChart("skill-heatmap");
  if (!jobs.length || !top15.length) emptyChart(heatmap);
  else heatmap.setOption({
    tooltip: { position: "top", formatter: (item) => `${heat.types[item.value[1]]} · ${top15[item.value[0]]}<br>出现率 ${item.value[2]}%` },
    grid: { left: 90, right: 22, top: 25, bottom: 80 },
    xAxis: { ...axisStyle(), type: "category", data: top15, axisLabel: { rotate: 38 } },
    yAxis: { ...axisStyle(), type: "category", data: heat.types },
    visualMap: { min: 0, max: Math.max(1, ...heat.data.map((item) => item[2])), calculable: true, orient: "horizontal", left: "center", bottom: 5, inRange: { color: ["#eef4f9", "#80afd1", "#2c5f8f"] } },
    series: [{ type: "heatmap", data: heat.data, label: { show: true, formatter: (item) => `${item.value[2]}%`, fontSize: 9 } }],
  });
}
