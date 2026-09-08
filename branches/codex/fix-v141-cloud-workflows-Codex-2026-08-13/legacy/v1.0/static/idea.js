const params = new URLSearchParams(window.location.search);
let relatedRows = [];
let principleNodes = [];
let principleEdges = [];
let principleMapData = null;
let selectedEdgeIndex = -1;
let lineageGraphData = null;
let lineageNodes = [];
let lineageEdges = [];
let selectedLineageEdgeIndex = -1;
let referenceLabels = {};
let lineageSymbolLabels = {};
let activeModalRef = null;
let dragState = null;
let suppressNodeClick = false;
let lineageDragState = null;
let suppressLineageNodeClick = false;
let nativeDragIndex = -1;
let currentIdea = null;
let currentMeta = {};
let regenerateRunId = "";
let regenerateTimer = null;
let relatedComparisonRunId = "";
let relatedComparisonTimer = null;
let redesignRunId = "";
let redesignTimer = null;
let comparisonWarning = "";
let principleZoom = 1;
let lineageZoom = 1;

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

async function api(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function block(title, content) {
  if (!content || (Array.isArray(content) && !content.length)) return "";
  const body = Array.isArray(content)
    ? `<ul>${content.map((item) => `<li>${formatValue(item)}</li>`).join("")}</ul>`
    : `<p>${escapeHtml(content)}</p>`;
  return `<section class="idea-section"><h2>${escapeHtml(title)}</h2>${body}</section>`;
}

function humanizeKey(key) {
  return String(key || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
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

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function graphZoomControls(target, zoom) {
  return `
    <div class="graph-toolbar" aria-label="${escapeHtml(target)} graph zoom controls">
      <button type="button" data-zoom-target="${escapeHtml(target)}" data-zoom-delta="-0.15">Zoom Out</button>
      <button type="button" data-zoom-target="${escapeHtml(target)}" data-zoom-reset="true">Reset</button>
      <button type="button" data-zoom-target="${escapeHtml(target)}" data-zoom-delta="0.15">Zoom In</button>
      <span>${Math.round(zoom * 100)}%</span>
    </div>
  `;
}

function scaledCanvasPoint(event, canvas, zoom) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left + canvas.scrollLeft) / zoom,
    y: (event.clientY - rect.top + canvas.scrollTop) / zoom,
  };
}

function updateGraphZoom(target, delta = 0, reset = false) {
  if (target === "lineage") {
    lineageZoom = reset ? 1 : clampNumber(lineageZoom + delta, 0.6, 1.8);
    const root = document.getElementById("symbolicLineage");
    root.innerHTML = renderLineageGraph(lineageGraphData || {});
    typesetMath(root);
    return;
  }
  principleZoom = reset ? 1 : clampNumber(principleZoom + delta, 0.6, 1.8);
  const root = document.getElementById("principleMap");
  root.innerHTML = renderPrincipleMap(principleMapData || {});
  typesetMath(root);
}

function realUserNote(idea) {
  const note = String(idea?.user_note || "").trim();
  if (!note) return "";
  if (/^redesign and improve the current idea/i.test(note)) return "";
  if (/related comparison rows:/i.test(note) && note.length > 800) return "";
  return note;
}

