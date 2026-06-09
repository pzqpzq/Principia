const params = new URLSearchParams(location.search);
const legacyTabs = {
  dashboard: "works",
  source_works: "works",
  graph: "works",
  gaps: "works",
  runs: "works",
  principles: "principles",
  ideas: "ideas",
};
const tabs = [
  ["works", "Works"],
  ["principles", "Principles"],
  ["insights", "Insights"],
  ["novelty", "Novelty"],
  ["benchmarks", "Benchmarks"],
  ["baselines", "Baselines"],
  ["ideas", "Ideas"],
];
const idKeys = {
  works: "work_id",
  principles: "principle_id",
  insights: "fact_id",
  novelty: "fact_id",
  baselines: "baseline_id",
  ideas: "idea_id",
  gaps: "gap_id",
  runs: "run_id",
  benchmarks: "benchmark_id",
};
const state = {
  activeTab: normalizeTab(params.get("tab") || "works"),
  fieldId: params.get("field_id") || "default",
  dashboard: null,
  projects: [],
  records: [],
  collections: {},
};

document.documentElement.lang = "en";

const el = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function normalizeTab(tab) {
  return legacyTabs[tab] || tab || "dashboard";
}

function query() {
  return el("searchInput").value.trim();
}

async function loadDashboard() {
  state.dashboard = await api(`/api/library/dashboard?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}`);
  renderFieldStatus(state.dashboard);
}

async function loadView() {
  renderTabs();
  el("mainPane").innerHTML = `<p class="muted">Loading ${escapeHtml(labelFor(state.activeTab))}.</p>`;
  el("detailPane").innerHTML = `<p class="muted">Select a record to inspect its local evidence and lineage.</p>`;
  await loadStatus();
  if (state.activeTab === "works") return loadWorks();
  if (state.activeTab === "principles") return loadPrinciples();
  if (state.activeTab === "insights") return loadFacts("insights", "insight");
  if (state.activeTab === "novelty") return loadFacts("novelty", "novelty");
  if (state.activeTab === "benchmarks") return loadBenchmarks();
  if (state.activeTab === "baselines") return loadBaselines();
  if (state.activeTab === "ideas") return loadIdeas();
}

async function loadProjects() {
  const data = await api("/api/library/projects");
  state.projects = data.items || [];
  if (!state.projects.some((project) => project.field_id === state.fieldId)) {
    state.fieldId = state.projects[0]?.field_id || "default";
    el("fieldSelect").value = state.fieldId;
  }
  renderProjects();
}

async function loadStatus() {
  state.dashboard = await api(`/api/library/dashboard?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}`);
  renderFieldStatus(state.dashboard);
  renderProjects();
}

function renderTabs() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.activeTab);
  });
  el("pageTitle").textContent = "Principia Library";
  el("pageSubtitle").textContent = "Local Field Observatory for papers, principles, benchmarks, gaps, ideas, and validation feedback.";
}

function renderProjects() {
  const options = state.projects.map((project) => `<option value="${escapeAttr(project.field_id)}">${escapeHtml(project.name || project.field_id)}</option>`).join("");
  if (options) {
    el("fieldSelect").innerHTML = options;
    el("fieldSelect").value = state.fieldId;
  }
  el("recordsList").innerHTML = state.projects.map((project) => {
    const counts = project.counts || {};
    const active = project.field_id === state.fieldId ? " active" : "";
    return `
      <article class="project-row${active}">
        <button type="button" data-project="${escapeAttr(project.field_id)}">
          <strong>${escapeHtml(project.name || project.field_id)}</strong>
          <span>${escapeHtml(project.query || project.description || (project.field_id === "default" ? "All local records" : "Local project"))}</span>
          <em>${counts.works || 0} works · ${counts.principles || 0} principles · ${counts.ideas || 0} ideas</em>
        </button>
        ${project.field_id !== "default" ? `<div class="project-actions"><button type="button" data-project-rename="${escapeAttr(project.field_id)}">Rename</button><button type="button" data-project-delete="${escapeAttr(project.field_id)}">Delete</button></div>` : ""}
      </article>
    `;
  }).join("") || emptyLine("No projects yet.");
}

function renderFieldStatus(dashboard) {
  const counts = dashboard?.counts || {};
  const coverage = dashboard?.coverage || {};
  const parts = [
    ["Works", counts.works],
    ["Principles", counts.principles],
    ["Benchmarks", counts.benchmarks],
    ["Baselines", counts.baselines],
    ["Ideas", counts.ideas],
    ["Validated", counts.validated_ideas],
    ["Open gaps", counts.gaps],
    ["Extraction", pct(avgCoverage(coverage))],
  ];
  el("fieldStatus").innerHTML = parts.map(([label, value]) => `<span><b>${escapeHtml(label)}</b> ${escapeHtml(value ?? 0)}</span>`).join("");
}

