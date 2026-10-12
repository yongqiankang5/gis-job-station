/** SPA 入口：负责视图路由、导航状态、全局错误提示和模块生命周期。 */

import { disposeCharts, errorMarkup } from "./utils.js";

const viewLoaders = {
  index: () => import("./views/index.js"),
  jobs: () => import("./views/jobs.js"),
  map: () => import("./views/map.js"),
  skills: () => import("./views/skills.js"),
  salary: () => import("./views/salary.js"),
  official: () => import("./views/official.js"),
  trend: () => import("./views/trend.js"),
};

const root = document.getElementById("view-root");
const sidebar = document.getElementById("sidebar");
const mobileToggle = document.getElementById("mobile-nav-toggle");
let activeView = null;
let cleanupView = null;
let navigationToken = 0;
let lastErrorMessage = "";
let lastErrorAt = 0;

/** 显示右上角短时消息。 */
function notify(message, type = "info") {
  const now = Date.now();
  if (message === lastErrorMessage && now - lastErrorAt < 1500) return;
  lastErrorMessage = message;
  lastErrorAt = now;
  const toast = document.createElement("div");
  toast.className = `toast ${type === "error" ? "error" : ""}`;
  toast.textContent = message;
  document.getElementById("toast-region").appendChild(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

/** 返回当前 hash 对应视图，非法值回退首页。 */
function currentView() {
  const name = location.hash.replace(/^#/, "") || "index";
  return viewLoaders[name] ? name : "index";
}

/** 更新侧栏激活状态和移动端导航。 */
function updateNavigation(view) {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  sidebar.classList.remove("open");
  mobileToggle.setAttribute("aria-expanded", "false");
}

/** 渲染通用骨架屏。 */
function renderSkeleton() {
  root.innerHTML = `
    <section class="initial-loading" aria-label="视图加载中">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton-grid">
        <div class="skeleton skeleton-card"></div><div class="skeleton skeleton-card"></div>
        <div class="skeleton skeleton-card"></div><div class="skeleton skeleton-card"></div>
      </div>
      <div class="dashboard-grid"><div class="skeleton" style="height:340px"></div><div class="skeleton" style="height:340px"></div></div>
    </section>`;
}

/** 加载并渲染当前模块；异步返回时校验令牌，避免快速切换串页。 */
async function navigate() {
  const view = currentView();
  const token = ++navigationToken;
  if (typeof cleanupView === "function") cleanupView();
  disposeCharts(root);
  cleanupView = null;
  activeView = view;
  updateNavigation(view);
  renderSkeleton();
  root.focus({ preventScroll: true });
  try {
    const module = await viewLoaders[view]();
    if (token !== navigationToken || activeView !== view) return;
    cleanupView = await module.render(root);
    document.title = `${module.title || "GIS 遥感就业情报站"}｜GIS 遥感就业情报站`;
  } catch (error) {
    if (token !== navigationToken) return;
    root.innerHTML = errorMarkup(error.message);
    notify(error.message || "页面加载失败", "error");
  }
}

mobileToggle.addEventListener("click", () => {
  const open = sidebar.classList.toggle("open");
  mobileToggle.setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", (event) => {
  if (window.innerWidth <= 760 && sidebar.classList.contains("open") && !sidebar.contains(event.target) && event.target !== mobileToggle) sidebar.classList.remove("open");
});
window.addEventListener("hashchange", navigate);
window.addEventListener("api:error", (event) => notify(event.detail?.message || "数据请求失败", "error"));
window.addEventListener("api:loading", (event) => {
  if (event.detail.pending === 0) {
    const now = new Date();
    document.getElementById("data-updated").textContent = `数据更新时间：${now.toLocaleString("zh-CN", { hour12: false })}`;
  }
});

window.GISApp = { notify, navigate };
navigate();