function linkifyReferences(value) {
  const text = String(value ?? "");
  if (!text) return "";
  const symbols = Object.keys(lineageSymbolLabels || {}).sort((a, b) => b.length - a.length);
  const escapedSymbols = symbols.map((symbol) => symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(
    escapedSymbols.length
      ? `\\b(?:MI|XI|P|TM|B|BL|W)-[A-Z0-9]+\\b|(?<![A-Za-z0-9_])(?:${escapedSymbols.join("|")})(?![A-Za-z0-9_])`
      : "\\b(?:MI|XI|P|TM|B|BL|W)-[A-Z0-9]+\\b",
    "g"
  );
  let cursor = 0;
  let output = "";
  for (const match of text.matchAll(pattern)) {
    const token = match[0];
    output += escapeHtml(text.slice(cursor, match.index));
    const ref = referenceLabels[token];
    if (ref) {
      output += `<button type="button" class="inline-ref" data-ref-id="${escapeHtml(token)}">${escapeHtml(ref.label || token)}</button>`;
    } else if (lineageSymbolLabels[token]) {
      output += `<button type="button" class="inline-ref symbol-ref" data-symbol-code="${escapeHtml(token)}">${escapeHtml(token)}</button>`;
    } else {
      output += escapeHtml(token);
    }
    cursor = match.index + token.length;
  }
  output += escapeHtml(text.slice(cursor));
  return output;
}

function expandableCell(value, key = "") {
  const text = String(value ?? "").trim();
  if (!text) return `<span class="muted">Not available</span>`;
  const needsToggle = text.length > 220;
  return `
    <div class="expand-cell ${needsToggle ? "collapsed" : ""}" data-expand-key="${escapeHtml(key)}">
      <div class="expand-cell-body">${linkifyReferences(text)}</div>
      ${
        needsToggle
          ? `<button type="button" class="show-more-btn" data-action="toggle-cell">Show more</button>`
          : ""
      }
    </div>
  `;
}

function richBlock(title, content) {
  if (!content || (Array.isArray(content) && !content.length)) return "";
  const body = Array.isArray(content)
    ? `<ul>${content.map((item) => `<li>${linkifyReferences(item)}</li>`).join("")}</ul>`
    : `<p>${linkifyReferences(content)}</p>`;
  return `<section class="idea-section"><h2>${escapeHtml(title)}</h2>${body}</section>`;
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

function renderRelated(rows) {
  relatedRows = rows || [];
  if (!relatedRows.length) {
    return `<p class="quality-warning">${escapeHtml(comparisonWarning || "No high-quality LLM comparison is available for this idea version.")}</p>`;
  }
  return `
    <table class="comparison-table">
      <thead>
        <tr>
          <th>Existed Idea</th>
          <th>Mechanistic Similarity</th>
          <th>Essential Difference</th>
          <th>Potential Advantage</th>
          <th>Potential Weakness</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        ${relatedRows
          .map(
            (row, index) => `
              <tr>
                <td><button type="button" class="link-button" data-related-index="${index}">${escapeHtml(row.title || row.source_paper_title || row.id || "Existed Idea")}</button></td>
                <td><strong>${escapeHtml(row.similarity)}</strong>${expandableCell(row.similarity_points || "", `sim-${index}`)}</td>
                <td>${expandableCell(row.differences, `diff-${index}`)}</td>
                <td>${expandableCell(row.potential_advantage, `adv-${index}`)}</td>
                <td>${expandableCell(row.potential_weakness, `weak-${index}`)}</td>
                <td>${row.source_paper_link ? `<a href="${escapeHtml(row.source_paper_link)}" target="_blank" rel="noreferrer">${escapeHtml(row.venue_or_source || row.year || "paper")}</a>` : escapeHtml(`${row.venue_or_source || ""} ${row.year || ""}`)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderPrincipleMap(map) {
  const nodes = map?.nodes || [];
  const edges = map?.edges || [];
  principleMapData = map || {};
  principleNodes = nodes;
  principleEdges = edges;
  if (!nodes.length) return `<p class="muted">No principle map has been derived yet.</p>`;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const height = Math.max(520, ...nodes.map((node) => Number(node.y || 80) + 120));
  const edgeHtml = edges
    .map((edge, edgeIndex) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return "";
      const x1 = Number(source.x || 80) + 250;
      const y1 = Number(source.y || 80) + 42;
      const x2 = Number(target.x || 680);
      const y2 = Number(target.y || 80) + 42;
      const mid = Math.round((x1 + x2) / 2);
      return `
        <path data-edge-index="${edgeIndex}" class="principle-edge ${edgeIndex === selectedEdgeIndex ? "selected" : ""} ${escapeHtml(edge.relation || "related")}" d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}" />
        <text data-edge-index="${edgeIndex}" class="principle-edge-label ${edgeIndex === selectedEdgeIndex ? "selected" : ""}" x="${mid - 36}" y="${Math.round((y1 + y2) / 2) - 6}">${escapeHtml((edge.relation || "related").replaceAll("_", " "))}</text>
      `;
    })
    .join("");
  const nodeHtml = nodes
    .map(
      (node, index) => `
        <button type="button" draggable="true" class="principle-map-node ${escapeHtml(node.type || "")}" style="left:${Number(node.x || 80)}px; top:${Number(node.y || 80)}px" data-principle-index="${index}">
          <span>${escapeHtml((node.type || "principle").replaceAll("_", " "))}</span>
          <strong title="${escapeHtml(node.full_label || node.label || node.id || "Principle")}">${escapeHtml(node.label || node.id || "Principle")}</strong>
          <small>${escapeHtml(node.source_paper_title || node.layer || "")}</small>
        </button>
      `
    )
    .join("");
  const width = 980;
  const zoom = principleZoom;
  const surfaceWidth = Math.ceil(width * zoom);
  const surfaceHeight = Math.ceil(height * zoom);
  return `
    ${graphZoomControls("principle", zoom)}
    <div class="principle-canvas" style="height:${height}px">
      <div class="graph-zoom-surface" style="width:${surfaceWidth}px; height:${surfaceHeight}px">
        <div class="graph-zoom-layer" style="width:${width}px; height:${height}px; transform: scale(${zoom})">
          <div class="canvas-legend">
            <span><i class="existing-dot"></i> Similar-idea principles</span>
            <span><i class="new-dot"></i> Generated idea principles</span>
          </div>
          <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${edgeHtml}</svg>
          ${renderEdgeInspector()}
          ${nodeHtml}
        </div>
      </div>
    </div>
  `;
}

function renderEdgeInspector() {
  const edge = principleEdges[selectedEdgeIndex];
  if (!edge) return `<aside class="edge-inspector muted">Click an edge to inspect the relationship.</aside>`;
  return `
    <aside class="edge-inspector active">
      <strong>${escapeHtml((edge.relation || "related").replaceAll("_", " "))}</strong>
      <p>${escapeHtml(edge.rationale || "")}</p>
    </aside>
  `;
}

function renderSources(sources) {
  if (!sources?.length) return `<p class="muted">No selected source evidence was stored.</p>`;
  return sources
    .map((ref) => {
      const item = ref.item || {};
      return `<article class="principle-node"><p class="eyebrow">${escapeHtml(ref.bucket)}</p><h3>${escapeHtml(item.title || item.name || item.id || ref.id)}</h3><p>${escapeHtml(item.idea_text || item.message_text || item.abstract_signature || item.summary || "")}</p></article>`;
    })
    .join("");
}

async function openRelated(index) {
  const row = relatedRows[index];
  if (!row) return;
  const query = new URLSearchParams({
    bucket: "existed_ideas",
    id: row.id,
    field_id: params.get("field_id") || "default",
    model_mode: params.get("model_mode") || "auto",
  });
  const data = await api(`/api/v2/item/detail?${query.toString()}`);
  const item = data.item || {};
  showInfoModal("Existed Idea", item.title || row.title, `
    ${block("Idea", item.idea_text || item.summary)}
    ${block("Mechanism", item.mechanism)}
    ${block("Source Paper", item.source_paper_title)}
    ${block("Venue / Year", `${item.venue_or_source || ""} ${item.year || ""}`)}
    ${item.source_paper_link ? `<section class="idea-section"><h2>Paper Link</h2><p><a href="${escapeHtml(item.source_paper_link)}" target="_blank" rel="noreferrer">${escapeHtml(item.source_paper_link)}</a></p></section>` : ""}
  `, { bucket: "existed_ideas", id: row.id });
}

async function init() {
  const query = new URLSearchParams({
    field_id: params.get("field_id") || "default",
    idea_id: params.get("idea_id") || "",
    model_mode: params.get("model_mode") || "auto",
    version: params.get("version") || "",
  });
  const data = await api(`/api/v2/my-idea/detail?${query.toString()}`);
  const idea = data.idea || {};
  const project = data.project || {};
  const meta = data.generation_meta || {};
  currentIdea = idea;
  currentMeta = meta;
  referenceLabels = data.reference_labels || {};
  comparisonWarning = data.comparison_warning || "";
  renderIdeaControls(idea, meta);
  document.getElementById("ideaTitle").textContent = idea.title || "My Idea";
  document.getElementById("ideaThesis").textContent = idea.one_sentence_thesis || idea.novelty_claim || "";
  document.getElementById("ideaCore").innerHTML = `
    ${block("Project Context", [`Project: ${project.name || idea.field_id || ""}`, `Goal: ${project.goal_text || project.query || ""}`])}
    ${block("Novelty Claim", idea.novelty_claim)}
    ${block("Mechanistic Design", idea.mechanistic_design)}
    ${block("Method Variants", idea.method_variants)}
    ${block("Derived Principles", idea.derived_principles)}
    ${block("Why It Might Work", idea.why_it_might_work)}
    ${block("Validation Protocol", idea.validation_protocol)}
    ${block("Relevant Baselines", idea.relevant_baselines)}
    ${block("Metrics", idea.metrics)}
    ${block("Risks", idea.risks)}
    ${block("User Note", realUserNote(idea))}
    ${block("Generation Metadata", [
      `Mode: ${meta.generation_mode || idea.generation_mode || "unknown"}`,
      `Model: ${meta.provider || ""} / ${meta.model_name || idea.model_name || ""}`,
      `Created: ${meta.created_at || idea.created_at || ""}`,
      `Selected evidence: ${(meta.selected_refs || idea.selected_refs || []).length}`,
      meta.llm_error || idea.llm_error || "",
    ].filter(Boolean))}
  `;
  document.getElementById("relatedTable").innerHTML = renderRelated(data.related_existed_ideas || []);
  if (!relatedComparisonRunId) document.getElementById("relatedComparisonStatus").textContent = relatedRows.length ? `Current comparison has ${relatedRows.length} row${relatedRows.length === 1 ? "" : "s"}.` : "";
  document.getElementById("principleMap").innerHTML = renderPrincipleMap(data.principle_map || {});
  document.getElementById("sourceEvidence").innerHTML = renderSources(data.source_evidence || []);
  loadSymbolicLineage().catch(() => {
    document.getElementById("symbolicLineage").innerHTML = `<p class="muted">No symbolic lineage graph is available for this idea version.</p>`;
  });
  typesetMath(document.body);
}

async function loadSymbolicLineage() {
  const ideaId = params.get("idea_id") || "";
  if (!ideaId) return;
  const graph = await api(`/api/v1/ideas/${encodeURIComponent(ideaId)}/lineage`);
  document.getElementById("symbolicLineage").innerHTML = renderLineageGraph(graph);
  typesetMath(document.getElementById("symbolicLineage"));
}

function renderLineageGraph(graph) {
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  lineageGraphData = graph || {};
  lineageNodes = nodes;
  lineageEdges = edges;
  if (!nodes.length) return `<p class="muted">No symbolic lineage graph is available for this idea version.</p>`;
  const depths = [...new Set(nodes.map((node) => Number(node.speculation_depth || 0)).sort((a, b) => a - b))];
  const byDepth = new Map(depths.map((depth) => [depth, nodes.filter((node) => Number(node.speculation_depth || 0) === depth)]));
  const positioned = nodes.map((node) => {
    const depth = Number(node.speculation_depth || 0);
    const layer = depths.indexOf(depth);
    const row = byDepth.get(depth)?.findIndex((entry) => entry.id === node.id) ?? 0;
    return {
      ...node,
      x: 42 + layer * 290,
      y: 96 + row * 168,
    };
  });
  lineageNodes = positioned;
  lineageSymbolLabels = Object.fromEntries(
    positioned
      .map((node) => [String(node.label || node.symbol_code || "").trim(), node])
      .filter(([symbol]) => symbol && symbol.length <= 48)
  );
  const byId = Object.fromEntries(positioned.map((node) => [node.id, node]));
  const width = Math.max(940, ...positioned.map((node) => node.x + 250));
  const height = Math.max(760, ...positioned.map((node) => node.y + 170));
  const zoom = lineageZoom;
  const surfaceWidth = Math.ceil(width * zoom);
  const surfaceHeight = Math.ceil(height * zoom);
  const edgeHtml = edges
    .map((edge, index) => {
      const source = byId[edge.source];
      const target = byId[edge.target];
      if (!source || !target) return "";
      const x1 = source.x + 210;
      const y1 = source.y + 48;
      const x2 = target.x;
      const y2 = target.y + 48;
      const mid = Math.round((x1 + x2) / 2);
      const selected = index === selectedLineageEdgeIndex ? "selected" : "";
      return `
        <path data-lineage-edge-index="${index}" class="lineage-edge ${selected}" d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}" />
        <text data-lineage-edge-index="${index}" class="lineage-edge-label ${selected}" x="${mid - 34}" y="${Math.round((y1 + y2) / 2) - 7}">${escapeHtml((edge.label || "supports").replaceAll("_", " "))}</text>
      `;
    })
    .join("");
  const nodeHtml = positioned
    .map(
      (node, index) => `
        <button type="button" class="lineage-graph-node ${escapeHtml(node.type || "")} ${escapeHtml(node.validation_status || "")}" style="left:${node.x}px; top:${node.y}px" data-lineage-node-index="${index}">
          <span>${escapeHtml(node.type || "node")} · L${escapeHtml(node.speculation_depth ?? 0)}</span>
          <strong>${escapeHtml(node.label || node.id)}</strong>
          <small>${escapeHtml(node.summary || node.expression || "Click to inspect this derivation node.")}</small>
        </button>
      `
    )
    .join("");
  return `
    <div class="lineage-graph">
      <div class="lineage-summary">
        <span class="badge">${escapeHtml(graph.derivation?.generation_mode || "principia_calculus")}</span>
        <span class="badge">${nodes.length} nodes</span>
        <span class="badge">${edges.length} edges</span>
        <span class="badge">${escapeHtml(graph.derivation?.status || "lineage")}</span>
      </div>
      ${graphZoomControls("lineage", zoom)}
      <div class="lineage-canvas" style="height:${height}px">
        <div class="graph-zoom-surface" style="width:${surfaceWidth}px; height:${surfaceHeight}px">
          <div class="graph-zoom-layer" style="width:${width}px; height:${height}px; transform: scale(${zoom})">
            <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${edgeHtml}</svg>
            ${nodeHtml}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderIdeaControls(idea, meta) {
  const modelSelect = document.getElementById("ideaModelMode");
  const currentMode = params.get("model_mode") || meta.model_mode || idea.model_mode || "auto";
  modelSelect.value = [...modelSelect.options].some((option) => option.value === currentMode) ? currentMode : "auto";
  const versions = meta.versions || idea.versions || [];
  const selectedVersion = params.get("version") || meta.version_id || idea.active_variant?.version_id || "";
  document.getElementById("ideaVersionSelect").innerHTML = versions.length
    ? versions
        .map((version) => {
          const label = `${version.is_user_edit ? "Manual" : version.provider || "model"} / ${version.model_name || version.model_mode || "version"} · ${version.extracted_at || ""}`;
          return `<option value="${escapeHtml(version.version_id)}" ${version.version_id === selectedVersion ? "selected" : ""}>${escapeHtml(label)}</option>`;
        })
        .join("")
    : `<option value="">Current</option>`;
  document.getElementById("ideaRunStatus").textContent = `Current: ${meta.provider || idea.provider || "model"} / ${meta.model_name || idea.model_name || "unknown"}`;
  renderIdeaEditFields(idea);
}

function ideaEditSchema() {
  return [
    { key: "title", label: "Title", type: "short" },
    { key: "one_sentence_thesis", label: "Short Thesis", type: "long" },
    { key: "novelty_claim", label: "Novelty Claim", type: "long" },
    { key: "mechanistic_design", label: "Mechanistic Design, one per line", type: "array" },
    { key: "method_variants", label: "Method Variants, one per line", type: "array" },
    { key: "why_it_might_work", label: "Why It Might Work, one per line", type: "array" },
    { key: "validation_protocol", label: "Validation Protocol, one per line", type: "array" },
    { key: "relevant_baselines", label: "Relevant Baselines, one per line", type: "array" },
    { key: "metrics", label: "Metrics, one per line", type: "array" },
    { key: "risks", label: "Risks, one per line", type: "array" },
    { key: "derived_principles", label: "Derived Principles, one per line", type: "array" },
  ];
}

function renderIdeaEditFields(idea) {
  const payload = idea.active_variant?.payload || idea;
  document.getElementById("ideaEditFields").innerHTML = ideaEditSchema()
    .map((field) => {
      const value = payload[field.key] ?? idea[field.key] ?? "";
      const text = field.type === "array" ? (Array.isArray(value) ? value.join("\n") : String(value || "")) : String(value ?? "");
      const rows = field.type === "short" ? 2 : field.type === "array" ? 4 : 5;
      return `
        <label class="full-field">
          <span>${escapeHtml(field.label)}</span>
          <textarea data-idea-edit-field="${escapeHtml(field.key)}" data-edit-type="${escapeHtml(field.type)}" rows="${rows}">${escapeHtml(text)}</textarea>
        </label>
      `;
    })
    .join("");
  document.getElementById("ideaEditInput").value = JSON.stringify(payload, null, 2);
}

function collectIdeaEditPayload() {
  const payload = {};
  document.querySelectorAll("[data-idea-edit-field]").forEach((field) => {
    const key = field.dataset.ideaEditField;
    const type = field.dataset.editType;
    const raw = field.value.trim();
    if (!raw) {
      payload[key] = type === "array" ? [] : "";
      return;
    }
    payload[key] = type === "array" ? raw.split(/\n+/).map((item) => item.trim()).filter(Boolean) : raw;
  });
  return payload;
}

async function saveIdeaEdit(event) {
  event.preventDefault();
  try {
    const advanced = document.getElementById("ideaEditInput").value.trim();
    const advancedPayload = advanced ? JSON.parse(advanced) : {};
    await post("/api/v2/item/update", {
      bucket: "my_ideas",
      id: params.get("idea_id") || "",
      payload: { ...advancedPayload, ...collectIdeaEditPayload() },
    });
    document.getElementById("ideaEditForm").hidden = true;
    await init();
  } catch (error) {
    alert(`Unable to save this idea edit: ${error.message}`);
  }
}

async function deleteIdea() {
  const title = document.getElementById("ideaTitle").textContent.trim() || params.get("idea_id") || "this idea";
  if (!confirm(`Delete "${title}"? This will remove the generated idea from its project.`)) return;
  await post("/api/v2/item/delete", { bucket: "my_ideas", id: params.get("idea_id") || "" });
  window.location.href = "/";
}

function exportIdeaMarkdown() {
  const query = new URLSearchParams({
    field_id: params.get("field_id") || "default",
    model_mode: document.getElementById("ideaModelMode").value || params.get("model_mode") || "auto",
    version: document.getElementById("ideaVersionSelect").value || params.get("version") || "",
  });
  window.open(`/api/v1/ideas/${encodeURIComponent(params.get("idea_id") || "")}/export?${query.toString()}`, "_blank");
}

function updateIdeaUrlVersion(versionId, modelMode) {
  const next = new URLSearchParams(window.location.search);
  if (versionId) next.set("version", versionId);
  else next.delete("version");
  if (modelMode) next.set("model_mode", modelMode);
  window.history.replaceState(null, "", `${window.location.pathname}?${next.toString()}`);
  params.set("model_mode", next.get("model_mode") || "auto");
  if (next.get("version")) params.set("version", next.get("version"));
  else params.delete("version");
}

async function regenerateIdea() {
  const modelMode = document.getElementById("ideaModelMode").value || "auto";
  const version = document.getElementById("ideaVersionSelect").value || params.get("version") || "";
  document.getElementById("regenerateIdeaBtn").disabled = true;
  document.getElementById("cancelRegenerateBtn").hidden = false;
  document.getElementById("ideaRunStatus").innerHTML = `
    <div class="status-line"><span class="status-spinner" aria-hidden="true"></span><strong>Starting regeneration...</strong></div>
  `;
  try {
    const result = await post("/api/v2/my-idea/regenerate/start", {
      field_id: params.get("field_id") || "default",
      idea_id: params.get("idea_id") || "",
      model_mode: modelMode,
      version,
    });
    regenerateRunId = result.run_id;
    pollRegenerate();
  } catch (error) {
    document.getElementById("regenerateIdeaBtn").disabled = false;
    document.getElementById("cancelRegenerateBtn").hidden = true;
    document.getElementById("ideaRunStatus").textContent = error.message || "Regeneration could not start.";
    alert(error.message || "Regeneration could not start.");
  }
}

async function pollRegenerate() {
  if (!regenerateRunId) return;
  clearTimeout(regenerateTimer);
  try {
    const data = await api(`/api/v2/llm/status?run_id=${encodeURIComponent(regenerateRunId)}`);
    const run = data.run || {};
    document.getElementById("ideaRunStatus").innerHTML = `
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml((run.stage || run.status || "regenerating").replaceAll("_", " "))}</strong>
        <span>${escapeHtml(run.message || "")}</span>
      </div>
    `;
    if (run.status === "complete") {
      const versionId = run.result_version_id || "";
      const modelMode = document.getElementById("ideaModelMode").value || "auto";
      regenerateRunId = "";
      document.getElementById("regenerateIdeaBtn").disabled = false;
      document.getElementById("cancelRegenerateBtn").hidden = true;
      updateIdeaUrlVersion(versionId, modelMode);
      await init();
      return;
    }
    if (run.status === "cancelled") {
      regenerateRunId = "";
      document.getElementById("regenerateIdeaBtn").disabled = false;
      document.getElementById("cancelRegenerateBtn").hidden = true;
      document.getElementById("ideaRunStatus").textContent = "Regeneration cancelled.";
      return;
    }
    if (run.status === "error") {
      regenerateRunId = "";
      document.getElementById("regenerateIdeaBtn").disabled = false;
      document.getElementById("cancelRegenerateBtn").hidden = true;
      alert(run.message || "The selected LLM could not regenerate this idea.");
      return;
    }
  } catch (error) {
    regenerateRunId = "";
    document.getElementById("regenerateIdeaBtn").disabled = false;
    document.getElementById("cancelRegenerateBtn").hidden = true;
    alert(error.message || "Regeneration status could not be loaded.");
    return;
  }
  regenerateTimer = setTimeout(pollRegenerate, 1200);
}

async function cancelRegenerate() {
  if (!regenerateRunId) return;
  await post("/api/v2/llm/cancel", { run_id: regenerateRunId });
  clearTimeout(regenerateTimer);
  regenerateRunId = "";
  document.getElementById("regenerateIdeaBtn").disabled = false;
  document.getElementById("cancelRegenerateBtn").hidden = true;
  document.getElementById("ideaRunStatus").textContent = "Regeneration cancelled.";
}

async function generateRelatedComparison() {
  const modelMode = document.getElementById("ideaModelMode").value || "auto";
  const version = document.getElementById("ideaVersionSelect").value || params.get("version") || "";
  document.getElementById("generateRelatedComparisonBtn").disabled = true;
  document.getElementById("cancelRelatedComparisonBtn").hidden = false;
  document.getElementById("relatedComparisonStatus").innerHTML = `
    <div class="status-line"><span class="status-spinner" aria-hidden="true"></span><strong>Starting related comparison...</strong></div>
  `;
  try {
    const result = await post("/api/v1/ideas/related-comparison/start", {
      field_id: params.get("field_id") || "default",
      idea_id: params.get("idea_id") || "",
      model_mode: modelMode,
      version,
    });
    relatedComparisonRunId = result.run_id;
    pollRelatedComparison();
  } catch (error) {
    document.getElementById("generateRelatedComparisonBtn").disabled = false;
    document.getElementById("cancelRelatedComparisonBtn").hidden = true;
    document.getElementById("relatedComparisonStatus").textContent = error.message || "Related comparison could not start.";
    alert(error.message || "Related comparison could not start.");
  }
}

async function pollRelatedComparison() {
  if (!relatedComparisonRunId) return;
  clearTimeout(relatedComparisonTimer);
  try {
    const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(relatedComparisonRunId)}`);
    const run = data.run || {};
    document.getElementById("relatedComparisonStatus").innerHTML = `
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml((run.stage || run.status || "comparing").replaceAll("_", " "))}</strong>
        <span>${escapeHtml(run.message || "")}</span>
      </div>
    `;
    if (Array.isArray(run.partial_related_rows) && run.partial_related_rows.length) {
      document.getElementById("relatedTable").innerHTML = renderRelated(run.partial_related_rows);
    }
    if (run.status === "complete") {
      relatedComparisonRunId = "";
      document.getElementById("generateRelatedComparisonBtn").disabled = false;
      document.getElementById("cancelRelatedComparisonBtn").hidden = true;
      await init();
      return;
    }
    if (run.status === "cancelled") {
      relatedComparisonRunId = "";
      document.getElementById("generateRelatedComparisonBtn").disabled = false;
      document.getElementById("cancelRelatedComparisonBtn").hidden = true;
      document.getElementById("relatedComparisonStatus").textContent = "Related comparison cancelled.";
      return;
    }
    if (run.status === "error") {
      relatedComparisonRunId = "";
      document.getElementById("generateRelatedComparisonBtn").disabled = false;
      document.getElementById("cancelRelatedComparisonBtn").hidden = true;
      const message = run.message || "The selected LLM could not generate a high-quality related-ideas comparison.";
      document.getElementById("relatedComparisonStatus").textContent = message;
      alert(message);
      return;
    }
  } catch (error) {
    relatedComparisonRunId = "";
    document.getElementById("generateRelatedComparisonBtn").disabled = false;
    document.getElementById("cancelRelatedComparisonBtn").hidden = true;
    alert(error.message || "Related comparison status could not be loaded.");
    return;
  }
  relatedComparisonTimer = setTimeout(pollRelatedComparison, 1200);
}

