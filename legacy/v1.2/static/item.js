const params = new URLSearchParams(window.location.search);
let currentItem = null;
let currentRunId = "";
let currentRunTimer = null;

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

function isUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function compact(value, length = 180) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, Math.max(0, length - 3)).trim()}...`;
}

function modelModeFromCloudKey(modelKey) {
  return String(modelKey || "").split(":")[2] || "";
}

function modelNameFromCloudKey(modelKey) {
  return String(modelKey || "").split(":")[1] || "";
}

function cloudOriginForItem(item) {
  const origin = item.cloud_origin || item.active_variant?.payload?.cloud_origin || item.active_variant?.cloud_origin || {};
  return origin && typeof origin === "object" ? origin : {};
}

function cloudOriginMatchesTarget(item) {
  const origin = cloudOriginForItem(item);
  if (!origin.cloud_snapshot_id) return false;
  const mode = document.getElementById("itemModelMode")?.value || params.get("model_mode") || "auto";
  if (mode === "auto") return true;
  const originMode = origin.cloud_model_mode || origin.model_mode || modelModeFromCloudKey(origin.cloud_model_key || origin.model_key || "");
  return originMode === mode;
}

function cloudSyncMatchesTarget(item) {
  if (item.cloud_sync_status !== "synced") return false;
  const mode = document.getElementById("itemModelMode")?.value || params.get("model_mode") || "auto";
  if (mode === "auto") return true;
  const syncByModel = item.cloud_sync_by_model && typeof item.cloud_sync_by_model === "object" ? item.cloud_sync_by_model : {};
  const modes = [];
  for (const key of [item.cloud_sync_model_key, item.model_key, ...Object.keys(syncByModel)].filter(Boolean)) {
    const keyMode = modelModeFromCloudKey(key);
    if (keyMode && !modes.includes(keyMode)) modes.push(keyMode);
  }
  for (const entry of Object.values(syncByModel)) {
    if (entry?.model_mode && !modes.includes(entry.model_mode)) modes.push(entry.model_mode);
  }
  if (item.model_mode && !modes.includes(item.model_mode)) modes.push(item.model_mode);
  return !modes.length || modes.includes(mode);
}

function cloudRecordMatchesTarget(item) {
  return cloudOriginMatchesTarget(item) || cloudSyncMatchesTarget(item);
}

function renderCloudBadge(item) {
  const badge = document.getElementById("itemCloudBadge");
  if (!badge) return;
  const origin = cloudOriginForItem(item);
  const visible = cloudRecordMatchesTarget(item);
  badge.hidden = !visible;
  if (visible) {
    const modelName = modelNameFromCloudKey(origin.cloud_model_key || origin.model_key || item.cloud_sync_model_key || item.model_key || "");
    badge.title = modelName ? `Cloud DB record from ${modelName}` : "Cloud DB record";
  }
}

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

function block(title, content) {
  if (!content || (Array.isArray(content) && !content.length)) return "";
  const body = Array.isArray(content)
    ? `<ul>${content.map((item) => `<li>${formatValue(item)}</li>`).join("")}</ul>`
    : `<p>${formatValue(content)}</p>`;
  return `<section><h3>${escapeHtml(title)}</h3>${body}</section>`;
}

function linkBlock(item) {
  const urls = [
    item.source_paper_link,
    item.paper_link,
    item.official_url,
    item.official_code_url,
    ...(item.source_paper_links || []),
    ...(item.source_urls || []),
  ].filter(isUrl);
  const unique = [...new Set(urls)];
  if (!unique.length) return "";
  return `<section><h3>Links</h3><ul>${unique.map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></li>`).join("")}</ul></section>`;
}

