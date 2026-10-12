/** Leaflet 岗位地图分布视图。 */

import { api } from "../api.js";
import { getCityCoords } from "../city_coords.js";
import { createChart, emptyChart, escapeHtml, formatNumber, palette, salaryColor } from "../utils.js";

export const title = "地图分布";

/** 加载城市岗位类型并在 Leaflet 弹窗绘制迷你饼图。 */
async function renderPopupChart(city, elementId) {
  const result = await api.jobs({ city, page: 1, page_size: 100 });
  const counts = result.items.reduce((counter, job) => ({ ...counter, [job.job_type]: (counter[job.job_type] || 0) + 1 }), {});
  const chart = createChart(elementId);
  const data = Object.entries(counts).map(([name, value]) => ({ name, value }));
  if (!data.length) emptyChart(chart, "暂无岗位类型数据");
  else chart.setOption({
    color: data.map((_, index) => palette(index)), tooltip: { trigger: "item" },
    series: [{ type: "pie", radius: ["30%", "66%"], label: { show: false }, data }],
  });
}

/** 渲染地图、标记、图层控制和省份表格。 */
export async function render(root) {
  const data = await api.cityDistribution(100);
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">地图分布</h1><p class="view-subtitle">观察岗位数量与城市平均薪资的空间差异</p></div></header>
    <section class="panel"><div id="jobs-map" aria-label="全国岗位分布地图"></div></section>
    <section class="panel" style="margin-top:16px"><div class="panel-header"><h2 class="panel-title">省份岗位分布</h2><span class="panel-note">点击省份可聚焦地图，再次点击恢复全国</span></div>
      <div class="table-wrap"><table class="province-table"><thead><tr><th>省份</th><th>岗位数</th><th>覆盖城市</th><th>公司数</th><th>平均薪资</th></tr></thead><tbody>${data.provinces.map((item) => `<tr data-province="${escapeHtml(item.province)}"><td>${escapeHtml(item.province)}</td><td>${item.job_count}</td><td>${item.city_count}</td><td>${item.company_count}</td><td>${formatNumber(item.average_salary, 1)}K</td></tr>`).join("") || '<tr><td colspan="5">暂无数据</td></tr>'}</tbody></table></div>
    </section>`;
  const map = L.map("jobs-map", { zoomControl: true }).setView([35.5, 104.5], 4);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
  const markerLayer = L.layerGroup().addTo(map);
  const mappedCities = data.cities.filter((city) => getCityCoords(city.city));
  let mode = "count";
  let provinceFilter = null;

  const drawMarkers = () => {
    markerLayer.clearLayers();
    mappedCities.filter((item) => !provinceFilter || item.province === provinceFilter).forEach((item, index) => {
      const coords = getCityCoords(item.city);
      const radius = mode === "count" ? Math.max(7, Math.min(25, 6 + Math.sqrt(item.job_count) * 2.2)) : 12;
      const color = mode === "salary" ? salaryColor(item.average_salary) : "#2c5f8f";
      const popupId = `popup-chart-${item.city.codePointAt(0) || 0}-${item.job_count}-${index}`;
      const marker = L.circleMarker(coords, { radius, color: "#fff", weight: 2, fillColor: color, fillOpacity: .84 });
      marker.bindPopup(`<div style="width:220px"><strong style="font-size:14px">${escapeHtml(item.city)}</strong><div style="margin-top:5px">岗位 ${item.job_count} 个 · 平均薪资 ${formatNumber(item.average_salary, 1)}K</div><div id="${popupId}" style="height:120px;margin-top:4px">加载岗位类型…</div></div>`, { maxWidth: 250 });
      marker.on("popupopen", () => renderPopupChart(item.city, popupId).catch(() => { const node = document.getElementById(popupId); if (node) node.textContent = "岗位类型加载失败"; }));
      marker.addTo(markerLayer);
    });
  };

  const ModeControl = L.Control.extend({
    onAdd() {
      const container = L.DomUtil.create("div", "leaflet-bar map-toolbar");
      container.innerHTML = '<button class="map-mode active" data-mode="count" type="button">岗位数量</button><button class="map-mode" data-mode="salary" type="button">平均薪资</button>';
      L.DomEvent.disableClickPropagation(container);
      container.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
        mode = button.dataset.mode; container.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button)); drawMarkers();
      }));
      return container;
    },
  });
  new ModeControl({ position: "topright" }).addTo(map);
  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const node = L.DomUtil.create("div", "map-legend");
    node.innerHTML = "圆大小：岗位数量<div class=\"legend-gradient\"></div>蓝色低薪 → 红色高薪";
    return node;
  };
  legend.addTo(map);
  drawMarkers();

  root.querySelectorAll(".province-table tbody tr[data-province]").forEach((row) => row.addEventListener("click", () => {
    const clicked = row.dataset.province;
    provinceFilter = provinceFilter === clicked ? null : clicked;
    root.querySelectorAll(".province-table tbody tr").forEach((item) => item.classList.toggle("active", item.dataset.province === provinceFilter));
    drawMarkers();
    const visible = mappedCities.filter((item) => !provinceFilter || item.province === provinceFilter).map((item) => getCityCoords(item.city));
    if (visible.length) map.fitBounds(visible, { padding: [30, 30], maxZoom: 7 }); else map.setView([35.5, 104.5], 4);
  }));
  const resizeTimer = window.setTimeout(() => map.invalidateSize(), 80);
  return () => { window.clearTimeout(resizeTimer); map.remove(); };
}