function renderDashboard() {
  const data = state.dashboard || {};
  const counts = data.counts || {};
  const coverage = data.coverage || {};
  const warnings = data.warnings || [];
  state.records = [
    ...(data.top_principles || []).map((item) => ({ ...item, _kind: "principles" })),
    ...warnings.map((item) => ({ ...item, _kind: "gaps" })),
  ];
  renderDashboardList(data);
  el("mainPane").innerHTML = `
    <section class="summary-grid">
      ${metricCard("Works", counts.works, `${counts.work_facts || 0} facts extracted`)}
      ${metricCard("Principles", counts.principles, `${counts.validated_ideas || 0} validated ideas`)}
      ${metricCard("Benchmarks", counts.benchmarks, `${counts.baselines || 0} baselines · ${counts.results || 0} results`)}
      ${metricCard("Open Gaps", counts.gaps, warnings[0]?.title || "No active warning")}
    </section>
    <section class="panel frontier-panel">
      <div>
        <h2>Current Frontier State</h2>
        <p>${richText(data.frontier_brief?.summary || "No local field records yet.")}</p>
      </div>
      <div class="evidence-stack">
        ${(data.frontier_brief?.evidence || []).map((item) => `<span class="badge">${escapeHtml(item.type)} · ${escapeHtml(trim(item.label, 42))}</span>`).join("")}
      </div>
    </section>
    <section class="two-column">
      <div class="panel">
        <h2>Extraction Coverage</h2>
        <div class="coverage-grid">
          ${Object.entries(coverage).map(([key, value]) => coverageRow(labelize(key), value)).join("")}
        </div>
      </div>
      <div class="panel">
        <h2>Principle Landscape</h2>
        <div class="family-list">
          ${(data.principle_families || []).map((item) => `
            <article>
              <strong>${escapeHtml(item.family)}</strong>
              <span>${item.principles} principles · ${item.works} works · ${item.ideas} ideas · confidence ${item.mean_confidence}</span>
            </article>
          `).join("") || emptyLine("No principle families yet.")}
        </div>
      </div>
    </section>
    <section class="two-column">
      <div class="panel">
        <h2>Top Principles</h2>
        ${miniList(data.top_principles || [], "principles")}
      </div>
      <div class="panel">
        <h2>Open Gaps</h2>
        ${miniList(warnings, "gaps")}
      </div>
    </section>
    <section class="panel">
      <h2>Frontier Timeline</h2>
      <div class="timeline">
        ${(data.timeline || []).map((item) => `
          <button type="button" data-open="${escapeAttr(item.id)}" data-kind="${escapeAttr(kindFromType(item.type))}">
            <span>${escapeHtml(item.time)}</span>
            <strong>${escapeHtml(item.type)}</strong>
            <em>${escapeHtml(item.label)}</em>
          </button>
        `).join("") || emptyLine("Timeline will appear after local works, principles, or gaps exist.")}
      </div>
    </section>
  `;
  el("detailPane").innerHTML = detailShell("Field Brief", [
    section("Evidence", (data.frontier_brief?.evidence || []).map((item) => `${item.type}: ${item.label}`)),
    section("Last Sync", [data.last_sync || "No local sync timestamp yet."]),
  ]);
}

function renderDashboardList(data) {
  const rows = [
    ...(data.top_principles || []).slice(0, 6).map((item) => ({
      id: item.principle_id,
      kind: "principles",
      title: item.name,
      subtitle: `${item.validation_level} · ${item.source_work_count} works · ${item.idea_count} ideas`,
    })),
    ...(data.warnings || []).slice(0, 6).map((item) => ({
      id: item.gap_id,
      kind: "gaps",
      title: item.title,
      subtitle: `${item.gap_type} · severity ${item.severity}`,
    })),
  ];
  el("recordsList").innerHTML = rows.map(recordRow).join("") || emptyLine("No field records yet.");
}

async function loadWorks() {
  const data = await api(`/api/library/works?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}&limit=500`);
  state.records = data.items || [];
  state.collections = data;
  el("mainPane").innerHTML = `
    <section class="panel">
      <h2>Works In Project</h2>
      <div class="record-table works-table">
        ${state.records.map((work) => `
          <button type="button" data-open="${escapeAttr(work.work_id)}" data-kind="works">
            <strong>${richText(trim(localized(work).title || work.title || work.work_id, 96))}</strong>
            <span>${escapeHtml([work.year, work.venue_or_source, work.validation_level].filter(Boolean).join(" · ") || "local")}</span>
            <span>${workBadges(work)}</span>
          </button>
        `).join("") || emptyLine("No local works match this search.")}
      </div>
    </section>
  `;
  if (state.records[0]) renderWorkDetail(state.records[0]);
}

async function loadPrinciples() {
  const data = await api(`/api/library/principles?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}&limit=500`);
  state.records = data.items || [];
  state.collections = data;
  el("mainPane").innerHTML = `
    <section class="principle-grid">
      ${state.records.map((principle) => principleCard(principle)).join("") || emptyLine("No principles match this search.")}
    </section>
  `;
  if (state.records[0]) renderPrincipleDetail(state.records[0]);
}

async function loadFacts(kind, factType) {
  const data = await api(`/api/library/${kind}?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}`);
  state.records = data.items || [];
  state.collections = data;
  const title = factType === "insight" ? "Extracted Insights" : "Novelty Claims";
  el("mainPane").innerHTML = `
    <section class="fact-grid">
      ${state.records.map((fact) => factCard(kind, fact)).join("") || emptyLine(`No ${factType} facts match this project.`)}
    </section>
  `;
  if (state.records[0]) renderFactDetail(kind, state.records[0]);
}

async function loadBenchmarks() {
  const data = await api(`/api/library/benchmarks?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}`);
  state.collections = data;
  state.records = data.items || [];
  el("mainPane").innerHTML = `
    <section class="panel">
      <h2>Benchmarks</h2>
      ${benchmarkMatrix(data)}
    </section>
  `;
  if (state.records[0]) renderBenchmarkDetail(state.records[0]);
}