async function cancelRelatedComparison() {
  if (!relatedComparisonRunId) return;
  await post("/api/v1/research/cancel", { run_id: relatedComparisonRunId });
  clearTimeout(relatedComparisonTimer);
  relatedComparisonRunId = "";
  document.getElementById("generateRelatedComparisonBtn").disabled = false;
  document.getElementById("cancelRelatedComparisonBtn").hidden = true;
  document.getElementById("relatedComparisonStatus").textContent = "Related comparison cancelled.";
}

async function redesignFromComparison() {
  const modelMode = document.getElementById("ideaModelMode").value || "auto";
  const version = document.getElementById("ideaVersionSelect").value || params.get("version") || "";
  if (!relatedRows.length) {
    alert("Generate related-ideas comparison first, then redesign from those rows.");
    return;
  }
  document.getElementById("redesignFromComparisonBtn").disabled = true;
  document.getElementById("cancelRedesignBtn").hidden = false;
  document.getElementById("ideaRunStatus").innerHTML = `
    <div class="status-line"><span class="status-spinner" aria-hidden="true"></span><strong>Starting comparison-grounded redesign...</strong></div>
  `;
  try {
    const result = await post("/api/v1/ideas/redesign-from-comparison/start", {
      field_id: params.get("field_id") || "default",
      idea_id: params.get("idea_id") || "",
      model_mode: modelMode,
      version,
    });
    redesignRunId = result.run_id;
    pollRedesign();
  } catch (error) {
    document.getElementById("redesignFromComparisonBtn").disabled = false;
    document.getElementById("cancelRedesignBtn").hidden = true;
    document.getElementById("ideaRunStatus").textContent = error.message || "Redesign could not start.";
    alert(error.message || "Redesign could not start.");
  }
}