function performanceTable(rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  return `
    <section class="wide-section">
      <h3>Performance</h3>
      <table class="mini-table">
        <thead><tr><th>Benchmark</th><th>Method</th><th>Metric</th><th>Result</th><th>Evidence</th></tr></thead>
        <tbody>
          ${rows.slice(0, 30).map((row) => {
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

function sourceWorksBlock(item) {
  const rows = (item.source_work_details || []).map(
    (work) =>
      `<li><a href="${escapeHtml(work.url_or_doi || "#")}" target="_blank" rel="noreferrer">${escapeHtml(work.title || work.work_id)}</a> ${escapeHtml(work.venue_or_source || "")} ${escapeHtml(work.year || "")}</li>`
  );
  return `<section><h3>Source Works</h3><ul>${rows.join("") || "<li>No linked source works.</li>"}</ul></section>`;
}

function versionBlock(item) {
  const version = item.active_variant || {};
  return `
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
}

function detailIdFor(bucket, item) {
  return String(
    item.detail_id ||
      item.canonical_id ||
      item.principle_id ||
      item.benchmark_id ||
      item.baseline_id ||
      item.idea_id ||
      item.work_id ||
      ""
  );
}

function detailTitleFor(bucket, item) {
  if (bucket === "benchmark_records") return item.benchmark_name || item.dataset || item.canonical_label || "Benchmark";
  if (bucket === "baseline_records") return item.baseline_name || item.canonical_label || "Baseline";
  if (bucket === "principles") return item.name || item.title || item.argument || "Principle";
  if (bucket === "takeaway_messages") return item.title || item.main_results || item.message_text || "Takeaway";
  if (bucket === "existed_ideas") return item.title || item.core_idea || item.idea_text || "Existed Idea";
  return item.title || item.name || item.work_id || "Record";
}

function detailSummaryFor(bucket, item) {
  if (bucket === "benchmark_records") return item.task || item.description || item.payload_summary || "";
  if (bucket === "baseline_records") return item.core_idea || item.methodology || item.description || item.payload_summary || "";
  if (bucket === "principles") return item.argument || item.abstract_signature || item.payload_summary || "";
  if (bucket === "takeaway_messages") return item.main_results || item.message_text || item.actionable_lesson || item.payload_summary || "";
  if (bucket === "existed_ideas") return item.core_idea || item.idea_text || item.mechanism || item.payload_summary || "";
  return item.summary || item.payload_summary || "";
}

function detailHref(bucket, id) {
  const query = new URLSearchParams({
    bucket,
    id,
    model_mode: params.get("model_mode") || document.getElementById("itemModelMode")?.value || "auto",
  });
  const fieldId = params.get("field_id") || "";
  if (fieldId) query.set("field_id", fieldId);
  return `/item.html?${query.toString()}`;
}

function workExtractionBlock(item) {
  const groups = item.work_extractions?.groups || {};
  const total = Number(item.work_extractions?.total || item.work_extraction_counts?.total || 0);
  const modelSelect = document.getElementById("itemModelMode");
  const selectedLabel = modelSelect?.selectedOptions?.[0]?.textContent?.trim() || "";
  const modelName = selectedLabel || item.work_extractions?.model_mode || item.model_name || item.active_variant?.model_name || "";
  const groupHtml = Object.entries(groups)
    .filter(([, group]) => Number(group?.total || group?.items?.length || 0) > 0)
    .map(([bucket, group]) => {
      const rows = (group.items || []).slice(0, 20).map((record) => {
        const id = detailIdFor(bucket, record);
        const title = detailTitleFor(bucket, record);
        const summary = detailSummaryFor(bucket, record);
        return `
          <li>
            <a href="${escapeHtml(detailHref(bucket, id))}" target="_blank" rel="noreferrer">${escapeHtml(compact(title, 120))}</a>
            ${summary ? `<p>${escapeHtml(compact(summary, 180))}</p>` : ""}
          </li>
        `;
      });
      return `
        <section class="work-extraction-panel">
          <h3>${escapeHtml(group.label || humanizeKey(bucket))} <span>${Number(group.total || group.items?.length || 0)}</span></h3>
          <ul>${rows.join("")}</ul>
        </section>
      `;
    })
    .join("");
  return `
    <section class="wide-section work-extraction-overview">
      <div class="section-heading-row">
        <div>
          <h2>Current LLM Extraction</h2>
          <p>${escapeHtml(modelName ? `${modelName} · ${total} extracted item(s)` : `${total} extracted item(s)`)}</p>
        </div>
      </div>
      ${groupHtml ? `<div class="work-extraction-grid">${groupHtml}</div>` : `<p class="subtle">No extracted records are available for this LLM version yet.</p>`}
    </section>
  `;
}

function renderItemBody(item, bucket) {
  const shared = `${linkBlock(item)}${sourceWorksBlock(item)}${block("Evidence", item.evidence)}${versionBlock(item)}`;
  if (bucket === "source_works") {
    return `
      <div class="idea-grid">
        ${block("Abstract", item.abstract || item.summary || "No abstract available.")}
        ${block("Publication", [item.venue_or_source, item.year, item.source_type].filter(Boolean).join(" · "))}
        ${block("Authors", item.authors)}
      </div>
      ${workExtractionBlock(item)}
      ${linkBlock(item)}
      ${versionBlock(item)}
    `;
  }
  if (bucket === "benchmark_records") {
    return `
      <div class="idea-grid">
        ${block("Benchmark", item.description || item.benchmark_name)}
        ${block("Task", item.task)}
        ${block("Data Form", item.data_form)}
        ${block("Scale", item.scale)}
        ${block("Metrics", item.metrics || item.metric)}
        ${block("Candidate Dataset Pages", item.candidate_dataset_pages)}
      </div>
      ${shared}
    `;
  }
  if (bucket === "baseline_records") {
    return `
      <div class="idea-grid">
        ${block("Core Idea", item.core_idea || item.description || item.summary)}
        ${block("Methodology", item.methodology || item.principle)}
        ${block("Discussion", item.discussion)}
        ${block("Baseline Type", item.baseline_type)}
        ${block("Benchmarks", item.benchmarks)}
      </div>
      ${performanceTable(item.performance)}
      ${shared}
    `;
  }
  if (bucket === "principles") {
    return `
      <div class="idea-grid">
        ${block("Argument", item.argument || item.abstract_signature)}
        ${block("Discussion", item.discussion)}
        ${block("Boundary Conditions", item.boundary_conditions)}
      </div>
      ${shared}
    `;
  }
  if (bucket === "existed_ideas") {
    return `
      <div class="idea-grid">
        ${block("Core Idea", item.core_idea || item.idea_text || item.summary)}
        ${block("Mechanism", item.mechanism)}
        ${block("Discussion", item.discussion)}
      </div>
      ${shared}
    `;
  }
  if (bucket === "takeaway_messages") {
    return `
      <div class="idea-grid">
        ${block("Main Results", item.main_results || item.message_text)}
        ${block("Condition", item.condition)}
        ${block("Discussion", item.discussion)}
        ${block("Actionable Lesson", item.actionable_lesson)}
      </div>
      ${shared}
    `;
  }
  return `
    <div class="idea-grid">
      ${block("Core Idea", item.idea_text || item.message_text || item.description || item.summary || item.abstract_signature)}
      ${block("Mechanism / Principle", item.mechanism || item.principle)}
      ${block("Condition", item.condition)}
      ${block("Finding", item.finding)}
      ${block("Actionable Lesson", item.actionable_lesson)}
    </div>
    ${shared}
  `;
}

function updateUrl(version = "", modelMode = "") {
  const next = new URLSearchParams(window.location.search);
  if (version) next.set("version", version);
  else next.delete("version");
  if (modelMode) next.set("model_mode", modelMode);
  window.history.replaceState(null, "", `${window.location.pathname}?${next.toString()}`);
  params.set("model_mode", next.get("model_mode") || "auto");
  if (next.get("version")) params.set("version", next.get("version"));
  else params.delete("version");
}

function renderControls(item) {
  const modelSelect = document.getElementById("itemModelMode");
  const modelMode = params.get("model_mode") || item.model_mode || "auto";
  modelSelect.value = [...modelSelect.options].some((option) => option.value === modelMode) ? modelMode : "auto";
  const versions = item.versions || [];
  const activeVersion = params.get("version") || item.active_variant?.version_id || "";
  document.getElementById("itemVersionSelect").innerHTML = versions.length
    ? versions
        .map((version) => {
          const label = `${version.is_user_edit ? "Manual" : version.provider || "model"} / ${version.model_name || version.model_mode || "version"} · ${version.extracted_at || ""}`;
          return `<option value="${escapeHtml(version.version_id)}" ${version.version_id === activeVersion ? "selected" : ""}>${escapeHtml(label)}</option>`;
        })
        .join("")
    : `<option value="">Current</option>`;
  document.getElementById("itemRunStatus").textContent = `Current: ${item.active_variant?.provider || item.provider || "model"} / ${item.active_variant?.model_name || item.model_name || "unknown"}`;
  renderEditFields(item);
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

function renderEditFields(item) {
  const bucket = params.get("bucket") || "";
  const payload = item.active_variant?.payload || item;
  document.getElementById("itemEditFields").innerHTML = editSchemaFor(bucket)
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
  document.getElementById("itemEditInput").value = JSON.stringify(payload, null, 2);
}

function collectEditPayload() {
  const payload = {};
  document.querySelectorAll("[data-edit-field]").forEach((field) => {
    const key = field.dataset.editField;
    const type = field.dataset.editType;
    const raw = field.value.trim();
    if (!raw) {
      payload[key] = type === "array" || type === "json" ? [] : "";
      return;
    }
    if (type === "array") payload[key] = raw.split(/\n+/).map((item) => item.trim()).filter(Boolean);
    else if (type === "json") payload[key] = JSON.parse(raw);
    else payload[key] = raw;
  });
  return payload;
}

async function saveEdit(event) {
  event.preventDefault();
  const bucket = params.get("bucket") || "";
  const id = params.get("id") || "";
  try {
    const advanced = document.getElementById("itemEditInput").value.trim();
    const advancedPayload = advanced ? JSON.parse(advanced) : {};
    const result = await post("/api/v2/item/update", {
      bucket,
      id,
      payload: { ...advancedPayload, ...collectEditPayload() },
    });
    currentItem = result.item;
    document.getElementById("itemEditForm").hidden = true;
    renderLoadedItem(currentItem, bucket);
  } catch (error) {
    alert(`Unable to save this edit: ${error.message}`);
  }
}

async function regenerateItem() {
  const bucket = params.get("bucket") || "";
  const id = params.get("id") || "";
  const modelMode = document.getElementById("itemModelMode").value || "auto";
  document.getElementById("refreshItemBtn").disabled = true;
  document.getElementById("cancelRefreshItemBtn").hidden = false;
  document.getElementById("itemRunStatus").innerHTML = `<div class="status-line"><span class="status-spinner" aria-hidden="true"></span><strong>Starting regeneration...</strong></div>`;
  try {
    const result = await post("/api/v2/item/refresh/start", {
      field_id: params.get("field_id") || "default",
      bucket,
      id,
      model_mode: modelMode,
    });
    currentRunId = result.run_id;
    pollRegeneration();
  } catch (error) {
    document.getElementById("refreshItemBtn").disabled = false;
    document.getElementById("cancelRefreshItemBtn").hidden = true;
    alert(error.message || "Regeneration could not start.");
  }
}

async function pollRegeneration() {
  if (!currentRunId) return;
  clearTimeout(currentRunTimer);
  const runStatus = document.getElementById("itemRunStatus");
  try {
    const data = await api(`/api/v2/llm/status?run_id=${encodeURIComponent(currentRunId)}`);
    const run = data.run || {};
    runStatus.innerHTML = `
      <div class="status-line">
        ${["queued", "running"].includes(run.status || "") ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}
        <strong>${escapeHtml((run.stage || run.status || "regenerating").replaceAll("_", " "))}</strong>
        <span>${escapeHtml(run.message || "")}</span>
      </div>
    `;
    if (run.status === "complete") {
      const version = run.result_version_id || "";
      currentRunId = "";
      document.getElementById("refreshItemBtn").disabled = false;
      document.getElementById("cancelRefreshItemBtn").hidden = true;
      updateUrl(version, document.getElementById("itemModelMode").value || "auto");
      await init();
      return;
    }
    if (run.status === "cancelled") {
      currentRunId = "";
      document.getElementById("refreshItemBtn").disabled = false;
      document.getElementById("cancelRefreshItemBtn").hidden = true;
      runStatus.textContent = "Regeneration cancelled.";
      return;
    }
    if (run.status === "error") {
      currentRunId = "";
      document.getElementById("refreshItemBtn").disabled = false;
      document.getElementById("cancelRefreshItemBtn").hidden = true;
      alert(run.message || "Regeneration failed.");
      return;
    }
  } catch (error) {
    currentRunId = "";
    document.getElementById("refreshItemBtn").disabled = false;
    document.getElementById("cancelRefreshItemBtn").hidden = true;
    alert(error.message || "Regeneration status could not be loaded.");
    return;
  }
  currentRunTimer = setTimeout(pollRegeneration, 1200);
}

async function cancelRegeneration() {
  if (!currentRunId) return;
  await post("/api/v2/llm/cancel", { run_id: currentRunId });
  clearTimeout(currentRunTimer);
  currentRunId = "";
  document.getElementById("refreshItemBtn").disabled = false;
  document.getElementById("cancelRefreshItemBtn").hidden = true;
  document.getElementById("itemRunStatus").textContent = "Regeneration cancelled.";
}

async function deleteItem() {
  const bucket = params.get("bucket") || "";
  const id = params.get("id") || "";
  const title = document.getElementById("itemTitle").textContent.trim() || id;
  if (!confirm(`Delete "${title}"? This will remove the record and its project links.`)) return;
  await post("/api/v2/item/delete", { bucket, id });
  window.location.href = "/";
}

function renderLoadedItem(item, bucket) {
  document.getElementById("itemKind").textContent = bucket.replaceAll("_", " ") || "record";
  document.getElementById("itemTitle").textContent = item.title || item.name || item.benchmark_name || item.baseline_name || "Record";
  renderControls(item);
  renderCloudBadge(item);
  document.getElementById("itemSummary").textContent =
    item.idea_text || item.message_text || item.description || item.summary || item.abstract_signature || item.task || "";
  document.getElementById("itemBody").innerHTML = renderItemBody(item, bucket);
}

async function init() {
  const bucket = params.get("bucket") || "";
  const query = new URLSearchParams({
    bucket,
    id: params.get("id") || "",
    version: params.get("version") || "",
    model_mode: params.get("model_mode") || "auto",
    field_id: params.get("field_id") || "default",
  });
  const data = await api(`/api/v2/item/detail?${query.toString()}`);
  const item = data.item || {};
  currentItem = item;
  renderLoadedItem(item, bucket);
}

document.getElementById("itemVersionSelect").addEventListener("change", async () => {
  updateUrl(document.getElementById("itemVersionSelect").value || "", document.getElementById("itemModelMode").value || "auto");
  await init();
});
document.getElementById("itemModelMode").addEventListener("change", async () => {
  updateUrl(document.getElementById("itemVersionSelect").value || "", document.getElementById("itemModelMode").value || "auto");
  await init();
});
document.getElementById("editItemBtn").addEventListener("click", () => {
  document.getElementById("itemEditForm").hidden = false;
  document.getElementById("itemEditForm").scrollIntoView({ block: "nearest" });
});
document.getElementById("cancelItemEditBtn").addEventListener("click", () => {
  document.getElementById("itemEditForm").hidden = true;
});
document.getElementById("itemEditForm").addEventListener("submit", saveEdit);
document.getElementById("refreshItemBtn").addEventListener("click", regenerateItem);
document.getElementById("cancelRefreshItemBtn").addEventListener("click", () => {
  cancelRegeneration().catch((error) => alert(error.message || "Unable to cancel regeneration."));
});
document.getElementById("deleteItemBtn").addEventListener("click", () => {
  deleteItem().catch((error) => alert(error.message || "Unable to delete this record."));
});

init().catch((error) => {
  document.getElementById("itemTitle").textContent = "Unable to load record";
  document.getElementById("itemSummary").textContent = error.message;
});