async function loadBaselines() {
  const data = await api(`/api/library/baselines?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}`);
  state.collections = data;
  state.records = data.items || [];
  el("mainPane").innerHTML = `
    <section class="baseline-grid">
      ${state.records.map((baseline) => baselineCard(baseline)).join("") || emptyLine("No baselines match this project.")}
    </section>
  `;
  if (state.records[0]) renderBaselineDetail(state.records[0]);
}

async function loadIdeas() {
  const data = await api(`/api/library/ideas?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}&limit=500`);
  state.records = data.items || [];
  el("mainPane").innerHTML = `
    <section class="idea-grid">
      ${state.records.map((idea) => ideaCard(idea)).join("") || emptyLine("No generated ideas match this search.")}
    </section>
  `;
  if (state.records[0]) renderIdeaDetail(state.records[0]);
}

async function loadRuns() {
  const data = await api(`/api/library/runs?field_id=${encodeURIComponent(state.fieldId)}&query=${encodeURIComponent(query())}&limit=500`);
  state.records = data.items || [];
  renderRecordList("runs", state.records);
  el("mainPane").innerHTML = `
    <section class="panel">
      <h2>Audit Trail</h2>
      <div class="run-list">
        ${state.records.map((run) => `
          <button type="button" data-open="${escapeAttr(run.run_id)}" data-kind="runs">
            <strong>${escapeHtml(run.type || "run")}</strong>
            <span>${escapeHtml(run.query || run.idea_id || run.field_id || run.goal_id || run.run_id)}</span>
            <em>${escapeHtml(run.created_at || "")}</em>
          </button>
        `).join("") || emptyLine("No local runs yet.")}
      </div>
    </section>
  `;
  if (state.records[0]) renderRunDetail(state.records[0]);
}

function renderRecordList(kind, records) {
  el("recordsList").innerHTML = records.map((item) => {
    const id = item[idKeys[kind]];
    const title = titleFor(kind, item);
    const subtitle = subtitleFor(kind, item);
    return recordRow({ id, kind, title, subtitle });
  }).join("") || emptyLine("No matching records.");
}

function recordRow({ id, kind, title, subtitle }) {
  return `
    <article class="record-row">
      <button type="button" data-open="${escapeAttr(id)}" data-kind="${escapeAttr(kind)}">
        <strong>${richText(trim(title || id, 96))}</strong>
        <span>${escapeHtml(subtitle || id)}</span>
      </button>
    </article>
  `;
}

function renderWorkDetail(work) {
  const facts = factsFor(work.work_id);
  const benchmarks = recordsFor("benchmark_records", "work_id", work.work_id);
  const baselines = recordsFor("baseline_records", "work_id", work.work_id);
  const results = recordsFor("result_records", "work_id", work.work_id);
  const view = localized(work);
  el("detailPane").innerHTML = detailShell(view.title || work.title || "Work", [
    metaLine([work.year, work.venue_or_source, work.source_type, work.validation_level]),
    work.url_or_doi ? `<a href="${escapeAttr(work.url_or_doi)}" target="_blank" rel="noreferrer">${escapeHtml(work.url_or_doi)}</a>` : "",
    section("Abstract", [view.abstract || work.abstract]),
    section("Core Idea", factTexts(facts, "core_idea").concat(view.work_principles || work.work_principles || []).slice(0, 4)),
    section("Motivation", factTexts(facts, "motivation")),
    section("Insights", factTexts(facts, "insight").concat(view.work_insights || work.work_insights || []).slice(0, 6)),
    section("Novelty", factTexts(facts, "novelty").concat(view.work_novelty || work.work_novelty || []).slice(0, 6)),
    section("Assumptions", factTexts(facts, "assumption")),
    section("Failure Modes", factTexts(facts, "failure_mode")),
    section("Benchmarks", benchmarks.map((item) => `${item.task} · ${item.dataset} · ${item.metric}`)),
    section("Baselines", baselines.map((item) => item.baseline_name)),
    section("Reported Results", results.map((item) => `${item.method_name}: ${item.value_text || item.value || item.metric}`)),
    actions("source_works", work.work_id, work),
  ]);
}

function renderPrincipleDetail(principle) {
  const view = localized(principle);
  const ideas = (state.dashboard?.recent_ideas || []).filter((idea) => (idea.source_principles || []).includes(principle.principle_id));
  el("detailPane").innerHTML = detailShell(view.name || principle.name || "Principle", [
    metaLine([principle.validation_level, `confidence ${principle.confidence_score ?? 0}`, principle.model_mode, principle.model_name]),
    section("Abstract Signature", [view.abstract_signature || principle.abstract_signature]),
    section("Mechanism", [view.mechanism || principle.mechanism]),
    section("Problem Pressure", [view.problem_pressure || principle.problem_pressure]),
    section("Objective", [view.objective || principle.objective]),
    section("Transfer Hooks", view.transfer_hooks || principle.transfer_hooks),
    section("Assumptions", view.assumptions || principle.assumptions),
    section("Tradeoffs", view.tradeoffs || principle.tradeoffs),
    section("Failure Modes", view.failure_modes || principle.failure_modes),
    section("Validation Notes", view.validation_notes || principle.validation_notes),
    section("Domain Tags", principle.domain_tags || []),
    section("Used By Ideas", ideas.map((idea) => idea.title || idea.idea_id)),
    actions("principles", principle.principle_id, principle),
  ]);
}

