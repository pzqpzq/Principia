const localTabs = [
  { key: "queued_works", label: "Queued Papers", idKey: "work_id", bucket: "source_works", workTab: true },
  { key: "research_tasks", label: "Research Tasks", idKey: "work_id", bucket: "source_works", workTab: true },
  { key: "ready_works", label: "Ready Papers", idKey: "work_id", bucket: "source_works", workTab: true },
  { key: "existed_ideas", label: "Existed Ideas", idKey: "canonical_id", bucket: "existed_ideas", conceptType: "existed_idea" },
  { key: "benchmarks", label: "Benchmarks", idKey: "benchmark_id", bucket: "benchmark_records", conceptType: "benchmark" },
  { key: "baselines", label: "Baselines", idKey: "baseline_id", bucket: "baseline_records", conceptType: "baseline" },
  { key: "principles", label: "Principles", idKey: "principle_id", bucket: "principles", conceptType: "principle" },
  { key: "takeaway_messages", label: "Takeaways", idKey: "canonical_id", bucket: "takeaway_messages", conceptType: "takeaway_message" },
];

const cloudTabs = [
  { key: "works", label: "Works", idKey: "work_id", bucket: "source_works" },
  { key: "existed_ideas", label: "Existed Ideas", idKey: "canonical_id", bucket: "existed_ideas", conceptType: "existed_idea" },
  { key: "benchmarks", label: "Benchmarks", idKey: "benchmark_id", bucket: "benchmark_records", conceptType: "benchmark" },
  { key: "baselines", label: "Baselines", idKey: "baseline_id", bucket: "baseline_records", conceptType: "baseline" },
  { key: "principles", label: "Principles", idKey: "principle_id", bucket: "principles", conceptType: "principle" },
  { key: "takeaway_messages", label: "Takeaways", idKey: "canonical_id", bucket: "takeaway_messages", conceptType: "takeaway_message" },
];
const tabs = [...localTabs, ...cloudTabs];

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
  ["openai_gpt55", "OpenAI / Local-compatible"],
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
const OTHER_FILTER_VALUE = "__other__";

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
  queuedIds: new Set(),
  researchTaskIds: new Set(),
  queueAdding: false,
  searchCancelRequested: false,
  searchControllers: [],
  queueAddActive: false,
  queueAddPaused: false,
  queueAddCancelRequested: false,
  queueAddControllers: [],
  crawlRunId: "",
  crawlPollTimer: null,
  activeLocalTab: "queued_works",
  localItems: [],
  localOffset: 0,
  localLimit: 10,
  localTotal: 0,
  localHasMore: false,
  localCounts: {},
  localTabCache: new Map(),
  localTabRequestId: 0,
  yearOptions: [],
  lastStatsAt: 0,
  lastLocalRefreshAt: 0,
  syncRunning: false,
  queueFilterMode: "all",
  queueFilterAction: "view",
  researchModelMode: localStorage.getItem("principia.cloudResearchModelMode") || "",
  activeCloudTab: "works",
  cloudItems: [],
  cloudOffset: 0,
  cloudLimit: 10,
  cloudTotal: 0,
  cloudHasMore: false,
  cloudWarning: "",
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

