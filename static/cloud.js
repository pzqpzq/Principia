const tabs = [
  { key: "works", label: "Works", idKey: "work_id", bucket: "source_works" },
  { key: "ready_works", label: "Ready Papers", idKey: "work_id", bucket: "source_works", workTab: true },
  { key: "existed_ideas", label: "Existed Ideas", idKey: "canonical_id", bucket: "existed_ideas", conceptType: "existed_idea" },
  { key: "benchmarks", label: "Benchmarks", idKey: "benchmark_id", bucket: "benchmark_records", conceptType: "benchmark" },
  { key: "baselines", label: "Baselines", idKey: "baseline_id", bucket: "baseline_records", conceptType: "baseline" },
  { key: "principles", label: "Principles", idKey: "principle_id", bucket: "principles", conceptType: "principle" },
  { key: "takeaway_messages", label: "Takeaways", idKey: "canonical_id", bucket: "takeaway_messages", conceptType: "takeaway_message" },
];
const cloudTabs = tabs.filter((tab) => tab.key !== "ready_works");

const modelOptions = [
  ["auto", "Auto router"],
  ["qwen_27b", "Qwen3.6-27B"],
  ["qwen_35b", "Qwen3.6-35B-A3B"],
  ["strong", "DeepSeek-V3"],
  ["deepseek_pro", "DeepSeek-V4-Pro"],
  ["deepseek_r1", "DeepSeek-R1"],
  ["kimi", "Kimi-K2.6 Pro"],
  ["qwen_122b", "Qwen3.5-122B-A10B"],
  ["qwen_397b", "Qwen3.5-397B-A17B"],
  ["glm", "GLM-5.1 Pro"],
  ["openai_gpt52_pro", "OpenAI GPT-5.2 Pro"],
  ["openai_gpt5_pro", "OpenAI GPT-5 Pro"],
  ["openai_gpt55", "OpenAI GPT-5.5"],
  ["openai_gpt55_pro_20260423", "OpenAI GPT-5.5 Pro 2026-04-23"],
];

const venueOptions = [
  "ICLR",
  "NeurIPS",
  "ICML",
  "CVPR",
  "ACL",
  "ICCV",
  "ECCV",
  "EMNLP",
  "AAAI",
  "TPAMI",
  "JMLR",
  "Nature",
  "Science",
  "Nature Machine Intelligence",
  "Nature Computational Science",
];

const priorityOptions = [
  ["venue", "Venue match"],
  ["recency", "Recent papers"],
  ["topic", "Topic match"],
  ["citation", "Citations"],
  ["oral", "Oral / spotlight"],
];