function renderBenchmarkDetail(benchmark) {
  el("detailPane").innerHTML = detailShell(`${benchmark.dataset} · ${benchmark.metric}`, [
    metaLine([benchmark.task, benchmark.split, benchmark.metric_direction, `${benchmark.source_count || 0} source works`]),
    section("Benchmark Introduction", [benchmark.description]),
    section("Data Form / Scale", [benchmark.data_form, benchmark.scale]),
    section("Source / Official Link", [benchmark.source, benchmark.official_url]),
    section("Evaluation Metric", [`${benchmark.metric} (${benchmark.metric_direction || "unknown direction"})`]),
    section("Mainstream Baseline Performance", (benchmark.baseline_performance || []).map((item) => `${item.method_name || "method"} · ${item.metric}: ${item.value_text || item.value || "not extracted"}`)),
    section("Source Works", (benchmark.source_work_ids || []).map((wid) => state.collections.works?.[wid]?.title || wid)),
  ]);
}

function renderBaselineDetail(baseline) {
  el("detailPane").innerHTML = detailShell(baseline.baseline_name || "Baseline", [
    metaLine([baseline.baseline_type, `${baseline.benchmarks?.length || 0} benchmarks`, `${baseline.source_work_ids?.length || 0} source works`]),
    section("Basic Introduction", [baseline.description]),
    section("Basic Principle", [baseline.principle]),
    section("Source / Official Code", [baseline.source, baseline.official_code_url]),
    section("Benchmarks", baseline.benchmarks || []),
    section("Performance Metrics", (baseline.performance || []).map((item) => `${item.method_name || baseline.baseline_name} · ${item.metric}: ${item.value_text || item.value || "not extracted"}`)),
    section("Source Works", baseline.source_titles || []),
  ]);
}

function renderFactDetail(kind, fact) {
  el("detailPane").innerHTML = detailShell(kind === "insights" ? "Insight" : "Novelty Claim", [
    metaLine([fact.source, fact.work_year, `confidence ${fact.confidence_score ?? 0}`]),
    section("Extracted Text", [fact.text]),
    section("Source Work", [fact.work_title]),
    section("Evidence", [fact.evidence_span?.source, fact.url_or_doi]),
  ]);
}

function renderGapDetail(gap) {
  el("detailPane").innerHTML = detailShell(gap.title || "Gap", [
    metaLine([gap.gap_type, `severity ${gap.severity}`, `novelty ${gap.novelty_potential}`]),
    section("Why It Matters", [gap.summary]),
    section("Related Works", gap.related_work_ids || []),
    section("Related Principles", gap.related_principle_ids || []),
    section("Related Benchmarks", gap.related_benchmark_ids || []),
    section("Suggested Idea Seeds", gap.suggested_idea_seeds || []),
  ]);
}

function renderIdeaDetail(idea) {
  const view = localized(idea);
  const estimate = idea._calibrated_estimate || {};
  const plan = idea._prompt_plan || {};
  el("detailPane").innerHTML = detailShell(view.title || idea.title || "Idea", [
    metaLine([idea.feedback_status || "unvalidated", idea.model_mode, idea.model_name]),
    section("Thesis", [view.one_sentence_thesis || idea.one_sentence_thesis]),
    section("Source Principles", idea.source_principle_names || idea.source_principles || []),
    section("Insights", view.source_insights || (idea.source_insights || []).map((fact) => `${fact.work_title || fact.work_id}: ${fact.text}`)),
    section("Novelty", view.source_novelty || (idea.source_novelty || []).map((fact) => `${fact.work_title || fact.work_id}: ${fact.text}`)),
    section("Mechanism Design", view.mechanism_design || idea.mechanism_design),
    section("Benchmarks / Baselines", [...(view.baselines || idea.baselines || []), ...(view.metrics || idea.metrics || [])]),
    section("Validation Plan", view.validation_protocol || idea.validation_protocol),
    estimatePanel(estimate),
    promptPlanPanel(plan),
    `<div class="action-row">
      <button type="button" data-feedback-supported="${escapeAttr(idea.idea_id)}">Mark Supported</button>
      <button type="button" data-copy-plan="${escapeAttr(idea.idea_id)}">Copy Prompt Plan</button>
      <button type="button" data-export-bundle="${escapeAttr(idea.idea_id)}">Export Bundle</button>
      <button class="danger" type="button" data-delete="${escapeAttr(idea.idea_id)}" data-bucket="ideas">Delete</button>
    </div>`,
  ]);
}

function renderRunDetail(run) {
  el("detailPane").innerHTML = detailShell(run.type || "Run", [
    metaLine([run.run_id, run.created_at]),
    section("Query / Field", [run.query || run.field_id || run.goal_id]),
    section("Works", run.work_ids || []),
    section("Principles", run.principle_ids || []),
    section("Ideas", run.idea_ids || []),
    section("Output Counts", [run.output_counts ? JSON.stringify(run.output_counts, null, 2) : ""]),
  ]);
}

function detailShell(title, parts) {
  return `
    <article class="detail-card">
      <header><h2>${richText(title)}</h2></header>
      ${parts.filter(Boolean).join("")}
    </article>
  `;
}

