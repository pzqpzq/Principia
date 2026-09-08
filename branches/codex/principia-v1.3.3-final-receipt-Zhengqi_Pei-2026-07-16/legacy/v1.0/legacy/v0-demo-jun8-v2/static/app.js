const tabs = [
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
  ideaRunId: "",
  refreshRunId: "",
  warningRunId: "",
  researchCountsSignature: "",
  researchTimer: null,
  ideaTimer: null,
  refreshTimer: null,
  detail: { bucket: "", id: "", item: null },
  assembler: { sourceType: "existed_ideas", items: [], selected: [] },
  projectModal: { mode: "create", fieldId: "" },
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

function setBusy(isBusy, message = "") {
  state.busy = isBusy;
  document.body.dataset.busy = isBusy ? "true" : "false";
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy && !button.dataset.allowBusy;
  });
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
  el("researchBtn").disabled = isRunning || state.busy;
  el("generateIdeaBtn").disabled = isRunning || state.busy;
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
  const running = !["complete", "error", "cancelled"].includes(run.status || "");
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

async function cancelRun(runId, label = "operation") {
  if (!runId) return;
  await post("/api/v2/llm/cancel", { run_id: runId });
  if (label === "research") {
    clearTimeout(state.researchTimer);
    setResearchRunning(false);
  }
  if (label === "idea") {
    clearTimeout(state.ideaTimer);
    state.ideaRunId = "";
    el("cancelIdeaGenerationBtn").hidden = true;
    setBusy(false);
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

function getGoalText() {
  return el("goalInput").value.trim();
}

function getTargetWorks() {
  const value = Number(el("targetWorksInput")?.value || 50);
  if (!Number.isFinite(value)) return 50;
  return Math.max(1, Math.min(100, Math.round(value)));
}

function idFor(tabKey, item) {
  const tab = tabs.find((entry) => entry.key === tabKey || entry.bucket === tabKey);
  return item?.[tab?.idKey] || item?.canonical_id || item?.benchmark_id || item?.baseline_id || item?.idea_id || "";
}

async function loadProjects(preferredId = "") {
  const data = await api("/api/v1/projects");
  state.projects = data.items || [];
  const first = state.projects.find((project) => project.field_id === (preferredId || state.activeProjectId)) || state.projects[0];
  state.activeProject = first || null;
  state.activeProjectId = first?.field_id || "default";
  renderProjects();
  renderProjectHeader();
}

async function loadSummary() {
  const summary = await api(`/api/v2/project/summary?field_id=${encodeURIComponent(state.activeProjectId)}`);
  state.activeProject = summary.project || state.activeProject;
  state.counts = summary.counts || {};
  const idx = state.projects.findIndex((project) => project.field_id === state.activeProjectId);
  if (idx >= 0) state.projects[idx] = { ...state.projects[idx], ...state.activeProject, counts: state.counts };
  renderProjects();
  renderProjectHeader();
  if (summary.last_research_run) {
    const run = summary.last_research_run;
    el("researchStatus").textContent = `${run.status || "idle"} · ${run.message || run.stage || ""}`;
  }
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
  el("goalInput").value = project.goal_text || project.query || el("goalInput").value || "";
  const settings = project.settings || {};
  el("modelModeInput").value = settings.model_mode || "auto";
  el("targetWorksInput").value = settings.paper_count || settings.target_works || settings.max_works || 50;
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

async function selectProject(fieldId) {
  state.activeProjectId = fieldId || state.activeProjectId;
  state.activeProject = state.projects.find((project) => project.field_id === state.activeProjectId) || state.projects[0] || null;
  state.activeProjectId = state.activeProject?.field_id || "default";
  state.offset = 0;
  state.items = [];
  renderProjects();
  renderProjectHeader();
  await loadSummary();
  await loadTab({ reset: true });
}

async function loadTab({ reset = false } = {}) {
  if (reset) {
    state.offset = 0;
    state.items = [];
    el("tabContent").innerHTML = `<div class="loading-row">Loading ${escapeHtml(tabLabel(state.activeTab))}...</div>`;
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
  });
  try {
    const data = await api(`/api/v2/project/tab?${params.toString()}`);
    state.counts = data.counts || state.counts;
    state.items = reset ? data.items || [] : [...state.items, ...(data.items || [])];
    state.offset = state.items.length;
    state.hasMore = Boolean(data.has_more);
    renderTabs();
    renderTabContent();
    el("moreBtn").hidden = !state.hasMore;
  } catch (error) {
    el("tabContent").innerHTML = `<div class="empty-state"><strong>Unable to load.</strong><span>${escapeHtml(error.message)}</span></div>`;
  } finally {
    el("moreBtn").textContent = "More";
  }
}

function renderTabContent() {
  if (!state.items.length) {
    const label = tabLabel(state.activeTab);
    el("tabContent").innerHTML = `<div class="empty-state"><strong>No ${escapeHtml(label)} yet.</strong><span>Run Research, or generate a new idea after selecting evidence.</span></div>`;
    return;
  }
  const renderer = {
    existed_ideas: renderExistedIdea,
    benchmarks: renderBenchmark,
    baselines: renderBaseline,
    principles: renderPrinciple,
    takeaway_messages: renderTakeawayMessage,
    my_ideas: renderMyIdea,
  }[state.activeTab];
  el("tabContent").innerHTML = state.items.map((item) => renderer(item)).join("");
}

function tabLabel(key) {
  return tabs.find((tab) => tab.key === key)?.label || key;
}

function rowShell(tabKey, item, body) {
  const id = idFor(tabKey, item);
  return `<article class="record-row record-${escapeHtml(tabKey)}" data-tab="${escapeHtml(tabKey)}" data-id="${escapeHtml(id)}">${body}</article>`;
}

function renderExistedIdea(item) {
  return rowShell(
    "existed_ideas",
    item,
    `
      <div>
        <h3>${escapeHtml(item.title || compact(item.idea_text, 88) || "Existed Idea")}</h3>
        <p>${escapeHtml(compact(item.idea_text || item.summary, 260))}</p>
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
        <h3>${escapeHtml(item.name || item.title || "Principle")}</h3>
        <p>${escapeHtml(compact(item.abstract_signature || item.mechanism || item.summary, 260))}</p>
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
        <h3>${escapeHtml(item.title || compact(item.message_text, 88) || "Takeaway Message")}</h3>
        <p>${escapeHtml(compact(item.message_text || item.finding || item.actionable_lesson, 260))}</p>
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
      <button type="button" data-action="details">Details</button>
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
        <p>${escapeHtml(compact(item.description || item.principle, 250))}</p>
        <div class="record-meta">
          <span>${escapeHtml(item.baseline_type || "published")}</span>
          <span>${Number(item.source_work_ids?.length || 0)} works</span>
          <span>${Number(item.performance?.length || 0)} results</span>
        </div>
      </div>
      <button type="button" data-action="details">Details</button>
    `
  );
}

function renderMyIdea(item) {
  return rowShell(
    "my_ideas",
    item,
    `
      <div>
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
  const data = await api(`/api/v2/item/detail?${params.toString()}`);
  state.detail = { bucket: tab.bucket, id, item: data.item };
  renderDetailModal(data.item);
  el("detailModal").hidden = false;
}

function renderDetailModal(item) {
  el("detailKind").textContent = state.detail.bucket.replaceAll("_", " ");
  el("detailTitle").textContent = item.title || item.name || item.benchmark_name || item.baseline_name || "Details";
  const versions = item.versions || [];
  el("detailVersionSelect").innerHTML = versions.length
    ? versions.map((version) => `<option value="${escapeHtml(version.version_id)}" ${version.version_id === item.active_variant?.version_id ? "selected" : ""}>${escapeHtml(version.is_user_edit ? "manual" : `${version.provider}:${version.model_name}`)} · ${escapeHtml(version.extracted_at || "")}</option>`).join("")
    : `<option value="">current</option>`;
  el("detailBody").innerHTML = detailSections(item);
  el("detailEditInput").value = JSON.stringify(item.active_variant?.payload || item, null, 2);
  renderDetailEditFields(item);
  el("detailEditForm").hidden = true;
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
      { key: "description", label: "Method Introduction", type: "long" },
      { key: "principle", label: "Method Principle", type: "long" },
      { key: "source_paper_link", label: "Source Paper Link", type: "short" },
      { key: "official_code_url", label: "Official Code Link", type: "short" },
      { key: "benchmarks", label: "Benchmarks, one per line", type: "array" },
      { key: "performance", label: "Performance rows as JSON array", type: "json" },
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
    { key: "idea_text", label: "Idea / Message Text", type: "long" },
    { key: "message_text", label: "Takeaway Message", type: "long" },
    { key: "mechanism", label: "Mechanism / Principle", type: "long" },
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
      ${detailBlock("Method Summary", item.description || item.summary)}
      ${detailBlock("Method Principle", item.principle)}
      ${detailBlock("Baseline Type", item.baseline_type)}
      ${detailList("Benchmarks", item.benchmarks)}
      ${performanceTable(item.performance)}
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
  return `
    ${detailBlock("Core Idea", item.idea_text || item.message_text || item.description || item.summary || item.abstract_signature || item.principle)}
    ${detailBlock("Mechanism / Principle", item.mechanism || item.principle)}
    ${detailBlock("Condition", item.condition)}
    ${detailBlock("Finding", item.finding)}
    ${detailBlock("Actionable Lesson", item.actionable_lesson)}
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
    const result = await post("/api/v2/research/start", {
      field_id: state.activeProjectId,
      goal_text: goal,
      model_mode: getModelMode(),
      target_works: targetWorks,
    });
    state.researchRunId = result.run_id;
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
  clearTimeout(state.researchTimer);
  try {
    const data = await api(`/api/v2/research/status?run_id=${encodeURIComponent(state.researchRunId)}`);
    const run = data.run || {};
    renderResearchStatus(run);
    const signature = JSON.stringify(run.counts || {});
    if (run.status === "running" && signature && signature !== state.researchCountsSignature) {
      state.researchCountsSignature = signature;
      await loadSummary();
      await loadTab({ reset: true });
    }
    if ((run.warnings || []).length && state.warningRunId !== run.run_id) {
      state.warningRunId = run.run_id;
      alert((run.warnings || []).join("\n\n"));
    }
    if (run.status === "complete") {
      setResearchRunning(false);
      await loadProjects(state.activeProjectId);
      await loadSummary();
      await loadTab({ reset: true });
      return;
    }
    if (run.status === "cancelled") {
      setResearchRunning(false);
      await loadSummary();
      return;
    }
    if (run.status === "error") {
      setResearchRunning(false);
      alert(run.message || "Research failed.");
      return;
    }
  } catch (error) {
    el("researchStatus").textContent = error.message;
    alert(error.message || "Research status could not be loaded.");
  }
  state.researchTimer = setTimeout(pollResearch, 1600);
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
  if (!confirm(`Delete project "${project?.name || fieldId}" and records that are not used by any other project?`)) return;
  await post("/api/v1/project/delete", { field_id: fieldId });
  await loadProjects("default");
  await selectProject("default");
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
  state.assembler = { sourceType: "existed_ideas", items: [], selected: state.assembler.selected || [] };
  el("assemblerSourceType").value = "existed_ideas";
  el("assemblerModelMode").value = getModelMode();
  el("assemblerUserNote").value = el("assemblerUserNote").value || "";
  el("assemblerDetail").innerHTML = `<p class="muted">Click an evidence card to inspect it before generation.</p>`;
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
          const id = item.canonical_id || item.principle_id || item.idea_id;
          const label = item.title || item.name || compact(item.idea_text || item.message_text || item.abstract_signature, 80);
          return `
            <article class="evidence-card" data-bucket="${escapeHtml(state.assembler.sourceType)}" data-id="${escapeHtml(id)}">
              <strong>${escapeHtml(label)}</strong>
              <p>${escapeHtml(compact(item.idea_text || item.message_text || item.abstract_signature || item.summary, 145))}</p>
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
  if (!id || state.assembler.selected.some((item) => item.bucket === bucket && item.id === id)) return;
  const item = state.assembler.items.find((entry) => (entry.canonical_id || entry.principle_id || entry.idea_id) === id) || null;
  state.assembler.selected.push({ bucket, id, item });
  renderSelectedEvidence();
  if (item) renderAssemblerDetail(item);
}

function unselectVisibleEvidence() {
  const source = state.assembler.sourceType;
  const visibleIds = new Set(state.assembler.items.map((item) => item.canonical_id || item.principle_id || item.idea_id).filter(Boolean));
  state.assembler.selected = state.assembler.selected.filter((ref) => !(ref.bucket === source && visibleIds.has(ref.id)));
  renderSelectedEvidence();
}

function clearSelectedEvidence() {
  state.assembler.selected = [];
  renderSelectedEvidence();
  el("assemblerDetail").innerHTML = `<p class="muted">Click an evidence card to inspect it before generation.</p>`;
}

function addMaterialFromRow(tabKey, id) {
  const allowed = new Set(["existed_ideas", "principles", "takeaway_messages"]);
  if (!allowed.has(tabKey) || !id) return;
  const item = state.items.find((entry) => idFor(tabKey, entry) === id) || null;
  if (state.assembler.selected.some((ref) => ref.bucket === tabKey && ref.id === id)) {
    el("researchStatus").textContent = "This material is already queued for Generate Idea.";
    return;
  }
  state.assembler.selected.push({ bucket: tabKey, id, item });
  el("researchStatus").textContent = `Queued 1 ${tabLabel(tabKey)} item for Generate Idea.`;
  if (!el("assemblerModal").hidden) {
    renderSelectedEvidence();
    if (item) renderAssemblerDetail(item);
  }
}

function renderSelectedEvidence() {
  el("selectedEvidence").innerHTML = state.assembler.selected.length
    ? state.assembler.selected
        .map((ref, index) => `<article class="selected-card"><span>${escapeHtml(ref.bucket.replaceAll("_", " "))}</span><strong>${escapeHtml(ref.item?.title || ref.item?.name || compact(ref.item?.idea_text || ref.item?.message_text || ref.id, 80))}</strong><div class="selected-actions"><button type="button" data-action="view-selected" data-index="${index}">View</button><button type="button" data-action="remove-selected" data-index="${index}">Remove</button></div></article>`)
        .join("")
    : `<p class="muted">No evidence selected yet.</p>`;
  renderAssemblyContext();
}

function renderAssemblerDetail(item) {
  const links = linkList("Links", [item.source_paper_link, item.paper_link, item.official_url, ...(item.source_paper_links || []), ...(item.source_urls || [])]);
  el("assemblerDetail").innerHTML = `
    <h3>${escapeHtml(item.title || item.name || "Evidence")}</h3>
    ${detailBlock("Summary", item.idea_text || item.message_text || item.abstract_signature || item.summary || "")}
    ${detailBlock("Mechanism", item.mechanism)}
    ${detailBlock("Condition", item.condition)}
    ${detailBlock("Finding", item.finding)}
    ${detailBlock("Actionable Lesson", item.actionable_lesson)}
    ${links}
  `;
}

function renderAssemblyContext() {
  el("assemblyContext").innerHTML = `<dl><dt>Project</dt><dd>${escapeHtml(state.activeProject?.name || "")}</dd><dt>Goal</dt><dd>${escapeHtml(compact(getGoalText(), 180) || "No goal saved yet.")}</dd><dt>Selected</dt><dd>${state.assembler.selected.length}</dd><dt>User Note</dt><dd>${escapeHtml(compact(el("assemblerUserNote")?.value || "", 160) || "No note yet.")}</dd></dl>`;
}

async function generateMyIdea() {
  const userNote = el("assemblerUserNote").value.trim();
  if (!state.assembler.selected.length && !userNote) {
    alert("Select evidence or add your own idea note first.");
    return;
  }
  setBusy(true, "Generating idea...");
  el("cancelIdeaGenerationBtn").hidden = false;
  el("assemblerDetail").innerHTML = `
    <div class="status-line">
      <span class="status-spinner" aria-hidden="true"></span>
      <strong>Calling the selected LLM to generate a project idea...</strong>
    </div>
  `;
  try {
    const result = await post("/api/v2/my-idea/generate/start", {
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
    setBusy(false);
    alert(error.message || "The selected LLM could not be called, so no idea was generated.");
  }
}

async function pollIdeaGeneration() {
  if (!state.ideaRunId) return;
  clearTimeout(state.ideaTimer);
  try {
    const data = await api(`/api/v2/llm/status?run_id=${encodeURIComponent(state.ideaRunId)}`);
    const run = data.run || {};
    el("assemblerDetail").innerHTML = `
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml((run.stage || run.status || "generating").replaceAll("_", " "))}</strong>
      </div>
      <p class="muted">${escapeHtml(run.message || "")}</p>
    `;
    if (run.status === "complete") {
      const ideaId = run.result_idea_id;
      const version = run.result_version_id || "";
      state.ideaRunId = "";
      el("cancelIdeaGenerationBtn").hidden = true;
      setBusy(false);
      el("assemblerModal").hidden = true;
      state.activeTab = "my_ideas";
      await loadSummary();
      await loadTab({ reset: true });
      const versionParam = version ? `&version=${encodeURIComponent(version)}` : "";
      window.open(`/idea.html?field_id=${encodeURIComponent(state.activeProjectId)}&idea_id=${encodeURIComponent(ideaId)}&model_mode=${encodeURIComponent(getAssemblerModelMode())}${versionParam}`, "_blank");
      return;
    }
    if (run.status === "cancelled") {
      state.ideaRunId = "";
      el("cancelIdeaGenerationBtn").hidden = true;
      setBusy(false);
      el("assemblerDetail").innerHTML = `<p class="muted">Idea generation was cancelled.</p>`;
      return;
    }
    if (run.status === "error") {
      state.ideaRunId = "";
      el("cancelIdeaGenerationBtn").hidden = true;
      setBusy(false);
      alert(run.message || "The selected LLM could not generate this idea.");
      return;
    }
  } catch (error) {
    state.ideaRunId = "";
    el("cancelIdeaGenerationBtn").hidden = true;
    setBusy(false);
    alert(error.message || "Idea generation status could not be loaded.");
  }
  state.ideaTimer = setTimeout(pollIdeaGeneration, 1200);
}

async function pollDetailRefresh() {
  if (!state.refreshRunId) return;
  clearTimeout(state.refreshTimer);
  try {
    const data = await api(`/api/v2/llm/status?run_id=${encodeURIComponent(state.refreshRunId)}`);
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
      await loadTab({ reset: true });
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
  ["projectModal", "detailModal", "assemblerModal", "apiKeysModal"].forEach((modalId) => {
    el(modalId).addEventListener("click", (event) => {
      if (event.target === el(modalId)) el(modalId).hidden = true;
    });
  });
  el("newProjectBtn").addEventListener("click", () => openProjectModal("create"));
  el("projectForm").addEventListener("submit", submitProject);
  el("cancelProjectModalBtn").addEventListener("click", closeProjectModal);
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
      await cancelRun(state.researchRunId, "research");
      el("researchStatus").textContent = "Research cancelled.";
    } catch (error) {
      alert(error.message || "Unable to cancel research.");
    }
  });
  el("generateIdeaBtn").addEventListener("click", openAssembler);
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
    await loadTab({ reset: true });
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
    await openDetail(row.dataset.tab, row.dataset.id);
  });
  el("reloadTabBtn").addEventListener("click", () => loadTab({ reset: true }));
  el("moreBtn").addEventListener("click", () => loadTab({ reset: false }));
  el("tabSearchInput").addEventListener("input", debounce(() => loadTab({ reset: true }), 250));
  el("modelModeInput").addEventListener("change", () => loadTab({ reset: true }));
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
      const result = await post("/api/v2/item/update", { bucket: state.detail.bucket, id: state.detail.id, payload: { ...advancedPayload, ...fieldPayload } });
      state.detail.item = result.item;
      renderDetailModal(result.item);
      await loadSummary();
      await loadTab({ reset: true });
    } catch (error) {
      alert(`Unable to save this edit: ${error.message}`);
    }
  });
  el("refreshDetailBtn").addEventListener("click", async () => {
    try {
      setBusy(true, "Refreshing item with selected LLM...");
      el("cancelDetailRefreshBtn").hidden = false;
      const result = await post("/api/v2/item/refresh/start", {
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
  el("closeAssemblerBtn").addEventListener("click", () => (el("assemblerModal").hidden = true));
  el("assemblerSourceType").addEventListener("change", loadAssemblerSources);
  el("assemblerModelMode").addEventListener("change", loadAssemblerSources);
  el("assemblerSearchInput").addEventListener("input", debounce(loadAssemblerSources, 250));
  el("assemblerUserNote").addEventListener("input", renderAssemblyContext);
  el("selectAllEvidenceBtn").addEventListener("click", () => {
    state.assembler.items.forEach((item) => addEvidence(state.assembler.sourceType, item.canonical_id || item.principle_id || item.idea_id));
  });
  el("unselectAllEvidenceBtn").addEventListener("click", unselectVisibleEvidence);
  el("clearSelectedEvidenceBtn").addEventListener("click", clearSelectedEvidence);
  el("assemblerSources").addEventListener("click", (event) => {
    const card = event.target.closest(".evidence-card");
    if (!card) return;
    const item = state.assembler.items.find((entry) => (entry.canonical_id || entry.principle_id || entry.idea_id) === card.dataset.id);
    if (event.target.closest("[data-action='add-evidence']")) addEvidence(card.dataset.bucket, card.dataset.id);
    if (event.target.closest("[data-action='view-evidence']") && item) renderAssemblerDetail(item);
  });
  el("selectedEvidence").addEventListener("click", (event) => {
    const index = Number(event.target.closest("[data-index]")?.dataset.index);
    if (!Number.isFinite(index)) return;
    if (event.target.closest("[data-action='remove-selected']")) {
      state.assembler.selected.splice(index, 1);
      renderSelectedEvidence();
    }
    if (event.target.closest("[data-action='view-selected']")) renderAssemblerDetail(state.assembler.selected[index]?.item || {});
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
  bindEvents();
  await loadProjects();
  await loadSummary();
  await loadTab({ reset: true });
}

init().catch((error) => {
  el("researchStatus").textContent = error.message;
});