const state = {
  fieldId: "cloud-crawl",
  candidates: [],
  selectedCandidates: new Set(),
  queueAdding: false,
  crawlRunId: "",
  crawlPollTimer: null,
  activeLocalTab: "works",
  localItems: [],
  localOffset: 0,
  localLimit: 10,
  localHasMore: false,
  localCounts: {},
  activeCloudTab: "works",
  cloudItems: [],
  cloudOffset: 0,
  cloudLimit: 10,
  cloudHasMore: false,
  lastContributionPath: "",
  detail: { item: null, tab: "", id: "", local: false },
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function compact(value, length = 220) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, Math.max(0, length - 3)).trim()}...`;
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString() : "0";
}

function isUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function post(path, payload) {
  return api(path, { method: "POST", body: JSON.stringify(payload || {}) });
}

function showToast(message, tone = "success") {
  const root = $("toastStack");
  const toast = document.createElement("div");
  toast.className = `toast ${tone}`;
  toast.textContent = message;
  root.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("leaving");
    window.setTimeout(() => toast.remove(), 240);
  }, 2600);
}

function setWorkflow(step) {
  document.querySelectorAll("[data-workflow-step]").forEach((node) => {
    node.classList.toggle("active", node.dataset.workflowStep === step);
    node.classList.toggle("done", ["discover", "research", "review", "sync"].indexOf(node.dataset.workflowStep) < ["discover", "research", "review", "sync"].indexOf(step));
  });
}

function setLoading(root, loading) {
  if (!root) return;
  root.classList.toggle("is-loading", Boolean(loading));
  [...root.querySelectorAll("button, input, select, textarea")].forEach((control) => {
    if (control.dataset.allowBusy === "true") return;
    control.disabled = Boolean(loading);
  });
}

function loadingRows(count = 4) {
  return Array.from({ length: count }, () => `<div class="skeleton-card"><span></span><span></span><span></span></div>`).join("");
}

function splitTopics(value) {
  return String(value || "")
    .split(/[,;\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function checkedValues(rootId) {
  return [...$(rootId).querySelectorAll("input[type='checkbox']:checked")].map((node) => node.value);
}

function renderModelSelects() {
  $("crawlModelMode").innerHTML = modelOptions.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
  $("cloudModelMode").innerHTML = `<option value="">All model versions</option>` + modelOptions.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
}

function renderChoiceGroups() {
  const currentYear = new Date().getFullYear();
  const years = [currentYear, currentYear - 1, currentYear - 2, currentYear - 3, currentYear - 4].filter((year) => year >= 2020);
  renderChips("venueChoices", venueOptions, new Set(["ICLR", "NeurIPS", "ICML", "CVPR", "ACL"]));
  renderChips("searchVenueChoices", venueOptions, new Set());
  renderChips("yearChoices", years.map(String), new Set([String(currentYear), String(currentYear - 1), String(currentYear - 2)]));
  renderChips("searchYearChoices", years.map(String), new Set());
  $("priorityChoices").innerHTML = priorityOptions
    .map(([value, label]) => chipHtml(value, label, true))
    .join("");
}

function renderChips(rootId, values, selected) {
  $(rootId).innerHTML = values.map((value) => chipHtml(value, value, selected.has(String(value)))).join("");
}

function chipHtml(value, label, checked) {
  return `
    <label class="choice-chip">
      <input type="checkbox" value="${escapeHtml(value)}" ${checked ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

async function loadStats() {
  try {
    const [stats, admin, local] = await Promise.all([
      api("/api/v1/cloud/stats"),
      api("/api/v1/cloud/admin/status"),
      api(`/api/v1/cloud/local/summary?field_id=${encodeURIComponent(state.fieldId)}`),
    ]);
    const counts = stats.counts || {};
    const cache = stats.cache || {};
    const localCounts = local.counts || {};
    const unsynced = Object.values(localCounts).reduce((sum, row) => sum + Number(row.unsynced || 0), 0);
    $("snapshotId").textContent = stats.snapshot_id || "-";
    $("workCount").textContent = formatNumber(counts.works);
    $("conceptCount").textContent = formatNumber(counts.concepts);
    $("payloadCacheCount").textContent = formatNumber(cache.payload_count);
    $("localUnsyncedCount").textContent = formatNumber(unsynced);
    $("adminMode").textContent = admin.mode || "-";
    $("cloudHeaderStatus").textContent = stats.warning || admin.message || "Cloud Library is ready.";
    state.localCounts = localCounts;
    renderLocalTabs();
  } catch (error) {
    $("cloudHeaderStatus").textContent = error.message;
  }
}

function crawlPayload({ candidates = [] } = {}) {
  return {
    admin_key: $("adminKey").value,
    venues: checkedValues("venueChoices"),
    years: checkedValues("yearChoices").map((item) => Number(item)).filter(Boolean),
    topics: splitTopics($("crawlTopics").value),
    priority_rules: checkedValues("priorityChoices"),
    max_papers: Number($("crawlMax").value || 100),
    model_mode: $("crawlModelMode").value || "auto",
    field_id: state.fieldId,
    timeout: Number($("crawlTimeout").value || 12),
    force: $("crawlForce").checked,
    dry_run: !candidates.length,
    candidates,
  };
}

function crawlPlanSlices(payload) {
  const venues = payload.venues.length ? payload.venues : [""];
  const years = payload.years.length ? payload.years : [""];
  const combos = [];
  for (const venue of venues) {
    for (const year of years) combos.push({ venue, year });
  }
  const perSlice = Math.max(1, Math.ceil(Number(payload.max_papers || 100) / Math.max(1, combos.length)));
  return combos.map(({ venue, year }) => ({
    ...payload,
    venues: venue ? [venue] : [],
    years: year ? [year] : [],
    max_papers: perSlice,
    dry_run: true,
    candidates: [],
  }));
}

async function addToQueue(event) {
  if (event) event.preventDefault();
  setWorkflow("discover");
  state.queueAdding = true;
  setLoading($("crawlForm"), true);
  if (!state.candidates.length) $("candidateList").innerHTML = loadingRows(5);
  $("crawlRunStatus").textContent = "Adding to queue";
  const basePayload = crawlPayload();
  const targetCount = Number(basePayload.max_papers || 100);
  const slices = crawlPlanSlices(basePayload);
  const seen = new Set(state.candidates.map(candidateKey));
  let added = 0;
  let completed = 0;
  const warnings = [];
  let cursor = 0;

  async function runSlice() {
    while (cursor < slices.length && added < targetCount) {
      const slice = slices[cursor++];
      try {
        const data = await post("/api/v1/cloud/admin/crawl/plan", slice);
        completed += 1;
        for (const item of filterCandidates(data.candidates || [])) {
          if (added >= targetCount) break;
          const key = candidateKey(item);
          if (!key || seen.has(key)) continue;
          seen.add(key);
          state.candidates.push({
            ...item,
            queue_status: item.queue_status || "queued",
            queue_added_at: new Date().toISOString(),
          });
          state.selectedCandidates.add(key);
          added += 1;
          $("crawlRunStatus").textContent = `Adding ${added}/${targetCount}`;
          renderCandidates();
          await new Promise((resolve) => window.requestAnimationFrame(resolve));
        }
        for (const warning of data.metadata_warnings || []) warnings.push(warning);
        $("crawlRunStatus").textContent = `Checked ${completed}/${slices.length}`;
      } catch (error) {
        completed += 1;
        warnings.push(error.message);
      }
    }
  }

  try {
    const workers = Array.from({ length: Math.min(3, Math.max(1, slices.length)) }, () => runSlice());
    await Promise.all(workers);
    renderCandidates();
    $("crawlRunStatus").textContent = added ? "Queue ready" : "No matches";
    const warning = warnings.filter(Boolean)[0];
    if (warning) showToast(warning, "warn");
  } finally {
    state.queueAdding = false;
    setLoading($("crawlForm"), false);
  }
}

function filterCandidates(items) {
  const venues = new Set(checkedValues("venueChoices"));
  const years = new Set(checkedValues("yearChoices").map(String));
  return (items || []).filter((item) => {
    const venue = String(item.venue_or_source || item.target_venue || "");
    const targetVenue = String(item.target_venue || "");
    const year = String(item.year || item.target_year || "");
    const venueOk = !venues.size || venues.has(venue) || venues.has(targetVenue);
    const yearOk = !years.size || years.has(year);
    return venueOk && yearOk;
  });
}

function candidateKey(item) {
  return String(item.work_id || item.source_record_id || item.title || "");
}

function queueStatus(item) {
  const status = item.cloud_research_status || {};
  return String(status.state || item.queue_status || "queued");
}

function queueStatusLabel(status) {
  return {
    queued: "Queued",
    researching: "Researching",
    ready: "Ready to Sync",
    needs_review: "Needs Review",
    metadata_only: "Metadata Only",
    failed: "Failed",
    stopped: "Stopped",
    synced: "Synced",
  }[status] || status.replaceAll("_", " ");
}

function queuedResearchCandidates() {
  return state.candidates.filter((item) => {
    const status = queueStatus(item);
    return !["researching", "ready", "synced"].includes(status);
  });
}

function setCandidateStatus(workId, status, message = "") {
  const key = String(workId || "");
  for (const item of state.candidates) {
    if (candidateKey(item) !== key && String(item.work_id || "") !== key) continue;
    item.queue_status = status;
    if (message) item.queue_message = message;
  }
}

async function refreshQueueStatuses({ silent = false } = {}) {
  if (!state.candidates.length) return;
  try {
    const params = new URLSearchParams({
      field_id: state.fieldId,
      tab: "works",
      offset: "0",
      limit: "1000",
      query: "",
      model_mode: $("crawlModelMode").value || "auto",
      sync_state: "all",
    });
    const data = await api(`/api/v1/cloud/local/tab?${params.toString()}`);
    state.localCounts = data.counts || state.localCounts;
    const byId = new Map();
    for (const item of data.items || []) {
      if (item.work_id) byId.set(String(item.work_id), item);
    }
    for (const item of state.candidates) {
      const local = byId.get(String(item.work_id || candidateKey(item)));
      if (!local) continue;
      item.work_id = local.work_id || item.work_id;
      item.cloud_research_status = local.cloud_research_status || item.cloud_research_status;
      item.queue_status = queueStatus(item);
      item.queue_message = item.cloud_research_status?.message || item.queue_message || "";
    }
    renderLocalTabs();
    renderCandidates();
  } catch (error) {
    if (!silent) showToast(error.message, "error");
  }
}

function renderCandidates() {
  const ready = state.candidates.filter((item) => queueStatus(item) === "ready").length;
  const running = state.candidates.filter((item) => queueStatus(item) === "researching").length;
  $("crawlCount").textContent = `${state.candidates.length} queued${running ? ` · ${running} running` : ""}${ready ? ` · ${ready} ready` : ""}`;
  if (!state.candidates.length) {
    $("candidateList").innerHTML = `
      <div class="empty-state compact">
        <strong>No queued papers.</strong>
        <span>Choose filters and add matching papers to the queue.</span>
      </div>
    `;
    return;
  }
  $("candidateList").innerHTML = state.candidates
    .map((item) => {
      const key = candidateKey(item);
      const status = queueStatus(item);
      const meta = [item.venue_or_source || item.target_venue, item.year || item.target_year, item.citation_count != null ? `${item.citation_count} citations` : "", item.source_provider].filter(Boolean).join(" · ");
      const missing = item.cloud_research_status?.missing_required || [];
      return `
        <article class="candidate-card status-${escapeHtml(status)}" data-candidate="${escapeHtml(key)}">
          <div>
            <h4>${escapeHtml(item.title || "Untitled paper")}</h4>
            <p>${escapeHtml(compact(item.abstract || "No abstract available.", 260))}</p>
            <div class="record-meta">
              <span>${escapeHtml(meta || "metadata")}</span>
              <span>${escapeHtml(item.priority_reason || "")}</span>
              ${missing.length ? `<span>Missing ${escapeHtml(missing.join(", "))}</span>` : ""}
            </div>
          </div>
          <div class="candidate-side">
            <span class="queue-status">${escapeHtml(queueStatusLabel(status))}</span>
            <button type="button" data-action="remove-queue" ${status === "researching" ? "disabled" : ""}>Remove</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function runResearch() {
  const selected = queuedResearchCandidates();
  if (!selected.length) {
    showToast("Add papers to the queue first, or remove ready/synced papers from the queue.", "warn");
    return;
  }
  setWorkflow("research");
  $("crawlRunStatus").textContent = "Starting";
  $("runProgressLabel").textContent = `Queued ${selected.length} paper(s).`;
  $("runProgressDetail").textContent = "Waiting for extraction to start.";
  setLoading($("crawlForm"), true);
  setResearchControls(true);
  try {
    const data = await post("/api/v1/cloud/admin/crawl/run", { ...crawlPayload({ candidates: selected }), max_papers: selected.length, dry_run: false });
    state.crawlRunId = data.run_id || "";
    $("crawlRunStatus").textContent = state.crawlRunId ? "Running" : "Queued";
    for (const item of selected) item.queue_status = "queued";
    renderCandidates();
    if (state.crawlRunId) pollCrawlRun();
  } catch (error) {
    $("crawlRunStatus").textContent = "Run failed";
    showToast(error.message, "error");
    setLoading($("crawlForm"), false);
    setResearchControls(false);
  }
}

function setResearchControls(running) {
  $("runResearch").disabled = Boolean(running);
  $("stopResearch").hidden = !running;
}

async function stopResearch() {
  if (!state.crawlRunId) return;
  $("runProgressLabel").textContent = "Stopping research.";
  $("runProgressDetail").textContent = "Completed papers will remain in the local results tabs.";
  try {
    await post("/api/v1/research/cancel", { run_id: state.crawlRunId });
    $("crawlRunStatus").textContent = "Stopping";
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function pollCrawlRun() {
  if (!state.crawlRunId) return;
  if (state.crawlPollTimer) window.clearTimeout(state.crawlPollTimer);
  try {
    const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(state.crawlRunId)}`);
    const run = data.run || {};
    const counts = run.counts || {};
    const planned = Number(counts.planned || run.target_works || 0);
    const done = Number(counts.extracted_works || 0) + Number(counts.cloud_hits || 0) + Number(counts.skipped_works || 0) + Number(counts.failed_works || 0);
    const stored = Number(counts.stored_works || 0);
    const effectiveDone = done || (["complete", "error", "cancelled"].includes(run.status) ? stored : run.stage === "metadata_store" ? stored : 0);
    const progress = planned ? Math.min(100, Math.round((effectiveDone / planned) * 100)) : 0;
    $("runProgressBar").style.width = `${progress}%`;
    $("runProgressLabel").textContent = run.message || `${run.status || "running"} · ${done}/${planned}`;
    $("runProgressDetail").textContent = [
      planned ? `${effectiveDone}/${planned} ${done ? "processed" : "stored"}` : "",
      counts.cloud_hits ? `${counts.cloud_hits} cloud hit(s)` : "",
      counts.failed_works ? `${counts.failed_works} failed` : "",
    ].filter(Boolean).join(" · ") || (run.stage || "running");
    $("crawlRunStatus").textContent = run.status || "running";
    if (counts.current_work_id) setCandidateStatus(counts.current_work_id, "researching", run.message || "Researching.");
    const terminal = ["complete", "error", "cancelled"].includes(run.status);
    if (terminal) {
      setLoading($("crawlForm"), false);
      setResearchControls(false);
      state.crawlRunId = "";
    }
    await loadLocalTab({ reset: true, silent: true });
    await refreshQueueStatuses({ silent: true });
    await loadStats();
    if (terminal) {
      setWorkflow("review");
      if (run.status === "complete") showToast("Research run complete.");
      if (run.status === "error") showToast(run.message || "Research finished with errors.", "error");
      if (run.status === "cancelled") showToast("Research stopped. Completed papers were saved.", "warn");
      return;
    }
  } catch (error) {
    $("crawlRunStatus").textContent = error.message;
    if (!state.crawlRunId) return;
  }
  state.crawlPollTimer = window.setTimeout(pollCrawlRun, 1800);
}

function renderLocalTabs() {
  $("localTabRow").innerHTML = tabs
    .map((tab) => {
      const counts = state.localCounts[tab.key] || {};
      const active = state.activeLocalTab === tab.key ? "active" : "";
      return `<button type="button" class="${active}" data-local-tab="${escapeHtml(tab.key)}">${escapeHtml(tab.label)} <span>${formatNumber(counts.unsynced || 0)}</span></button>`;
    })
    .join("");
}

async function loadLocalTab({ reset = false, silent = false } = {}) {
  if (reset) {
    state.localOffset = 0;
    state.localItems = [];
    if (!silent) $("localTabContent").innerHTML = loadingRows(4);
  } else {
    $("localMoreBtn").textContent = "Loading...";
  }
  const params = new URLSearchParams({
    field_id: state.fieldId,
    tab: state.activeLocalTab,
    offset: String(state.localOffset),
    limit: String(state.localLimit),
    query: $("localTabSearch").value.trim(),
    model_mode: $("crawlModelMode").value || "auto",
    sync_state: "unsynced",
  });
  try {
    const data = await api(`/api/v1/cloud/local/tab?${params.toString()}`);
    state.localCounts = data.counts || state.localCounts;
    state.localItems = reset ? data.items || [] : [...state.localItems, ...(data.items || [])];
    state.localOffset = state.localItems.length;
    state.localHasMore = Boolean(data.has_more);
    renderLocalTabs();
    renderLocalItems();
  } catch (error) {
    $("localTabContent").innerHTML = `<div class="empty-state"><strong>Unable to load records.</strong><span>${escapeHtml(error.message)}</span></div>`;
  } finally {
    $("localMoreBtn").textContent = "Load More";
    $("localMoreBtn").hidden = !state.localHasMore;
  }
}

function renderLocalItems() {
  if (!state.localItems.length) {
    $("localTabContent").innerHTML = `<div class="empty-state"><strong>No unsynced ${escapeHtml(tabLabel(state.activeLocalTab))}.</strong><span>Newly researched cloud-crawl records appear here until synced.</span></div>`;
    return;
  }
  $("localTabContent").innerHTML = state.localItems.map((item) => renderRecordCard(state.activeLocalTab, item, { local: true })).join("");
}

function tabLabel(key) {
  return tabs.find((tab) => tab.key === key)?.label || key;
}

function idFor(tabKey, item) {
  const tab = tabs.find((entry) => entry.key === tabKey);
  return String(item?.[tab?.idKey] || item?.canonical_id || item?.concept_id || item?.work_id || item?.id || "");
}

function renderRecordCard(tabKey, item, { local = false, cloud = false } = {}) {
  if (tabKey === "works" || tabKey === "ready_works") return renderWorkCard(item, { local, cloud, tabKey });
  if (tabKey === "benchmarks") return renderBenchmarkCard(item, { local, cloud });
  if (tabKey === "baselines") return renderBaselineCard(item, { local, cloud });
  if (tabKey === "principles") return renderTextCard(tabKey, item, "Principle", item.name || item.title, item.argument || item.abstract_signature || item.summary, { local, cloud });
  if (tabKey === "takeaway_messages") return renderTextCard(tabKey, item, "Takeaway", item.title, item.main_results || item.message_text || item.finding || item.actionable_lesson, { local, cloud });
  return renderTextCard(tabKey, item, "Existed Idea", item.title, item.core_idea || item.idea_text || item.summary, { local, cloud });
}

function cardAttrs(tabKey, item, local, cloud) {
  return `data-tab="${escapeHtml(tabKey)}" data-id="${escapeHtml(idFor(tabKey, item))}" data-local="${local ? "1" : "0"}" data-cloud="${cloud ? "1" : "0"}"`;
}

function renderWorkCard(item, opts) {
  const links = [item.url_or_doi, item.paper_link, ...(item.source_urls || [])].filter(isUrl);
  const meta = [item.venue_or_source || item.venue || item.target_venue || item.source_type, item.year || item.target_year || "n.d.", item.model_name || "", item.work_extracted ? "extracted" : ""].filter(Boolean).join(" · ");
  const status = item.cloud_research_status || {};
  const missing = status.missing_required || [];
  return `
    <article class="record-row record-works" ${cardAttrs(opts.tabKey || "works", item, opts.local, opts.cloud)}>
      <div>
        <h3>${escapeHtml(item.title || item.canonical_title || "Untitled Work")}</h3>
        <p>${escapeHtml(compact(item.abstract || item.summary || "No abstract available.", 320))}</p>
        <div class="record-meta">
          <span>${escapeHtml(meta)}</span>
          ${status.state ? `<span class="inline-status">${escapeHtml(queueStatusLabel(status.state))}</span>` : ""}
          ${missing.length ? `<span>Missing ${escapeHtml(missing.join(", "))}</span>` : ""}
          ${links[0] ? `<a href="${escapeHtml(links[0])}" target="_blank" rel="noreferrer">Paper</a>` : ""}
        </div>
      </div>
      <div class="record-actions">${recordButtons(opts)}</div>
    </article>
  `;
}

function renderTextCard(tabKey, item, fallback, title, body, opts) {
  const meta = [item.venue_or_source || item.venue || "source", item.year || "n.d.", item.model_name || ""].filter(Boolean).join(" · ");
  return `
    <article class="record-row record-${escapeHtml(tabKey)}" ${cardAttrs(tabKey, item, opts.local, opts.cloud)}>
      <div>
        <h3>${escapeHtml(title || compact(body, 88) || fallback)}</h3>
        <p>${escapeHtml(compact(body || item.payload_summary || "No summary available.", 300))}</p>
        <div class="record-meta"><span>${escapeHtml(meta)}</span></div>
      </div>
      <div class="record-actions">${recordButtons(opts)}</div>
    </article>
  `;
}

function renderBenchmarkCard(item, opts) {
  return `
    <article class="record-row record-benchmarks" ${cardAttrs("benchmarks", item, opts.local, opts.cloud)}>
      <div class="benchmark-row-grid">
        <div><span class="mini-label">Benchmark</span><strong>${escapeHtml(item.benchmark_name || item.dataset || item.canonical_label || "Benchmark")}</strong></div>
        <div><span class="mini-label">Task</span><span>${escapeHtml(compact(item.task || "unspecified", 80))}</span></div>
        <div><span class="mini-label">Data</span><span>${escapeHtml(compact(item.data_form || "public dataset", 80))}</span></div>
        <div><span class="mini-label">Metrics</span><span>${escapeHtml(compact((item.metrics || [item.metric]).filter(Boolean).join(", "), 80))}</span></div>
      </div>
      <div class="record-actions">${recordButtons(opts)}</div>
    </article>
  `;
}

function renderBaselineCard(item, opts) {
  return `
    <article class="record-row record-baselines" ${cardAttrs("baselines", item, opts.local, opts.cloud)}>
      <div>
        <h3>${escapeHtml(item.baseline_name || item.canonical_label || "Baseline")}</h3>
        <p>${escapeHtml(compact(item.core_idea || item.methodology || item.description || item.principle || item.payload_summary, 300))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.baseline_type || "published")}</span>
          <span>${Number(item.source_work_ids?.length || item.source_works?.length || 0)} works</span>
        </div>
      </div>
      <div class="record-actions">${recordButtons(opts)}</div>
    </article>
  `;
}

function recordButtons(opts) {
  if (opts.cloud) {
    return `<button type="button" data-action="hydrate-cloud">Load Local</button><button type="button" data-action="details">Details</button>`;
  }
  return `<button type="button" data-action="open-tab">Open Tab</button><button type="button" data-action="details">Details</button>`;
}

async function syncUnsynced() {
  setWorkflow("sync");
  $("syncStatus").textContent = "Preparing ready papers for cloud contribution.";
  try {
    const allWorks = await api(`/api/v1/cloud/local/tab?${new URLSearchParams({ field_id: state.fieldId, tab: "ready_works", offset: "0", limit: "1000", sync_state: "unsynced", model_mode: $("crawlModelMode").value || "auto" }).toString()}`);
    const workIds = (allWorks.items || []).map((item) => item.work_id).filter(Boolean);
    if (!workIds.length) {
      $("syncStatus").textContent = "No ready papers to upload. A paper needs existed ideas, principles, and takeaways first.";
      showToast("No ready papers to upload.", "warn");
      return;
    }
    const prepared = await post("/api/v1/cloud/upload/prepare", {
      admin_key: $("adminKey").value,
      upload_mode: $("uploadMode").value,
      model_mode: $("crawlModelMode").value || "auto",
      work_ids: workIds,
      field_id: state.fieldId,
    });
    state.lastContributionPath = prepared.path || "";
    if (!prepared.ok || !state.lastContributionPath) {
      const rejected = prepared.upload_decisions?.filter((item) => !item.upload_allowed) || [];
      const missing = rejected.flatMap((item) => item.missing_required_extractions || []);
      $("syncStatus").textContent = missing.length
        ? `Upload blocked: missing ${[...new Set(missing)].join(", ")}.`
        : `Prepared with ${prepared.rejected_work_ids?.length || 0} rejected work(s).`;
      showToast("Contribution prepared but no work passed upload rules.", "warn");
      return;
    }
    $("syncStatus").textContent = `Prepared ${prepared.allowed_work_ids.length} work(s). Submitting through maintainer direct push.`;
    const submitted = await post("/api/v1/cloud/upload/submit", {
      admin_key: $("adminKey").value,
      upload_mode: $("uploadMode").value,
      contribution_path: state.lastContributionPath,
      field_id: state.fieldId,
      work_ids: workIds,
      local_work_ids: prepared.local_work_ids || workIds,
    });
    const pushed = submitted.direct_push && submitted.direct_push.pushed;
    $("syncStatus").textContent = pushed
      ? `Synced ${formatNumber(submitted.sync_result?.work_ids?.length || prepared.allowed_work_ids.length)} work(s) to ${submitted.direct_push.branch}.`
      : "Contribution file is prepared; direct push did not complete.";
    showToast(pushed ? "Cloud sync complete." : "Cloud contribution prepared.", pushed ? "success" : "warn");
    state.candidates = state.candidates.filter((item) => !workIds.includes(String(item.work_id || candidateKey(item))));
    await loadStats();
    await loadLocalTab({ reset: true });
    renderCandidates();
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  }
}

async function clearSyncedCache() {
  if (!window.confirm("Clear cloud-crawled records that are already synced and not used by other projects?")) return;
  $("syncStatus").textContent = "Clearing synced local cache.";
  try {
    const result = await post("/api/v1/cloud/local/cleanup", {
      admin_key: $("adminKey").value,
      field_id: state.fieldId,
    });
    $("syncStatus").textContent = `Removed ${formatNumber(result.deleted?.records || 0)} local record(s) and ${formatNumber(result.deleted?.project_memberships || 0)} cloud-crawl membership(s).`;
    await loadStats();
    await loadLocalTab({ reset: true });
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  }
}

function renderCloudResultTabs() {
  const counts = cloudResultCounts();
  $("cloudResultTabRow").innerHTML = cloudTabs
    .map((tab) => `<button type="button" class="${state.activeCloudTab === tab.key ? "active" : ""}" data-cloud-tab="${escapeHtml(tab.key)}">${escapeHtml(tab.label)} <span>${formatNumber(counts[tab.key] || 0)}</span></button>`)
    .join("");
}

function cloudResultCounts() {
  const counts = { works: state.cloudItems.length };
  for (const tab of cloudTabs.slice(1)) counts[tab.key] = derivedConceptRows(tab.key).length;
  return counts;
}

async function searchCloud(event, { reset = true } = {}) {
  if (event) event.preventDefault();
  if (reset) {
    state.cloudOffset = 0;
    state.cloudItems = [];
    $("cloudResults").innerHTML = loadingRows(4);
  }
  $("cloudSearchStatus").textContent = "Searching";
  try {
    const payload = {
      query: $("cloudQuery").value.trim(),
      venues: checkedValues("searchVenueChoices"),
      years: checkedValues("searchYearChoices").map((item) => Number(item)).filter(Boolean),
      concept_type: $("conceptTypeFilter").value,
      model_mode: $("cloudModelMode").value,
      limit: state.cloudLimit,
      offset: state.cloudOffset,
    };
    const data = await post("/api/v1/cloud/search", payload);
    state.cloudItems = reset ? data.items || [] : [...state.cloudItems, ...(data.items || [])];
    state.cloudOffset = state.cloudItems.length;
    state.cloudHasMore = Boolean(data.has_more);
    $("cloudSearchStatus").textContent = `${formatNumber(state.cloudItems.length)} loaded`;
    renderCloudResultTabs();
    renderCloudResults();
    $("cloudMoreBtn").hidden = !state.cloudHasMore;
  } catch (error) {
    $("cloudSearchStatus").textContent = "Search failed";
    $("cloudResults").innerHTML = `<div class="empty-state"><strong>Unable to search cloud.</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

function derivedConceptRows(tabKey) {
  const tab = tabs.find((entry) => entry.key === tabKey);
  if (!tab || tab.key === "works") return state.cloudItems;
  const rows = [];
  for (const work of state.cloudItems) {
    const labels = work.concept_labels || [];
    const types = work.concept_types || [];
    labels.forEach((label, index) => {
      if (types[index] && types[index] !== tab.conceptType) return;
      if (!types[index] && $("conceptTypeFilter").value && $("conceptTypeFilter").value !== tab.conceptType) return;
      rows.push({
        canonical_id: `${work.work_id || work.title}-${tab.key}-${index}`,
        title: label,
        core_idea: label,
        argument: label,
        main_results: label,
        venue_or_source: work.venue,
        year: work.year,
        source_work_ids: [work.work_id].filter(Boolean),
        source_work_title: work.title,
        source_work: work,
      });
    });
  }
  return rows;
}

function renderCloudResults() {
  const rows = state.activeCloudTab === "works" ? state.cloudItems : derivedConceptRows(state.activeCloudTab);
  if (!rows.length) {
    $("cloudResults").innerHTML = `<div class="empty-state"><strong>No ${escapeHtml(tabLabel(state.activeCloudTab))} found.</strong><span>Search results load ten records at a time.</span></div>`;
    return;
  }
  $("cloudResults").innerHTML = rows.map((item) => renderRecordCard(state.activeCloudTab, item, { cloud: true })).join("");
}

async function hydrateCloudRow(row) {
  const id = row.dataset.id;
  let item = state.cloudItems.find((entry) => String(entry.work_id || entry.title) === id) || state.cloudItems.find((entry) => String(entry.work_id || "") === id);
  if (!item && row.dataset.tab !== "works") {
    const derived = derivedConceptRows(row.dataset.tab).find((entry) => String(entry.canonical_id || entry.title) === id);
    item = derived?.source_work || null;
  }
  if (!item) return;
  try {
    const data = await post("/api/v1/cloud/resolve", {
      candidates: [item],
      hydrate: true,
      field_id: state.fieldId,
      model_key: "",
    });
    const decision = (data.items || [])[0] || {};
    showToast(decision.hydrated ? "Cloud record loaded into local cache." : decision.decision || "Cloud record checked.", decision.should_extract ? "warn" : "success");
    await loadStats();
    await loadLocalTab({ reset: true, silent: true });
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function openLocalDetail(tabKey, id) {
  const tab = tabs.find((entry) => entry.key === tabKey);
  const params = new URLSearchParams({ bucket: tab.bucket, id, model_mode: $("crawlModelMode").value || "auto" });
  const data = await api(`/api/v1/item/detail?${params.toString()}`);
  openDetailModal(data.item, { tabKey, id, local: true });
}

function openCloudDetail(tabKey, id) {
  const rows = tabKey === "works" ? state.cloudItems : derivedConceptRows(tabKey);
  const item = rows.find((entry) => String(entry.work_id || entry.canonical_id || entry.title) === id);
  if (item) openDetailModal(item, { tabKey, id, local: false });
}

function openDetailModal(item, { tabKey, id, local }) {
  state.detail = { item, tab: tabKey, id, local };
  $("detailKind").textContent = local ? tabLabel(tabKey) : `Cloud ${tabLabel(tabKey)}`;
  $("detailTitle").textContent = item.title || item.name || item.benchmark_name || item.baseline_name || item.canonical_title || "Details";
  $("detailBody").innerHTML = detailSections(item, tabKey);
  $("detailRaw").textContent = JSON.stringify(item, null, 2);
  $("openDetailTab").hidden = !local;
  $("detailModal").hidden = false;
}

function detailSections(item, tabKey) {
  const links = [item.url_or_doi, item.paper_link, item.official_url, item.official_code_url, ...(item.source_urls || []), ...(item.source_paper_links || [])].filter(isUrl);
  const shared = `
    ${detailList("Links", links, true)}
    ${detailBlock("Evidence", item.evidence || item.snippet)}
    ${detailBlock("Version", [item.provider || item.model_name, item.extracted_at || item.updated_at].filter(Boolean).join(" / "))}
  `;
  if (tabKey === "works" || tabKey === "ready_works") {
    return `
      ${detailBlock("Abstract", item.abstract || item.summary)}
      ${detailKeyValues({
        Venue: item.venue_or_source || item.venue || item.target_venue,
        Year: item.year || item.target_year,
        Authors: Array.isArray(item.authors) ? item.authors.join(", ") : item.authors,
        DOI: item.doi,
        "arXiv": item.arxiv_id,
        "Cloud Sync": item.cloud_sync_status || item.decision,
      })}
      ${detailList("Concept Signals", item.concept_labels)}
      ${shared}
    `;
  }
  if (tabKey === "benchmarks") {
    return `${detailBlock("Description", item.description || item.benchmark_name)}${detailBlock("Task", item.task)}${detailBlock("Data Form", item.data_form)}${detailList("Metrics", item.metrics || item.metric)}${shared}`;
  }
  if (tabKey === "baselines") {
    return `${detailBlock("Core Idea", item.core_idea || item.description || item.summary)}${detailBlock("Methodology", item.methodology || item.principle)}${detailList("Benchmarks", item.benchmarks)}${shared}`;
  }
  if (tabKey === "principles") {
    return `${detailBlock("Argument", item.argument || item.abstract_signature || item.summary)}${detailBlock("Discussion", item.discussion)}${detailList("Boundary Conditions", item.boundary_conditions)}${shared}`;
  }
  if (tabKey === "takeaway_messages") {
    return `${detailBlock("Main Results", item.main_results || item.message_text || item.finding)}${detailBlock("Condition", item.condition)}${detailBlock("Actionable Lesson", item.actionable_lesson)}${shared}`;
  }
  return `${detailBlock("Core Idea", item.core_idea || item.idea_text || item.summary)}${detailBlock("Mechanism", item.mechanism)}${detailBlock("Discussion", item.discussion)}${shared}`;
}

function detailBlock(title, value) {
  if (!value) return "";
  return `<section><h3>${escapeHtml(title)}</h3><p>${escapeHtml(Array.isArray(value) ? value.join("; ") : value)}</p></section>`;
}

function detailList(title, values, links = false) {
  const list = Array.isArray(values) ? values.filter(Boolean) : values ? [values] : [];
  if (!list.length) return "";
  return `<section><h3>${escapeHtml(title)}</h3><ul>${list.slice(0, 32).map((item) => `<li>${links && isUrl(item) ? `<a href="${escapeHtml(item)}" target="_blank" rel="noreferrer">${escapeHtml(item)}</a>` : escapeHtml(item)}</li>`).join("")}</ul></section>`;
}

function detailKeyValues(values) {
  const rows = Object.entries(values).filter(([, value]) => value !== "" && value != null && !(Array.isArray(value) && !value.length));
  if (!rows.length) return "";
  return `<section><h3>Metadata</h3><dl class="key-values">${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(Array.isArray(value) ? value.join(", ") : value)}</dd>`).join("")}</dl></section>`;
}

function openCurrentDetailInTab() {
  if (!state.detail.local) return;
  const tab = tabs.find((entry) => entry.key === state.detail.tab);
  if (!tab || !state.detail.id) return;
  window.open(`/item.html?bucket=${encodeURIComponent(tab.bucket)}&id=${encodeURIComponent(state.detail.id)}&field_id=${encodeURIComponent(state.fieldId)}&model_mode=${encodeURIComponent($("crawlModelMode").value || "auto")}`, "_blank");
}

async function exportAdminOperation(event) {
  event.preventDefault();
  $("adminStatus").textContent = "Exporting";
  try {
    const action = $("adminAction").value;
    const targetId = $("adminTargetId").value.trim();
    const field = $("adminField").value.trim();
    const rawValue = $("adminValue").value.trim();
    const payload = { target_id: targetId };
    if (action === "edit" && field) payload.fields = { [field]: parseAdminValue(rawValue) };
    if (action === "merge-concepts") payload.source_ids = rawValue.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
    const data = await post(`/api/v1/cloud/admin/${action}`, {
      admin_key: $("adminKey").value,
      target_type: $("adminTargetType").value,
      reason: $("adminReason").value.trim(),
      payload,
    });
    $("adminStatus").textContent = "Exported";
    showToast(`Admin operation exported: ${data.operation?.operation_id || action}`);
  } catch (error) {
    $("adminStatus").textContent = "Failed";
    showToast(error.message, "error");
  }
}

function parseAdminValue(raw) {
  if (!raw) return "";
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function resetCloudSearch() {
  $("cloudQuery").value = "";
  $("conceptTypeFilter").value = "";
  $("cloudModelMode").value = "";
  $("searchVenueChoices").querySelectorAll("input").forEach((input) => (input.checked = false));
  $("searchYearChoices").querySelectorAll("input").forEach((input) => (input.checked = false));
  state.cloudItems = [];
  state.cloudOffset = 0;
  renderCloudResultTabs();
  renderCloudResults();
}

function debounce(fn, delay = 250) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

function wireEvents() {
  $("refreshStats").addEventListener("click", () => {
    loadStats();
    loadLocalTab({ reset: true });
  });
  $("crawlForm").addEventListener("submit", addToQueue);
  $("runResearch").addEventListener("click", runResearch);
  $("stopResearch").addEventListener("click", stopResearch);
  $("candidateList").addEventListener("click", (event) => {
    const card = event.target.closest("[data-candidate]");
    if (!card) return;
    if (event.target.closest("[data-action='remove-queue']")) {
      state.candidates = state.candidates.filter((item) => candidateKey(item) !== card.dataset.candidate);
      state.selectedCandidates.delete(card.dataset.candidate);
      renderCandidates();
    }
  });
  $("selectAllCandidates").addEventListener("click", () => {
    refreshQueueStatuses();
  });
  $("clearCandidateSelection").addEventListener("click", () => {
    if (state.crawlRunId) {
      showToast("Stop the active research run before clearing the queue.", "warn");
      return;
    }
    state.candidates = [];
    state.selectedCandidates.clear();
    renderCandidates();
  });
  $("localTabRow").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-local-tab]");
    if (!button) return;
    state.activeLocalTab = button.dataset.localTab;
    await loadLocalTab({ reset: true });
  });
  $("localTabContent").addEventListener("click", async (event) => {
    const row = event.target.closest("[data-id]");
    if (!row) return;
    if (event.target.closest("[data-action='open-tab']")) {
      state.detail = { tab: row.dataset.tab, id: row.dataset.id, local: true };
      openCurrentDetailInTab();
      return;
    }
    await openLocalDetail(row.dataset.tab, row.dataset.id);
  });
  $("reloadLocalTab").addEventListener("click", () => loadLocalTab({ reset: true }));
  $("localMoreBtn").addEventListener("click", () => loadLocalTab({ reset: false }));
  $("localTabSearch").addEventListener("input", debounce(() => loadLocalTab({ reset: true, silent: true }), 260));
  $("syncUnsynced").addEventListener("click", syncUnsynced);
  $("clearSyncedCache").addEventListener("click", clearSyncedCache);
  $("cloudSearchForm").addEventListener("submit", (event) => searchCloud(event, { reset: true }));
  $("cloudMoreBtn").addEventListener("click", () => searchCloud(null, { reset: false }));
  $("resetCloudSearch").addEventListener("click", resetCloudSearch);
  $("cloudResultTabRow").addEventListener("click", (event) => {
    const button = event.target.closest("[data-cloud-tab]");
    if (!button) return;
    state.activeCloudTab = button.dataset.cloudTab;
    renderCloudResultTabs();
    renderCloudResults();
  });
  $("cloudResults").addEventListener("click", async (event) => {
    const row = event.target.closest("[data-id]");
    if (!row) return;
    if (event.target.closest("[data-action='hydrate-cloud']")) {
      await hydrateCloudRow(row);
      return;
    }
    openCloudDetail(row.dataset.tab, row.dataset.id);
  });
  $("adminForm").addEventListener("submit", exportAdminOperation);
  $("closeDetail").addEventListener("click", () => ($("detailModal").hidden = true));
  $("openDetailTab").addEventListener("click", openCurrentDetailInTab);
}

async function init() {
  renderModelSelects();
  renderChoiceGroups();
  renderLocalTabs();
  renderCloudResultTabs();
  wireEvents();
  await loadStats();
  await loadLocalTab({ reset: true });
  renderCloudResults();
}

init();