function metricCard(label, value, sub) {
  return `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? 0)}</strong><em>${escapeHtml(sub || "")}</em></article>`;
}

function coverageRow(label, value) {
  const width = Math.max(0, Math.min(100, Math.round((Number(value) || 0) * 100)));
  return `
    <div class="coverage-row">
      <span>${escapeHtml(label)}</span>
      <b>${width}%</b>
      <i><em style="width:${width}%"></em></i>
    </div>
  `;
}

function principleCard(principle) {
  const view = localized(principle);
  return `
    <article class="principle-card" data-open="${escapeAttr(principle.principle_id)}" data-kind="principles">
      <button type="button" data-open="${escapeAttr(principle.principle_id)}" data-kind="principles">
        <span class="badge">${escapeHtml(principle.validation_level || "L0")} · confidence ${escapeHtml(principle.confidence_score ?? 0)}</span>
        <h2>${richText(view.name || principle.name || principle.principle_id)}</h2>
        <p>${richText(trim(view.abstract_signature || principle.abstract_signature || principle.mechanism || "", 180))}</p>
        <small>${(principle.domain_tags || []).slice(0, 4).map((tag) => `<b>${escapeHtml(tag)}</b>`).join("")}</small>
      </button>
    </article>
  `;
}

function gapCard(gap) {
  return `
    <article class="gap-card">
      <button type="button" data-open="${escapeAttr(gap.gap_id)}" data-kind="gaps">
        <span class="badge">${escapeHtml(gap.gap_type)} · severity ${escapeHtml(gap.severity)}</span>
        <h2>${escapeHtml(gap.title)}</h2>
        <p>${escapeHtml(gap.summary)}</p>
      </button>
    </article>
  `;
}

function ideaCard(idea) {
  const view = localized(idea);
  const estimate = idea._calibrated_estimate || {};
  return `
    <article class="idea-card">
      <button type="button" data-open="${escapeAttr(idea.idea_id)}" data-kind="ideas">
        <span class="badge">${escapeHtml(idea.feedback_status || "unvalidated")} · ${escapeHtml(estimate.estimate_confidence || "uncalibrated")}</span>
        <h2>${richText(view.title || idea.title || idea.idea_id)}</h2>
        <p>${richText(trim(view.one_sentence_thesis || idea.one_sentence_thesis || idea.insight || "", 190))}</p>
        <small>${escapeHtml((idea.source_principles || []).length)} source principles · ${escapeHtml((idea.baselines || []).length)} baselines</small>
      </button>
    </article>
  `;
}

function factCard(kind, fact) {
  return `
    <article class="fact-card">
      <button type="button" data-open="${escapeAttr(fact.fact_id)}" data-kind="${escapeAttr(kind)}">
        <span class="badge">${escapeHtml(fact.source || "local")} · confidence ${escapeHtml(fact.confidence_score ?? 0)}</span>
        <h2>${richText(trim(fact.text, 170))}</h2>
        <p>${escapeHtml(fact.work_title || fact.work_id)}</p>
      </button>
    </article>
  `;
}

function baselineCard(baseline) {
  return `
    <article class="baseline-card">
      <button type="button" data-open="${escapeAttr(baseline.baseline_id)}" data-kind="baselines">
        <span class="badge">${escapeHtml(baseline.baseline_type || "baseline")} · ${escapeHtml((baseline.benchmarks || []).length)} benchmarks</span>
        <h2>${escapeHtml(baseline.baseline_name || baseline.baseline_id)}</h2>
        <p>${escapeHtml(trim(baseline.description || baseline.principle || "", 190))}</p>
        <small>${escapeHtml((baseline.performance || [])[0]?.value_text || "performance not extracted")}</small>
      </button>
    </article>
  `;
}