async function pollRedesign() {
  if (!redesignRunId) return;
  clearTimeout(redesignTimer);
  try {
    const data = await api(`/api/v1/research/status?run_id=${encodeURIComponent(redesignRunId)}`);
    const run = data.run || {};
    document.getElementById("ideaRunStatus").innerHTML = `
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml((run.stage || run.status || "redesigning").replaceAll("_", " "))}</strong>
        <span>${escapeHtml(run.message || "")}</span>
      </div>
    `;
    if (run.status === "complete") {
      const versionId = run.result_version_id || "";
      const modelMode = document.getElementById("ideaModelMode").value || "auto";
      redesignRunId = "";
      document.getElementById("redesignFromComparisonBtn").disabled = false;
      document.getElementById("cancelRedesignBtn").hidden = true;
      updateIdeaUrlVersion(versionId, modelMode);
      await init();
      return;
    }
    if (run.status === "cancelled") {
      redesignRunId = "";
      document.getElementById("redesignFromComparisonBtn").disabled = false;
      document.getElementById("cancelRedesignBtn").hidden = true;
      document.getElementById("ideaRunStatus").textContent = "Redesign cancelled.";
      return;
    }
    if (run.status === "error") {
      redesignRunId = "";
      document.getElementById("redesignFromComparisonBtn").disabled = false;
      document.getElementById("cancelRedesignBtn").hidden = true;
      alert(run.message || "The selected LLM could not redesign this idea.");
      return;
    }
  } catch (error) {
    redesignRunId = "";
    document.getElementById("redesignFromComparisonBtn").disabled = false;
    document.getElementById("cancelRedesignBtn").hidden = true;
    alert(error.message || "Redesign status could not be loaded.");
    return;
  }
  redesignTimer = setTimeout(pollRedesign, 1200);
}

