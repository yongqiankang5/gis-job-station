/** 后端 API 访问层：统一查询参数、超时、错误和批量岗位读取。 */

const DEFAULT_TIMEOUT = 15000;
let pendingRequests = 0;

/** 广播全局请求状态，供页面显示加载提示。 */
function emitLoading() {
  window.dispatchEvent(new CustomEvent("api:loading", { detail: { pending: pendingRequests } }));
}

/** 把普通对象转换为 URL 查询字符串，自动跳过空值。 */
export function buildQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    query.set(key, Array.isArray(value) ? value.join(",") : String(value));
  });
  return query.toString();
}

/** 发起 JSON 请求，失败时抛出带中文提示的异常。 */
export async function request(path, { params, timeout = DEFAULT_TIMEOUT, ...options } = {}) {
  const query = buildQuery(params);
  const url = query ? `${path}?${query}` : path;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);
  pendingRequests += 1;
  emitLoading();
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      signal: controller.signal,
      ...options,
    });
    if (!response.ok) {
      let detail = `请求失败（${response.status}）`;
      try {
        const body = await response.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch (_) { /* 非 JSON 错误页保持通用提示。 */ }
      throw new Error(detail);
    }
    return await response.json();
  } catch (error) {
    const friendly = error.name === "AbortError" ? new Error("请求超时，请稍后重试") : error;
    window.dispatchEvent(new CustomEvent("api:error", { detail: { message: friendly.message } }));
    throw friendly;
  } finally {
    window.clearTimeout(timer);
    pendingRequests = Math.max(0, pendingRequests - 1);
    emitLoading();
  }
}

/** 分页读取匹配岗位，供箱线图和中位数等浏览器端统计使用。 */
export async function getAllJobs(params = {}, maxRecords = 2000) {
  const pageSize = 100;
  const first = await request("/api/jobs", { params: { ...params, page: 1, page_size: pageSize } });
  const items = [...first.items];
  const pages = Math.min(first.pages, Math.ceil(maxRecords / pageSize));
  for (let page = 2; page <= pages; page += 1) {
    const result = await request("/api/jobs", { params: { ...params, page, page_size: pageSize } });
    items.push(...result.items);
  }
  return items.slice(0, maxRecords);
}

/** 生成岗位 CSV 导出地址，由浏览器直接下载附件。 */
export function exportJobs(params = {}) {
  const query = buildQuery(params);
  const anchor = document.createElement("a");
  anchor.href = `/api/jobs/export${query ? `?${query}` : ""}`;
  anchor.download = "gis_jobs_export.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export const api = {
  overview: () => request("/api/stats/overview"),
  cityDistribution: (topN = 20) => request("/api/stats/city-distribution", { params: { top_n: topN } }),
  salaryDistribution: () => request("/api/stats/salary-distribution"),
  skillAnalysis: (topN = 30) => request("/api/stats/skill-analysis", { params: { top_n: topN } }),
  requirementAnalysis: () => request("/api/stats/requirement-analysis"),
  companyAnalysis: (topN = 20) => request("/api/stats/company-analysis", { params: { top_n: topN } }),
  officialAnalysis: () => request("/api/stats/official-analysis"),
  trend: (months = 12) => request("/api/stats/trend", { params: { months } }),
  jobs: (params) => request("/api/jobs", { params }),
  official: (params) => request("/api/official", { params }),
};
