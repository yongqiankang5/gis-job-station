/** 岗位查询视图。 */

import { api, exportJobs } from "../api.js";
import { escapeHtml, formatDate, formatSalary, sourceIcon } from "../utils.js";

export const title = "岗位查询";

/** 读取多选框选中值。 */
function selectedValues(select) {
  return [...select.selectedOptions].map((option) => option.value).filter(Boolean);
}

/** 生成岗位来源安全链接。 */
function safeUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : "#";
}

/** 生成可读页码窗口。 */
function pageNumbers(current, total) {
  const start = Math.max(1, Math.min(current - 2, total - 4));
  const end = Math.min(total, Math.max(5, current + 2));
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) => start + index);
}

/** 渲染单个岗位卡片。 */
function jobCard(job) {
  return `
    <article class="job-card" data-job-id="${job.id}">
      <div class="job-card-header" role="button" tabindex="0" aria-expanded="false">
        <div><h3 class="job-title">${escapeHtml(job.job_title)}</h3><p class="company-line">${escapeHtml(job.company_name)} · ${escapeHtml(job.city)}${job.district ? ` · ${escapeHtml(job.district)}` : ""}</p></div>
        <strong class="salary-text">${escapeHtml(formatSalary(job))}</strong>
      </div>
      <div class="tag-row"><span class="tag type">${escapeHtml(job.company_type)}</span><span class="tag">${escapeHtml(job.education)}</span><span class="tag">${escapeHtml(job.experience)}</span><span class="tag">${escapeHtml(job.job_type)}</span></div>
      <div class="tag-row">${(job.skills || []).slice(0, 5).map((skill) => `<span class="tag skill">${escapeHtml(skill)}</span>`).join("") || '<span class="tag">暂无技能标签</span>'}</div>
      <div class="job-footer"><span><i class="source-badge">${escapeHtml(sourceIcon(job.source))}</i> ${escapeHtml(job.source)} · ${escapeHtml(formatDate(job.publish_date))}</span><span>质量分 ${job.quality_score}</span></div>
      <div class="job-description"><strong>职位描述</strong><p>${escapeHtml(job.job_description || "暂无完整职位描述")}</p><a class="job-link" href="${escapeHtml(safeUrl(job.url))}" target="_blank" rel="noopener noreferrer">查看招聘来源 ↗</a></div>
    </article>`;
}

/** 渲染结果卡片和分页器。 */
function renderResults(container, pagination, data, onPage) {
  container.innerHTML = data.items.length ? data.items.map(jobCard).join("") : '<div class="panel empty-state span-full">暂无符合当前条件的岗位</div>';
  pagination.innerHTML = data.pages > 1 ? `
    <button class="page-button" data-page="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>‹</button>
    ${pageNumbers(data.page, data.pages).map((page) => `<button class="page-button ${page === data.page ? "active" : ""}" data-page="${page}">${page}</button>`).join("")}
    <button class="page-button" data-page="${data.page + 1}" ${data.page >= data.pages ? "disabled" : ""}>›</button>` : "";
  pagination.querySelectorAll("button:not(:disabled)").forEach((button) => button.addEventListener("click", () => onPage(Number(button.dataset.page))));
  container.querySelectorAll(".job-card-header").forEach((header) => {
    const toggle = () => {
      const card = header.closest(".job-card");
      card.classList.toggle("expanded");
      header.setAttribute("aria-expanded", String(card.classList.contains("expanded")));
    };
    header.addEventListener("click", toggle);
    header.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); } });
  });
}