async function cancelRedesign() {
  if (!redesignRunId) return;
  await post("/api/v1/research/cancel", { run_id: redesignRunId });
  clearTimeout(redesignTimer);
  redesignRunId = "";
  document.getElementById("redesignFromComparisonBtn").disabled = false;
  document.getElementById("cancelRedesignBtn").hidden = true;
  document.getElementById("ideaRunStatus").textContent = "Redesign cancelled.";
}

document.addEventListener("click", (event) => {
  const zoomButton = event.target.closest("[data-zoom-target]");
  if (zoomButton) {
    updateGraphZoom(
      zoomButton.dataset.zoomTarget || "principle",
      Number(zoomButton.dataset.zoomDelta || 0),
      zoomButton.dataset.zoomReset === "true"
    );
    return;
  }
  const toggleCell = event.target.closest("[data-action='toggle-cell']");
  if (toggleCell) {
    const cell = toggleCell.closest(".expand-cell");
    if (cell) {
      cell.classList.toggle("expanded");
      cell.classList.toggle("collapsed", !cell.classList.contains("expanded"));
      toggleCell.textContent = cell.classList.contains("expanded") ? "Show less" : "Show more";
    }
    return;
  }
  const inlineRef = event.target.closest("[data-ref-id]");
  if (inlineRef) {
    openReferenceDetail(inlineRef.dataset.refId);
    return;
  }
  const symbolRef = event.target.closest("[data-symbol-code]");
  if (symbolRef) {
    openLineageSymbol(symbolRef.dataset.symbolCode);
    return;
  }
  const edge = event.target.closest("[data-edge-index]");
  if (edge) {
    selectPrincipleEdge(Number(edge.dataset.edgeIndex));
    return;
  }
  const lineageEdge = event.target.closest("[data-lineage-edge-index]");
  if (lineageEdge) {
    openLineageEdge(Number(lineageEdge.dataset.lineageEdgeIndex));
    return;
  }
  const lineageNode = event.target.closest("[data-lineage-node-index]");
  if (lineageNode) {
    if (!suppressLineageNodeClick) openLineageNode(Number(lineageNode.dataset.lineageNodeIndex));
    suppressLineageNodeClick = false;
    return;
  }
  const button = event.target.closest("[data-related-index]");
  if (button) openRelated(Number(button.dataset.relatedIndex));
  const nodeButton = event.target.closest("[data-principle-index]");
  if (nodeButton && !suppressNodeClick) openPrincipleNode(Number(nodeButton.dataset.principleIndex));
  suppressNodeClick = false;
});

