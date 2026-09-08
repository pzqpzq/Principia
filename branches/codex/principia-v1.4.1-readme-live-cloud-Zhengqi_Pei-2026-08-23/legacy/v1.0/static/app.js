const tabs = [
  { key: "works", label: "Works", idKey: "work_id", bucket: "source_works" },
  { key: "existed_ideas", label: "Existed Ideas", idKey: "canonical_id", bucket: "existed_ideas" },
  { key: "benchmarks", label: "Benchmarks", idKey: "benchmark_id", bucket: "benchmark_records" },
  { key: "baselines", label: "Baselines", idKey: "baseline_id", bucket: "baseline_records" },
  { key: "principles", label: "Principles", idKey: "principle_id", bucket: "principles" },
  { key: "takeaway_messages", label: "Takeaway Messages", idKey: "canonical_id", bucket: "takeaway_messages" },
  { key: "my_ideas", label: "My Ideas", idKey: "idea_id", bucket: "my_ideas" },
];

const state = {
  projects: [],
  activeProjectId: "default",
  activeProject: null,
  activeTab: "existed_ideas",
  counts: {},
  items: [],
  offset: 0,
  limit: 10,
  hasMore: false,
  busy: false,
  researchActive: false,
  researchRunId: "",
  researchRunProjectId: "",
  ideaRunId: "",
  ideaRunProjectId: "",
  refreshRunId: "",
  workExtractRunId: "",
  workExtractRuns: {},
  warningRunId: "",
  researchCountsSignature: "",
  tabRenderSignature: "",
  atlas: { symbols: [], conceptCounts: {} },
  researchTimer: null,
  ideaTimer: null,
  refreshTimer: null,
  workExtractTimer: null,
  detail: { bucket: "", id: "", item: null },
  assembler: { sourceType: "existed_ideas", items: [], selected: [] },
  projectModal: { mode: "create", fieldId: "" },
  deleteProject: { fieldId: "" },
  toastTimer: null,
};

const el = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function compact(value, length = 180) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= length) return text;
  return `${text.slice(0, Math.max(0, length - 3)).trim()}...`;
}

function isUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) throw new Error(payload?.error || `HTTP ${response.status}`);
  return payload;
}

function post(path, payload) {
  return api(path, { method: "POST", body: JSON.stringify(payload || {}) });
}

function showToast(message, tone = "success") {
  const stack = el("toastStack");
  if (!stack) return;
  const toast = document.createElement("div");
  toast.className = `toast ${tone}`;
  toast.textContent = message;
  stack.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("leaving");
    window.setTimeout(() => toast.remove(), 260);
  }, 2600);
}

function typesetMath(root = document.body) {
  if (window.MathJax?.typesetPromise) {
    window.MathJax.typesetPromise([root]).catch(() => {});
    return;
  }
  renderMathFallback(root);
}

function readableLatex(value) {
  return String(value ?? "")
    .trim()
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1)/($2)")
    .replace(/\\sqrt\{([^{}]+)\}/g, "sqrt($1)")
    .replace(/\\(?:mathbb|mathbf|mathrm|mathit|operatorname)\{([^{}]+)\}/g, "$1")
    .replace(/\^\{([^{}]+)\}/g, "^$1")
    .replace(/_\{([^{}]+)\}/g, "_$1")
    .replace(/\\to\b/g, "->")
    .replace(/\\rightarrow\b/g, "->")
    .replace(/\\leftarrow\b/g, "<-")
    .replace(/\\Rightarrow\b/g, "=>")
    .replace(/\\leq\b/g, "≤")
    .replace(/\\geq\b/g, "≥")
    .replace(/\\neq\b/g, "≠")
    .replace(/\\approx\b/g, "≈")
    .replace(/\\times\b/g, "×")
    .replace(/\\cdot\b/g, "·")
    .replace(/\\infty\b/g, "∞")
    .replace(/\\sum\b/g, "Σ")
    .replace(/\\prod\b/g, "Π")
    .replace(/\\forall\b/g, "∀")
    .replace(/\\exists\b/g, "∃")
    .replace(/\\land\b/g, "∧")
    .replace(/\\lor\b/g, "∨")
    .replace(/\\neg\b/g, "¬")
    .replace(/\\alpha\b/g, "α")
    .replace(/\\beta\b/g, "β")
    .replace(/\\gamma\b/g, "γ")
    .replace(/\\delta\b/g, "δ")
    .replace(/\\epsilon\b/g, "ε")
    .replace(/\\lambda\b/g, "λ")
    .replace(/\\mu\b/g, "μ")
    .replace(/\\pi\b/g, "π")
    .replace(/\\sigma\b/g, "σ")
    .replace(/\\theta\b/g, "θ")
    .replace(/\\s+/g, " ")
    .replace(/\\([A-Za-z]+)/g, "$1");
}

function renderMathFallback(root = document.body) {
  if (!root) return;
  const pattern = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$[^$\n]{1,500}\$|\\\([^()\n]{1,500}\\\))/g;
  const skipTags = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "OPTION", "CODE", "PRE"]);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || skipTags.has(parent.tagName) || parent.closest(".math-fallback")) return NodeFilter.FILTER_REJECT;
      pattern.lastIndex = 0;
      return pattern.test(node.nodeValue || "") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    const text = node.nodeValue || "";
    pattern.lastIndex = 0;
    let cursor = 0;
    const fragment = document.createDocumentFragment();
    for (const match of text.matchAll(pattern)) {
      if (match.index > cursor) fragment.append(document.createTextNode(text.slice(cursor, match.index)));
      const raw = match[0];
      const block = raw.startsWith("$$") || raw.startsWith("\\[");
      const content = raw.startsWith("$$")
        ? raw.slice(2, -2)
        : raw.startsWith("$")
          ? raw.slice(1, -1)
          : raw.startsWith("\\[")
            ? raw.slice(2, -2)
            : raw.slice(2, -2);
      const span = document.createElement(block ? "div" : "span");
      span.className = `math-fallback ${block ? "math-block" : "math-inline"}`;
      span.textContent = readableLatex(content);
      fragment.append(span);
      cursor = match.index + raw.length;
    }
    if (cursor < text.length) fragment.append(document.createTextNode(text.slice(cursor)));
    node.parentNode?.replaceChild(fragment, node);
  });
}

function rememberWorkspaceState() {
  localStorage.setItem("principia.activeProjectId", state.activeProjectId || "");
  localStorage.setItem("principia.activeTab", state.activeTab || "existed_ideas");
}

function clearTransientStatus(message = "Ready") {
  if (state.researchActive || state.ideaRunId || state.refreshRunId || state.workExtractRunId) return;
  el("researchStatus").classList.remove("running");
  el("researchStatus").textContent = message;
}

function preserveScrollAfter(work) {
  const y = window.scrollY;
  return Promise.resolve(work()).finally(() => {
    requestAnimationFrame(() => window.scrollTo({ top: y, behavior: "auto" }));
  });
}

function setBusy(isBusy, message = "") {
  state.busy = isBusy;
  document.body.dataset.busy = isBusy ? "true" : "false";
  if (message) {
    el("researchStatus").classList.toggle("running", isBusy);
    el("researchStatus").innerHTML = `
      <div class="status-line">
        ${isBusy ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml(message)}</strong>
      </div>
      ${isBusy ? `<div class="progress-track" aria-hidden="true"><span style="width: 18%"></span></div>` : ""}
    `;
  }
  if (!isBusy && !state.researchActive) el("researchStatus").classList.remove("running");
}

function setResearchRunning(isRunning) {
  state.researchActive = isRunning;
  document.body.dataset.researchRunning = isRunning ? "true" : "false";
  el("researchBtn").disabled = isRunning;
  el("generateIdeaBtn").disabled = false;
  el("cancelResearchBtn").hidden = !isRunning;
}

function renderResearchStatus(run) {
  const stage = run.stage || run.status || "running";
  const message = run.message || "";
  const counts = run.counts || {};
  const done = Number(counts.llm_batches_done || counts.processed_works || 0);
  const total = Number(counts.llm_batches_total || counts.found_works || counts.target_works || 0);
  const percent = total > 0 ? Math.max(4, Math.min(100, Math.round((done / total) * 100))) : (run.status === "complete" ? 100 : 12);
  const countText = Object.keys(counts).length
    ? Object.entries(counts)
        .filter(([, value]) => value !== "" && value != null)
        .map(([key, value]) => `${key.replaceAll("_", " ")} ${value}`)
        .join(" / ")
    : "";
  const running = !["complete", "error", "partial_error", "cancelled"].includes(run.status || "");
  el("researchStatus").classList.toggle("running", running);
  el("researchStatus").innerHTML = `
    <div class="status-line">
      ${running ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
      <strong>${escapeHtml(stage.replaceAll("_", " "))}</strong>
      <span>${escapeHtml(message)}</span>
    </div>
    <div class="progress-track" aria-hidden="true"><span style="width: ${percent}%"></span></div>
    ${countText ? `<small>${escapeHtml(countText)}</small>` : ""}
  `;
}

function renderIdeaGenerationStatus(run) {
  const symbolic = String(run.type || "").includes("symbolic");
  const stages = symbolic
    ? ["v1_memory_sync", "symbol_table", "symbolic_prompt_pack", "principia_calculus_llm", "derivation_verification", "saving_lineage", "complete"]
    : ["collecting_evidence", "llm_generation", "normalizing_idea", "saving_idea", "related_comparison", "v1_memory_sync", "complete"];
  const stage = run.stage || run.status || "queued";
  const currentIndex = Math.max(0, stages.indexOf(stage));
  const percent = run.status === "complete"
    ? 100
    : Math.max(8, Math.min(96, Math.round(((currentIndex + 0.5) / stages.length) * 100)));
  const counts = run.counts || {};
  const countText = Object.entries(counts)
    .filter(([, value]) => value !== "" && value != null)
    .slice(0, 6)
    .map(([key, value]) => `${key.replaceAll("_", " ")} ${value}`)
    .join(" / ");
  return `
    <section class="generation-status">
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml(stage.replaceAll("_", " "))}</strong>
      </div>
      <p class="muted">${escapeHtml(run.message || "")}</p>
      <div class="progress-track" aria-hidden="true"><span style="width: ${percent}%"></span></div>
      ${countText ? `<small>${escapeHtml(countText)}</small>` : ""}
      <ol class="stage-list">
        ${stages.map((item, index) => `
          <li class="${index < currentIndex || run.status === "complete" ? "done" : index === currentIndex ? "active" : ""}">
            ${escapeHtml(item.replaceAll("_", " "))}
          </li>
        `).join("")}
      </ol>
    </section>
  `;
}

