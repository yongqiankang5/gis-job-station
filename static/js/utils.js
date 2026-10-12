/** 通用格式化、图表生命周期、颜色与统计计算工具。 */

const charts = new Set();
let resizeTimer = 0;

/** 安全转义外部数据，防止作为 HTML 执行。 */
export function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

/** 格式化整数或小数。 */
export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

/** 格式化岗位月薪。 */
export function formatSalary(job) {
  if (job.salary_min != null && job.salary_max != null) return `${formatNumber(job.salary_min, 1)}–${formatNumber(job.salary_max, 1)}K`;
  if (job.salary_min != null) return `${formatNumber(job.salary_min, 1)}K 以上`;
  return job.salary_note || "面议";
}

/** 格式化日期为 YYYY-MM-DD。 */
export function formatDate(value) {
  if (!value) return "日期未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(date).replaceAll("/", "-");
}

/** 根据来源平台返回短图标。 */
export function sourceIcon(source) {
  const icons = { boss: "B", zhaopin: "智", liepin: "猎", "58": "58", manual: "录" };
  return icons[source] || "源";
}

/** 由薪资生成从蓝到红的渐变色。 */
export function salaryColor(value, minimum = 5, maximum = 40) {
  if (value == null) return "#8ba5bb";
  const ratio = Math.max(0, Math.min(1, (Number(value) - minimum) / Math.max(1, maximum - minimum)));
  const hue = 210 - ratio * 205;
  return `hsl(${hue} 65% 52%)`;
}

/** 从主色板循环取色。 */
export function palette(index) {
  const colors = ["#2c5f8f", "#4d89b7", "#73a8ca", "#3f8f73", "#68aa91", "#e0a14a", "#d96f4a", "#8a6db1", "#6f7d8a"];
  return colors[index % colors.length];
}

/** 创建并登记 ECharts 实例。 */
export function createChart(elementOrId) {
  const element = typeof elementOrId === "string" ? document.getElementById(elementOrId) : elementOrId;
  if (!element || !window.echarts) return null;
  const existing = window.echarts.getInstanceByDom(element);
  const chart = existing || window.echarts.init(element);
  charts.add(chart);
  return chart;
}

/** 显示图表无数据占位。 */
export function emptyChart(chart, message = "暂无数据") {
  if (!chart) return;
  chart.clear();
  chart.setOption({
    graphic: [{ type: "text", left: "center", top: "middle", style: { text: message, fill: "#8795a1", fontSize: 14 } }],
  });
}

/** 销毁指定容器内的图表，避免 SPA 切换视图产生内存泄漏。 */
export function disposeCharts(container = document) {
  [...charts].forEach((chart) => {
    const dom = chart.getDom();
    if (!dom?.isConnected || container.contains(dom)) {
      chart.dispose();
      charts.delete(chart);
    }
  });
}

/** 生成 ECharts 通用坐标系设置。 */
export function axisStyle() {
  return {
    axisLine: { lineStyle: { color: "#cdd8e1" } },
    axisTick: { show: false },
    axisLabel: { color: "#687887", fontSize: 11 },
    splitLine: { lineStyle: { color: "#edf1f4" } },
  };
}

/** 计算用于 ECharts boxplot 的 [min,Q1,median,Q3,max]。 */
export function boxplotValues(values) {
  const sorted = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const quantile = (q) => {
    const position = (sorted.length - 1) * q;
    const base = Math.floor(position);
    const fraction = position - base;
    return sorted[base + 1] === undefined ? sorted[base] : sorted[base] + fraction * (sorted[base + 1] - sorted[base]);
  };
  return [sorted[0], quantile(.25), quantile(.5), quantile(.75), sorted.at(-1)].map((item) => Number(item.toFixed(2)));
}

/** 计算数值数组中位数。 */
export function median(values) {
  const box = boxplotValues(values);
  return box ? box[2] : null;
}

/** 将数组按指定字段分组。 */
export function groupBy(items, getter) {
  return items.reduce((groups, item) => {
    const key = typeof getter === "function" ? getter(item) : item[getter];
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
    return groups;
  }, {});
}

/** 显示页面级错误占位。 */
export function errorMarkup(message = "数据加载失败，请稍后重试") {
  return `<section class="panel error-state"><div><strong>暂时无法加载数据</strong><p>${escapeHtml(message)}</p><button class="secondary-button" type="button" onclick="location.reload()">重新加载</button></div></section>`;
}

/** 全局窗口变化时批量重绘所有可见图表。 */
window.addEventListener("resize", () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    charts.forEach((chart) => { if (!chart.isDisposed()) chart.resize(); });
  }, 120);
});