/** 加载筛选元数据、结果列表并绑定交互。 */
export async function render(root) {
  const [cityData, skillData] = await Promise.all([api.cityDistribution(100), api.skillAnalysis(20)]);
  let page = 1;
  let active = true;
  const selectedSkills = new Set();
  root.innerHTML = `
    <header class="view-header"><div><h1 class="view-title">岗位查询</h1><p class="view-subtitle">组合筛选职位，点击卡片查看完整岗位描述</p></div><button id="jobs-export" class="secondary-button" type="button">导出 CSV</button></header>
    <details class="panel filter-panel" open>
      <summary class="filter-summary">筛选条件</summary>
      <form id="jobs-filter" class="filter-form">
        <div class="filter-grid">
          <label class="field"><span>关键词</span><input name="keyword" type="search" placeholder="职位、公司或 JD"></label>
          <label class="field"><span>城市（Ctrl / ⌘ 多选）</span><select name="city" multiple>${cityData.cities.map((item) => `<option value="${escapeHtml(item.city)}">${escapeHtml(item.city)}（${item.job_count}）</option>`).join("")}</select></label>
          <label class="field"><span>岗位类型</span><select name="job_type" multiple>${["开发","算法","数据处理","分析","事业单位","销售","其他"].map((item) => `<option>${item}</option>`).join("")}</select></label>
          <label class="field"><span>学历要求</span><select name="education" multiple>${["不限","大专","本科","硕士","博士"].map((item) => `<option>${item}</option>`).join("")}</select></label>
          <label class="field"><span>经验要求</span><select name="experience" multiple>${["不限","应届","1-3年","3-5年","5-10年","10年以上"].map((item) => `<option>${item}</option>`).join("")}</select></label>
          <label class="field"><span>最低月薪：<b id="salary-min-label">0K</b></span><input id="salary-min" type="range" min="0" max="50" step="1" value="0"></label>
          <label class="field"><span>最高月薪：<b id="salary-max-label">50K+</b></span><input id="salary-max" type="range" min="0" max="50" step="1" value="50"></label>
          <label class="field"><span>公司类型</span><select name="company_type" multiple>${["国企","民营","上市公司","事业单位","外资","合资","其他"].map((item) => `<option>${item}</option>`).join("")}</select></label>
          <label class="field"><span>排序</span><select name="sort"><option value="publish_desc">最新发布</option><option value="salary_desc">薪资从高到低</option><option value="salary_asc">薪资从低到高</option><option value="quality_desc">质量分从高到低</option></select></label>
          <label class="field"><span>最低质量分</span><input name="min_quality" type="number" min="0" max="100" value="0"></label>
          <div class="field span-2"><span>技能标签（多选为 AND 关系）</span><div id="skill-selector" class="skill-selector">${skillData.top_skills.map((item) => `<button class="skill-chip" type="button" data-skill="${escapeHtml(item.name)}">${escapeHtml(item.name)} · ${item.count}</button>`).join("") || "暂无技能标签"}</div></div>
        </div>
        <div class="filter-actions"><button id="jobs-reset" class="ghost-button" type="button">重置</button><button class="primary-button" type="submit">查询</button></div>
      </form>
    </details>
    <div class="result-toolbar"><div id="jobs-meta" class="result-meta">正在查询岗位…</div></div>
    <section id="jobs-results" class="job-grid"><div class="panel empty-state span-full">正在加载岗位数据</div></section>
    <nav id="jobs-pagination" class="pagination" aria-label="岗位分页"></nav>`;

  const form = root.querySelector("#jobs-filter");
  const results = root.querySelector("#jobs-results");
  const meta = root.querySelector("#jobs-meta");
  const pagination = root.querySelector("#jobs-pagination");
  const minRange = root.querySelector("#salary-min");
  const maxRange = root.querySelector("#salary-max");

  const params = () => {
    const data = new FormData(form);
    const minimum = Number(minRange.value);
    const maximum = Number(maxRange.value);
    return {
      keyword: data.get("keyword"), city: selectedValues(form.elements.city), job_type: selectedValues(form.elements.job_type),
      education: selectedValues(form.elements.education), experience: selectedValues(form.elements.experience),
      company_type: selectedValues(form.elements.company_type), sort: data.get("sort"), min_quality: data.get("min_quality"),
      salary_min: minimum > 0 ? minimum : "", salary_max: maximum < 50 ? maximum : "", skills: [...selectedSkills],
    };
  };

  const load = async () => {
    meta.textContent = "正在查询岗位…";
    try {
      const data = await api.jobs({ ...params(), page, page_size: 20 });
      if (!active) return;
      meta.innerHTML = `共 <strong>${data.total}</strong> 条结果 · 第 ${data.page} / ${Math.max(data.pages, 1)} 页`;
      renderResults(results, pagination, data, (nextPage) => { page = nextPage; load(); window.scrollTo({ top: 0, behavior: "smooth" }); });
    } catch (error) {
      if (active) results.innerHTML = `<div class="panel error-state span-full">${escapeHtml(error.message)}</div>`;
    }
  };

  root.querySelectorAll(".skill-chip").forEach((chip) => chip.addEventListener("click", () => {
    chip.classList.toggle("selected");
    if (chip.classList.contains("selected")) selectedSkills.add(chip.dataset.skill); else selectedSkills.delete(chip.dataset.skill);
  }));
  const syncRanges = (changed) => {
    if (changed === "min" && Number(minRange.value) > Number(maxRange.value)) maxRange.value = minRange.value;
    if (changed === "max" && Number(maxRange.value) < Number(minRange.value)) minRange.value = maxRange.value;
    root.querySelector("#salary-min-label").textContent = `${minRange.value}K`;
    root.querySelector("#salary-max-label").textContent = Number(maxRange.value) >= 50 ? "50K+" : `${maxRange.value}K`;
  };
  minRange.addEventListener("input", () => syncRanges("min"));
  maxRange.addEventListener("input", () => syncRanges("max"));
  form.addEventListener("submit", (event) => { event.preventDefault(); page = 1; load(); });
  root.querySelector("#jobs-reset").addEventListener("click", () => {
    form.reset(); selectedSkills.clear(); root.querySelectorAll(".skill-chip").forEach((chip) => chip.classList.remove("selected")); page = 1; syncRanges(); load();
  });
  root.querySelector("#jobs-export").addEventListener("click", () => exportJobs(params()));
  await load();
  return () => { active = false; };
}