async function cancelRun(runId, label = "operation") {
  if (!runId) return;
  await post("/api/v1/research/cancel", { run_id: runId });
  if (label === "research") {
    clearTimeout(state.researchTimer);
    setResearchRunning(false);
  }
  if (label === "idea") {
    clearTimeout(state.ideaTimer);
    state.ideaRunId = "";
    el("cancelIdeaGenerationBtn").hidden = true;
    el("assembleIdeaBtn").disabled = false;
    setBusy(false);
    clearTransientStatus("Ready");
  }
  if (label === "refresh") {
    clearTimeout(state.refreshTimer);
    state.refreshRunId = "";
    el("cancelDetailRefreshBtn").hidden = true;
    setBusy(false);
  }
}

function getModelMode() {
  return el("modelModeInput").value || "auto";
}

function getAssemblerModelMode() {
  return el("assemblerModelMode")?.value || getModelMode();
}

function getAssemblerGenerationMode() {
  return el("assemblerGenerationMode")?.value || "standard";
}

function getGoalText() {
  return el("goalInput").value.trim();
}

function getTargetWorks() {
  const value = Number(el("targetWorksInput")?.value || 100);
  if (!Number.isFinite(value)) return 100;
  return Math.max(1, Math.min(200, Math.round(value)));
}

function idFor(tabKey, item) {
  const tab = tabs.find((entry) => entry.key === tabKey || entry.bucket === tabKey);
  return item?.[tab?.idKey] || item?.canonical_id || item?.benchmark_id || item?.baseline_id || item?.idea_id || "";
}

function recordIdForEvidence(sourceType, item) {
  const tab = tabs.find((entry) => entry.key === sourceType || entry.bucket === sourceType);
  return item?.[tab?.idKey] || item?.work_id || item?.canonical_id || item?.principle_id || item?.benchmark_id || item?.baseline_id || item?.idea_id || "";
}

function evidenceLabel(item) {
  return item?.title || item?.name || item?.benchmark_name || item?.baseline_name || compact(item?.idea_text || item?.message_text || item?.abstract_signature || item?.abstract || item?.summary || item?.description || "", 80);
}

async function loadProjects(preferredId = "") {
  const data = await api("/api/v1/projects");
  const existingById = Object.fromEntries((state.projects || []).map((project) => [project.field_id, project]));
  state.projects = (data.items || []).map((project) => {
    const previous = existingById[project.field_id] || {};
    return { ...previous, ...project, counts: project.counts || previous.counts || {} };
  });
  const savedId = localStorage.getItem("principia.activeProjectId") || "";
  const desiredId = preferredId || savedId || state.activeProjectId;
  const first = state.projects.find((project) => project.field_id === desiredId) || state.projects[0];
  state.activeProject = first || null;
  state.activeProjectId = first?.field_id || "default";
  rememberWorkspaceState();
  renderProjects();
  renderProjectHeader();
}

async function loadSummary() {
  const summary = await api(`/api/v1/project/summary?field_id=${encodeURIComponent(state.activeProjectId)}`);
  state.activeProject = summary.project || state.activeProject;
  state.counts = summary.counts || {};
  const idx = state.projects.findIndex((project) => project.field_id === state.activeProjectId);
  if (idx >= 0) state.projects[idx] = { ...state.projects[idx], ...state.activeProject, counts: state.counts };
  renderProjects();
  renderProjectHeader();
  if (summary.last_research_run && !state.ideaRunId && String(summary.last_research_run.type || "").includes("research") && summary.last_research_run.field_id === state.activeProjectId) {
    const run = summary.last_research_run;
    if (["queued", "running"].includes(run.status || "")) {
      state.researchRunId = run.run_id || state.researchRunId;
      state.researchRunProjectId = state.activeProjectId;
      setResearchRunning(true);
      renderResearchStatus(run);
      pollResearch();
    } else if (!state.researchActive) {
      el("researchStatus").textContent = `${run.status || "idle"} · ${run.message || run.stage || ""}`;
    }
  } else if (!state.ideaRunId && !state.workExtractRunId && state.researchRunProjectId !== state.activeProjectId) {
    state.researchRunId = "";
    state.researchRunProjectId = "";
    setResearchRunning(false);
    clearTransientStatus("Ready");
  }
  await loadResearchAtlas(summary);
}