document.getElementById("closeExistedIdeaBtn").addEventListener("click", () => {
  document.getElementById("existedIdeaModal").hidden = true;
});

document.getElementById("existedIdeaModal").addEventListener("click", (event) => {
  if (event.target === document.getElementById("existedIdeaModal")) {
    document.getElementById("existedIdeaModal").hidden = true;
  }
});

async function openPrincipleNode(index) {
  const node = principleNodes[index];
  if (!node) return;
  if (node.ref_bucket === "principles" && node.ref_id) {
    await openReferenceDetailBy(node.ref_bucket, node.ref_id, node.full_label || node.label || "Principle");
    return;
  }
  showInfoModal((node.type || "principle").replaceAll("_", " "), node.full_label || node.label || "Principle", `
    ${block("Type", (node.type || "principle").replaceAll("_", " "))}
    ${block("Summary", node.summary)}
    ${block("Source Paper", node.source_paper_title)}
    ${node.source_paper_link ? `<section class="idea-section"><h2>Paper Link</h2><p><a href="${escapeHtml(node.source_paper_link)}" target="_blank" rel="noreferrer">${escapeHtml(node.source_paper_link)}</a></p></section>` : ""}
  `, node.ref_bucket && node.ref_id ? { bucket: node.ref_bucket, id: node.ref_id } : null);
}

function openLineageNode(index) {
  const node = lineageNodes[index];
  if (!node) return;
  showInfoModal("Lineage Node", node.label || node.id || "Derivation Node", `
    ${block("Type", `${node.type || "node"} · depth ${node.speculation_depth ?? 0}`)}
    ${block("Validation", [node.validation_status || "", node.verifier_status || ""].filter(Boolean))}
    ${richBlock("Expression", node.expression)}
    ${richBlock("Summary", node.summary)}
    ${block("Concept ID", node.concept_id)}
  `);
}

function openLineageSymbol(symbolCode) {
  const node = lineageSymbolLabels[String(symbolCode || "").trim()];
  if (!node) return;
  showInfoModal("Symbol", node.label || symbolCode || "Symbol", `
    ${block("Type", `${node.type || "node"} · depth ${node.speculation_depth ?? 0}`)}
    ${block("Validation", [node.validation_status || "", node.verifier_status || ""].filter(Boolean))}
    ${richBlock("Expression", node.expression)}
    ${richBlock("Summary", node.summary)}
    ${block("Concept ID", node.concept_id)}
  `);
}

