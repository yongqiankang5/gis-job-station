/** 事业单位招录统计与记录表格视图。 */

import { api } from "../api.js";
import { getCityCoords } from "../city_coords.js";
import { axisStyle, createChart, emptyChart, escapeHtml, formatNumber, palette } from "../utils.js";

export const title = "事业单位";

const PROVINCE_CAPITAL = {
  北京:"北京",天津:"天津",上海:"上海",重庆:"重庆",河北:"石家庄",山西:"太原",内蒙古:"呼和浩特",辽宁:"沈阳",吉林:"长春",黑龙江:"哈尔滨",
  江苏:"南京",浙江:"杭州",安徽:"合肥",福建:"福州",江西:"南昌",山东:"济南",河南:"郑州",湖北:"武汉",湖南:"长沙",广东:"广州",广西:"南宁",
  海南:"海口",四川:"成都",贵州:"贵阳",云南:"昆明",西藏:"拉萨",陕西:"西安",甘肃:"兰州",青海:"西宁",宁夏:"银川",新疆:"乌鲁木齐",香港:"香港",澳门:"澳门",
};

/** 渲染事业单位记录表格。 */
function recordsTable(data) {
  return `
    <div class="table-wrap"><table class="data-table"><thead><tr><th>年份</th><th>单位</th><th>级别</th><th>省市</th><th>岗位</th><th>计划</th><th>实际拟聘</th><th>学历</th></tr></thead>
    <tbody>${data.items.map((item) => `<tr><td>${item.year}</td><td>${escapeHtml(item.unit_name)}</td><td>${escapeHtml(item.unit_level)}</td><td>${escapeHtml(item.province)} · ${escapeHtml(item.city)}</td><td>${escapeHtml(item.job_title)}</td><td>${item.planned_count ?? "—"}</td><td>${item.actual_count ?? "—"}</td><td>${escapeHtml(item.education)}</td></tr>`).join("") || '<tr><td colspan="8">暂无符合条件的招录记录</td></tr>'}</tbody></table></div>`;
}