function renderProjects() {
  el("projectList").innerHTML = state.projects.length
    ? state.projects
        .map((project) => {
          const counts = project.counts || {};
          const active = project.field_id === state.activeProjectId;
          const countText = `${counts.existed_ideas || counts.ideas || 0} ideas / ${counts.benchmarks || 0} benchmarks`;
          return `
            <article class="project-item ${active ? "active" : ""}" draggable="true" data-field-id="${escapeHtml(project.field_id)}">
              <button type="button" class="project-main" data-action="select-project" data-field-id="${escapeHtml(project.field_id)}">
                <strong>${escapeHtml(project.name || "Untitled Project")}</strong>
                <span>${escapeHtml(countText)}</span>
              </button>
              <div class="project-actions">
                ${project.field_id === "default" ? "" : `<button type="button" data-action="edit-project" data-field-id="${escapeHtml(project.field_id)}">Edit</button>`}
                ${project.field_id === "default" ? "" : `<button type="button" data-action="delete-project" data-field-id="${escapeHtml(project.field_id)}">Delete</button>`}
              </div>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-state">No projects yet. Create one to start.</p>`;
}

function renderProjectHeader() {
  const project = state.activeProject || {};
  el("projectTitle").textContent = project.name || "No Project";
  el("projectDescription").textContent = project.description || "Research, structure, and generate ideas from field evidence.";
  el("goalInput").placeholder = "Generate a novel, testable idea for improving long-context reasoning efficiency in LLM agents.";
  el("goalInput").value = project.goal_text || project.query || "";
  const settings = project.settings || {};
  el("modelModeInput").value = settings.model_mode || "auto";
  el("targetWorksInput").value = settings.paper_count || settings.target_works || settings.max_works || 100;
  renderTabs();
}

function renderTabs() {
  el("tabRow").innerHTML = tabs
    .map((tab) => {
      const count = state.counts?.[tab.key] || 0;
      return `<button type="button" class="${state.activeTab === tab.key ? "active" : ""}" data-tab="${tab.key}">${tab.label} <span>${count}</span></button>`;
    })
    .join("");
}

function atlasCountRows(counts = {}) {
  return [
    ["Works", counts.works || 0],
    ["Existed", counts.existed_ideas || 0],
    ["Principles", counts.principles || 0],
    ["Takeaways", counts.takeaway_messages || 0],
    ["Benchmarks", counts.benchmarks || 0],
    ["Baselines", counts.baselines || 0],
    ["My Ideas", counts.my_ideas || 0],
  ];
}

function renderResearchAtlas({ counts = state.counts, lastRun = null, symbols = state.atlas.symbols, conceptCounts = state.atlas.conceptCounts } = {}) {
  const status = lastRun?.status || "idle";
  const stage = lastRun?.stage || "";
  el("atlasStats").innerHTML = [
    ...atlasCountRows(counts).map(([label, value]) => `
      <div class="atlas-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${Number(value || 0)}</strong>
      </div>
    `),
    `
      <div class="atlas-stat atlas-run">
        <span>Last Run</span>
        <strong>${escapeHtml(status)}</strong>
        ${stage ? `<small>${escapeHtml(stage.replaceAll("_", " "))}</small>` : ""}
      </div>
    `,
  ].join("");

  const conceptEntries = Object.entries(conceptCounts || {}).filter(([, count]) => Number(count) > 0);
  el("atlasConcepts").innerHTML = conceptEntries.length
    ? conceptEntries
        .map(([type, count]) => `<span class="atlas-chip">${escapeHtml(type.replaceAll("_", " "))}<strong>${Number(count)}</strong></span>`)
        .join("")
    : `<span class="muted">No v1 concepts in scope yet.</span>`;

  el("atlasSymbols").innerHTML = symbols?.length
    ? symbols
        .slice(0, 10)
        .map((symbol) => `
          <span class="symbol-chip" title="${escapeHtml(symbol.gloss || symbol.label || "")}">
            <strong>${escapeHtml(symbol.short_code || symbol.symbol || "")}</strong>
            <small>${escapeHtml(compact(symbol.label || symbol.concept_type || "", 36))}</small>
          </span>
        `)
        .join("")
    : `<span class="muted">No symbols minted yet.</span>`;
}

async function loadResearchAtlas(summary = {}) {
  renderResearchAtlas({ counts: summary.counts || state.counts, lastRun: summary.last_research_run || null });
  try {
    const symbols = await api(`/api/v1/symbols/table?namespace=${encodeURIComponent(state.activeProjectId)}&limit=12`).catch(() => ({ items: [] }));
    const counts = summary.counts || state.counts || {};
    const conceptCounts = {
      existed_idea: counts.existed_ideas || 0,
      principle: counts.principles || 0,
      takeaway_message: counts.takeaway_messages || 0,
      benchmark: counts.benchmarks || 0,
      baseline: counts.baselines || 0,
      generated_idea: counts.my_ideas || 0,
    };
    state.atlas = { symbols: symbols.items || [], conceptCounts };
    renderResearchAtlas({ counts: summary.counts || state.counts, lastRun: summary.last_research_run || null, symbols: state.atlas.symbols, conceptCounts });
  } catch (error) {
    renderResearchAtlas({ counts: summary.counts || state.counts, lastRun: summary.last_research_run || null });
  }
}

async function selectProject(fieldId) {
  const previousProjectId = state.activeProjectId;
  state.activeProjectId = fieldId || state.activeProjectId;
  state.activeProject = state.projects.find((project) => project.field_id === state.activeProjectId) || state.projects[0] || null;
  state.activeProjectId = state.activeProject?.field_id || "default";
  if (previousProjectId !== state.activeProjectId) {
    state.assembler = { sourceType: "existed_ideas", items: [], selected: [], projectId: state.activeProjectId };
    state.workExtractRuns = {};
    state.workExtractRunId = "";
    state.researchRunId = "";
    state.researchRunProjectId = "";
    clearTimeout(state.researchTimer);
    setResearchRunning(false);
    clearTransientStatus("Ready");
  }
  state.offset = 0;
  state.items = [];
  state.tabRenderSignature = "";
  rememberWorkspaceState();
  renderProjects();
  renderProjectHeader();
  await loadSummary();
  await loadTab({ reset: true });
}

async function loadTab({ reset = false, preserveScroll = false, silent = false } = {}) {
  const priorScrollY = window.scrollY;
  if (reset) {
    state.offset = 0;
    if (!silent) {
      state.items = [];
      state.tabRenderSignature = "";
      el("tabContent").innerHTML = `<div class="loading-row">Loading ${escapeHtml(tabLabel(state.activeTab))}...</div>`;
    }
  } else {
    el("moreBtn").textContent = "Loading...";
  }
  const params = new URLSearchParams({
    field_id: state.activeProjectId,
    tab: state.activeTab,
    offset: String(state.offset),
    limit: String(state.limit),
    query: el("tabSearchInput").value.trim(),
    model_mode: getModelMode(),
    sort: el("tabSortInput")?.value || "composite",
  });
  try {
    const data = await api(`/api/v1/project/tab?${params.toString()}`);
    state.counts = data.counts || state.counts;
    if (state.activeTab === "works") state.workExtractRuns = data.work_extraction_runs || {};
    state.items = reset ? data.items || [] : [...state.items, ...(data.items || [])];
    state.offset = state.items.length;
    state.hasMore = Boolean(data.has_more);
    renderTabs();
    renderTabContent({ stable: silent });
    el("moreBtn").hidden = !state.hasMore;
  } catch (error) {
    el("tabContent").innerHTML = `<div class="empty-state"><strong>Unable to load.</strong><span>${escapeHtml(error.message)}</span></div>`;
  } finally {
    el("moreBtn").textContent = "More";
    if (preserveScroll) {
      requestAnimationFrame(() => window.scrollTo({ top: priorScrollY, behavior: "auto" }));
    }
  }
}

function renderTabContent({ stable = false } = {}) {
  if (!state.items.length) {
    const label = tabLabel(state.activeTab);
    el("tabContent").innerHTML = `<div class="empty-state"><strong>No ${escapeHtml(label)} yet.</strong><span>Run Research, or generate a new idea after selecting evidence.</span></div>`;
    state.tabRenderSignature = `${state.activeTab}:empty`;
    return;
  }
  const renderer = {
    works: renderWork,
    existed_ideas: renderExistedIdea,
    benchmarks: renderBenchmark,
    baselines: renderBaseline,
    principles: renderPrinciple,
    takeaway_messages: renderTakeawayMessage,
    my_ideas: renderMyIdea,
  }[state.activeTab];
  if (!renderer) {
    el("tabContent").innerHTML = `<div class="empty-state"><strong>Unsupported tab.</strong><span>${escapeHtml(state.activeTab)}</span></div>`;
    return;
  }
  const signature = JSON.stringify(
    state.items.map((item) => ({
      id: idFor(state.activeTab, item),
      updated_at: item.updated_at || item.extracted_at || item.created_at || "",
      run: state.activeTab === "works" ? state.workExtractRuns?.[item.work_id || idFor(state.activeTab, item)]?.status || item.work_extraction_run?.status || "" : "",
      queue: state.activeTab === "works" ? state.workExtractRuns?.[item.work_id || idFor(state.activeTab, item)]?.queue_position || item.work_extraction_run?.queue_position || 0 : 0,
    }))
  );
  if (stable && signature === state.tabRenderSignature) return;
  state.tabRenderSignature = signature;
  el("tabContent").innerHTML = state.items.map((item) => renderer(item)).join("");
  typesetMath(el("tabContent"));
}

function renderWork(item) {
  const links = [item.url_or_doi, item.paper_link, ...(item.source_urls || [])].filter(isUrl);
  const extractionCounts = item.work_extraction_counts || {};
  const extractedTotal = Number(extractionCounts.total || 0);
  const activeRun = state.workExtractRuns?.[item.work_id] || item.work_extraction_run || null;
  const runStatus = activeRun?.status || "";
  const queuedPosition = Number(activeRun?.queue_position || 0);
  const extractLabel = runStatus === "running"
    ? "In Progress"
    : runStatus === "queued"
      ? `Queued${queuedPosition ? ` #${queuedPosition}` : ""}`
      : extractedTotal > 0
        ? `Update Extraction (${extractedTotal})`
        : "Research Work";
  const extractClass = runStatus ? `work-extract-${runStatus}` : extractedTotal > 0 ? "work-extract-done" : "";
  const extractTitle = runStatus
    ? "Click to stop this work extraction. Completed records will be kept."
    : extractedTotal > 0
      ? "This work already has extracted records. Click to update."
      : "Extract ideas, principles, takeaways, benchmarks, and baselines from this work.";
  return rowShell(
    "works",
    item,
    `
      <div>
        <h3>${escapeHtml(item.title || "Untitled Work")}</h3>
        <p>${escapeHtml(compact(item.abstract || item.summary || "No abstract available.", 320))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.venue_or_source || item.source_type || "source")}</span>
          <span>${escapeHtml(item.year || "n.d.")}</span>
          ${links[0] ? `<a href="${escapeHtml(links[0])}" target="_blank" rel="noreferrer">Open</a>` : ""}
        </div>
      </div>
      <div class="record-actions">
        <button type="button" data-action="add-material">Add Material</button>
        <button type="button" data-action="extract-work" class="${extractClass}" title="${escapeHtml(extractTitle)}">${escapeHtml(extractLabel)}</button>
        <button type="button" data-action="details">Details</button>
      </div>
    `
  );
}

function tabLabel(key) {
  return tabs.find((tab) => tab.key === key)?.label || key;
}

function tabKeyForBucket(bucket) {
  return tabs.find((tab) => tab.bucket === bucket || tab.key === bucket)?.key || "";
}

function materialTabs() {
  return new Set(["works", "existed_ideas", "benchmarks", "baselines", "principles", "takeaway_messages"]);
}

function normalizedDisplayText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function argumentTitle(value, fallback = "Principle") {
  const text = String(value || "")
    .replace(/^\s*(principle|argument|core idea|summary)\s*[:.-]\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return fallback;
  return compact(text, 110);
}

function principleDisplayTitle(item) {
  const base = String(item.name || item.title || "").trim();
  const normalized = normalizedDisplayText(base);
  const duplicateCount = normalized
    ? state.items.filter((entry) => normalizedDisplayText(entry.name || entry.title || "") === normalized).length
    : 0;
  if (base && duplicateCount <= 1 && normalized !== "principle") return base;
  return argumentTitle(item.argument || item.abstract_signature || item.summary, base || "Principle");
}

function rowShell(tabKey, item, body) {
  const id = idFor(tabKey, item);
  return `<article class="record-row record-${escapeHtml(tabKey)}" data-tab="${escapeHtml(tabKey)}" data-id="${escapeHtml(id)}">${body}</article>`;
}

function renderSymbolBadges(item) {
  const symbol = item.symbol_code || item.active_variant?.payload?.symbol || item.symbol?.short_code || "";
  const badges = [];
  if (symbol) badges.push(`<span class="record-badge symbol-badge">${escapeHtml(symbol)}</span>`);
  if (item.generation_mode === "principia_calculus" || item.derivation_id) badges.push(`<span class="record-badge">Principia Calculus</span>`);
  if (item.validation_status === "speculative_unverified" || item.feedback_status === "speculative_unverified") badges.push(`<span class="record-badge warning">L0 speculative</span>`);
  return badges.length ? `<div class="record-badges">${badges.join("")}</div>` : "";
}

function renderExistedIdea(item) {
  return rowShell(
    "existed_ideas",
    item,
    `
      <div>
        <h3>${escapeHtml(item.title || compact(item.idea_text, 88) || "Existed Idea")}</h3>
        <p>${escapeHtml(compact(item.core_idea || item.idea_text || item.summary, 300))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.venue_or_source || "source")}</span>
          <span>${escapeHtml(item.year || "n.d.")}</span>
          <span>${escapeHtml(item.model_name || "model")}</span>
        </div>
      </div>
      <div class="record-actions">
        <button type="button" data-action="add-material">Add Material</button>
        <button type="button" data-action="details">Details</button>
      </div>
    `
  );
}

function renderPrinciple(item) {
  return rowShell(
    "principles",
    item,
    `
      <div>
        <h3>${escapeHtml(principleDisplayTitle(item))}</h3>
        <p>${escapeHtml(compact(item.argument || item.abstract_signature || item.summary, 300))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.venue_or_source || "source")}</span>
          <span>${escapeHtml(item.year || "n.d.")}</span>
          <span>${escapeHtml(item.model_name || "model")}</span>
        </div>
      </div>
      <div class="record-actions">
        <button type="button" data-action="add-material">Add Material</button>
        <button type="button" data-action="details">Details</button>
      </div>
    `
  );
}

function renderTakeawayMessage(item) {
  return rowShell(
    "takeaway_messages",
    item,
    `
      <div>
        <h3>${escapeHtml(item.title || compact(item.main_results || item.message_text, 88) || "Takeaway Message")}</h3>
        <p>${escapeHtml(compact(item.main_results || item.message_text || item.finding || item.actionable_lesson, 300))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.venue_or_source || "source")}</span>
          <span>${escapeHtml(item.year || "n.d.")}</span>
          <span>${escapeHtml(item.model_name || "model")}</span>
        </div>
      </div>
      <div class="record-actions">
        <button type="button" data-action="add-material">Add Material</button>
        <button type="button" data-action="details">Details</button>
      </div>
    `
  );
}

function renderBenchmark(item) {
  return rowShell(
    "benchmarks",
    item,
    `
      <div class="benchmark-row-grid">
        <div><span class="mini-label">Benchmark</span><strong>${escapeHtml(item.benchmark_name || item.dataset || "Benchmark")}</strong></div>
        <div><span class="mini-label">Task</span><span>${escapeHtml(compact(item.task || "unspecified", 74))}</span></div>
        <div><span class="mini-label">Data Form</span><span>${escapeHtml(compact(item.data_form || "public dataset", 74))}</span></div>
        <div><span class="mini-label">Metrics</span><span>${escapeHtml(compact((item.metrics || [item.metric]).filter(Boolean).join(", "), 74))}</span></div>
      </div>
      <div class="record-actions">
        <button type="button" data-action="add-material">Add Material</button>
        <button type="button" data-action="details">Details</button>
      </div>
    `
  );
}

function renderBaseline(item) {
  return rowShell(
    "baselines",
    item,
    `
      <div>
        <h3>${escapeHtml(item.baseline_name || "Baseline")}</h3>
        <p>${escapeHtml(compact(item.core_idea || item.methodology || item.description || item.principle, 300))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.baseline_type || "published")}</span>
          <span>${Number(item.source_work_ids?.length || 0)} works</span>
          <span>${Number(item.performance?.length || 0)} results</span>
        </div>
      </div>
      <div class="record-actions">
        <button type="button" data-action="add-material">Add Material</button>
        <button type="button" data-action="details">Details</button>
      </div>
    `
  );
}

function renderMyIdea(item) {
  return rowShell(
    "my_ideas",
    item,
    `
      <div>
        ${renderSymbolBadges(item)}
        <h3>${escapeHtml(item.title || "My Idea")}</h3>
        <p>${escapeHtml(compact(item.one_sentence_thesis || item.novelty_claim, 260))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.model_name || "model")}</span>
          <span>${Number(item.selected_refs?.length || 0)} evidence</span>
          <span>${Number(item.derived_principles?.length || 0)} principles</span>
        </div>
      </div>
      <button type="button" data-action="open-my-idea">Details</button>
    `
  );
}

async function openDetail(tabKey, id, version = "") {
  const tab = tabs.find((entry) => entry.key === tabKey);
  const params = new URLSearchParams({ bucket: tab.bucket, id, version, model_mode: getModelMode() });
  const data = await api(`/api/v1/item/detail?${params.toString()}`);
  state.detail = { bucket: tab.bucket, id, item: data.item };
  renderDetailModal(data.item);
  el("detailModal").hidden = false;
}

function renderDetailModal(item) {
  el("detailKind").textContent = state.detail.bucket.replaceAll("_", " ");
  el("detailTitle").textContent = state.detail.bucket === "principles"
    ? principleDisplayTitle(item)
    : item.title || item.name || item.benchmark_name || item.baseline_name || "Details";
  const detailTabKey = tabKeyForBucket(state.detail.bucket);
  el("detailAddMaterialBtn").hidden = !materialTabs().has(detailTabKey);
  const versions = item.versions || [];
  el("detailVersionSelect").innerHTML = versions.length
    ? versions.map((version) => `<option value="${escapeHtml(version.version_id)}" ${version.version_id === item.active_variant?.version_id ? "selected" : ""}>${escapeHtml(version.is_user_edit ? "manual" : `${version.provider}:${version.model_name}`)} · ${escapeHtml(version.extracted_at || "")}</option>`).join("")
    : `<option value="">current</option>`;
  el("detailBody").innerHTML = detailSections(item);
  el("detailEditInput").value = JSON.stringify(item.active_variant?.payload || item, null, 2);
  renderDetailEditFields(item);
  el("detailEditForm").hidden = true;
  typesetMath(el("detailModal"));
}

function renderDetailEditFields(item) {
  const schema = editSchemaFor(state.detail.bucket);
  const payload = item.active_variant?.payload || item;
  el("detailEditFields").innerHTML = schema
    .map((field) => {
      const value = payload[field.key] ?? item[field.key] ?? "";
      const text = field.type === "array" ? (Array.isArray(value) ? value.join("\n") : String(value || "")) : field.type === "json" ? JSON.stringify(value || [], null, 2) : String(value ?? "");
      const rows = field.type === "short" ? 2 : field.type === "array" ? 4 : field.type === "json" ? 7 : 5;
      return `
        <label class="full-field">
          <span>${escapeHtml(field.label)}</span>
          <textarea data-edit-field="${escapeHtml(field.key)}" data-edit-type="${escapeHtml(field.type)}" rows="${rows}">${escapeHtml(text)}</textarea>
        </label>
      `;
    })
    .join("");
}

function editSchemaFor(bucket) {
  if (bucket === "benchmark_records") {
    return [
      { key: "benchmark_name", label: "Benchmark / Dataset Name", type: "short" },
      { key: "description", label: "Introduction", type: "long" },
      { key: "official_url", label: "Official Download / Dataset Page", type: "short" },
      { key: "task", label: "Task", type: "short" },
      { key: "data_form", label: "Data Form", type: "long" },
      { key: "scale", label: "Scale", type: "short" },
      { key: "metrics", label: "Metrics, one per line", type: "array" },
    ];
  }
  if (bucket === "baseline_records") {
    return [
      { key: "baseline_name", label: "Baseline Method Name", type: "short" },
      { key: "core_idea", label: "Core Idea", type: "long" },
      { key: "methodology", label: "Methodology", type: "long" },
      { key: "discussion", label: "Discussion", type: "long" },
      { key: "description", label: "Method Introduction", type: "long" },
      { key: "principle", label: "Method Principle", type: "long" },
      { key: "source_paper_link", label: "Source Paper Link", type: "short" },
      { key: "official_code_url", label: "Official Code Link", type: "short" },
      { key: "benchmarks", label: "Benchmarks, one per line", type: "array" },
      { key: "performance", label: "Performance rows as JSON array", type: "json" },
    ];
  }
  if (bucket === "principles") {
    return [
      { key: "name", label: "Name", type: "short" },
      { key: "argument", label: "Argument", type: "long" },
      { key: "evidence", label: "Evidence", type: "long" },
      { key: "discussion", label: "Discussion", type: "long" },
      { key: "boundary_conditions", label: "Boundary Conditions, one per line", type: "array" },
      { key: "source_paper_link", label: "Source Paper Link", type: "short" },
    ];
  }
  if (bucket === "existed_ideas") {
    return [
      { key: "title", label: "Title", type: "short" },
      { key: "core_idea", label: "Core Idea", type: "long" },
      { key: "mechanism", label: "Mechanism", type: "long" },
      { key: "discussion", label: "Discussion", type: "long" },
      { key: "evidence", label: "Evidence", type: "long" },
      { key: "source_paper_link", label: "Source Paper Link", type: "short" },
    ];
  }
  if (bucket === "takeaway_messages") {
    return [
      { key: "title", label: "Title", type: "short" },
      { key: "main_results", label: "Main Results", type: "long" },
      { key: "condition", label: "Condition", type: "long" },
      { key: "discussion", label: "Discussion", type: "long" },
      { key: "evidence", label: "Evidence", type: "long" },
      { key: "actionable_lesson", label: "Actionable Lesson", type: "long" },
      { key: "source_paper_link", label: "Source Paper Link", type: "short" },
    ];
  }
  if (bucket === "my_ideas") {
    return [
      { key: "title", label: "Title", type: "short" },
      { key: "one_sentence_thesis", label: "Short Thesis", type: "long" },
      { key: "novelty_claim", label: "Novelty Claim", type: "long" },
      { key: "mechanistic_design", label: "Mechanistic Design, one per line", type: "array" },
      { key: "why_it_might_work", label: "Why It Might Work, one per line", type: "array" },
      { key: "validation_protocol", label: "Validation Protocol, one per line", type: "array" },
      { key: "relevant_baselines", label: "Relevant Baselines, one per line", type: "array" },
      { key: "metrics", label: "Metrics, one per line", type: "array" },
      { key: "risks", label: "Risks, one per line", type: "array" },
    ];
  }
  return [
    { key: "title", label: "Title", type: "short" },
    { key: "core_idea", label: "Core Idea", type: "long" },
    { key: "argument", label: "Principle Argument", type: "long" },
    { key: "main_results", label: "Main Results", type: "long" },
    { key: "idea_text", label: "Idea / Message Text", type: "long" },
    { key: "message_text", label: "Takeaway Message", type: "long" },
    { key: "mechanism", label: "Mechanism / Principle", type: "long" },
    { key: "discussion", label: "Discussion", type: "long" },
    { key: "condition", label: "Condition", type: "short" },
    { key: "finding", label: "Finding", type: "long" },
    { key: "actionable_lesson", label: "Actionable Lesson", type: "long" },
    { key: "source_paper_link", label: "Source Paper Link", type: "short" },
  ];
}

function collectDetailEditPayload() {
  const fields = [...document.querySelectorAll("[data-edit-field]")];
  const payload = {};
  fields.forEach((field) => {
    const key = field.dataset.editField;
    const type = field.dataset.editType;
    const raw = field.value.trim();
    if (!raw) {
      payload[key] = type === "array" || type === "json" ? [] : "";
      return;
    }
    if (type === "array") {
      payload[key] = raw.split(/\n+/).map((item) => item.trim()).filter(Boolean);
      return;
    }
    if (type === "json") {
      payload[key] = JSON.parse(raw);
      return;
    }
    payload[key] = raw;
  });
  return payload;
}

function detailSections(item) {
  const bucket = state.detail.bucket;
  const sourceLinks = [
    item.source_paper_link,
    item.paper_link,
    item.official_url,
    item.official_code_url,
    ...(item.source_paper_links || []),
    ...(item.source_urls || []),
  ].filter(isUrl);
  const links = linkList("Links", sourceLinks);
  const sourceWorks = (item.source_work_details || []).map((work) => `<li><a href="${escapeHtml(work.url_or_doi || "#")}" target="_blank" rel="noreferrer">${escapeHtml(work.title || work.work_id)}</a> <span>${escapeHtml(work.venue_or_source || "")} ${escapeHtml(work.year || "")}</span></li>`).join("");
  const version = item.active_variant || {};
  const versionBlock = `
    <section>
      <h3>Version</h3>
      <dl class="key-values">
        <dt>Model</dt><dd>${escapeHtml(version.is_user_edit ? "Manual edit" : `${version.provider || item.provider || "model"} / ${version.model_name || item.model_name || ""}`)}</dd>
        <dt>Extracted</dt><dd>${escapeHtml(version.extracted_at || item.extracted_at || "")}</dd>
        <dt>Confidence</dt><dd>${escapeHtml(version.confidence_score ?? item.confidence_score ?? "")}</dd>
        <dt>Needs Review</dt><dd>${item.needs_review || version.needs_review ? "Yes" : "No"}</dd>
      </dl>
    </section>
  `;
  const shared = `
    ${links}
    ${sourceWorks ? `<section><h3>Source Works</h3><ul>${sourceWorks}</ul></section>` : ""}
    ${detailBlock("Evidence", item.evidence)}
    ${versionBlock}
  `;
  if (bucket === "benchmark_records") {
    return `
      ${detailBlock("Benchmark", item.description || item.benchmark_name)}
      ${detailBlock("Task", item.task)}
      ${detailBlock("Data Form", item.data_form)}
      ${detailBlock("Scale", item.scale)}
      ${detailList("Metrics", item.metrics || item.metric)}
      ${detailBlock("Public Dataset Page", item.official_url ? "Official/download page is linked below." : "Official page not verified yet; use candidate pages for curation.")}
      ${detailList("Candidate Dataset Pages", item.candidate_dataset_pages)}
      ${detailList("Main Baselines", item.baseline_performance)}
      ${shared}
    `;
  }
  if (bucket === "baseline_records") {
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
  if (bucket === "my_ideas") {
    return `
      ${detailBlock("Novelty Claim", item.novelty_claim)}
      ${detailList("Mechanistic Design", item.mechanistic_design)}
      ${detailList("Why It Might Work", item.why_it_might_work)}
      ${detailList("Validation Protocol", item.validation_protocol)}
      ${detailList("Relevant Baselines", item.relevant_baselines)}
      ${detailList("Metrics", item.metrics)}
      ${detailList("Risks", item.risks)}
      ${detailBlock("User Note", item.user_note)}
      ${shared}
    `;
  }
  if (bucket === "principles") {
    return `
      ${detailBlock("Argument", item.argument || item.abstract_signature)}
      ${detailBlock("Discussion", item.discussion)}
      ${detailList("Boundary Conditions", item.boundary_conditions)}
      ${shared}
    `;
  }
  if (bucket === "existed_ideas") {
    return `
      ${detailBlock("Core Idea", item.core_idea || item.idea_text || item.summary)}
      ${detailBlock("Mechanism", item.mechanism)}
      ${detailBlock("Discussion", item.discussion)}
      ${shared}
    `;
  }
  if (bucket === "takeaway_messages") {
    return `
      ${detailBlock("Main Results", item.main_results || item.message_text)}
      ${detailBlock("Condition", item.condition)}
      ${detailBlock("Discussion", item.discussion)}
      ${detailBlock("Actionable Lesson", item.actionable_lesson)}
      ${shared}
    `;
  }
  return `
    ${detailBlock("Core Idea", item.core_idea || item.idea_text || item.description || item.summary)}
    ${detailBlock("Argument", item.argument || item.abstract_signature)}
    ${detailBlock("Main Results", item.main_results || item.message_text)}
    ${detailBlock("Mechanism / Principle", item.mechanism || item.principle)}
    ${detailBlock("Condition", item.condition)}
    ${detailBlock("Finding", item.finding)}
    ${detailBlock("Actionable Lesson", item.actionable_lesson)}
    ${detailBlock("Discussion", item.discussion)}
    ${shared}
  `;
}

function detailBlock(title, content) {
  if (!content) return "";
  return `<section><h3>${escapeHtml(title)}</h3><p>${escapeHtml(Array.isArray(content) ? content.join("; ") : content)}</p></section>`;
}

function detailList(title, content) {
  if (!Array.isArray(content) || !content.length) return "";
  return `<section><h3>${escapeHtml(title)}</h3><ul>${content.slice(0, 24).map((item) => `<li>${formatValue(item)}</li>`).join("")}</ul></section>`;
}

function formatValue(value) {
  if (value == null || value === "") return "";
  if (typeof value !== "object") return escapeHtml(value);
  if (Array.isArray(value)) return value.map(formatValue).join("; ");
  return `<dl class="inline-object">${Object.entries(value)
    .filter(([, val]) => val !== "" && val != null && !(Array.isArray(val) && !val.length))
    .map(([key, val]) => `<dt>${escapeHtml(humanizeKey(key))}</dt><dd>${formatValue(val)}</dd>`)
    .join("")}</dl>`;
}

function humanizeKey(key) {
  return String(key || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function linkList(title, urls) {
  const unique = [...new Set((urls || []).filter(isUrl))];
  if (!unique.length) return "";
  return `<section><h3>${escapeHtml(title)}</h3><ul>${unique.map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></li>`).join("")}</ul></section>`;
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

function openRecordTab(tabKey, id) {
  const tab = tabs.find((entry) => entry.key === tabKey);
  if (!tab || !id) return;
  window.open(`/item.html?bucket=${encodeURIComponent(tab.bucket)}&id=${encodeURIComponent(id)}&field_id=${encodeURIComponent(state.activeProjectId)}&model_mode=${encodeURIComponent(getModelMode())}`, "_blank");
}

async function startResearch() {
  const goal = getGoalText();
  if (!goal) {
    alert("Please enter a research goal or idea draft first.");
    return;
  }
  const targetWorks = getTargetWorks();
  setBusy(true, "Starting research...");
  try {
    await post("/api/v1/project/update", {
      field_id: state.activeProjectId,
      goal_text: goal,
      query: goal,
      settings: { model_mode: getModelMode(), language: "en", source_mode: "online+local", paper_count: targetWorks, target_works: targetWorks, max_works: targetWorks },
    }).catch(() => {});
    const result = await post("/api/v1/research/start", {
      field_id: state.activeProjectId,
      goal_text: goal,
      model_mode: getModelMode(),
      target_works: targetWorks,
    });
    state.researchRunId = result.run_id;
    state.researchRunProjectId = state.activeProjectId;
    state.warningRunId = "";
    state.researchCountsSignature = "";
    setResearchRunning(true);
    pollResearch();
  } catch (error) {
    alert(error.message || "Research could not be started.");
    setResearchRunning(false);
  } finally {
    setBusy(false);
    if (state.researchActive) setResearchRunning(true);
  }
}

async function pollResearch() {
  if (!state.researchRunId) return;
  if (state.researchRunProjectId && state.researchRunProjectId !== state.activeProjectId) return;
  clearTimeout(state.researchTimer);
  try {
    const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(state.researchRunId)}`);
    const run = data.run || {};
    if (run.field_id && run.field_id !== state.activeProjectId) {
      state.researchRunId = "";
      state.researchRunProjectId = "";
      setResearchRunning(false);
      clearTransientStatus("Ready");
      return;
    }
    renderResearchStatus(run);
    const signature = JSON.stringify(run.counts || {});
    if (run.status === "running" && signature && signature !== state.researchCountsSignature) {
      state.researchCountsSignature = signature;
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true, silent: true });
    }
    if ((run.warnings || []).length && state.warningRunId !== run.run_id) {
      state.warningRunId = run.run_id;
      alert((run.warnings || []).join("\n\n"));
    }
    if (run.status === "complete") {
      setResearchRunning(false);
      state.researchRunId = "";
      state.researchRunProjectId = "";
      await loadProjects(state.activeProjectId);
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true, silent: true });
      return;
    }
    if (run.status === "cancelled") {
      setResearchRunning(false);
      state.researchRunId = "";
      state.researchRunProjectId = "";
      await loadSummary();
      return;
    }
    if (run.status === "error") {
      setResearchRunning(false);
      state.researchRunId = "";
      state.researchRunProjectId = "";
      alert(run.message || "Research failed.");
      return;
    }
    if (run.status === "partial_error") {
      setResearchRunning(false);
      state.researchRunId = "";
      state.researchRunProjectId = "";
      await loadProjects(state.activeProjectId);
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true, silent: true });
      alert(run.message || "Research stopped after preserving completed records.");
      return;
    }
  } catch (error) {
    el("researchStatus").textContent = error.message;
    alert(error.message || "Research status could not be loaded.");
  }
  state.researchTimer = setTimeout(pollResearch, 1600);
}