function post(path, payload, options = {}) {
  return api(path, { method: "POST", body: JSON.stringify(payload || {}), ...options });
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

function setButtonBusy(button, loading, busyText = "Loading...", idleText = "") {
  if (!button) return;
  if (loading) {
    button.dataset.idleText = button.dataset.idleText || button.textContent;
    button.textContent = busyText;
    button.classList.add("is-loading");
    button.disabled = true;
  } else {
    button.textContent = idleText || button.dataset.idleText || button.textContent;
    button.classList.remove("is-loading");
    button.disabled = false;
  }
}

function setQueueAddLoading(loading) {
  state.queueAdding = Boolean(loading);
  state.queueAddActive = Boolean(loading);
  const panel = document.querySelector(".candidate-panel");
  panel?.classList.toggle("is-loading", Boolean(loading));
  setButtonBusy($("addSearchResultsToQueue"), Boolean(loading), "Adding...");
  const pauseButton = $("pauseQueueAdd");
  if (pauseButton) {
    pauseButton.disabled = !loading;
    pauseButton.textContent = state.queueAddPaused ? "Resume" : "Pause";
  }
  if ($("cancelQueueAdd")) $("cancelQueueAdd").disabled = !loading;
}

function updateQueueAddControls() {
  const adding = Boolean(state.queueAddActive);
  if ($("pauseQueueAdd")) {
    $("pauseQueueAdd").disabled = !adding;
    $("pauseQueueAdd").textContent = state.queueAddPaused ? "Resume" : "Pause";
  }
  if ($("cancelQueueAdd")) $("cancelQueueAdd").disabled = !adding;
  if ($("addSearchResultsToQueue") && !adding) {
    $("addSearchResultsToQueue").disabled = !state.candidates.some((item) => queueStatus(item) !== "queued");
  }
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitForQueueAddResume() {
  while (state.queueAddPaused && !state.queueAddCancelRequested) {
    $("crawlRunStatus").textContent = "Queue add paused";
    await sleep(150);
  }
}

function chunkItems(items, size = 25) {
  const chunks = [];
  for (let index = 0; index < items.length; index += size) chunks.push(items.slice(index, index + size));
  return chunks;
}

function toggleQueueAddPause() {
  if (!state.queueAddActive) return;
  state.queueAddPaused = !state.queueAddPaused;
  updateQueueAddControls();
  $("crawlRunStatus").textContent = state.queueAddPaused ? "Queue add paused" : "Resuming queue add...";
}

function cancelQueueAdd() {
  if (!state.queueAddActive) return;
  state.queueAddCancelRequested = true;
  state.queueAddPaused = false;
  $("crawlRunStatus").textContent = "Cancelling queue add...";
  for (const controller of state.queueAddControllers) controller.abort();
  updateQueueAddControls();
}

function setLocalTabLoading(loading) {
  $("localTabContent")?.classList.toggle("is-loading", Boolean(loading));
  $("reloadLocalTab").disabled = Boolean(loading);
}

function splitTopics(value) {
  const base = String(value || "")
    .split(/[,;\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return expandTopicVariants(base);
}

function expandTopicVariants(topics) {
  const variants = [];
  for (const topic of topics || []) {
    const text = String(topic || "").trim();
    if (!text) continue;
    variants.push(text);
    if (text.includes("^")) {
      variants.push(text.replace(/\^+/g, ""));
      variants.push(text.replace(/\^+/g, " "));
    }
    const compacted = text.replace(/[^A-Za-z0-9]+/g, "").toLowerCase();
    if (compacted === "vit3") {
      variants.push("VIT3", "ViT3", "VIT 3", "ViT 3", "vision transformer 3", "vision transformer cubed");
    }
  }
  return [...new Set(variants.map((item) => item.trim()).filter(Boolean))];
}

function checkedValues(rootId) {
  return [...$(rootId).querySelectorAll("input[type='checkbox']:checked")]
    .map((node) => node.value)
    .filter((value) => value !== "__all__");
}

function filterSelection(rootId) {
  const values = checkedValues(rootId);
  return {
    values: values.filter((value) => value !== OTHER_FILTER_VALUE),
    includeOther: values.includes(OTHER_FILTER_VALUE),
  };
}

function renderModelSelects() {
  $("crawlModelMode").innerHTML = modelOptions.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
  $("queueFilterMode").innerHTML = `<option value="all">All queued papers</option>` + modelOptions.map(([value, label]) => `<option value="${escapeHtml(value)}">Missing ${escapeHtml(label)}</option>`).join("");
  $("researchModelMode").innerHTML = modelOptions.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
  $("cloudModelMode").innerHTML = `<option value="">All model versions</option>` + modelOptions.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
  $("queueFilterMode").value = state.queueFilterMode;
  const initialResearchMode = state.researchModelMode || $("crawlModelMode").value || "auto";
  $("researchModelMode").value = initialResearchMode;
  state.researchModelMode = initialResearchMode;
}

function targetModelMode() {
  return state.researchModelMode || $("crawlModelMode")?.value || "auto";
}

function localModelMode() {
  if (state.activeLocalTab === "queued_works") return state.queueFilterMode;
  if (state.activeLocalTab === "research_tasks") return "all";
  if (state.activeLocalTab === "ready_works") return "all";
  return targetModelMode();
}

function modelLabel(mode) {
  if (mode === "all") return "All queued papers";
  return modelOptions.find(([value]) => value === mode)?.[1] || mode || "Auto router";
}

function modelLabelFromKey(modelKey) {
  const parts = String(modelKey || "").split(":");
  return parts[1] || modelLabel(parts[2] || "");
}

function displayModelForItem(item, fallbackMode = "") {
  const status = item.cloud_research_status || {};
  const explicit = item.cloud_target_model_name || status.model_name || item.model_name || item.llm_model;
  if (explicit) return explicit;
  const keys = Array.isArray(item.model_keys) ? item.model_keys : [item.model_key].filter(Boolean);
  if (keys.length) {
    const preferred = fallbackMode ? keys.find((key) => String(key).split(":")[2] === fallbackMode) : "";
    return modelLabelFromKey(preferred || keys[0]);
  }
  return modelLabel(fallbackMode || targetModelMode());
}

function clearLocalCache() {
  state.localTabCache.clear();
}

function mergeLocalCounts(counts) {
  if (counts && Object.keys(counts).length) state.localCounts = counts;
}

function renderChoiceGroups() {
  const currentYear = new Date().getFullYear();
  const years = [currentYear, currentYear - 1, currentYear - 2, currentYear - 3, currentYear - 4].filter((year) => year >= 2020);
  state.yearOptions = years.map(String);
  renderChips("venueChoices", venueOptions, new Set(["ICLR", "NeurIPS", "ICML", "CVPR", "ACL"]), { selectAll: true, other: true });
  renderChips("searchVenueChoices", venueOptions, new Set(), { selectAll: true, other: true });
  renderChips("yearChoices", state.yearOptions, new Set([String(currentYear), String(currentYear - 1), String(currentYear - 2)]), { selectAll: true, other: true });
  renderChips("searchYearChoices", state.yearOptions, new Set(), { selectAll: true, other: true });
  $("priorityChoices").innerHTML = priorityOptions
    .map(([value, label]) => chipHtml(value, label, true))
    .join("");
}

function renderChips(rootId, values, selected, { selectAll = false, other = false } = {}) {
  $(rootId).innerHTML = [
    selectAll ? chipHtml("__all__", "Select all", false, "select-all") : "",
    ...values.map((value) => chipHtml(value, value, selected.has(String(value)))),
    other ? chipHtml(OTHER_FILTER_VALUE, "Others", selected.has(OTHER_FILTER_VALUE), "other-chip") : "",
  ].join("");
}

function chipHtml(value, label, checked, extraClass = "") {
  return `
    <label class="choice-chip ${escapeHtml(extraClass)}">
      <input type="checkbox" value="${escapeHtml(value)}" ${checked ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

function wireSelectAllChips(rootId) {
  const root = $(rootId);
  if (!root) return;
  root.addEventListener("change", (event) => {
    const input = event.target.closest("input[type='checkbox']");
    if (!input) return;
    const all = root.querySelector("input[value='__all__']");
    const items = [...root.querySelectorAll("input[type='checkbox']")].filter((node) => node.value !== "__all__");
    if (input.value === "__all__") {
      items.forEach((node) => (node.checked = input.checked));
      return;
    }
    if (all) all.checked = items.length > 0 && items.every((node) => node.checked);
  });
}

async function loadStats() {
  try {
    const [stats, admin, local] = await Promise.all([
      api("/api/v1/cloud/stats"),
      api("/api/v1/cloud/admin/status"),
      api(`/api/v1/cloud/local/summary?${new URLSearchParams({ field_id: state.fieldId, model_mode: targetModelMode() }).toString()}`),
    ]);
    const counts = stats.counts || {};
    const cache = stats.cache || {};
    const localCounts = local.counts || {};
    const workStageUnsynced = Math.max(
      Number(localCounts.queued_works?.unsynced || 0),
      Number(localCounts.research_tasks?.unsynced || 0),
      Number(localCounts.ready_works?.unsynced || 0),
      Number(localCounts.works?.unsynced || 0)
    );
    const conceptUnsynced = ["existed_ideas", "benchmarks", "baselines", "principles", "takeaway_messages"]
      .reduce((sum, key) => sum + Number(localCounts[key]?.unsynced || 0), 0);
    const unsynced = workStageUnsynced + conceptUnsynced;
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
  const venueFilter = filterSelection("venueChoices");
  const yearFilter = filterSelection("yearChoices");
  return {
    admin_key: $("adminKey").value,
    venues: venueFilter.values,
    venue_other: venueFilter.includeOther,
    known_venues: venueOptions,
    years: yearFilter.values.map((item) => Number(item)).filter(Boolean),
    year_other: yearFilter.includeOther,
    known_years: state.yearOptions.map((item) => Number(item)).filter(Boolean),
    topics: splitTopics($("crawlTopics").value),
    priority_rules: checkedValues("priorityChoices"),
    max_papers: Number($("crawlMax").value || 100),
    model_mode: candidates.length ? targetModelMode() : ($("crawlModelMode")?.value || "auto"),
    field_id: state.fieldId,
    timeout: Number($("crawlTimeout").value || 12),
    parallelism: Math.max(1, Math.min(Number($("crawlParallelism").value || 4), 8)),
    dry_run: !candidates.length,
    candidates,
  };
}

function crawlPlanSlices(payload) {
  const venues = [...(payload.venues || []), ...(payload.venue_other ? [OTHER_FILTER_VALUE] : [])];
  const years = [...(payload.years || []), ...(payload.year_other ? [OTHER_FILTER_VALUE] : [])];
  const venueSlices = venues.length ? venues : [""];
  const yearSlices = years.length ? years : [""];
  const combos = [];
  for (const venue of venueSlices) {
    for (const year of yearSlices) combos.push({ venue, year });
  }
  const perSlice = Math.max(1, Math.ceil(Number(payload.max_papers || 100) / Math.max(1, combos.length)));
  return combos.map(({ venue, year }) => ({
    ...payload,
    venues: venue && venue !== OTHER_FILTER_VALUE ? [venue] : [],
    venue_other: venue === OTHER_FILTER_VALUE,
    years: year && year !== OTHER_FILTER_VALUE ? [year] : [],
    year_other: year === OTHER_FILTER_VALUE,
    max_papers: perSlice,
    dry_run: true,
    candidates: [],
  }));
}

async function addToQueue(event) {
  if (event) event.preventDefault();
  if (state.queueAdding) return;
  setWorkflow("discover");
  state.queueAdding = true;
  state.searchCancelRequested = false;
  state.searchControllers = [];
  setLoading($("crawlForm"), true);
  setButtonBusy($("planCrawl"), true, "Searching...");
  $("cancelSearch").disabled = false;
  if (!state.candidates.length) $("candidateList").innerHTML = loadingRows(5);
  $("addSearchResultsToQueue").disabled = true;
  $("crawlRunStatus").textContent = "Searching";
  const basePayload = crawlPayload();
  const targetCount = Number(basePayload.max_papers || 100);
  const slices = crawlPlanSlices(basePayload);
  const seen = new Set(state.candidates.map(candidateKey).filter(Boolean));
  let found = 0;
  let completed = 0;
  const warnings = [];
  let cursor = 0;

  async function runSlice() {
    while (!state.searchCancelRequested && cursor < slices.length && found < targetCount) {
      const slice = slices[cursor++];
      const controller = new AbortController();
      state.searchControllers.push(controller);
      try {
        const data = await post("/api/v1/cloud/admin/crawl/plan", slice, { signal: controller.signal });
        completed += 1;
        for (const item of filterCandidates(data.candidates || [])) {
          if (state.searchCancelRequested) break;
          if (found >= targetCount) break;
          const key = candidateKey(item);
          if (!key || seen.has(key)) continue;
          seen.add(key);
          state.candidates.push({
            ...item,
            queue_status: item.queue_status || "search_result",
            searched_at: new Date().toISOString(),
          });
          found += 1;
          $("crawlRunStatus").textContent = `Found ${found}/${targetCount}`;
          renderCandidates();
          await new Promise((resolve) => window.requestAnimationFrame(resolve));
        }
        for (const warning of data.metadata_warnings || []) warnings.push(warning);
        $("crawlRunStatus").textContent = `Checked ${completed}/${slices.length}`;
      } catch (error) {
        completed += 1;
        if (error.name !== "AbortError") warnings.push(error.message);
      } finally {
        state.searchControllers = state.searchControllers.filter((item) => item !== controller);
      }
    }
  }

  try {
    const workers = Array.from({ length: Math.min(3, Math.max(1, slices.length)) }, () => runSlice());
    await Promise.all(workers);
    renderCandidates();
    $("crawlRunStatus").textContent = state.searchCancelRequested
      ? `Search cancelled · kept ${formatNumber(state.candidates.length)} searched paper(s)`
      : found
        ? `Search ready · ${formatNumber(found)} new`
        : "No new matches";
    const warning = warnings.filter(Boolean)[0];
    if (warning) showToast(warning, "warn");
  } finally {
    state.queueAdding = false;
    state.searchCancelRequested = false;
    state.searchControllers = [];
    setLoading($("crawlForm"), false);
    setButtonBusy($("planCrawl"), false);
    $("cancelSearch").disabled = true;
    $("addSearchResultsToQueue").disabled = !state.candidates.some((item) => queueStatus(item) !== "queued");
  }
}

function cancelDiscoverSearch() {
  if (!state.queueAdding) return;
  state.searchCancelRequested = true;
  $("crawlRunStatus").textContent = "Cancelling search...";
  for (const controller of state.searchControllers) controller.abort();
}

async function addSearchResultsToQueue() {
  if (state.queueAdding) return;
  const candidates = state.candidates.filter((item) => queueStatus(item) !== "queued");
  if (!candidates.length) {
    showToast("No new searched papers to add.", "warn");
    return;
  }
  state.queueAddPaused = false;
  state.queueAddCancelRequested = false;
  state.queueAddControllers = [];
  setQueueAddLoading(true);
  updateQueueAddControls();
  $("crawlRunStatus").textContent = `Adding 0/${candidates.length} searched papers to queue`;
  let added = 0;
  let failed = 0;

  function applyQueuedWorks(chunk, data) {
    const works = data.works || data.tab?.items || [];
    const byKey = new Map();
    const byTitle = new Map();
    for (const work of works) {
      const key = candidateKey(work);
      if (key) byKey.set(key, work);
      const title = String(work.title || work.canonical_title || "").trim().toLowerCase();
      if (title) byTitle.set(title, work);
      if (work.work_id) state.queuedIds.add(String(work.work_id));
    }
    for (const candidate of chunk) {
      const title = String(candidate.title || candidate.canonical_title || "").trim().toLowerCase();
      const local = byKey.get(candidateKey(candidate)) || byTitle.get(title) || null;
      const targetKey = candidateKey(candidate);
      for (const item of state.candidates) {
        if (candidateKey(item) !== targetKey && String(item.title || "").trim().toLowerCase() !== title) continue;
        item.work_id = local?.work_id || item.work_id;
        item.cloud_research_status = local?.cloud_research_status || item.cloud_research_status || { state: "queued" };
        item.queue_status = "queued";
        item.queue_message = local?.cloud_research_status?.message || "Queued for cloud research.";
        if (item.work_id) state.queuedIds.add(String(item.work_id));
      }
    }
  }

  async function addChunk(chunk) {
    const controller = new AbortController();
    state.queueAddControllers.push(controller);
    try {
      const data = await post("/api/v1/cloud/local/queue/add", {
      field_id: state.fieldId,
      model_mode: "all",
        candidates: chunk,
        recover_abstracts: false,
        include_tab: false,
        include_counts: false,
      }, { signal: controller.signal });
      applyQueuedWorks(chunk, data);
      added += chunk.length;
      clearLocalCache();
      renderLocalTabs();
      renderCandidates();
      if (state.activeLocalTab === "queued_works") await loadLocalTab({ reset: true, silent: true, preserveScroll: true });
    } finally {
      state.queueAddControllers = state.queueAddControllers.filter((item) => item !== controller);
    }
  }

  try {
    const chunks = chunkItems(candidates, 25);
    for (const chunk of chunks) {
      if (state.queueAddCancelRequested) break;
      await waitForQueueAddResume();
      if (state.queueAddCancelRequested) break;
      try {
        await addChunk(chunk);
      } catch (error) {
        if (error.name === "AbortError" || state.queueAddCancelRequested) break;
        failed += chunk.length;
        console.warn("Queue add failed", error);
      }
      $("crawlRunStatus").textContent = `Queued ${added}/${candidates.length}${failed ? ` · ${failed} failed` : ""}`;
      await new Promise((resolve) => window.requestAnimationFrame(resolve));
    }
    await loadStats();
    await loadLocalTab({ reset: true, silent: true });
    const cancelled = state.queueAddCancelRequested;
    $("crawlRunStatus").textContent = `${cancelled ? "Queue add cancelled" : "Queued"} · ${added} paper(s)${failed ? ` · ${failed} failed` : ""}`;
    showToast(`${cancelled ? "Stopped after adding" : "Added"} ${added} paper(s) to the research queue.${failed ? ` ${failed} failed.` : ""}`, cancelled || failed ? "warn" : "success");
  } catch (error) {
    $("crawlRunStatus").textContent = "Queue add failed";
    showToast(error.message, "error");
  } finally {
    state.queueAddPaused = false;
    state.queueAddCancelRequested = false;
    state.queueAddControllers = [];
    setQueueAddLoading(false);
    updateQueueAddControls();
    $("addSearchResultsToQueue").disabled = !state.candidates.some((item) => queueStatus(item) !== "queued");
  }
}

function filterCandidates(items) {
  const venueFilter = filterSelection("venueChoices");
  const yearFilter = filterSelection("yearChoices");
  const venues = new Set(venueFilter.values);
  const years = new Set(yearFilter.values.map(String));
  const knownVenues = new Set(venueOptions.map((item) => item.toLowerCase()));
  const knownYears = new Set(state.yearOptions.map(String));
  const topics = splitTopics($("crawlTopics").value);
  return (items || []).filter((item) => {
    const venue = String(item.venue_or_source || item.venue || "");
    const year = String(item.year || item.target_year || "");
    const venueOtherOk = venueFilter.includeOther && (!venue || !knownVenues.has(venue.toLowerCase()));
    const yearOtherOk = yearFilter.includeOther && (!year || !knownYears.has(year));
    const venueOk = (!venues.size && !venueFilter.includeOther) || venues.has(venue) || venueOtherOk;
    const yearOk = (!years.size && !yearFilter.includeOther) || years.has(year) || yearOtherOk;
    const topicOk = !topics.length || topicRelevanceScore(item, topics) > 0;
    return venueOk && yearOk && topicOk;
  });
}

function topicRelevanceScore(item, topics) {
  const text = [item.title, item.abstract, item.venue_or_source, JSON.stringify(item.community_signals || {})]
    .join(" ")
    .toLowerCase()
    .replaceAll("-", " ");
  let score = Number(item.topic_score || 0);
  for (const topic of topics) {
    const normalized = String(topic || "").toLowerCase().replaceAll("-", " ").trim();
    if (!normalized) continue;
    if (text.includes(normalized)) score = Math.max(score, 1);
    const tokens = normalized.split(/[^a-z0-9]+/).filter((token) => token.length >= 4);
    if (tokens.length >= 2 && tokens.every((token) => text.includes(token))) score = Math.max(score, 0.6);
    if (normalized.includes("test time scaling") || normalized.includes("test-time scaling")) {
      for (const phrase of ["inference time scaling", "inference time compute", "test time compute", "inference compute scaling"]) {
        if (text.includes(phrase)) score = Math.max(score, 0.8);
      }
    }
  }
  return score;
}

function candidateKey(item) {
  return String(item.work_id || item.source_record_id || item.title || "");
}

function queueStatus(item) {
  const status = item.cloud_research_status || {};
  return String(status.state || item.queue_status || "search_result");
}

function queueStatusLabel(status) {
  return {
    search_result: "Search Result",
    queued: "Queued",
    research_task: "Research Task",
    researching: "Researching",
    ready: "Ready to Sync",
    done: "Done",
    needs_review: "Needs Review",
    metadata_only: "Metadata Only",
    failed: "Failed",
    stopped: "Stopped",
    synced: "Synced",
  }[status] || status.replaceAll("_", " ");
}

async function researchTaskCandidates(modelMode = "all") {
  const data = await api(`/api/v1/cloud/local/tab?${new URLSearchParams({
    field_id: state.fieldId,
    tab: "research_tasks",
    offset: "0",
    limit: "1000",
    query: "",
    model_mode: modelMode || "all",
    sync_state: "unsynced",
    include_counts: "0",
  }).toString()}`);
  mergeLocalCounts(data.counts);
  renderLocalTabs();
  return (data.items || []).filter((item) => {
    const status = queueStatus(item);
    return ["research_task", "queued", "done", "ready", "needs_review", "metadata_only", "failed", "stopped"].includes(status);
  });
}

function openQueueFilterModal(action = "view") {
  state.queueFilterAction = action;
  $("queueFilterMode").value = state.queueFilterMode;
  $("queueFilterTitle").textContent = action === "add_all" ? "Choose Queued Papers to Add" : "Choose LLM Coverage Filter";
  $("applyQueueFilter").textContent = action === "add_all" ? "Add Filtered Papers" : "Apply Filter";
  $("queueFilterModal").hidden = false;
}

async function applyQueueFilterModal() {
  state.queueFilterMode = $("queueFilterMode").value || "all";
  $("queueFilterModal").hidden = true;
  clearLocalCache();
  if (state.queueFilterAction === "add_all") {
    await addAllQueuedToResearchTasks(state.queueFilterMode);
    state.queueFilterAction = "view";
    return;
  }
  await loadStats();
  await loadLocalTab({ reset: true, preserveScroll: true });
}

async function addAllQueuedToResearchTasks(modelMode = "all") {
  const button = $("addAllQueuedToTasks");
  setButtonBusy(button, true, "Adding...");
  setLocalTabLoading(true);
  try {
    const data = await post("/api/v1/cloud/local/tasks/add-all", {
      field_id: state.fieldId,
      model_mode: modelMode || "all",
      limit: 10000,
      include_tab: false,
      include_counts: false,
    });
    const ids = [...new Set((data.added_work_ids || []).map((item) => String(item || "")).filter(Boolean))];
    const existingIds = [...new Set((data.existing_task_work_ids || []).map((item) => String(item || "")).filter(Boolean))];
    if (!ids.length) {
      for (const id of existingIds) {
        state.researchTaskIds.add(id);
        setCandidateStatus(id, "research_task", "Already in Research Tasks.");
      }
      clearLocalCache();
      if (existingIds.length) {
        renderLocalTabs();
        renderCandidates();
        await loadLocalTab({ reset: true, silent: true, preserveScroll: true });
        showToast(`All ${formatNumber(existingIds.length)} matching queued paper(s) are already in Research Tasks.`, "warn");
      } else {
        showToast("No queued papers match that filter.", "warn");
      }
      return;
    }
    for (const id of ids) {
      state.researchTaskIds.add(id);
      setCandidateStatus(id, "research_task", "Added to Research Tasks.");
    }
    clearLocalCache();
    const taskCounts = state.localCounts.research_tasks || {};
    state.localCounts.research_tasks = {
      ...taskCounts,
      total: Math.max(Number(taskCounts.total || 0), Number(taskCounts.unsynced || 0)) + ids.length,
      unsynced: Number(taskCounts.unsynced || 0) + ids.length,
      synced: Number(taskCounts.synced || 0),
    };
    if (state.activeLocalTab === "research_tasks") {
      state.localItems = [];
      state.localTotal = Number(state.localCounts.research_tasks.unsynced || ids.length);
      renderLocalItems();
      renderLocalPager();
    }
    renderLocalTabs();
    renderCandidates();
    window.setTimeout(() => {
      loadStats().catch(() => {});
      if (state.activeLocalTab === "research_tasks") loadLocalTab({ reset: true, silent: true, preserveScroll: true }).catch(() => {});
    }, 50);
    showToast(`Added ${formatNumber(ids.length)} queued paper(s) to Research Tasks.`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
    setLocalTabLoading(false);
  }
}

function setCandidateStatus(workId, status, message = "") {
  const key = String(workId || "");
  for (const item of state.candidates) {
    if (candidateKey(item) !== key && String(item.work_id || "") !== key) continue;
    item.queue_status = status;
    item.cloud_research_status = { ...(item.cloud_research_status || {}), state: status };
    if (status === "research_task") item.cloud_research_status.task_state = "research_task";
    if (status === "queued") item.cloud_research_status.task_state = "";
    if (message) item.queue_message = message;
  }
}

async function refreshQueueStatuses({ silent = false } = {}) {
  try {
    const fetchTab = (tab) =>
      api(`/api/v1/cloud/local/tab?${new URLSearchParams({
        field_id: state.fieldId,
        tab,
        offset: "0",
        limit: "1000",
        query: "",
        model_mode: tab === "queued_works" ? state.queueFilterMode : "all",
        sync_state: "unsynced",
        include_counts: "0",
      }).toString()}`);
    const [queued, tasks, ready] = await Promise.all([fetchTab("queued_works"), fetchTab("research_tasks"), fetchTab("ready_works")]);
    mergeLocalCounts(queued.counts || tasks.counts || ready.counts);
    state.queuedIds = new Set((queued.items || []).map((item) => String(item.work_id || "")).filter(Boolean));
    state.researchTaskIds = new Set((tasks.items || []).map((item) => String(item.work_id || "")).filter(Boolean));
    const byId = new Map();
    for (const item of [...(queued.items || []), ...(tasks.items || []), ...(ready.items || [])]) {
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
  const queued = state.candidates.filter((item) => queueStatus(item) === "queued").length;
  const running = state.candidates.filter((item) => queueStatus(item) === "researching").length;
  $("crawlCount").textContent = `${state.candidates.length} found${queued ? ` · ${queued} queued` : ""}${running ? ` · ${running} running` : ""}`;
  $("addSearchResultsToQueue").disabled = state.queueAdding || !state.candidates.some((item) => queueStatus(item) !== "queued");
  if (!state.candidates.length) {
    $("candidateList").innerHTML = `
      <div class="empty-state compact">
        <strong>No searched papers yet.</strong>
        <span>Choose filters and run a search.</span>
      </div>
    `;
    return;
  }
  $("candidateList").innerHTML = state.candidates
    .map((item) => {
      const key = candidateKey(item);
      const status = queueStatus(item);
      const topicScore = Number(item.topic_score || 0);
      const meta = [
        item.venue_or_source || item.target_venue,
        item.year || item.target_year,
        topicScore ? `topic ${topicScore.toFixed(2)}` : "",
        item.citation_count != null ? `${item.citation_count} citations` : "",
        item.source_provider,
      ].filter(Boolean).join(" · ");
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
            <button type="button" data-action="remove-search-result" ${status === "researching" ? "disabled" : ""}>Remove</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function runResearch() {
  if (state.crawlRunId) {
    showToast("A research run is already active.", "warn");
    return;
  }
  $("researchModelMode").value = targetModelMode();
  $("researchModelModal").hidden = false;
}

async function confirmResearchModel() {
  state.researchModelMode = $("researchModelMode").value || "auto";
  localStorage.setItem("principia.cloudResearchModelMode", state.researchModelMode);
  $("researchModelModal").hidden = true;
  clearLocalCache();
  setButtonBusy($("runResearch"), true, "Checking Tasks...");
  try {
    let selected = await researchTaskCandidates("all");
    if (!selected.length) {
      selected = await researchTaskCandidates(state.researchModelMode);
    }
    if (!selected.length) {
      setButtonBusy($("runResearch"), false);
      showToast("Add papers to Research Tasks first.", "warn");
      return;
    }
    await addResearchTasks(selected.map((item) => item.work_id), null, state.researchModelMode);
    selected = await researchTaskCandidates(state.researchModelMode);
    await startResearchForCandidates(selected);
  } catch (error) {
    setButtonBusy($("runResearch"), false);
    showToast(error.message, "error");
  }
}

async function addResearchTasks(workIds, button = null, modelMode = "all") {
  const ids = [...new Set((workIds || []).map(String).filter(Boolean))];
  if (!ids.length) return;
  if (button) setButtonBusy(button, true, "Adding...");
  setLocalTabLoading(true);
  try {
    const data = await post("/api/v1/cloud/local/tasks/add", {
      field_id: state.fieldId,
      model_mode: modelMode || "all",
      work_ids: ids,
      include_tab: false,
      include_counts: false,
    });
    clearLocalCache();
    for (const id of ids) {
      state.researchTaskIds.add(id);
      setCandidateStatus(id, "research_task", "Added to Research Tasks.");
    }
    await loadStats();
    if (state.activeLocalTab === "queued_works" || state.activeLocalTab === "research_tasks") await loadLocalTab({ reset: false, silent: true, preserveScroll: true });
    renderCandidates();
    showToast(`Added ${formatNumber(data.added_work_ids?.length || 0)} paper(s) to Research Tasks.`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    if (button) setButtonBusy(button, false);
    setLocalTabLoading(false);
  }
}

async function removeResearchTasks(workIds, button = null) {
  const ids = [...new Set((workIds || []).map(String).filter(Boolean))];
  if (!ids.length) return;
  if (button) setButtonBusy(button, true, "Removing...");
  setLocalTabLoading(true);
  try {
    await post("/api/v1/cloud/local/tasks/remove", {
      field_id: state.fieldId,
      model_mode: "all",
      work_ids: ids,
    });
    for (const id of ids) {
      state.researchTaskIds.delete(id);
      setCandidateStatus(id, "queued", "Returned to queued papers.");
    }
    clearLocalCache();
    await loadStats();
    await loadLocalTab({ reset: false, silent: true, preserveScroll: true });
    renderCandidates();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    if (button) setButtonBusy(button, false);
    setLocalTabLoading(false);
  }
}

async function startResearchForCandidates(selected) {
  setWorkflow("research");
  clearLocalCache();
  state.lastLocalRefreshAt = 0;
  state.lastStatsAt = 0;
  $("crawlRunStatus").textContent = "Starting";
  $("runProgressLabel").textContent = `Queued ${selected.length} paper(s).`;
  $("runProgressDetail").textContent = "Waiting for extraction to start.";
  setLoading($("crawlForm"), true);
  setResearchControls(true);
  try {
    const data = await post("/api/v1/cloud/admin/crawl/run", { ...crawlPayload({ candidates: selected }), max_papers: selected.length, dry_run: false });
    state.crawlRunId = data.run_id || "";
    $("crawlRunStatus").textContent = state.crawlRunId ? "Running" : "Queued";
    for (const item of selected) setCandidateStatus(item.work_id || candidateKey(item), "queued");
    renderCandidates();
    if (state.crawlRunId) pollCrawlRun();
  } catch (error) {
    $("crawlRunStatus").textContent = "Run failed";
    showToast(error.message, "error");
    setLoading($("crawlForm"), false);
    setResearchControls(false);
    throw error;
  }
}

function setResearchControls(running) {
  if (running) {
    setButtonBusy($("runResearch"), true, "Research Running...");
  } else {
    setButtonBusy($("runResearch"), false);
  }
  $("stopResearch").disabled = !running;
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
    const currentIndex = Number(counts.current_index || 0);
    const processed = Number(counts.processed_works || 0);
    const activeWorks = Number(counts.active_works || (Array.isArray(counts.active_work_ids) ? counts.active_work_ids.length : 0));
    const parallelism = Number(counts.parallelism || 0);
    const inFlightFloor = currentIndex ? Math.max(0, currentIndex - 1) : 0;
    const effectiveDone = Math.max(done, processed, inFlightFloor, (["complete", "error", "cancelled"].includes(run.status) ? stored : run.stage === "metadata_store" ? stored : 0));
    const inFlightProgress = planned && currentIndex ? Math.max(4, Math.round(((currentIndex - 0.5) / planned) * 100)) : 0;
    const progress = planned ? Math.min(100, Math.max(Math.round((effectiveDone / planned) * 100), inFlightProgress)) : 0;
    $("runProgressBar").style.width = `${progress}%`;
    $("runProgressLabel").textContent = run.message || `${run.status || "running"} · ${done}/${planned}`;
    $("runProgressDetail").textContent = [
      planned ? `${effectiveDone}/${planned} processed${activeWorks ? ` · active ${activeWorks}/${planned}` : ""}` : "",
      parallelism ? `${parallelism} worker(s)` : "",
      counts.ready_works ? `${counts.ready_works} ready` : "",
      counts.needs_review_works ? `${counts.needs_review_works} need review` : "",
      counts.cloud_hits ? `${counts.cloud_hits} cloud hit(s)` : "",
      counts.failed_works ? `${counts.failed_works} failed` : "",
    ].filter(Boolean).join(" · ") || (run.stage || "running");
    $("crawlRunStatus").textContent = run.status || "running";
    const activeIds = Array.isArray(counts.active_work_ids) ? counts.active_work_ids.map(String).filter(Boolean) : [];
    for (const activeId of activeIds) setCandidateStatus(activeId, "researching", run.message || "Researching.");
    if (counts.current_work_id) setCandidateStatus(counts.current_work_id, "researching", run.message || "Researching.");
    const terminal = ["complete", "error", "cancelled"].includes(run.status);
    if (terminal) {
      setLoading($("crawlForm"), false);
      setResearchControls(false);
      state.crawlRunId = "";
    }
    const now = Date.now();
    if (terminal || now - state.lastLocalRefreshAt > 1800 || Number(counts.ready_works || 0) > 0) {
      clearLocalCache();
      await loadLocalTab({ reset: true, silent: true });
      await refreshQueueStatuses({ silent: true });
      state.lastLocalRefreshAt = now;
    }
    if (terminal || now - state.lastStatsAt > 2000) {
      await loadStats();
      state.lastStatsAt = now;
    }
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
  $("localTabRow").innerHTML = localTabs
    .map((tab) => {
      const counts = state.localCounts[tab.key] || {};
      const active = state.activeLocalTab === tab.key ? "active" : "";
      return `<button type="button" class="${active}" data-local-tab="${escapeHtml(tab.key)}">${escapeHtml(tab.label)} <span>${formatNumber(counts.unsynced || 0)}</span></button>`;
    })
    .join("");
}

async function loadLocalTab({ reset = false, silent = false, pageDelta = 0, preserveScroll = false } = {}) {
  const requestId = ++state.localTabRequestId;
  const scrollY = preserveScroll ? window.scrollY : null;
  if (reset) {
    state.localOffset = 0;
    state.localItems = [];
    renderLocalTabs();
    const cacheKey = localTabCacheKey(0);
    const cached = state.localTabCache.get(cacheKey);
    if (cached) {
      state.localItems = cached.items || [];
      state.localOffset = 0;
      state.localTotal = Number(cached.total || 0);
      state.localHasMore = Boolean(cached.has_more);
      renderLocalItems();
      renderLocalPager();
    } else if (!silent) {
      $("localTabContent").innerHTML = loadingRows(4);
    }
  } else if (pageDelta) {
    state.localOffset = Math.max(0, state.localOffset + pageDelta * state.localLimit);
    $("localTabContent").innerHTML = loadingRows(4);
  }
  setLocalTabLoading(true);
  const params = new URLSearchParams({
    field_id: state.fieldId,
    tab: state.activeLocalTab,
    offset: String(state.localOffset),
    limit: String(state.localLimit),
    query: $("localTabSearch").value.trim(),
    model_mode: localModelMode(),
    sync_state: "unsynced",
    include_counts: "0",
  });
  try {
    const data = await api(`/api/v1/cloud/local/tab?${params.toString()}`);
    if (requestId !== state.localTabRequestId) return;
    mergeLocalCounts(data.counts);
    state.localItems = data.items || [];
    if (state.activeLocalTab === "queued_works" && reset) state.queuedIds = new Set((data.items || []).map((item) => String(item.work_id || "")).filter(Boolean));
    if (state.activeLocalTab === "research_tasks") state.researchTaskIds = new Set((data.items || []).map((item) => String(item.work_id || "")).filter(Boolean));
    state.localOffset = Number(data.offset || state.localOffset || 0);
    state.localTotal = Number(data.total || 0);
    state.localHasMore = Boolean(data.has_more);
    state.localCounts[state.activeLocalTab] = {
      ...(state.localCounts[state.activeLocalTab] || {}),
      total: state.localTotal,
      unsynced: state.localTotal,
      synced: 0,
    };
    state.localTabCache.set(localTabCacheKey(reset ? 0 : Number(params.get("offset") || 0)), {
      items: state.localItems,
      total: state.localTotal,
      has_more: state.localHasMore,
    });
    renderLocalTabs();
    renderLocalItems();
  } catch (error) {
    if (requestId !== state.localTabRequestId) return;
    $("localTabContent").innerHTML = `<div class="empty-state"><strong>Unable to load records.</strong><span>${escapeHtml(error.message)}</span></div>`;
  } finally {
    if (requestId !== state.localTabRequestId) return;
    setLocalTabLoading(false);
    renderLocalPager();
    if (preserveScroll && scrollY !== null) window.scrollTo(window.scrollX, scrollY);
  }
}

function renderLocalPager() {
  const pager = $("localMoreBtn");
  if (!pager) return;
  const total = Number(state.localTotal || 0);
  const page = Math.floor(Number(state.localOffset || 0) / state.localLimit) + 1;
  const pages = Math.max(1, Math.ceil(total / state.localLimit));
  pager.hidden = total <= state.localLimit;
  const info = $("localPageInfo");
  if (info) info.textContent = `Page ${page} of ${pages}`;
  const prev = pager.querySelector("[data-page-action='prev']");
  const next = pager.querySelector("[data-page-action='next']");
  if (prev) prev.disabled = state.localOffset <= 0;
  if (next) next.disabled = !state.localHasMore;
}

function localTabCacheKey(offset) {
  return [
    targetModelMode(),
    state.queueFilterMode,
    state.activeLocalTab,
    String(offset || 0),
    $("localTabSearch")?.value?.trim() || "",
  ].join("|");
}

function renderLocalItems() {
  if (!state.localItems.length) {
    const emptyCopy = {
      queued_works: "Queued papers appear here. Filter by LLM to find papers missing that cloud version, then add selected papers to Research Tasks.",
      research_tasks: "Papers staged for the selected research LLM appear here before extraction starts.",
      ready_works: "Research-complete papers with at least one high-quality existed idea or principle appear here before sync.",
    }[state.activeLocalTab] || "Extracted records for ready papers appear here so you can inspect quality before cloud sync.";
    $("localTabContent").innerHTML = `<div class="empty-state"><strong>No ${escapeHtml(tabLabel(state.activeLocalTab))}.</strong><span>${escapeHtml(emptyCopy)}</span></div>`;
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
  if (["works", "queued_works", "research_tasks", "ready_works"].includes(tabKey)) return renderWorkCard(item, { local, cloud, tabKey });
  if (tabKey === "benchmarks") return renderBenchmarkCard(item, { local, cloud });
  if (tabKey === "baselines") return renderBaselineCard(item, { local, cloud });
  if (tabKey === "principles") return renderTextCard(tabKey, item, "Principle", item.name || item.title, item.argument || item.abstract_signature || item.summary, { local, cloud });
  if (tabKey === "takeaway_messages") return renderTextCard(tabKey, item, "Takeaway", item.title, item.main_results || item.message_text || item.finding || item.actionable_lesson, { local, cloud });
  return renderTextCard(tabKey, item, "Existed Idea", item.title, item.core_idea || item.idea_text || item.summary, { local, cloud });
}

function cardAttrs(tabKey, item, local, cloud) {
  const status = item.cloud_research_status || {};
  const modelMode = item.ready_model_mode || item.cloud_target_model_mode || status.model_mode || item.model_mode || localModelMode();
  return `data-tab="${escapeHtml(tabKey)}" data-id="${escapeHtml(idFor(tabKey, item))}" data-model-mode="${escapeHtml(modelMode)}" data-local="${local ? "1" : "0"}" data-cloud="${cloud ? "1" : "0"}"`;
}

function renderWorkCard(item, opts) {
  const links = [item.url_or_doi, item.paper_link, ...(item.source_urls || [])].filter(isUrl);
  const status = item.cloud_research_status || {};
  const displayModel = displayModelForItem(item, opts.cloud ? $("cloudModelMode").value : localModelMode());
  const meta = [item.venue_or_source || item.venue || item.target_venue || item.source_type, item.year || item.target_year || "n.d.", displayModel, item.work_extracted ? "extracted" : ""].filter(Boolean).join(" · ");
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
      <div class="record-actions">${recordButtons({ ...opts, item })}</div>
    </article>
  `;
}

function renderTextCard(tabKey, item, fallback, title, body, opts) {
  const meta = [item.venue_or_source || item.venue || "source", item.year || "n.d.", displayModelForItem(item, opts.cloud ? $("cloudModelMode").value : localModelMode())].filter(Boolean).join(" · ");
  return `
    <article class="record-row record-${escapeHtml(tabKey)}" ${cardAttrs(tabKey, item, opts.local, opts.cloud)}>
      <div>
        <h3>${escapeHtml(title || compact(body, 88) || fallback)}</h3>
        <p>${escapeHtml(compact(body || item.payload_summary || "No summary available.", 300))}</p>
        <div class="record-meta"><span>${escapeHtml(meta)}</span></div>
      </div>
      <div class="record-actions">${recordButtons({ ...opts, tabKey, item })}</div>
    </article>
  `;
}

function renderBenchmarkCard(item, opts) {
  const metrics = Array.isArray(item.metrics) ? item.metrics : [item.metrics || item.metric].filter(Boolean);
  return `
    <article class="record-row record-benchmarks" ${cardAttrs("benchmarks", item, opts.local, opts.cloud)}>
      <div class="benchmark-row-grid">
        <div><span class="mini-label">Benchmark</span><strong>${escapeHtml(item.benchmark_name || item.dataset || item.canonical_label || "Benchmark")}</strong></div>
        <div><span class="mini-label">Task</span><span>${escapeHtml(compact(item.task || "unspecified", 80))}</span></div>
        <div><span class="mini-label">Data</span><span>${escapeHtml(compact(item.data_form || "public dataset", 80))}</span></div>
        <div><span class="mini-label">Metrics</span><span>${escapeHtml(compact(metrics.join(", "), 80))}</span></div>
      </div>
      <div class="record-actions">${recordButtons({ ...opts, tabKey: "benchmarks", item })}</div>
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
      <div class="record-actions">${recordButtons({ ...opts, tabKey: "baselines", item })}</div>
    </article>
  `;
}

function recordButtons(opts) {
  if (opts.cloud) {
    return `<button type="button" data-action="hydrate-cloud">Load Local</button><button type="button" data-action="details">Details</button>`;
  }
  if (opts.tabKey === "queued_works") {
    const item = opts.item || {};
    const workId = String(item.work_id || idFor("queued_works", item) || "");
    const status = item.cloud_research_status || {};
    const added = state.researchTaskIds.has(workId) || String(status.task_state || status.state || "") === "research_task";
    return `<button type="button" data-action="add-task" class="${added ? "task-added" : ""}" ${added ? "disabled" : ""}>${added ? "Added" : "Add to Research"}</button><button type="button" data-action="remove-queue">Remove</button><button type="button" data-action="open-tab">Details</button>`;
  }
  if (opts.tabKey === "research_tasks") {
    return `<button type="button" data-action="remove-task">Remove</button><button type="button" data-action="open-tab">Details</button>`;
  }
  if (opts.tabKey === "ready_works") {
    return `<button type="button" data-action="sync-one">Sync to Cloud</button><button type="button" data-action="open-tab">Open Tab</button><button type="button" data-action="details">Details</button>`;
  }
  if (["existed_ideas", "benchmarks", "baselines", "principles", "takeaway_messages"].includes(opts.tabKey)) {
    return `<button type="button" data-action="sync-record">Sync to Cloud</button><button type="button" data-action="open-tab">Open Tab</button><button type="button" data-action="details">Details</button>`;
  }
  return `<button type="button" data-action="open-tab">Open Tab</button><button type="button" data-action="details">Details</button>`;
}

async function removeQueuedWorks(workIds) {
  const ids = [...new Set((workIds || []).map(String).filter(Boolean))];
  if (!ids.length) return;
  setLocalTabLoading(true);
  try {
    await post("/api/v1/cloud/local/queue/remove", {
      field_id: state.fieldId,
      model_mode: "all",
      work_ids: ids,
    });
    clearLocalCache();
    for (const item of state.candidates) {
      if (!ids.includes(String(item.work_id || candidateKey(item)))) continue;
      item.queue_status = "search_result";
      item.cloud_research_status = {};
      if (item.work_id) state.queuedIds.delete(String(item.work_id));
    }
    await loadStats();
    await loadLocalTab({ reset: true });
    renderCandidates();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLocalTabLoading(false);
  }
}

async function syncUnsynced() {
  if (state.syncRunning) return;
  state.syncRunning = true;
  setWorkflow("sync");
  setSyncLoading(true, "Checking...");
  $("syncStatus").textContent = "Checking ready papers for upload eligibility.";
  try {
    const allWorks = await api(`/api/v1/cloud/local/tab?${new URLSearchParams({ field_id: state.fieldId, tab: "ready_works", offset: "0", limit: "1000", sync_state: "unsynced", model_mode: "all", include_counts: "0" }).toString()}`);
    const grouped = new Map();
    for (const item of allWorks.items || []) {
      const workId = String(item.work_id || "");
      if (!workId) continue;
      const mode = item.ready_model_mode || item.cloud_research_status?.model_mode || item.model_mode || targetModelMode();
      if (!grouped.has(mode)) grouped.set(mode, []);
      grouped.get(mode).push(workId);
    }
    if (!grouped.size) {
      $("syncStatus").textContent = "No ready papers to upload. A paper needs at least one high-quality existed idea or principle first.";
      showToast("No ready papers to upload.", "warn");
      return;
    }
    state.syncRunning = false;
    for (const [mode, workIds] of grouped.entries()) {
      await syncWorksToCloud(workIds, mode);
    }
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    if (state.syncRunning) {
      state.syncRunning = false;
      setSyncLoading(false);
    }
  }
}

async function syncSingleReadyWork(workId, button, modelMode = "") {
  if (state.syncRunning) return;
  setButtonBusy(button, true, "Syncing...");
  try {
    await syncWorksToCloud([workId], modelMode || targetModelMode());
  } finally {
    setButtonBusy(button, false);
  }
}

async function syncSingleLocalRecord(tabKey, recordId, button, modelMode = "") {
  if (state.syncRunning) return;
  const item = state.localItems.find((entry) => idFor(tabKey, entry) === String(recordId || ""));
  let workIds = itemWorkIds(item);
  let uploadMode = modelMode || item?.model_mode || item?.cloud_target_model_mode || targetModelMode();
  if (!workIds.length) {
    try {
      const tab = tabs.find((entry) => entry.key === tabKey);
      const detail = await api(`/api/v1/item/detail?${new URLSearchParams({ bucket: tab.bucket, id: recordId, model_mode: uploadMode }).toString()}`);
      workIds = itemWorkIds(detail.item || {});
      uploadMode = uploadMode || detail.item?.model_mode || targetModelMode();
    } catch {
      workIds = [];
    }
  }
  if (!workIds.length) {
    $("syncStatus").textContent = "This record is missing source-paper links, so it cannot be synced safely.";
    showToast("No source paper found for this record.", "warn");
    return;
  }
  setButtonBusy(button, true, "Syncing...");
  try {
    await syncWorksToCloud(workIds, uploadMode);
  } finally {
    setButtonBusy(button, false);
  }
}

function itemWorkIds(item) {
  const ids = [];
  const add = (value) => {
    if (Array.isArray(value)) {
      value.forEach(add);
      return;
    }
    if (value && typeof value === "object") {
      add(value.work_id || value.source_id || value.id);
      return;
    }
    const id = String(value || "").trim();
    if (id) ids.push(id);
  };
  add(item?.source_work_ids);
  add(item?.source_works);
  add(item?.work_id);
  add(item?.source_id);
  add(item?.source_work_details);
  return [...new Set(ids)];
}

async function syncWorksToCloud(workIds, modelMode = targetModelMode()) {
  const ids = [...new Set((workIds || []).map(String).filter(Boolean))];
  if (!ids.length) return;
  const uploadModelMode = modelMode || targetModelMode();
  state.syncRunning = true;
  setWorkflow("sync");
  $("syncStatus").textContent = `Preparing ${ids.length} ready paper(s) from ${modelLabel(uploadModelMode)} for cloud contribution.`;
  setSyncLoading(true);
  try {
    const prepared = await post("/api/v1/cloud/upload/prepare", {
      admin_key: $("adminKey").value,
      upload_mode: $("uploadMode").value,
      model_mode: uploadModelMode,
      work_ids: ids,
      field_id: state.fieldId,
    });
    state.lastContributionPath = prepared.path || "";
    const decisionSummary = summarizeUploadDecisions(prepared.upload_decisions || []);
    const cachedLocalIds = localIdsForUploadDecisions(prepared, (decision) => ["cloud_cache_hit", "source_unchanged"].includes(String(decision.cloud_decision || "")));
    const hardRejected = (prepared.upload_decisions || []).filter((decision) => !decision.upload_allowed && !["cloud_cache_hit", "source_unchanged"].includes(String(decision.cloud_decision || "")));
    if (!prepared.ok || !state.lastContributionPath) {
      if (cachedLocalIds.length) {
        await markCachedWorksSynced(cachedLocalIds, prepared, uploadModelMode);
        $("syncStatus").textContent = `${formatNumber(cachedLocalIds.length)} paper(s) are already in the searchable cloud snapshot and were marked synced locally.${hardRejected.length ? ` ${hardRejected.length} still blocked: ${summarizeUploadDecisions(hardRejected)}` : ""}`;
        showToast(hardRejected.length ? "Cloud cache hits marked synced; some papers still need required extractions." : "Already in cloud; marked synced locally.", hardRejected.length ? "warn" : "success");
        clearLocalCache();
        await loadStats();
        await loadLocalTab({ reset: true });
        await searchCloud(null, { reset: true });
        renderCandidates();
        return;
      }
      $("syncStatus").textContent = decisionSummary || `Prepared with ${prepared.rejected_work_ids?.length || 0} rejected work(s).`;
      showToast("No paper passed upload rules. See the rule-specific reason in the sync status.", "warn");
      return;
    }
    const rejectedCount = Number(prepared.rejected_work_ids?.length || 0);
    $("syncStatus").textContent = `Prepared ${prepared.allowed_work_ids.length} work(s)${rejectedCount ? `; ${rejectedCount} rejected by rules` : ""}. Submitting accepted papers only.`;
    const submitted = await post("/api/v1/cloud/upload/submit", {
      admin_key: $("adminKey").value,
      upload_mode: $("uploadMode").value,
      contribution_path: state.lastContributionPath,
      field_id: state.fieldId,
      model_mode: uploadModelMode,
      work_ids: prepared.allowed_work_ids || ids,
      local_work_ids: prepared.allowed_local_work_ids || prepared.allowed_work_ids || ids,
    });
    const published = Boolean(submitted.ok && submitted.cloud_publish?.available_for_search);
    const releaseNote = submitted.cloud_publish?.github_release?.will_run_on_push ? " GitHub release publication is running from the pushed contribution." : "";
    if (cachedLocalIds.length) await markCachedWorksSynced(cachedLocalIds, prepared, uploadModelMode);
    $("syncStatus").textContent = published
      ? `Published ${formatNumber(prepared.allowed_work_ids.length)} accepted work(s) into the searchable cloud snapshot.${cachedLocalIds.length ? ` ${cachedLocalIds.length} were already present and marked synced.` : ""}${hardRejected.length ? ` ${hardRejected.length} blocked: ${summarizeUploadDecisions(hardRejected)}` : ""}${releaseNote}`
      : (submitted.cloud_publish?.message || submitted.direct_push?.error || decisionSummary || "Contribution was submitted, but the cloud snapshot is not searchable yet.");
    showToast(published ? "Cloud sync complete." : "Cloud publish did not complete.", published ? "success" : "warn");
    if (published) state.candidates = state.candidates.filter((item) => !ids.includes(String(item.work_id || candidateKey(item))));
    clearLocalCache();
    await loadStats();
    await loadLocalTab({ reset: true });
    if (published) await searchCloud(null, { reset: true });
    renderCandidates();
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    state.syncRunning = false;
    setSyncLoading(false);
  }
}

function localIdsForUploadDecisions(prepared, predicate) {
  const workIdMap = prepared.legacy_sync?.work_id_map || {};
  const exportToLocal = new Map(Object.entries(workIdMap).map(([localId, exportId]) => [String(exportId), String(localId)]));
  const ids = [];
  for (const decision of prepared.upload_decisions || []) {
    if (!predicate(decision)) continue;
    const exportId = String(decision.work_id || "");
    const localId = String(decision.local_work_id || exportToLocal.get(exportId) || "");
    if (localId) ids.push(localId);
  }
  return [...new Set(ids)];
}

async function markCachedWorksSynced(workIds, prepared, modelMode = targetModelMode()) {
  const ids = [...new Set((workIds || []).map(String).filter(Boolean))];
  if (!ids.length) return {};
  return post("/api/v1/cloud/local/mark-synced", {
    admin_key: $("adminKey").value,
    field_id: state.fieldId,
    model_mode: modelMode || targetModelMode(),
    work_ids: ids,
    contribution_path: prepared.path || "",
    status: "synced",
  });
}

function summarizeUploadDecisions(decisions) {
  const rejected = (decisions || []).filter((item) => !item.upload_allowed);
  if (!rejected.length) return "";
  return rejected.slice(0, 6).map((item) => `${item.title || item.work_id}: ${uploadDecisionText(item)}`).join(" · ");
}

function uploadDecisionText(item) {
  const decision = item.cloud_decision || "rejected";
  if (decision === "missing_required_extractions") {
    return `missing ${[...new Set(item.missing_required_extractions || [])].join(", ") || "required extractions"}`;
  }
  if (decision === "cloud_cache_hit" || decision === "source_unchanged") return "cloud already has this model version and source is unchanged";
  if (decision === "stale_local_source") return "local source appears older than cloud";
  if (decision === "validation_failed") return "contribution validation failed";
  return decision.replaceAll("_", " ");
}

function setSyncLoading(loading, label = "Syncing...") {
  setButtonBusy($("syncUnsynced"), Boolean(loading), label);
  $("uploadMode").disabled = Boolean(loading);
  $("clearSyncedCache").disabled = Boolean(loading);
  $("clearQueuedPapers").disabled = Boolean(loading);
  $("clearResearchTasks").disabled = Boolean(loading);
  document.querySelector(".sync-actions")?.classList.toggle("is-loading", Boolean(loading));
}

async function clearSyncedCache() {
  if (!window.confirm("Clear cloud-crawled records that are already synced and not used by other projects?")) return;
  $("syncStatus").textContent = "Clearing synced local cache.";
  setSyncLoading(true);
  try {
    const result = await post("/api/v1/cloud/local/cleanup", {
      admin_key: $("adminKey").value,
      field_id: state.fieldId,
    });
    $("syncStatus").textContent = `Removed ${formatNumber(result.deleted?.records || 0)} local record(s) and ${formatNumber(result.deleted?.project_memberships || 0)} cloud-crawl membership(s).`;
    clearLocalCache();
    await loadStats();
    await loadLocalTab({ reset: true });
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    setSyncLoading(false);
  }
}

async function clearQueuedPapers() {
  if (!window.confirm("Clear all queued papers? Research Tasks and Ready Papers will be kept.")) return;
  $("syncStatus").textContent = "Clearing queued papers.";
  setSyncLoading(true);
  try {
    const result = await post("/api/v1/cloud/local/queue/clear", {
      admin_key: $("adminKey").value,
      field_id: state.fieldId,
    });
    $("syncStatus").textContent = `Cleared ${formatNumber(result.cleared || 0)} queued paper(s).`;
    state.queuedIds = new Set();
    for (const item of state.candidates) {
      if (queueStatus(item) === "queued") {
        item.queue_status = "search_result";
        item.cloud_research_status = {};
      }
    }
    clearLocalCache();
    await loadStats();
    await loadLocalTab({ reset: true });
    renderCandidates();
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    setSyncLoading(false);
  }
}

async function clearResearchTasks() {
  if (!window.confirm(`Clear research tasks for ${modelLabel(targetModelMode())}? Queued and Ready Papers will be kept.`)) return;
  $("syncStatus").textContent = "Clearing research tasks.";
  setSyncLoading(true);
  try {
    const result = await post("/api/v1/cloud/local/tasks/clear", {
      admin_key: $("adminKey").value,
      field_id: state.fieldId,
      model_mode: targetModelMode(),
    });
    $("syncStatus").textContent = `Cleared ${formatNumber(result.cleared || 0)} research task(s).`;
    state.researchTaskIds = new Set();
    for (const item of state.candidates) {
      if (queueStatus(item) === "research_task") {
        item.queue_status = "queued";
        item.cloud_research_status = { ...(item.cloud_research_status || {}), state: "queued", task_state: "" };
      }
    }
    clearLocalCache();
    await loadStats();
    await loadLocalTab({ reset: true });
    renderCandidates();
  } catch (error) {
    $("syncStatus").textContent = error.message;
    showToast(error.message, "error");
  } finally {
    setSyncLoading(false);
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
  setLoading($("cloudSearchForm"), true);
  try {
    const venueFilter = filterSelection("searchVenueChoices");
    const yearFilter = filterSelection("searchYearChoices");
    const payload = {
      query: $("cloudQuery").value.trim(),
      venues: venueFilter.values,
      venue_other: venueFilter.includeOther,
      known_venues: venueOptions,
      years: yearFilter.values.map((item) => Number(item)).filter(Boolean),
      year_other: yearFilter.includeOther,
      known_years: state.yearOptions.map((item) => Number(item)).filter(Boolean),
      concept_type: $("conceptTypeFilter").value,
      model_mode: $("cloudModelMode").value,
      limit: state.cloudLimit,
      offset: state.cloudOffset,
    };
    const data = await post("/api/v1/cloud/search", payload);
    state.cloudItems = data.items || [];
    state.cloudOffset = Number(data.offset || state.cloudOffset || 0);
    state.cloudTotal = Number(data.total || 0);
    state.cloudHasMore = Boolean(data.has_more);
    state.cloudWarning = data.warning || "";
    $("cloudSearchStatus").textContent = state.cloudWarning || `${formatNumber(state.cloudItems.length)} loaded`;
    renderCloudResultTabs();
    renderCloudResults();
    renderCloudPager();
  } catch (error) {
    $("cloudSearchStatus").textContent = "Search failed";
    $("cloudResults").innerHTML = `<div class="empty-state"><strong>Unable to search cloud.</strong><span>${escapeHtml(error.message)}</span></div>`;
  } finally {
    setLoading($("cloudSearchForm"), false);
    renderCloudPager();
  }
}

function renderCloudPager() {
  const pager = $("cloudMoreBtn");
  if (!pager) return;
  const knownTotal = Number(state.cloudTotal || 0);
  const total = knownTotal || (state.cloudHasMore ? state.cloudOffset + state.cloudLimit + 1 : state.cloudOffset + state.cloudItems.length);
  const page = Math.floor(Number(state.cloudOffset || 0) / state.cloudLimit) + 1;
  const pages = Math.max(page, Math.ceil(total / state.cloudLimit));
  pager.hidden = page <= 1 && !state.cloudHasMore;
  const info = $("cloudPageInfo");
  if (info) info.textContent = knownTotal ? `Page ${page} of ${pages}` : `Page ${page}`;
  const prev = pager.querySelector("[data-page-action='prev']");
  const next = pager.querySelector("[data-page-action='next']");
  if (prev) prev.disabled = state.cloudOffset <= 0;
  if (next) next.disabled = !state.cloudHasMore;
}

function derivedConceptRows(tabKey) {
  const tab = tabs.find((entry) => entry.key === tabKey);
  if (!tab || tab.key === "works") return state.cloudItems;
  const rows = [];
  for (const work of state.cloudItems) {
    const records = Array.isArray(work.concept_records) ? work.concept_records : [];
    for (const record of records) {
      if (record.concept_type !== tab.conceptType) continue;
      rows.push({
        ...record,
        source_work: work,
        source_work_title: record.source_work_title || work.title,
        venue_or_source: record.venue_or_source || work.venue,
        year: record.year || work.year,
      });
    }
    if (records.length) continue;
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
    const message = state.cloudWarning || "Search results load ten records at a time.";
    $("cloudResults").innerHTML = `<div class="empty-state"><strong>No ${escapeHtml(tabLabel(state.activeCloudTab))} found.</strong><span>${escapeHtml(message)}</span></div>`;
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

async function openLocalDetail(tabKey, id, modelMode = "") {
  const tab = tabs.find((entry) => entry.key === tabKey);
  const params = new URLSearchParams({ bucket: tab.bucket, id, model_mode: modelMode || localModelMode() });
  const data = await api(`/api/v1/item/detail?${params.toString()}`);
  openDetailModal(data.item, { tabKey, id, local: true });
}

function openCloudDetail(tabKey, id) {
  const rows = tabKey === "works" ? state.cloudItems : derivedConceptRows(tabKey);
  const item = rows.find((entry) => String(idFor(tabKey, entry) || entry.work_id || entry.canonical_id || entry.title) === id);
  if (item) openDetailModal(item, { tabKey, id, local: false });
}

function openDetailModal(item, { tabKey, id, local }) {
  state.detail = { item, tab: tabKey, id, local };
  $("detailKind").textContent = local ? tabLabel(tabKey) : `Cloud ${tabLabel(tabKey)}`;
  $("detailTitle").textContent = item.title || item.name || item.benchmark_name || item.baseline_name || item.canonical_title || "Details";
  $("detailBody").innerHTML = detailSections(item, tabKey);
  if ($("detailRaw")) $("detailRaw").textContent = JSON.stringify(item, null, 2);
  $("openDetailTab").hidden = !local;
  $("detailModal").hidden = false;
}

function detailSections(item, tabKey) {
  const links = [item.url_or_doi, item.paper_link, item.official_url, item.official_code_url, ...(item.source_urls || []), ...(item.source_paper_links || [])].filter(isUrl);
  const shared = `
    ${detailList("Links", links, true)}
    ${detailSourceWorks(item.source_work_details)}
    ${detailEvidence(item)}
    ${detailBlock("Version", [item.provider || displayModelForItem(item, $("cloudModelMode")?.value || targetModelMode()), item.extracted_at || item.updated_at].filter(Boolean).join(" / "))}
  `;
  if (["works", "queued_works", "ready_works"].includes(tabKey)) {
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
    return `
      ${detailBlock("Benchmark", item.description || item.benchmark_name || item.dataset)}
      ${detailBlock("Task", item.task)}
      ${detailBlock("Data Form", item.data_form)}
      ${detailBlock("Scale", item.scale)}
      ${detailList("Metrics", item.metrics || item.metric)}
      ${detailList("Candidate Dataset Pages", item.candidate_dataset_pages)}
      ${detailList("Main Baselines", item.baseline_performance)}
      ${shared}
    `;
  }
  if (tabKey === "baselines") {
    return `
      ${detailBlock("Core Idea", item.core_idea || item.description || item.summary)}
      ${detailBlock("Methodology", item.methodology || item.principle)}
      ${detailBlock("Baseline Type", item.baseline_type)}
      ${detailList("Benchmarks", item.benchmarks)}
      ${performanceTable(item.performance)}
      ${detailBlock("Discussion", item.discussion)}
      ${shared}
    `;
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
  return `<section><h3>${escapeHtml(title)}</h3><p>${formatPlainValue(value)}</p></section>`;
}

function detailList(title, values, links = false) {
  const list = Array.isArray(values) ? values.filter(Boolean) : values ? [values] : [];
  if (!list.length) return "";
  return `<section><h3>${escapeHtml(title)}</h3><ul>${list.slice(0, 32).map((item) => `<li>${links && isUrl(item) ? `<a href="${escapeHtml(item)}" target="_blank" rel="noreferrer">${escapeHtml(item)}</a>` : formatValue(item)}</li>`).join("")}</ul></section>`;
}

function detailKeyValues(values) {
  const rows = Object.entries(values).filter(([, value]) => value !== "" && value != null && !(Array.isArray(value) && !value.length));
  if (!rows.length) return "";
  return `<section><h3>Metadata</h3><dl class="key-values">${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${formatPlainValue(value)}</dd>`).join("")}</dl></section>`;
}

function detailSourceWorks(works) {
  if (!Array.isArray(works) || !works.length) return "";
  return `<section><h3>Source Works</h3><ul>${works.slice(0, 12).map((work) => {
    const label = [work.title || work.work_id, work.venue_or_source, work.year].filter(Boolean).join(" · ");
    return `<li>${work.url_or_doi && isUrl(work.url_or_doi) ? `<a href="${escapeHtml(work.url_or_doi)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>` : escapeHtml(label)}</li>`;
  }).join("")}</ul></section>`;
}

function formatValue(value) {
  if (value == null || value === "") return "";
  if (typeof value === "string") {
    const parsed = parseJsonMaybe(value);
    if (parsed && typeof parsed === "object") return formatValue(parsed);
    return escapeHtml(value);
  }
  if (typeof value !== "object") return escapeHtml(value);
  if (Array.isArray(value)) return value.map(formatValue).join("; ");
  return `<dl class="inline-object">${Object.entries(value)
    .filter(([, val]) => meaningfulDetailValue(val))
    .map(([key, val]) => `<dt>${escapeHtml(humanizeKey(key))}</dt><dd>${formatValue(val)}</dd>`)
    .join("")}</dl>`;
}

function formatPlainValue(value) {
  if (value == null || value === "") return "";
  if (Array.isArray(value)) return value.filter(meaningfulDetailValue).map(formatPlainValue).join("; ");
  if (typeof value === "object") return formatValue(value);
  const parsed = typeof value === "string" ? parseJsonMaybe(value) : null;
  if (parsed && typeof parsed === "object") return formatValue(parsed);
  return escapeHtml(value);
}

function parseJsonMaybe(value) {
  const text = String(value || "").trim();
  if (!text || !["{", "["].includes(text[0])) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function meaningfulDetailValue(value) {
  if (value == null || value === "") return false;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    return Boolean(text) && !["unspecified", "unknown", "n/a", "none", "null"].includes(text);
  }
  if (Array.isArray(value)) return value.some(meaningfulDetailValue);
  return true;
}

function detailEvidence(item) {
  const evidence = normalizeEvidence(item);
  if (!evidence.length) return "";
  return `<section><h3>Evidence</h3><ul>${evidence.slice(0, 8).map((entry) => `<li>${entry}</li>`).join("")}</ul></section>`;
}

function normalizeEvidence(item) {
  const candidates = [];
  if (Array.isArray(item.evidence_items)) candidates.push(...item.evidence_items);
  if (item.evidence) candidates.push(item.evidence);
  if (item.snippet) candidates.push(item.snippet);
  return candidates
    .map((entry) => {
      const parsed = typeof entry === "string" ? parseJsonMaybe(entry) : entry;
      if (parsed && typeof parsed === "object") return evidenceObjectSummary(parsed);
      if (typeof entry === "string") return evidenceStringSummary(entry);
      return formatPlainValue(entry);
    })
    .filter(Boolean);
}

function evidenceStringSummary(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.startsWith("{") && /"\w+"\s*:/.test(text)) {
    const get = (key) => {
      const match = text.match(new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`));
      return match?.[1] || "";
    };
    const fields = [
      ["Dataset", get("dataset") || get("benchmark_name")],
      ["Task", get("task")],
      ["Metric", get("metric")],
      ["Direction", get("metric_direction")],
      ["Source", get("source")],
      ["Excerpt", get("text")],
    ].filter(([, fieldValue]) => meaningfulDetailValue(fieldValue));
    if (fields.length) {
      return `<dl class="inline-object">${fields.map(([key, fieldValue]) => `<dt>${escapeHtml(key)}</dt><dd>${formatPlainValue(compact(fieldValue, key === "Excerpt" ? 360 : 120))}</dd>`).join("")}</dl>`;
    }
    return "";
  }
  return formatPlainValue(compact(text, 520));
}

function evidenceObjectSummary(entry) {
  const span = entry.evidence_span && typeof entry.evidence_span === "object" ? entry.evidence_span : {};
  const fields = [
    ["Dataset", entry.dataset || entry.benchmark_name],
    ["Task", entry.task],
    ["Metric", entry.metric],
    ["Direction", entry.metric_direction],
    ["Source", span.source || entry.source],
    ["Excerpt", span.text || entry.text || entry.evidence || entry.quote],
  ].filter(([, value]) => meaningfulDetailValue(value));
  if (!fields.length) return formatValue(entry);
  return `<dl class="inline-object">${fields.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${formatPlainValue(compact(String(value), key === "Excerpt" ? 360 : 120))}</dd>`).join("")}</dl>`;
}

function humanizeKey(key) {
  return String(key || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function performanceTable(rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  return `
    <section class="wide-section">
      <h3>Performance</h3>
      <table class="mini-table">
        <thead><tr><th>Benchmark</th><th>Method</th><th>Metric</th><th>Result</th><th>Evidence</th></tr></thead>
        <tbody>
          ${rows.slice(0, 20).map((row) => {
            if (typeof row !== "object") return `<tr><td colspan="5">${escapeHtml(row)}</td></tr>`;
            return `<tr>
              <td>${escapeHtml(row.benchmark_name || row.dataset || row.benchmark_id || "")}</td>
              <td>${escapeHtml(row.method_name || row.baseline_name || "")}</td>
              <td>${escapeHtml(row.metric || "")}</td>
              <td>${escapeHtml(row.value_text || row.value || "")} ${escapeHtml(row.unit || "")}</td>
              <td>${escapeHtml(row.evidence || row.evidence_span?.text || "")}</td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    </section>
  `;
}

function openCurrentDetailInTab() {
  if (!state.detail.local) return;
  const tab = tabs.find((entry) => entry.key === state.detail.tab);
  if (!tab || !state.detail.id) return;
  window.open(`/item.html?bucket=${encodeURIComponent(tab.bucket)}&id=${encodeURIComponent(state.detail.id)}&field_id=${encodeURIComponent(state.fieldId)}&model_mode=${encodeURIComponent(state.detail.modelMode || localModelMode())}`, "_blank");
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
  state.cloudWarning = "";
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
  wireSelectAllChips("venueChoices");
  wireSelectAllChips("yearChoices");
  wireSelectAllChips("searchVenueChoices");
  wireSelectAllChips("searchYearChoices");
  $("refreshStats").addEventListener("click", () => {
    clearLocalCache();
    setButtonBusy($("refreshStats"), true, "Refreshing...");
    Promise.all([loadStats(), loadLocalTab({ reset: true })]).finally(() => setButtonBusy($("refreshStats"), false));
  });
  $("crawlForm").addEventListener("submit", addToQueue);
  $("cancelSearch").addEventListener("click", cancelDiscoverSearch);
  $("addSearchResultsToQueue").addEventListener("click", addSearchResultsToQueue);
  $("pauseQueueAdd").addEventListener("click", toggleQueueAddPause);
  $("cancelQueueAdd").addEventListener("click", cancelQueueAdd);
  $("addAllQueuedToTasks").addEventListener("click", () => openQueueFilterModal("add_all"));
  $("runResearch").addEventListener("click", runResearch);
  $("confirmResearchModel").addEventListener("click", confirmResearchModel);
  $("cancelResearchModel").addEventListener("click", () => ($("researchModelModal").hidden = true));
  $("applyQueueFilter").addEventListener("click", applyQueueFilterModal);
  $("cancelQueueFilter").addEventListener("click", () => ($("queueFilterModal").hidden = true));
  $("stopResearch").addEventListener("click", stopResearch);
  $("candidateList").addEventListener("click", async (event) => {
    const card = event.target.closest("[data-candidate]");
    if (!card) return;
    if (event.target.closest("[data-action='remove-search-result']")) {
      state.candidates = state.candidates.filter((item) => candidateKey(item) !== card.dataset.candidate && String(item.work_id || "") !== card.dataset.candidate);
      renderCandidates();
    }
  });
  $("clearCandidateSelection").addEventListener("click", () => {
    if (state.crawlRunId) {
      showToast("Stop the active research run before clearing searched results.", "warn");
      return;
    }
    state.candidates = [];
    renderCandidates();
  });
  $("localTabRow").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-local-tab]");
    if (!button) return;
    state.activeLocalTab = button.dataset.localTab;
    if (state.activeLocalTab === "queued_works") {
      openQueueFilterModal("view");
      renderLocalTabs();
      return;
    }
    await loadLocalTab({ reset: true });
  });
  $("localTabContent").addEventListener("click", async (event) => {
    const row = event.target.closest("[data-id]");
    if (!row) return;
    const addTaskButton = event.target.closest("[data-action='add-task']");
    if (addTaskButton) {
      await addResearchTasks([row.dataset.id], addTaskButton);
      return;
    }
    const removeTaskButton = event.target.closest("[data-action='remove-task']");
    if (removeTaskButton) {
      await removeResearchTasks([row.dataset.id], removeTaskButton);
      return;
    }
    const syncButton = event.target.closest("[data-action='sync-one']");
    if (syncButton) {
      await syncSingleReadyWork(row.dataset.id, syncButton, row.dataset.modelMode || targetModelMode());
      return;
    }
    const syncRecordButton = event.target.closest("[data-action='sync-record']");
    if (syncRecordButton) {
      await syncSingleLocalRecord(row.dataset.tab, row.dataset.id, syncRecordButton, row.dataset.modelMode || localModelMode());
      return;
    }
    if (event.target.closest("[data-action='remove-queue']")) {
      await removeQueuedWorks([row.dataset.id]);
      return;
    }
    if (event.target.closest("[data-action='open-tab']")) {
      state.detail = { tab: row.dataset.tab, id: row.dataset.id, local: true, modelMode: row.dataset.modelMode || localModelMode() };
      openCurrentDetailInTab();
      return;
    }
    await openLocalDetail(row.dataset.tab, row.dataset.id, row.dataset.modelMode || localModelMode());
  });
  $("reloadLocalTab").addEventListener("click", () => {
    clearLocalCache();
    loadLocalTab({ reset: true });
  });
  $("localMoreBtn").addEventListener("click", (event) => {
    const button = event.target.closest("[data-page-action]");
    if (!button) return;
    loadLocalTab({ reset: false, pageDelta: button.dataset.pageAction === "prev" ? -1 : 1 });
  });
  $("localTabSearch").addEventListener("input", debounce(() => {
    clearLocalCache();
    loadLocalTab({ reset: true, silent: true });
  }, 260));
  $("crawlModelMode").addEventListener("change", async () => {
    state.candidates = [];
    state.queuedIds = new Set();
    clearLocalCache();
    await loadStats();
    await loadLocalTab({ reset: true });
    renderCandidates();
  });
  $("syncUnsynced").addEventListener("click", syncUnsynced);
  $("clearSyncedCache").addEventListener("click", clearSyncedCache);
  $("clearQueuedPapers").addEventListener("click", clearQueuedPapers);
  $("clearResearchTasks").addEventListener("click", clearResearchTasks);
  $("cloudSearchForm").addEventListener("submit", (event) => searchCloud(event, { reset: true }));
  $("cloudMoreBtn").addEventListener("click", (event) => {
    const button = event.target.closest("[data-page-action]");
    if (!button) return;
    state.cloudOffset = Math.max(0, state.cloudOffset + (button.dataset.pageAction === "prev" ? -state.cloudLimit : state.cloudLimit));
    $("cloudResults").innerHTML = loadingRows(4);
    searchCloud(null, { reset: false });
  });
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
  await Promise.all([loadStats(), loadLocalTab({ reset: true })]);
  renderCloudResults();
}

init();
