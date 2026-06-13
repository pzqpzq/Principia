const state = {
  results: [],
  lastContributionPath: "",
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString() : "0";
}

function setStatus(text, warn = false) {
  $("statusLine").textContent = text || "";
  $("statusLine").classList.toggle("warning", Boolean(warn));
}

async function loadStats() {
  try {
    const [stats, admin] = await Promise.all([api("/api/v1/cloud/stats"), api("/api/v1/cloud/admin/status")]);
    const counts = stats.counts || {};
    const cache = stats.cache || {};
    $("snapshotId").textContent = stats.snapshot_id || "-";
    $("workCount").textContent = formatNumber(counts.works);
    $("conceptCount").textContent = formatNumber(counts.concepts);
    $("assetCount").textContent = formatNumber(stats.assets);
    $("payloadCacheCount").textContent = formatNumber(cache.payload_count);
    $("adminMode").textContent = admin.mode || "-";
    if (stats.warning) setStatus(stats.warning, true);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderResults(items) {
  state.results = items || [];
  $("resultCount").textContent = String(state.results.length);
  const root = $("results");
  root.innerHTML = "";
  for (const item of state.results) {
    const title = item.title || item.canonical_title || item.work_id || item.concept_id || item.asset_id || "Cloud record";
    const meta = [
      item.venue,
      item.year,
      item.doi,
      item.arxiv_id,
      item.openalex_id,
      item.decision,
      Array.isArray(item.model_keys) ? `${item.model_keys.length} model(s)` : "",
    ]
      .filter(Boolean)
      .join(" · ");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-item";
    button.innerHTML = `
      <div class="result-title">${escapeHtml(title)}</div>
      <div class="result-meta">${escapeHtml(meta || item.title_hash || "")}</div>
    `;
    button.addEventListener("click", () => showDetail(item));
    root.appendChild(button);
  }
}

function showDetail(item) {
  $("detailKind").textContent = item.work_id ? "work" : item.concept_id ? "concept" : "record";
  $("detailJson").textContent = JSON.stringify(item, null, 2);
}

async function search(event) {
  event.preventDefault();
  const query = $("query").value.trim();
  setStatus("Searching...");
  try {
    const data = await api("/api/v1/cloud/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        limit: 50,
        venue: $("venueFilter").value.trim(),
        year: $("yearFilter").value.trim(),
        concept_type: $("conceptTypeFilter").value,
      }),
    });
    renderResults(data.items || []);
    setStatus(`${(data.items || []).length} result(s) from ${data.snapshot_id || "local cloud cache"}.`);
  } catch (error) {
    renderResults([]);
    setStatus(error.message, true);
  }
}

async function prepareContribution(event) {
  event.preventDefault();
  $("uploadStatus").textContent = "Preparing...";
  $("uploadJson").textContent = "{}";
  try {
    const data = await api("/api/v1/cloud/upload/prepare", {
      method: "POST",
      body: JSON.stringify({
        admin_key: $("uploadKey").value,
        upload_mode: $("uploadMode").value,
        model_key: $("uploadModelKey").value.trim(),
        work_ids: splitList($("uploadWorkIds").value),
      }),
    });
    state.lastContributionPath = data.path || "";
    $("uploadStatus").textContent = data.ok ? `Prepared ${data.contribution_id}` : `Prepared with ${data.rejected_work_ids?.length || 0} rejected work(s)`;
    $("uploadJson").textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    $("uploadStatus").textContent = error.message;
  }
}

async function planCrawl(event) {
  event.preventDefault();
  await submitCrawl("/api/v1/cloud/admin/crawl/plan");
}

async function runCrawl() {
  await submitCrawl("/api/v1/cloud/admin/crawl/run");
}

async function submitCrawl(path) {
  setStatus(path.endsWith("/run") ? "Exporting crawler operation..." : "Planning crawler batch...");
  try {
    const data = await api(path, {
      method: "POST",
      body: JSON.stringify({
        admin_key: $("crawlKey").value,
        venues: splitList($("crawlVenues").value),
        years: splitList($("crawlYears").value).map((item) => Number(item)).filter(Boolean),
        topics: splitList($("crawlTopics").value),
        priority_rules: splitList($("crawlRules").value),
        max_papers: Number($("crawlMax").value || 100),
        model_key: $("crawlModelKey").value.trim(),
        dry_run: path.endsWith("/plan"),
      }),
    });
    $("crawlCount").textContent = String((data.candidates || []).length);
    showDetail(data);
    setStatus(path.endsWith("/run") ? `Crawler operation exported: ${data.path || data.plan_id}` : `Crawler plan ready: ${data.plan_id}`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function exportAdminOperation(event) {
  event.preventDefault();
  setStatus("Exporting admin operation...");
  try {
    const action = $("adminAction").value;
    const payload = JSON.parse($("adminPayload").value || "{}");
    const data = await api(`/api/v1/cloud/admin/${action}`, {
      method: "POST",
      body: JSON.stringify({
        admin_key: $("adminKey").value,
        target_type: $("adminTargetType").value.trim() || "record",
        reason: $("adminReason").value.trim(),
        payload,
      }),
    });
    $("adminOpKind").textContent = action;
    showDetail(data);
    setStatus(`Admin operation exported: ${data.path || data.operation?.operation_id || action}`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function splitList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

$("cloudSearch").addEventListener("submit", search);
$("refreshStats").addEventListener("click", loadStats);
$("uploadForm").addEventListener("submit", prepareContribution);
$("crawlForm").addEventListener("submit", planCrawl);
$("runCrawl").addEventListener("click", runCrawl);
$("adminForm").addEventListener("submit", exportAdminOperation);
loadStats();