async function extractWorkFromRow(workId, force = false) {
  if (!workId) return;
  const activeRun = state.workExtractRuns?.[workId];
  if (activeRun && ["queued", "running"].includes(activeRun.status || "")) {
    if (!confirm("Stop this work extraction? Completed records will be kept.")) return;
    await cancelRun(activeRun.run_id, "work extraction");
    delete state.workExtractRuns[workId];
    renderTabContent();
    showToast("Work extraction stopped. Completed records were kept.", "info");
    return;
  }
  showToast(force ? "Updating this work extraction..." : "Checking this work extraction state...", "info");
  const result = await post("/api/v1/work/extract/start", {
    field_id: state.activeProjectId,
    work_id: workId,
    goal_text: getGoalText(),
    model_mode: getModelMode(),
    force,
  });
  if (result.already_extracted && !force) {
    const counts = result.counts || {};
    const total = counts.total || 0;
    if (!confirm(`This work already has ${total} extracted record${total === 1 ? "" : "s"}. Update its extraction with the selected LLM?`)) return;
    await extractWorkFromRow(workId, true);
    return;
  }
  state.workExtractRuns = {
    ...(state.workExtractRuns || {}),
    [workId]: {
      run_id: result.run_id,
      status: result.status || (result.queued ? "queued" : "running"),
      stage: result.queued ? "queued" : "work_extraction",
      queue_position: result.queue_position || 0,
      message: result.queued ? "Work extraction queued." : "Extracting this work with the selected LLM.",
    },
  };
  state.workExtractRunId = result.run_id;
  renderTabContent();
  showToast(result.queued ? "Work extraction queued." : "Work extraction started. Completed partial records will be kept if you stop it.", "info");
  renderResearchStatus({
    run_id: result.run_id,
    status: result.queued ? "queued" : "running",
    stage: result.queued ? "queued" : "work_extraction",
    message: result.queued ? "Work extraction queued." : "Extracting this work with the selected LLM.",
    counts: { work_id: workId },
  });
  pollWorkExtraction();
}