function openLineageEdge(index) {
  selectedLineageEdgeIndex = index;
  const edge = lineageEdges[index];
  if (!edge) return;
  document.getElementById("symbolicLineage").innerHTML = renderLineageGraph(lineageGraphData || {});
  const byId = Object.fromEntries(lineageNodes.map((node) => [node.id, node]));
  showInfoModal("Lineage Edge", (edge.label || "supports").replaceAll("_", " "), `
    ${block("Source", byId[edge.source]?.label || edge.source)}
    ${block("Target", byId[edge.target]?.label || edge.target)}
    ${block("Rationale", edge.rationale)}
  `);
}

function showInfoModal(kind, title, bodyHtml, ref = null) {
  activeModalRef = ref;
  document.getElementById("existedIdeaKind").textContent = kind || "Details";
  document.getElementById("existedIdeaTitle").textContent = title || "Details";
  document.getElementById("existedIdeaBody").innerHTML = bodyHtml || "";
  document.getElementById("openModalDetailBtn").hidden = !ref;
  document.getElementById("existedIdeaModal").hidden = false;
  typesetMath(document.getElementById("existedIdeaModal"));
}

async function openReferenceDetail(refId) {
  const ref = referenceLabels[refId];
  if (!ref) return;
  await openReferenceDetailBy(ref.bucket, ref.id, ref.label || ref.id);
}

async function openReferenceDetailBy(bucket, id, fallbackLabel = "") {
  const query = new URLSearchParams({
    bucket,
    id,
    field_id: params.get("field_id") || "default",
    model_mode: params.get("model_mode") || "auto",
  });
  const data = await api(`/api/v2/item/detail?${query.toString()}`);
  const item = data.item || {};
  const title = item.title || item.name || item.benchmark_name || item.baseline_name || fallbackLabel || id;
  showInfoModal(bucket.replaceAll("_", " "), title, `
    ${block("Summary", item.idea_text || item.message_text || item.abstract_signature || item.description || item.summary || item.novelty_claim)}
    ${block("Mechanism / Principle", item.mechanism || item.principle)}
    ${block("Source Paper", item.source_paper_title)}
    ${block("Venue / Year", `${item.venue_or_source || ""} ${item.year || ""}`)}
    ${item.source_paper_link ? `<section class="idea-section"><h2>Paper Link</h2><p><a href="${escapeHtml(item.source_paper_link)}" target="_blank" rel="noreferrer">${escapeHtml(item.source_paper_link)}</a></p></section>` : ""}
  `, { bucket, id });
}

function openActiveModalDetail() {
  if (!activeModalRef) return;
  if (activeModalRef.bucket === "my_ideas") {
    window.open(`/idea.html?field_id=${encodeURIComponent(params.get("field_id") || "default")}&idea_id=${encodeURIComponent(activeModalRef.id)}&model_mode=${encodeURIComponent(params.get("model_mode") || "auto")}`, "_blank");
    return;
  }
  window.open(`/item.html?bucket=${encodeURIComponent(activeModalRef.bucket)}&id=${encodeURIComponent(activeModalRef.id)}&field_id=${encodeURIComponent(params.get("field_id") || "default")}&model_mode=${encodeURIComponent(params.get("model_mode") || "auto")}`, "_blank");
}

function selectPrincipleEdge(index) {
  selectedEdgeIndex = index;
  document.getElementById("principleMap").innerHTML = renderPrincipleMap(principleMapData || {});
}

function updatePrincipleEdges() {
  const byId = new Map(principleNodes.map((node) => [node.id, node]));
  principleEdges.forEach((edge, index) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) return;
    const x1 = Number(source.x || 80) + 250;
    const y1 = Number(source.y || 80) + 42;
    const x2 = Number(target.x || 680);
    const y2 = Number(target.y || 80) + 42;
    const mid = Math.round((x1 + x2) / 2);
    const path = document.querySelector(`.principle-edge[data-edge-index="${index}"]`);
    const label = document.querySelector(`.principle-edge-label[data-edge-index="${index}"]`);
    if (path) path.setAttribute("d", `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`);
    if (label) {
      label.setAttribute("x", String(mid - 36));
      label.setAttribute("y", String(Math.round((y1 + y2) / 2) - 6));
    }
  });
}

function updateLineageEdges() {
  const byId = new Map(lineageNodes.map((node) => [node.id, node]));
  lineageEdges.forEach((edge, index) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) return;
    const x1 = Number(source.x || 42) + 210;
    const y1 = Number(source.y || 88) + 48;
    const x2 = Number(target.x || 42);
    const y2 = Number(target.y || 88) + 48;
    const mid = Math.round((x1 + x2) / 2);
    const path = document.querySelector(`.lineage-edge[data-lineage-edge-index="${index}"]`);
    const label = document.querySelector(`.lineage-edge-label[data-lineage-edge-index="${index}"]`);
    if (path) path.setAttribute("d", `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`);
    if (label) {
      label.setAttribute("x", String(mid - 34));
      label.setAttribute("y", String(Math.round((y1 + y2) / 2) - 7));
    }
  });
}

function startLineageNodeDrag(event) {
  if (lineageDragState) return;
  const nodeButton = event.target.closest("[data-lineage-node-index]");
  if (!nodeButton || (event.button != null && event.button !== 0)) return;
  const index = Number(nodeButton.dataset.lineageNodeIndex);
  const canvas = nodeButton.closest(".lineage-canvas");
  if (!canvas || !Number.isFinite(index)) return;
  event.preventDefault?.();
  const point = scaledCanvasPoint(event, canvas, lineageZoom);
  const left = Number(String(nodeButton.style.left || "0").replace("px", ""));
  const top = Number(String(nodeButton.style.top || "0").replace("px", ""));
  lineageDragState = {
    index,
    node: nodeButton,
    canvas,
    offsetX: point.x - left,
    offsetY: point.y - top,
    moved: false,
  };
  nodeButton.classList.add("dragging");
  if (event.pointerId != null) nodeButton.setPointerCapture?.(event.pointerId);
}

function moveLineageNodeDrag(event) {
  if (!lineageDragState) return;
  event.preventDefault?.();
  const point = scaledCanvasPoint(event, lineageDragState.canvas, lineageZoom);
  const maxX = Math.max(20, lineageDragState.canvas.scrollWidth / lineageZoom - 240);
  const x = Math.max(20, Math.min(maxX, point.x - lineageDragState.offsetX));
  const y = Math.max(50, point.y - lineageDragState.offsetY);
  const node = lineageNodes[lineageDragState.index];
  if (!node) return;
  node.x = Math.round(x);
  node.y = Math.round(y);
  lineageDragState.node.style.left = `${node.x}px`;
  lineageDragState.node.style.top = `${node.y}px`;
  lineageDragState.moved = true;
  updateLineageEdges();
}