/** 渲染事业单位视图并绑定筛选分页。 */
export async function render(root) {
  const analysis = await api.officialAnalysis();
  const planned = analysis.by_year.reduce((sum, item) => sum + item.planned_count, 0);
  const actual = analysis.by_year.reduce((sum, item) => sum + item.actual_count, 0);
  const rates = analysis.by_unit.map((item) => item.fulfillment_rate).filter((value) => value != null);
  const averageRate = rates.length ? rates.reduce((sum, value) => sum + value, 0) / rates.length : null;
  const years = analysis.by_year.map((item) => item.year).sort((a, b) => b - a);
  const provinces = analysis.by_province.map((item) => item.province);
  let page = 1;
  let active = true;
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">事业单位招录</h1><p class="view-subtitle">公开招录计划、实际拟聘与人才培养来源分析</p></div></header>
    <section class="metric-grid">
      <article class="metric-card"><span class="metric-label">计划招录人数</span><strong class="metric-value">${formatNumber(planned)}</strong><small class="metric-change neutral">累计公开计划</small></article>
      <article class="metric-card"><span class="metric-label">实际拟聘人数</span><strong class="metric-value">${formatNumber(actual)}</strong><small class="metric-change neutral">有公示数据的记录</small></article>
      <article class="metric-card"><span class="metric-label">平均兑现率</span><strong class="metric-value">${formatNumber(averageRate, 1)}<em class="metric-unit">%</em></strong><small class="metric-change neutral">按单位计算</small></article>
      <article class="metric-card"><span class="metric-label">招录记录</span><strong class="metric-value">${formatNumber(analysis.record_count)}</strong><small class="metric-change neutral">公开政府数据</small></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><h2 class="panel-title">年度招录计划与实际</h2></div><div id="official-year-chart" class="chart"></div></article>
      <article class="panel"><div class="panel-header"><h2 class="panel-title">省份招录分布</h2><span class="panel-note">圆大小表示计划人数</span></div><div id="official-map" style="height:330px;border-radius:10px"></div></article>
      <article class="panel span-full"><div class="panel-header"><h2 class="panel-title">拟聘人员毕业院校 Top20</h2></div><div id="official-school-chart" class="chart tall"></div></article>
      <article class="panel span-full"><div class="panel-header"><h2 class="panel-title">招录记录</h2><span id="official-meta" class="panel-note"></span></div>
        <form id="official-filter" class="official-filters"><select name="year"><option value="">全部年份</option>${years.map((year) => `<option>${year}</option>`).join("")}</select><select name="province"><option value="">全部省份</option>${provinces.map((province) => `<option>${escapeHtml(province)}</option>`).join("")}</select><select name="unit_level"><option value="">全部级别</option>${["中央","省","市","县"].map((item) => `<option>${item}</option>`).join("")}</select><input name="keyword" type="search" placeholder="单位、岗位或专业"><button class="primary-button" type="submit">筛选</button></form>
        <div id="official-records"></div><nav id="official-pagination" class="pagination"></nav>
      </article>
    </section>`;

  const yearChart = createChart("official-year-chart");
  if (!analysis.by_year.length) emptyChart(yearChart);
  else yearChart.setOption({
    color: [palette(0), palette(6)], tooltip: { trigger: "axis" }, legend: { bottom: 0 }, grid: { left: 48, right: 18, top: 20, bottom: 50 },
    xAxis: { ...axisStyle(), type: "category", data: analysis.by_year.map((item) => item.year) }, yAxis: { ...axisStyle(), type: "value", minInterval: 1 },
    series: [{ name: "计划招录", type: "bar", data: analysis.by_year.map((item) => item.planned_count) }, { name: "实际拟聘", type: "bar", data: analysis.by_year.map((item) => item.actual_count) }],
  });

  const map = L.map("official-map", { zoomControl: false, attributionControl: false }).setView([35.5, 104.5], 3);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 8 }).addTo(map);
  analysis.by_province.forEach((item) => {
    const coords = getCityCoords(PROVINCE_CAPITAL[item.province]);
    if (!coords) return;
    L.circleMarker(coords, { radius: Math.max(6, Math.min(22, 5 + Math.sqrt(item.planned_count) * 2)), color: "#fff", weight: 2, fillColor: "#2c5f8f", fillOpacity: .82 })
      .bindPopup(`<strong>${escapeHtml(item.province)}</strong><br>计划 ${item.planned_count} 人<br>实际 ${item.actual_count} 人`).addTo(map);
  });

  const schools = analysis.top_schools.slice(0, 20).reverse();
  const schoolChart = createChart("official-school-chart");
  if (!schools.length) emptyChart(schoolChart);
  else schoolChart.setOption({
    color: ["#3f8f73"], tooltip: { trigger: "axis" }, grid: { left: 125, right: 24, top: 12, bottom: 25 },
    xAxis: { ...axisStyle(), type: "value", minInterval: 1 }, yAxis: { ...axisStyle(), type: "category", data: schools.map((item) => item.name) },
    series: [{ type: "bar", data: schools.map((item) => item.count), itemStyle: { borderRadius: [0, 5, 5, 0] } }],
  });

  const form = root.querySelector("#official-filter");
  const records = root.querySelector("#official-records");
  const pagination = root.querySelector("#official-pagination");
  const loadRecords = async () => {
    const values = Object.fromEntries(new FormData(form));
    const data = await api.official({ ...values, page, page_size: 20 });
    if (!active) return;
    root.querySelector("#official-meta").textContent = `共 ${data.total} 条 · 第 ${data.page}/${Math.max(data.pages, 1)} 页`;
    records.innerHTML = recordsTable(data);
    pagination.innerHTML = data.pages > 1 ? `<button class="page-button" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button><button class="page-button" data-page="${page + 1}" ${page >= data.pages ? "disabled" : ""}>下一页</button>` : "";
    pagination.querySelectorAll("button:not(:disabled)").forEach((button) => button.addEventListener("click", () => { page = Number(button.dataset.page); loadRecords(); }));
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); page = 1; loadRecords().catch((error) => { records.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`; }); });
  await loadRecords();
  const resizeTimer = window.setTimeout(() => map.invalidateSize(), 80);
  return () => { active = false; window.clearTimeout(resizeTimer); map.remove(); };
}