function benchmarkMatrix(data) {
  const rows = data.items || [];
  if (!rows.length) return emptyLine("No structured benchmark records yet.");
  return `
    <div class="matrix">
      <div class="matrix-head"><span>Task</span><span>Benchmark</span><span>Data Form</span><span>Metric</span><span>Main Baselines</span><span>Performance</span></div>
      ${rows.map((row) => {
        return `
          <button type="button" data-open="${escapeAttr(row.benchmark_id)}" data-kind="benchmarks">
            <span>${escapeHtml(row.task || "task")}</span>
            <strong>${escapeHtml(row.dataset || "dataset")}</strong>
            <span>${escapeHtml(trim(row.data_form || row.description || "", 72))}</span>
            <span>${escapeHtml(row.metric || "metric")}</span>
            <span>${escapeHtml([...(new Set((row.baselines || []).map((item) => item.baseline_name)))].join(", ") || "missing")}</span>
            <span>${escapeHtml((row.baseline_performance || []).map((item) => item.value_text || item.value || item.metric).join("; ") || "needs result")}</span>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function graphLegend(data) {
  const counts = {};
  for (const node of data.nodes || []) counts[node.type] = (counts[node.type] || 0) + 1;
  return Object.entries(counts).map(([type, count]) => recordRow({ id: type, kind: "graph", title: labelize(type), subtitle: `${count} nodes` })).join("") || emptyLine("No graph nodes yet.");
}

function graphSvg(data) {
  const nodes = (data.nodes || []).slice(0, 80);
  const edges = data.edges || [];
  if (!nodes.length) return emptyLine("No graph data yet.");
  const columns = ["field", "work", "insight", "novelty", "principle", "benchmark", "result", "idea", "gap"];
  const xFor = (type) => 70 + Math.max(0, columns.indexOf(type)) * 135;
  const groups = groupBy(nodes, "type");
  const positions = {};
  for (const [type, group] of Object.entries(groups)) {
    group.slice(0, 12).forEach((node, idx) => {
      positions[node.id] = { x: xFor(type), y: 70 + idx * 44 };
    });
  }
  const edgeLines = edges
    .filter((edge) => positions[edge.source] && positions[edge.target])
    .slice(0, 140)
    .map((edge) => {
      const a = positions[edge.source];
      const b = positions[edge.target];
      return `<line x1="${a.x + 44}" y1="${a.y}" x2="${b.x - 44}" y2="${b.y}" />`;
    }).join("");
  const nodeShapes = nodes
    .filter((node) => positions[node.id])
    .map((node) => {
      const pos = positions[node.id];
      return `
        <g class="graph-node graph-${escapeAttr(node.type)}" transform="translate(${pos.x - 46}, ${pos.y - 18})">
          <rect width="92" height="36" rx="6"></rect>
          <text x="46" y="14">${escapeHtml(labelize(node.type))}</text>
          <text x="46" y="27">${escapeHtml(trim(node.label || node.id, 16))}</text>
        </g>
      `;
    }).join("");
  return `<svg class="graph-svg" viewBox="0 0 1200 640" role="img" aria-label="Principia field graph">${edgeLines}${nodeShapes}</svg>`;
}

function estimatePanel(estimate) {
  if (!estimate || !Object.keys(estimate).length) return "";
  return `
    <section>
      <h3>Result Estimate</h3>
      <div class="estimate-grid">
        <span>Metric <b>${escapeHtml(estimate.primary_metric || "unknown")}</b></span>
        <span>Mean <b>${escapeHtml(estimate.mean ?? "n/a")}</b></span>
        <span>Useful signal <b>${pct(estimate.probability_useful_signal || 0)}</b></span>
        <span>Confidence <b>${escapeHtml(estimate.estimate_confidence || "uncalibrated")}</b></span>
      </div>
      ${section("Cheapest Falsification", [estimate.cheapest_falsification])}
      ${section("Calibration Basis", [estimate.calibration_basis?.confidence_reason])}
    </section>
  `;
}

function promptPlanPanel(plan) {
  if (!plan || !Object.keys(plan).length) return "";
  return `
    <section>
      <h3>Implementation Prompt Plan</h3>
      <ol class="prompt-steps">
        ${(plan.prompts || []).map((step) => `<li><b>${escapeHtml(step.step_id)}</b> ${escapeHtml(step.objective)}</li>`).join("")}
      </ol>
    </section>
  `;
}

function section(title, values) {
  const items = (Array.isArray(values) ? values : [values]).filter(Boolean);
  if (!items.length) return "";
  return `<section><h3>${escapeHtml(title)}</h3><ul>${items.map((item) => `<li>${richText(cleanLabeledText(item))}</li>`).join("")}</ul></section>`;
}

function actions(bucket, id, item) {
  return `
    <div class="action-row">
      <button type="button" data-highlight="${escapeAttr(id)}" data-bucket="${escapeAttr(bucket)}">${item.highlighted ? "Unmark Highlight" : "Highlight"}</button>
      <button class="danger" type="button" data-delete="${escapeAttr(id)}" data-bucket="${escapeAttr(bucket)}">Delete</button>
    </div>
  `;
}

function miniList(items, kind) {
  if (!items.length) return emptyLine("None yet.");
  return `<div class="mini-list">${items.slice(0, 7).map((item) => {
    const id = item[idKeys[kind]] || item.principle_id || item.gap_id || item._id;
    return `<button type="button" data-open="${escapeAttr(id)}" data-kind="${escapeAttr(kind)}"><strong>${escapeHtml(trim(titleFor(kind, item), 70))}</strong><span>${escapeHtml(subtitleFor(kind, item))}</span></button>`;
  }).join("")}</div>`;
}

function metaLine(values) {
  const text = values.filter(Boolean).join(" · ");
  return text ? `<p class="meta-line">${escapeHtml(text)}</p>` : "";
}

function titleFor(kind, item) {
  if (kind === "works") return localized(item).title || item.title || item.work_id;
  if (kind === "principles") return localized(item).name || item.name || item.principle_id;
  if (kind === "insights" || kind === "novelty") return item.text || item.fact_id;
  if (kind === "baselines") return item.baseline_name || item.baseline_id;
  if (kind === "ideas") return localized(item).title || item.title || item.idea_id;
  if (kind === "gaps") return item.title || item.gap_id;
  if (kind === "runs") return item.type || item.run_id;
  if (kind === "benchmarks") return `${item.dataset || "Benchmark"} · ${item.metric || "metric"}`;
  return item.title || item.name || item.id || "";
}

function subtitleFor(kind, item) {
  if (kind === "works") return [item.year, item.venue_or_source, item.validation_level].filter(Boolean).join(" · ");
  if (kind === "principles") return [item.validation_level, `confidence ${item.confidence_score ?? 0}`, ...(item.domain_tags || []).slice(0, 2)].filter(Boolean).join(" · ");
  if (kind === "insights" || kind === "novelty") return [item.work_title, `confidence ${item.confidence_score ?? 0}`].filter(Boolean).join(" · ");
  if (kind === "baselines") return [item.baseline_type, `${(item.benchmarks || []).length} benchmarks`].filter(Boolean).join(" · ");
  if (kind === "ideas") return [item.feedback_status || "unvalidated", `${(item.source_principles || []).length} principles`].join(" · ");
  if (kind === "gaps") return [item.gap_type, `severity ${item.severity}`].join(" · ");
  if (kind === "runs") return [item.created_at, item.query || item.idea_id || item.field_id].filter(Boolean).join(" · ");
  if (kind === "benchmarks") return [item.task, item.split, item.metric_direction].filter(Boolean).join(" · ");
  return "";
}

function workBadges(work) {
  const facts = factsFor(work.work_id);
  const benchmarks = recordsFor("benchmark_records", "work_id", work.work_id);
  const badges = [];
  if (facts.some((fact) => fact.fact_type === "core_idea") || (work.work_principles || []).length) badges.push("Core idea");
  if (facts.some((fact) => fact.fact_type === "insight") || (work.work_insights || []).length) badges.push("Insight");
  if (benchmarks.length) badges.push(`${benchmarks.length} benchmarks`);
  if (work.highlighted) badges.push("Highlighted");
  return badges.map((badge) => `<b>${escapeHtml(badge)}</b>`).join("");
}

function factsFor(workId) {
  return (state.collections.work_facts || []).filter((fact) => fact.work_id === workId);
}

function factTexts(facts, type) {
  return facts.filter((fact) => fact.fact_type === type).map((fact) => fact.text);
}

function recordsFor(collection, key, value) {
  return (state.collections[collection] || []).filter((item) => item[key] === value);
}

function groupBy(items, key) {
  const groups = {};
  for (const item of items || []) {
    const value = item[key] || "unknown";
    (groups[value] ||= []).push(item);
  }
  return groups;
}

function localized(item) {
  const variants = item.language_variants || {};
  return variants.en || {};
}

function avgCoverage(coverage) {
  const values = Object.values(coverage || {}).map(Number);
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function pct(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function labelFor(tab) {
  return tabs.find(([id]) => id === tab)?.[1] || tab;
}

function labelize(value) {
  return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function kindFromType(type) {
  return { work: "works", principle: "principles", idea: "ideas", gap: "gaps", benchmark: "benchmarks" }[type] || type;
}

function emptyLine(text) {
  return `<p class="muted empty">${escapeHtml(text)}</p>`;
}

function trim(text, max) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length > max ? `${value.slice(0, max - 3)}...` : value;
}

function cleanLabeledText(text) {
  let value = String(text || "").replace(/\s+/g, " ").trim();
  for (let i = 0; i < 3; i += 1) {
    value = value.replace(/^(novelty|insight|principle|general principle|reusable mechanism|core idea|motivation)\s*[:：]\s*/i, "").trim();
  }
  return value;
}

function mathText(math) {
  let value = escapeHtml(String(math || "").trim());
  value = value.replace(/\\texttt\{([^{}]+)\}/g, "<code>$1</code>");
  value = value.replace(/\\text\{([^{}]+)\}/g, "$1");
  value = value.replace(/\\mathrm\{([^{}]+)\}/g, "$1");
  value = value.replace(/\^\{([^{}]+)\}/g, "<sup>$1</sup>");
  value = value.replace(/_\{([^{}]+)\}/g, "<sub>$1</sub>");
  value = value.replace(/\^([A-Za-z0-9+\-=]+)/g, "<sup>$1</sup>");
  value = value.replace(/_([A-Za-z0-9+\-=]+)/g, "<sub>$1</sub>");
  return `<span class="math-inline">${value}</span>`;
}

function richText(text) {
  const value = String(text || "");
  const pattern = /\$([^$\n]+)\$|\\\((.*?)\\\)/g;
  let cursor = 0;
  let html = "";
  for (const match of value.matchAll(pattern)) {
    html += escapeHtml(value.slice(cursor, match.index));
    html += mathText(match[1] || match[2] || "");
    cursor = match.index + match[0].length;
  }
  html += escapeHtml(value.slice(cursor));
  return html;
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/'/g, "&#39;");
}

async function updateHighlight(bucket, id) {
  const item = state.records.find((record) => record[idKeys[state.activeTab]] === id || record[idKeys[record._kind]] === id);
  await api("/api/item/update", {
    method: "POST",
    body: JSON.stringify({ bucket, id, highlighted: !(item?.highlighted) }),
  });
  await loadView();
}

async function deleteRecord(bucket, id) {
  if (!window.confirm("Delete this local record?")) return;
  await api("/api/item/delete", { method: "POST", body: JSON.stringify({ bucket, id }) });
  await loadView();
}

async function postSupportedFeedback(ideaId) {
  await api("/api/library/feedback", {
    method: "POST",
    body: JSON.stringify({ field_id: state.fieldId, idea_id: ideaId, outcome_label: "supported", source: "user" }),
  });
  await loadView();
}

async function copyPromptPlan(ideaId) {
  const bundle = await api(`/api/library/assistant_export?field_id=${encodeURIComponent(state.fieldId)}&idea_id=${encodeURIComponent(ideaId)}&target_agent=codex`);
  const prompts = bundle.prompt_plan?.prompts || [];
  const text = prompts.map((step) => `${step.step_id} ${step.objective}\n\n${step.prompt_text}`).join("\n\n---\n\n");
  await navigator.clipboard.writeText(text || JSON.stringify(bundle, null, 2));
}

async function exportBundle(ideaId) {
  const bundle = await api(`/api/library/assistant_export?field_id=${encodeURIComponent(state.fieldId)}&idea_id=${encodeURIComponent(ideaId)}&target_agent=codex`);
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `PRINCIPIA_BUNDLE_${ideaId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function importFeedback() {
  const raw = window.prompt("Paste PRINCIPIA_FEEDBACK.json");
  if (!raw) return;
  const payload = JSON.parse(raw);
  payload.field_id = payload.field_id || state.fieldId;
  await api("/api/library/feedback", { method: "POST", body: JSON.stringify(payload) });
  await loadView();
}

document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    state.activeTab = normalizeTab(button.dataset.tab);
    history.replaceState(null, "", `?library=1&tab=${encodeURIComponent(state.activeTab)}&field_id=${encodeURIComponent(state.fieldId)}`);
    loadView().catch(showError);
  });
});

el("refreshBtn").addEventListener("click", () => loadView().catch(showError));
el("syncBtn").addEventListener("click", async () => {
  el("syncBtn").disabled = true;
  try {
    await api("/api/library/sync", {
      method: "POST",
      body: JSON.stringify({ field_id: state.fieldId, query: query() }),
    });
    await loadProjects();
    await loadView();
  } catch (err) {
    showError(err);
  } finally {
    el("syncBtn").disabled = false;
  }
});
el("importFeedbackBtn").addEventListener("click", () => importFeedback().catch(showError));
el("fieldSelect").addEventListener("change", () => {
  state.fieldId = el("fieldSelect").value || "default";
  loadView().catch(showError);
});
el("newProjectBtn").addEventListener("click", async () => {
  const name = window.prompt("Project name");
  if (!name) return;
  const project = await api("/api/library/project/create", {
    method: "POST",
    body: JSON.stringify({ name, query: query() }),
  });
  state.fieldId = project.field_id;
  await loadProjects();
  await loadView();
});
el("searchInput").addEventListener("input", () => {
  window.clearTimeout(window.__principiaLibrarySearch);
  window.__principiaLibrarySearch = window.setTimeout(() => loadView().catch(showError), 280);
});

document.body.addEventListener("click", async (event) => {
  const project = event.target.closest("[data-project]");
  if (project) {
    state.fieldId = project.dataset.project || "default";
    history.replaceState(null, "", `?library=1&tab=${encodeURIComponent(state.activeTab)}&field_id=${encodeURIComponent(state.fieldId)}`);
    loadView().catch(showError);
    return;
  }
  const rename = event.target.closest("[data-project-rename]");
  if (rename) {
    const current = state.projects.find((item) => item.field_id === rename.dataset.projectRename);
    const name = window.prompt("Rename project", current?.name || "");
    if (!name) return;
    await api("/api/library/project/update", {
      method: "POST",
      body: JSON.stringify({ field_id: rename.dataset.projectRename, name }),
    });
    await loadProjects();
    await loadView();
    return;
  }
  const deleteProject = event.target.closest("[data-project-delete]");
  if (deleteProject) {
    if (!window.confirm("Delete this project? Records remain in All Local Records.")) return;
    await api("/api/library/project/delete", {
      method: "POST",
      body: JSON.stringify({ field_id: deleteProject.dataset.projectDelete }),
    });
    state.fieldId = "default";
    await loadProjects();
    await loadView();
    return;
  }
  const open = event.target.closest("[data-open]");
  if (open && open.dataset.kind !== "graph") {
    const kind = open.dataset.kind;
    const id = open.dataset.open;
    const item = state.records.find((record) => record[idKeys[kind]] === id || record.principle_id === id || record.gap_id === id || record.run_id === id);
    if (kind === "works" && item) renderWorkDetail(item);
    if (kind === "principles" && item) renderPrincipleDetail(item);
    if ((kind === "insights" || kind === "novelty") && item) renderFactDetail(kind, item);
    if (kind === "benchmarks") {
      const benchmark = (state.collections.items || state.records || []).find((record) => record.benchmark_id === id);
      if (benchmark) renderBenchmarkDetail(benchmark);
    }
    if (kind === "baselines" && item) renderBaselineDetail(item);
    if (kind === "gaps" && item) renderGapDetail(item);
    if (kind === "ideas" && item) renderIdeaDetail(item);
    if (kind === "runs" && item) renderRunDetail(item);
  }
  const highlight = event.target.closest("[data-highlight]");
  if (highlight) updateHighlight(highlight.dataset.bucket, highlight.dataset.highlight).catch(showError);
  const del = event.target.closest("[data-delete]");
  if (del) deleteRecord(del.dataset.bucket, del.dataset.delete).catch(showError);
  const supported = event.target.closest("[data-feedback-supported]");
  if (supported) postSupportedFeedback(supported.dataset.feedbackSupported).catch(showError);
  const copy = event.target.closest("[data-copy-plan]");
  if (copy) copyPromptPlan(copy.dataset.copyPlan).catch(showError);
  const bundle = event.target.closest("[data-export-bundle]");
  if (bundle) exportBundle(bundle.dataset.exportBundle).catch(showError);
});

function showError(err) {
  el("mainPane").innerHTML = `<p class="error">${escapeHtml(err.message || String(err))}</p>`;
}

loadProjects()
  .then(loadView)
  .catch(showError);