function endLineageNodeDrag() {
  if (!lineageDragState) return;
  suppressLineageNodeClick = Boolean(lineageDragState.moved);
  lineageDragState.node.classList.remove("dragging");
  lineageDragState = null;
}

function startNodeDrag(event) {
  if (dragState) return;
  const nodeButton = event.target.closest("[data-principle-index]");
  if (!nodeButton || (event.button != null && event.button !== 0)) return;
  const index = Number(nodeButton.dataset.principleIndex);
  const canvas = nodeButton.closest(".principle-canvas");
  if (!canvas || !Number.isFinite(index)) return;
  event.preventDefault?.();
  const point = scaledCanvasPoint(event, canvas, principleZoom);
  const left = Number(String(nodeButton.style.left || "0").replace("px", ""));
  const top = Number(String(nodeButton.style.top || "0").replace("px", ""));
  dragState = {
    index,
    node: nodeButton,
    canvas,
    offsetX: point.x - left,
    offsetY: point.y - top,
    moved: false,
  };
  nodeButton.classList.add("dragging");
  if (event.pointerId != null) nodeButton.setPointerCapture?.(event.pointerId);
}

function moveNodeDrag(event) {
  if (!dragState) return;
  event.preventDefault?.();
  const point = scaledCanvasPoint(event, dragState.canvas, principleZoom);
  const maxX = Math.max(20, dragState.canvas.scrollWidth / principleZoom - 270);
  const x = Math.max(20, Math.min(maxX, point.x - dragState.offsetX));
  const y = Math.max(50, point.y - dragState.offsetY);
  const node = principleNodes[dragState.index];
  if (!node) return;
  node.x = Math.round(x);
  node.y = Math.round(y);
  dragState.node.style.left = `${node.x}px`;
  dragState.node.style.top = `${node.y}px`;
  dragState.moved = true;
  updatePrincipleEdges();
}

function endNodeDrag() {
  if (!dragState) return;
  suppressNodeClick = Boolean(dragState.moved);
  dragState.node.classList.remove("dragging");
  dragState = null;
}

document.addEventListener("pointerdown", startNodeDrag);
document.addEventListener("pointermove", moveNodeDrag);
document.addEventListener("pointerup", endNodeDrag);
document.addEventListener("mousedown", startNodeDrag);
document.addEventListener("mousemove", moveNodeDrag);
document.addEventListener("mouseup", endNodeDrag);
document.addEventListener("pointerdown", startLineageNodeDrag);
document.addEventListener("pointermove", moveLineageNodeDrag);
document.addEventListener("pointerup", endLineageNodeDrag);
document.addEventListener("mousedown", startLineageNodeDrag);
document.addEventListener("mousemove", moveLineageNodeDrag);
document.addEventListener("mouseup", endLineageNodeDrag);

document.addEventListener("dragstart", (event) => {
  const nodeButton = event.target.closest("[data-principle-index]");
  if (!nodeButton) return;
  nativeDragIndex = Number(nodeButton.dataset.principleIndex);
  event.dataTransfer?.setData("text/plain", String(nativeDragIndex));
  event.dataTransfer?.setDragImage?.(nodeButton, 24, 24);
});

document.addEventListener("dragover", (event) => {
  if (event.target.closest(".principle-canvas")) event.preventDefault();
});

document.addEventListener("drop", (event) => {
  const canvas = event.target.closest(".principle-canvas");
  const index = Number(event.dataTransfer?.getData("text/plain") || nativeDragIndex);
  if (!canvas || !Number.isFinite(index) || index < 0) return;
  event.preventDefault();
  const node = principleNodes[index];
  const nodeButton = document.querySelector(`.principle-map-node[data-principle-index="${index}"]`);
  if (!node || !nodeButton) return;
  const point = scaledCanvasPoint(event, canvas, principleZoom);
  const maxX = Math.max(20, canvas.scrollWidth / principleZoom - 270);
  node.x = Math.max(20, Math.min(maxX, Math.round(point.x - 125)));
  node.y = Math.max(50, Math.round(point.y - 42));
  nodeButton.style.left = `${node.x}px`;
  nodeButton.style.top = `${node.y}px`;
  nativeDragIndex = -1;
  suppressNodeClick = true;
  updatePrincipleEdges();
});

document.getElementById("openModalDetailBtn").addEventListener("click", openActiveModalDetail);
document.getElementById("editIdeaBtn").addEventListener("click", () => {
  document.getElementById("ideaEditForm").hidden = false;
  document.getElementById("ideaEditForm").scrollIntoView({ block: "nearest" });
});
document.getElementById("cancelIdeaEditBtn").addEventListener("click", () => {
  document.getElementById("ideaEditForm").hidden = true;
});
document.getElementById("ideaEditForm").addEventListener("submit", saveIdeaEdit);
document.getElementById("exportIdeaMarkdownBtn").addEventListener("click", exportIdeaMarkdown);
document.getElementById("regenerateIdeaBtn").addEventListener("click", regenerateIdea);
document.getElementById("cancelRegenerateBtn").addEventListener("click", () => {
  cancelRegenerate().catch((error) => alert(error.message || "Unable to cancel regeneration."));
});
document.getElementById("generateRelatedComparisonBtn").addEventListener("click", generateRelatedComparison);
document.getElementById("cancelRelatedComparisonBtn").addEventListener("click", () => {
  cancelRelatedComparison().catch((error) => alert(error.message || "Unable to cancel related comparison."));
});
document.getElementById("redesignFromComparisonBtn").addEventListener("click", redesignFromComparison);
document.getElementById("cancelRedesignBtn").addEventListener("click", () => {
  cancelRedesign().catch((error) => alert(error.message || "Unable to cancel redesign."));
});
document.getElementById("deleteIdeaBtn").addEventListener("click", () => {
  deleteIdea().catch((error) => alert(error.message || "Unable to delete this idea."));
});
document.getElementById("ideaVersionSelect").addEventListener("change", async () => {
  const version = document.getElementById("ideaVersionSelect").value || "";
  updateIdeaUrlVersion(version, document.getElementById("ideaModelMode").value || "auto");
  await init();
});
document.getElementById("ideaModelMode").addEventListener("change", () => {
  updateIdeaUrlVersion(document.getElementById("ideaVersionSelect").value || "", document.getElementById("ideaModelMode").value || "auto");
});

init().catch((error) => {
  document.getElementById("ideaTitle").textContent = "Unable to load idea";
  document.getElementById("ideaThesis").textContent = error.message;
});