async function pollWorkExtraction() {
  const activeEntries = Object.entries(state.workExtractRuns || {}).filter(([, run]) => ["queued", "running"].includes(run?.status || ""));
  if (!activeEntries.length) {
    state.workExtractRunId = "";
    clearTransientStatus("Ready");
    return;
  }
  clearTimeout(state.workExtractTimer);
  try {
    let terminalChanged = false;
    const statuses = await Promise.all(
      activeEntries.map(async ([workId, current]) => {
        const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(current.run_id)}`);
        return [workId, data.run || {}];
      })
    );
    for (const [workId, run] of statuses) {
      if (["queued", "running"].includes(run.status || "")) {
        state.workExtractRuns[workId] = {
          ...(state.workExtractRuns[workId] || {}),
          run_id: run.run_id,
          status: run.status,
          stage: run.stage,
          message: run.message,
          queue_position: run.queue_position || 0,
        };
        renderResearchStatus(run);
        continue;
      }
      terminalChanged = true;
      delete state.workExtractRuns[workId];
      if (run.status === "complete") showToast("Work extraction complete.");
      if (run.status === "cancelled") showToast("Work extraction stopped. Completed records were kept.", "info");
      if (run.status === "error") alert(run.message || "Work extraction failed.");
    }
    state.workExtractRunId = Object.values(state.workExtractRuns || {})[0]?.run_id || "";
    if (terminalChanged) {
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true, silent: true });
      if (!state.workExtractRunId) clearTransientStatus("Ready");
    } else {
      renderTabContent({ stable: true });
    }
  } catch (error) {
    clearTransientStatus("Ready");
    alert(error.message || "Work extraction status could not be loaded.");
    return;
  }
  state.workExtractTimer = setTimeout(pollWorkExtraction, 1600);
}

function openProjectModal(mode, project = null) {
  state.projectModal = { mode, fieldId: project?.field_id || "" };
  el("projectModalTitle").textContent = mode === "edit" ? "Edit Project" : "New Project";
  el("saveProjectModalBtn").textContent = mode === "edit" ? "Save Project" : "Create Project";
  el("skipProjectDescriptionBtn").hidden = mode === "edit";
  el("projectNameInput").value = project?.name || "";
  el("projectDescriptionInput").value = project?.description || "";
  el("projectModal").hidden = false;
  el("projectNameInput").focus();
}

function closeProjectModal() {
  el("projectModal").hidden = true;
  el("projectForm").reset();
  state.projectModal = { mode: "create", fieldId: "" };
}

async function submitProject(event) {
  event.preventDefault();
  const name = el("projectNameInput").value.trim();
  const description = el("projectDescriptionInput").value.trim();
  if (!name) return;
  if (state.projectModal.mode === "edit") {
    const fieldId = state.projectModal.fieldId;
    await post("/api/v1/project/update", { field_id: fieldId, name, description });
    closeProjectModal();
    await loadProjects(fieldId);
    await selectProject(fieldId);
    return;
  }
  const project = await post("/api/v1/project/create", { name, description, settings: { model_mode: getModelMode() } });
  closeProjectModal();
  await loadProjects(project.field_id);
  await selectProject(project.field_id);
}

async function deleteProject(fieldId) {
  if (!fieldId || fieldId === "default") return;
  const project = state.projects.find((item) => item.field_id === fieldId);
  state.deleteProject = { fieldId };
  el("deleteProjectTitle").textContent = `Delete ${project?.name || "Project"}`;
  el("deleteProjectMessage").textContent = "This removes the project from the sidebar immediately. Local works, concepts, ideas, benchmarks, and baselines are kept unless you choose the cleanup option below.";
  el("deleteProjectLocalDataInput").checked = false;
  el("deleteProjectModal").hidden = false;
}

function closeDeleteProjectModal() {
  el("deleteProjectModal").hidden = true;
  el("deleteProjectLocalDataInput").checked = false;
  state.deleteProject = { fieldId: "" };
}

async function confirmDeleteProject() {
  const fieldId = state.deleteProject.fieldId;
  if (!fieldId || fieldId === "default") return;
  const deleteLocalData = el("deleteProjectLocalDataInput").checked;
  const remaining = state.projects.filter((item) => item.field_id !== fieldId);
  state.projects = remaining;
  if (state.activeProjectId === fieldId) {
    state.activeProject = remaining.find((item) => item.field_id === "default") || remaining[0] || null;
    state.activeProjectId = state.activeProject?.field_id || "default";
    state.items = [];
    state.offset = 0;
    rememberWorkspaceState();
    renderProjectHeader();
    renderTabContent();
  }
  renderProjects();
  closeDeleteProjectModal();
  clearTimeout(state.researchTimer);
  state.researchRunId = "";
  setResearchRunning(false);
  await post("/api/v1/project/delete", { field_id: fieldId, delete_local_data: deleteLocalData });
  const nextId = state.activeProjectId === fieldId ? "default" : state.activeProjectId;
  await loadProjects(nextId);
  await selectProject(nextId);
}

async function editApiKeys() {
  const current = await api("/api/settings");
  el("apiKeysStatus").textContent = `SiliconFlow: ${current.siliconflow?.configured ? current.siliconflow.masked || "configured" : "not configured"} / OpenAI: ${current.openai?.configured ? current.openai.masked || "configured" : "not configured"}. Leave a field blank to keep its current value.`;
  el("siliconflowKeyInput").value = "";
  el("openaiKeyInput").value = "";
  el("apiKeysModal").hidden = false;
}

async function submitApiKeys(event) {
  event.preventDefault();
  const payload = {};
  const silicon = el("siliconflowKeyInput").value.trim();
  const openai = el("openaiKeyInput").value.trim();
  if (silicon) payload.siliconflow_api_key = silicon;
  if (openai) payload.openai_api_key = openai;
  if (Object.keys(payload).length) await post("/api/settings", payload);
  el("apiKeysModal").hidden = true;
  el("apiKeysForm").reset();
}

async function openAssembler() {
  const keepSelected = state.assembler.projectId === state.activeProjectId ? state.assembler.selected || [] : [];
  state.assembler = { sourceType: "existed_ideas", items: [], selected: keepSelected, projectId: state.activeProjectId };
  el("assemblerSourceType").value = "existed_ideas";
  el("assemblerModelMode").value = getModelMode();
  el("assemblerUserNote").value = keepSelected.length ? el("assemblerUserNote").value || "" : "";
  el("assemblerDetail").innerHTML = "";
  el("assemblerModal").hidden = false;
  renderAssemblyContext();
  renderSelectedEvidence();
  await loadAssemblerSources();
}

async function loadAssemblerSources() {
  const source = el("assemblerSourceType").value;
  const params = new URLSearchParams({
    field_id: state.activeProjectId,
    source,
    query: el("assemblerSearchInput").value.trim(),
    model_mode: getAssemblerModelMode(),
    limit: "20",
  });
  const data = await api(`/api/v2/assembler/sources?${params.toString()}`);
  state.assembler.sourceType = source;
  state.assembler.items = data.items || [];
  renderAssemblerSources();
}

function renderAssemblerSources() {
  el("assemblerSources").innerHTML = state.assembler.items.length
    ? state.assembler.items
        .map((item) => {
          const id = recordIdForEvidence(state.assembler.sourceType, item);
          const label = evidenceLabel(item);
          return `
            <article class="evidence-card" data-bucket="${escapeHtml(state.assembler.sourceType)}" data-id="${escapeHtml(id)}">
              <strong>${escapeHtml(label)}</strong>
              <p>${escapeHtml(compact(item.core_idea || item.argument || item.main_results || item.idea_text || item.message_text || item.abstract_signature || item.abstract || item.summary || item.methodology || item.description || item.principle, 145))}</p>
              <div class="evidence-actions">
                <button type="button" data-action="add-evidence">Add</button>
                <button type="button" data-action="view-evidence">View</button>
              </div>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-state">No evidence found. Run Research first.</p>`;
}

function addEvidence(bucket, id) {
  if (!id) return;
  if (state.assembler.projectId !== state.activeProjectId) {
    state.assembler = { sourceType: state.assembler.sourceType || "existed_ideas", items: state.assembler.items || [], selected: [], projectId: state.activeProjectId };
  }
  if (state.assembler.selected.some((item) => item.bucket === bucket && item.id === id)) {
    showToast("That material is already selected.", "info");
    return;
  }
  const item = state.assembler.items.find((entry) => recordIdForEvidence(bucket, entry) === id) || null;
  state.assembler.selected.push({ bucket, id, item });
  renderSelectedEvidence();
  if (item) renderAssemblerDetail(item);
  showToast("Material added to Generate Idea.");
}

function unselectVisibleEvidence() {
  const source = state.assembler.sourceType;
  const visibleIds = new Set(state.assembler.items.map((item) => recordIdForEvidence(source, item)).filter(Boolean));
  state.assembler.selected = state.assembler.selected.filter((ref) => !(ref.bucket === source && visibleIds.has(ref.id)));
  renderSelectedEvidence();
}

function clearSelectedEvidence() {
  state.assembler.selected = [];
  state.assembler.projectId = state.activeProjectId;
  renderSelectedEvidence();
  el("assemblerDetail").innerHTML = "";
}

function addMaterialRef(tabKey, id, item = null) {
  if (!materialTabs().has(tabKey) || !id) return false;
  if (state.assembler.projectId !== state.activeProjectId) {
    state.assembler = { sourceType: state.assembler.sourceType || "existed_ideas", items: [], selected: [], projectId: state.activeProjectId };
  }
  if (state.assembler.selected.some((ref) => ref.bucket === tabKey && ref.id === id)) {
    showToast("This material is already queued for Generate Idea.", "info");
    return false;
  }
  state.assembler.selected.push({ bucket: tabKey, id, item });
  showToast(`Added 1 ${tabLabel(tabKey)} item to Generate Idea.`);
  if (!el("assemblerModal").hidden) {
    renderSelectedEvidence();
    if (item) renderAssemblerDetail(item);
  }
  return true;
}

function addMaterialFromRow(tabKey, id) {
  const item = state.items.find((entry) => idFor(tabKey, entry) === id) || null;
  addMaterialRef(tabKey, id, item);
}

function addMaterialFromDetail() {
  const tabKey = tabKeyForBucket(state.detail.bucket);
  if (!materialTabs().has(tabKey)) {
    showToast("This record type cannot be added as generation material.", "info");
    return;
  }
  const item = state.detail.item || null;
  const id = idFor(tabKey, item || {}) || state.detail.id;
  addMaterialRef(tabKey, id, item);
}

function renderSelectedEvidence() {
  el("selectedEvidence").innerHTML = state.assembler.selected.length
    ? state.assembler.selected
        .map((ref, index) => `<article class="selected-card" data-selected-index="${index}"><span>${escapeHtml(ref.bucket.replaceAll("_", " "))}</span><strong>${escapeHtml(evidenceLabel(ref.item) || ref.id)}</strong><div class="selected-actions"><button type="button" data-action="view-selected" data-index="${index}">View</button><button type="button" data-action="remove-selected" data-index="${index}">Remove</button></div></article>`)
        .join("")
    : `<p class="muted">No evidence selected yet.</p>`;
  renderAssemblyContext();
}

function renderAssemblerDetail(item) {
  const links = linkList("Links", [item.source_paper_link, item.paper_link, item.official_url, item.url_or_doi, ...(item.source_paper_links || []), ...(item.source_urls || [])]);
  el("assemblerDetail").innerHTML = `
    <h3>${escapeHtml(evidenceLabel(item) || "Evidence")}</h3>
    ${detailBlock("Summary", item.core_idea || item.argument || item.main_results || item.idea_text || item.message_text || item.abstract_signature || item.abstract || item.summary || item.description || "")}
    ${detailBlock("Mechanism", item.mechanism || item.methodology || item.principle)}
    ${detailBlock("Discussion", item.discussion)}
    ${detailBlock("Task", item.task)}
    ${detailList("Metrics", item.metrics)}
    ${performanceTable(item.performance)}
    ${detailBlock("Condition", item.condition)}
    ${detailBlock("Finding", item.finding)}
    ${detailBlock("Actionable Lesson", item.actionable_lesson)}
    ${links}
  `;
  typesetMath(el("assemblerDetail"));
}

function renderAssemblyContext() {
  const modeLabel = getAssemblerGenerationMode() === "symbolic" ? "Principia Calculus" : "Standard";
  el("assemblyContext").innerHTML = `<dl><dt>Project</dt><dd>${escapeHtml(state.activeProject?.name || "")}</dd><dt>Goal</dt><dd>${escapeHtml(compact(getGoalText(), 180) || "No goal saved yet.")}</dd><dt>Mode</dt><dd>${escapeHtml(modeLabel)}</dd><dt>Selected</dt><dd>${state.assembler.selected.length}</dd><dt>User Note</dt><dd>${escapeHtml(compact(el("assemblerUserNote")?.value || "", 160) || "No note yet.")}</dd></dl>`;
}

async function generateMyIdea() {
  const userNote = el("assemblerUserNote").value.trim();
  if (!state.assembler.selected.length && !userNote) {
    alert("Select evidence or add your own idea note first.");
    return;
  }
  setBusy(true, "Generating idea...");
  el("cancelIdeaGenerationBtn").hidden = false;
  el("assembleIdeaBtn").disabled = true;
  el("assemblerDetail").innerHTML = renderIdeaGenerationStatus({
    status: "queued",
    stage: "collecting_evidence",
    message: "Starting generation run and preparing selected evidence.",
    type: getAssemblerGenerationMode() === "symbolic" ? "v1_symbolic_idea_generate" : "v1_standard_idea_generate",
    counts: { selected_refs: state.assembler.selected.length, user_note_chars: userNote.length },
  });
  try {
    const mode = getAssemblerGenerationMode();
    const endpoint = mode === "symbolic" ? "/api/v1/ideas/symbolic-generate/start" : "/api/v1/ideas/standard-generate/start";
    const result = await post(endpoint, {
      field_id: state.activeProjectId,
      goal_text: getGoalText(),
      selected_refs: state.assembler.selected.map(({ bucket, id }) => ({ bucket, id })),
      user_note: userNote,
      model_mode: getAssemblerModelMode(),
    });
    state.ideaRunId = result.run_id;
    pollIdeaGeneration();
  } catch (error) {
    el("cancelIdeaGenerationBtn").hidden = true;
    el("assembleIdeaBtn").disabled = false;
    setBusy(false);
    clearTransientStatus("Ready");
    alert(error.message || "The selected LLM could not be called, so no idea was generated.");
  }
}

async function pollIdeaGeneration() {
  if (!state.ideaRunId) return;
  clearTimeout(state.ideaTimer);
  try {
    const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(state.ideaRunId)}`);
    const run = data.run || {};
    el("assemblerDetail").innerHTML = renderIdeaGenerationStatus(run);
    if (run.status === "complete") {
      const ideaId = run.result_idea_id;
      const version = run.result_version_id || "";
      state.ideaRunId = "";
      state.assembler.selected = [];
      state.assembler.projectId = state.activeProjectId;
      el("cancelIdeaGenerationBtn").hidden = true;
      el("assembleIdeaBtn").disabled = false;
      setBusy(false);
      clearTransientStatus("Idea generated.");
      el("assemblerModal").hidden = true;
      state.activeTab = "my_ideas";
      rememberWorkspaceState();
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true });
      const versionParam = version ? `&version=${encodeURIComponent(version)}` : "";
      window.open(`/idea.html?field_id=${encodeURIComponent(state.activeProjectId)}&idea_id=${encodeURIComponent(ideaId)}&model_mode=${encodeURIComponent(getAssemblerModelMode())}${versionParam}`, "_blank");
      return;
    }
    if (run.status === "cancelled") {
      state.ideaRunId = "";
      el("cancelIdeaGenerationBtn").hidden = true;
      el("assembleIdeaBtn").disabled = false;
      setBusy(false);
      clearTransientStatus("Ready");
      el("assemblerDetail").innerHTML = `<p class="muted">Idea generation was cancelled.</p>`;
      return;
    }
    if (run.status === "error") {
      state.ideaRunId = "";
      el("cancelIdeaGenerationBtn").hidden = true;
      el("assembleIdeaBtn").disabled = false;
      setBusy(false);
      clearTransientStatus("Ready");
      alert(run.message || "The selected LLM could not generate this idea.");
      return;
    }
  } catch (error) {
    state.ideaRunId = "";
    el("cancelIdeaGenerationBtn").hidden = true;
    el("assembleIdeaBtn").disabled = false;
    setBusy(false);
    clearTransientStatus("Ready");
    alert(error.message || "Idea generation status could not be loaded.");
  }
  state.ideaTimer = setTimeout(pollIdeaGeneration, 1200);
}

async function pollDetailRefresh() {
  if (!state.refreshRunId) return;
  clearTimeout(state.refreshTimer);
  try {
    const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(state.refreshRunId)}`);
    const run = data.run || {};
    el("researchStatus").innerHTML = `
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml((run.stage || run.status || "refreshing").replaceAll("_", " "))}</strong>
        <span>${escapeHtml(run.message || "")}</span>
      </div>
    `;
    if (run.status === "complete") {
      state.refreshRunId = "";
      el("cancelDetailRefreshBtn").hidden = true;
      setBusy(false);
      await openDetail(tabs.find((tab) => tab.bucket === state.detail.bucket)?.key || "existed_ideas", state.detail.id, run.result_version_id || "");
      await loadTab({ reset: true, preserveScroll: true });
      return;
    }
    if (run.status === "cancelled") {
      state.refreshRunId = "";
      el("cancelDetailRefreshBtn").hidden = true;
      setBusy(false);
      return;
    }
    if (run.status === "error") {
      state.refreshRunId = "";
      el("cancelDetailRefreshBtn").hidden = true;
      setBusy(false);
      alert(run.message || "Item refresh failed.");
      return;
    }
  } catch (error) {
    state.refreshRunId = "";
    el("cancelDetailRefreshBtn").hidden = true;
    setBusy(false);
    alert(error.message || "Item refresh status could not be loaded.");
    return;
  }
  state.refreshTimer = setTimeout(pollDetailRefresh, 1200);
}

function bindEvents() {
  ["projectModal", "deleteProjectModal", "clearRecordsModal", "detailModal", "assemblerModal", "apiKeysModal"].forEach((modalId) => {
    el(modalId).addEventListener("click", (event) => {
      if (event.target === el(modalId)) el(modalId).hidden = true;
    });
  });
  el("newProjectBtn").addEventListener("click", () => openProjectModal("create"));
  el("projectForm").addEventListener("submit", submitProject);
  el("cancelProjectModalBtn").addEventListener("click", closeProjectModal);
  el("cancelDeleteProjectBtn").addEventListener("click", closeDeleteProjectModal);
  el("confirmDeleteProjectBtn").addEventListener("click", () => {
    confirmDeleteProject().catch((error) => {
      alert(error.message || "Unable to delete this project.");
      loadProjects(state.activeProjectId).then(() => loadTab({ reset: true, preserveScroll: true })).catch(() => {});
    });
  });
  el("skipProjectDescriptionBtn").addEventListener("click", () => {
    el("projectDescriptionInput").value = "";
    el("projectForm").requestSubmit();
  });
  el("projectList").addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action]");
    if (!action) return;
    const fieldId = action.dataset.fieldId;
    if (action.dataset.action === "select-project") await selectProject(fieldId);
    if (action.dataset.action === "edit-project") openProjectModal("edit", state.projects.find((project) => project.field_id === fieldId));
    if (action.dataset.action === "delete-project") await deleteProject(fieldId);
  });
  el("researchBtn").addEventListener("click", startResearch);
  el("cancelResearchBtn").addEventListener("click", async () => {
    try {
      if (state.researchRunId) {
        await cancelRun(state.researchRunId, "research");
        el("researchStatus").textContent = "Research stopped. Completed records were kept.";
        return;
      }
      const activeWorkRuns = Object.values(state.workExtractRuns || {}).filter((run) => ["queued", "running"].includes(run?.status || ""));
      if (!activeWorkRuns.length) return;
      await Promise.all(activeWorkRuns.map((run) => cancelRun(run.run_id, "work extraction")));
      clearTimeout(state.workExtractTimer);
      state.workExtractRuns = {};
      state.workExtractRunId = "";
      renderTabContent();
      el("researchStatus").textContent = "Work extraction queue stopped. Completed records were kept.";
    } catch (error) {
      alert(error.message || "Unable to stop this operation.");
    }
  });
  el("generateIdeaBtn").addEventListener("click", openAssembler);
  el("refreshAtlasBtn").addEventListener("click", () => loadResearchAtlas({ counts: state.counts }));
  el("cleanupRecordsBtn").addEventListener("click", async () => {
    try {
      const result = await post("/api/v1/local-records/cleanup", {});
      const repaired = result.repaired || {};
      showToast(`Repaired records: ideas ${repaired.existed_ideas || 0}, baselines ${repaired.baseline_records || 0}, merged ${repaired.merged_duplicates || 0}.`);
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true });
    } catch (error) {
      alert(error.message || "Unable to repair local records.");
    }
  });
  el("clearRecordsBtn").addEventListener("click", () => {
    el("clearRecordsModal").hidden = false;
  });
  el("cancelClearRecordsBtn").addEventListener("click", () => {
    el("clearRecordsModal").hidden = true;
  });
  el("confirmClearRecordsBtn").addEventListener("click", async () => {
    try {
      await post("/api/v1/local-records/clear", {});
      el("clearRecordsModal").hidden = true;
      showToast("Local records cleared.");
      state.assembler.selected = [];
      await loadProjects(state.activeProjectId);
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true });
    } catch (error) {
      alert(error.message || "Unable to clear local records.");
    }
  });
  el("apiKeysBtn").addEventListener("click", editApiKeys);
  el("apiKeysForm").addEventListener("submit", submitApiKeys);
  el("cancelApiKeysBtn").addEventListener("click", () => (el("apiKeysModal").hidden = true));
  el("clearApiKeysFormBtn").addEventListener("click", () => {
    el("siliconflowKeyInput").value = "";
    el("openaiKeyInput").value = "";
  });
  el("tabRow").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    state.activeTab = button.dataset.tab;
    rememberWorkspaceState();
    await loadTab({ reset: true, preserveScroll: true });
  });
  el("tabContent").addEventListener("click", async (event) => {
    const row = event.target.closest("[data-id]");
    if (!row) return;
    if (event.target.closest("[data-action='open-my-idea']")) {
      window.open(`/idea.html?field_id=${encodeURIComponent(state.activeProjectId)}&idea_id=${encodeURIComponent(row.dataset.id)}&model_mode=${encodeURIComponent(getModelMode())}`, "_blank");
      return;
    }
    if (event.target.closest("[data-action='details']")) {
      openRecordTab(row.dataset.tab, row.dataset.id);
      return;
    }
    if (event.target.closest("[data-action='add-material']")) {
      addMaterialFromRow(row.dataset.tab, row.dataset.id);
      return;
    }
    const extractButton = event.target.closest("[data-action='extract-work']");
    if (extractButton) {
      if (!["work-extract-running", "work-extract-queued"].some((klass) => extractButton.classList.contains(klass))) {
        extractButton.disabled = true;
        extractButton.textContent = "Checking...";
      }
      extractWorkFromRow(row.dataset.id)
        .catch((error) => alert(error.message || "Unable to extract this work."))
        .finally(() => {
          extractButton.disabled = false;
          loadTab({ reset: true, preserveScroll: true, silent: true });
        });
      return;
    }
    await openDetail(row.dataset.tab, row.dataset.id);
  });
  el("reloadTabBtn").addEventListener("click", () => loadTab({ reset: true, preserveScroll: true }));
  el("moreBtn").addEventListener("click", () => loadTab({ reset: false }));
  el("tabSearchInput").addEventListener("input", debounce(() => loadTab({ reset: true, preserveScroll: true }), 250));
  el("tabSortInput").addEventListener("change", () => loadTab({ reset: true, preserveScroll: true }));
  el("modelModeInput").addEventListener("change", () => loadTab({ reset: true, preserveScroll: true }));
  el("closeDetailBtn").addEventListener("click", () => (el("detailModal").hidden = true));
  el("detailVersionSelect").addEventListener("change", () => openDetail(tabs.find((tab) => tab.bucket === state.detail.bucket)?.key || "existed_ideas", state.detail.id, el("detailVersionSelect").value));
  el("editDetailBtn").addEventListener("click", () => {
    el("detailEditForm").hidden = false;
    el("detailEditForm").scrollIntoView({ block: "nearest" });
  });
  el("cancelDetailEditBtn").addEventListener("click", (event) => {
    event.preventDefault();
    el("detailEditForm").hidden = true;
    el("detailBody").scrollIntoView({ block: "nearest" });
  });
  el("detailEditForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const fieldPayload = collectDetailEditPayload();
      let advancedPayload = {};
      const advanced = el("detailEditInput").value.trim();
      if (advanced) advancedPayload = JSON.parse(advanced);
      const result = await post("/api/v1/item/update", { bucket: state.detail.bucket, id: state.detail.id, payload: { ...advancedPayload, ...fieldPayload } });
      state.detail.item = result.item;
      renderDetailModal(result.item);
      await loadSummary();
      await loadTab({ reset: true, preserveScroll: true });
    } catch (error) {
      alert(`Unable to save this edit: ${error.message}`);
    }
  });
  el("refreshDetailBtn").addEventListener("click", async () => {
    try {
      setBusy(true, "Refreshing item with selected LLM...");
      el("cancelDetailRefreshBtn").hidden = false;
      const result = await post("/api/v1/item/refresh/start", {
        field_id: state.activeProjectId,
        bucket: state.detail.bucket,
        id: state.detail.id,
        model_mode: getModelMode(),
      });
      state.refreshRunId = result.run_id;
      pollDetailRefresh();
    } catch (error) {
      el("cancelDetailRefreshBtn").hidden = true;
      setBusy(false);
      alert(error.message || "Unable to refresh this item.");
    }
  });
  el("cancelDetailRefreshBtn").addEventListener("click", async () => {
    try {
      await cancelRun(state.refreshRunId, "refresh");
      alert("Item refresh cancelled.");
    } catch (error) {
      alert(error.message || "Unable to cancel refresh.");
    }
  });
  el("openDetailTabBtn").addEventListener("click", () => {
    if (state.detail.bucket === "my_ideas") {
      window.open(`/idea.html?field_id=${encodeURIComponent(state.activeProjectId)}&idea_id=${encodeURIComponent(state.detail.id)}&model_mode=${encodeURIComponent(getModelMode())}`, "_blank");
      return;
    }
    window.open(`/item.html?bucket=${encodeURIComponent(state.detail.bucket)}&id=${encodeURIComponent(state.detail.id)}&field_id=${encodeURIComponent(state.activeProjectId)}&model_mode=${encodeURIComponent(getModelMode())}`, "_blank");
  });
  el("detailAddMaterialBtn").addEventListener("click", addMaterialFromDetail);
  el("closeAssemblerBtn").addEventListener("click", () => (el("assemblerModal").hidden = true));
  el("assemblerSourceType").addEventListener("change", loadAssemblerSources);
  el("assemblerModelMode").addEventListener("change", loadAssemblerSources);
  el("assemblerGenerationMode").addEventListener("change", renderAssemblyContext);
  el("assemblerSearchInput").addEventListener("input", debounce(loadAssemblerSources, 250));
  el("assemblerUserNote").addEventListener("input", renderAssemblyContext);
  el("selectAllEvidenceBtn").addEventListener("click", () => {
    state.assembler.items.forEach((item) => addEvidence(state.assembler.sourceType, recordIdForEvidence(state.assembler.sourceType, item)));
  });
  el("unselectAllEvidenceBtn").addEventListener("click", unselectVisibleEvidence);
  el("clearSelectedEvidenceBtn").addEventListener("click", clearSelectedEvidence);
  el("assemblerSources").addEventListener("click", (event) => {
    const card = event.target.closest(".evidence-card");
    if (!card) return;
    const item = state.assembler.items.find((entry) => recordIdForEvidence(card.dataset.bucket, entry) === card.dataset.id);
    if (event.target.closest("[data-action='add-evidence']")) {
      addEvidence(card.dataset.bucket, card.dataset.id);
      return;
    }
    if (item) renderAssemblerDetail(item);
  });
  el("selectedEvidence").addEventListener("click", (event) => {
    const selectedCard = event.target.closest("[data-selected-index]");
    const index = Number(event.target.closest("[data-index]")?.dataset.index ?? selectedCard?.dataset.selectedIndex);
    if (!Number.isFinite(index)) return;
    if (event.target.closest("[data-action='remove-selected']")) {
      state.assembler.selected.splice(index, 1);
      renderSelectedEvidence();
      return;
    }
    renderAssemblerDetail(state.assembler.selected[index]?.item || {});
  });
  el("assembleIdeaBtn").addEventListener("click", generateMyIdea);
  el("cancelIdeaGenerationBtn").addEventListener("click", async () => {
    try {
      await cancelRun(state.ideaRunId, "idea");
      el("assemblerDetail").innerHTML = `<p class="muted">Idea generation was cancelled.</p>`;
    } catch (error) {
      alert(error.message || "Unable to cancel idea generation.");
    }
  });
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

async function init() {
  const savedTab = localStorage.getItem("principia.activeTab");
  if (tabs.some((tab) => tab.key === savedTab)) state.activeTab = savedTab;
  bindEvents();
  await loadProjects(localStorage.getItem("principia.activeProjectId") || "");
  await loadSummary();
  await loadTab({ reset: true, preserveScroll: true });
}

init().catch((error) => {
  el("researchStatus").textContent = error.message;
});
