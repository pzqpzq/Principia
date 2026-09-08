from __future__ import annotations

import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from principia_retrieval import RetrievalConfig

from .features import canonical_evidence_registry, idea_markdown, select_evidence
from .ideas import IdeaService
from .llm import LLMClient, LLMConfig
from .models import (
    CancelToken,
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    LocalCorpusConfig,
    LocalCorpusDiagnostics,
    PipelineResult,
    RunStatus,
    SciDialectConfig,
    WorkList,
)
from .pipeline import PipelineConfig, PipelineController, PipelineJob, list_pipeline_runs
from .research import ResearchService, SearchSource
from .run import ProgressCallback
from .storage import WorkspaceStorage
from .validation import ValidationPlan, build_validation_plan, write_validation_plan


class Workspace:
    """Top-level local-first Principia workspace."""

    def __init__(
        self,
        root: str | Path = ".",
        *,
        llm: LLMClient | None = None,
        llm_config: LLMConfig | None = None,
        search_sources: dict[str, SearchSource] | None = None,
        allow_remote_private_content: bool = False,
        outputs: str | Path | None = None,
        layout: Literal["legacy", "project"] = "legacy",
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.layout = layout
        if layout not in {"legacy", "project"}:
            raise ValueError("layout must be 'legacy' or 'project'")
        if outputs is None:
            self._outputs_dir = self.root / (
                "principia_outputs" if layout == "legacy" else "outputs"
            )
        else:
            self._outputs_dir = Path(outputs).expanduser().resolve()
        self.storage = WorkspaceStorage(self.root)
        self._ensure_visible_workspace()
        self.llm = llm or LLMClient(llm_config)
        self.allow_remote_private_content = bool(allow_remote_private_content)
        self.research = ResearchService(self.storage, self.llm, search_sources=search_sources)
        self.ideas = IdeaService(self.storage, self.llm)

    @classmethod
    def project(cls, root: str | Path = ".", **kwargs: Any) -> Workspace:
        """Open the recommended project layout with shared research artifacts.

        ``Workspace.project(".")`` keeps the reusable work/feature pool in
        ``workspace/`` and writes each generated idea to ``outputs/<idea_id>/``.
        This is the concise, presentation-friendly layout used by the official
        tutorials. Existing ``Workspace(path)`` callers retain the legacy layout.
        """

        if "outputs" in kwargs or "layout" in kwargs:
            raise TypeError("Workspace.project() manages outputs and layout automatically")
        project_root = Path(root).expanduser().resolve()
        project_root.mkdir(parents=True, exist_ok=True)
        return cls(
            project_root / "workspace",
            outputs=project_root / "outputs",
            layout="project",
            **kwargs,
        )

    @property
    def path(self) -> Path:
        return self.root

    @property
    def db_path(self) -> Path:
        return self.storage.db_path

    @property
    def artifacts_dir(self) -> Path:
        return self.storage.artifacts_dir

    @property
    def outputs_dir(self) -> Path:
        return self._outputs_dir

    @property
    def project_root(self) -> Path:
        return self.root.parent if self.layout == "project" else self.root

    def counts(self) -> dict[str, int]:
        return self.storage.counts()

    def run_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.storage.list_run_events(run_id)

    def load_works(self, *, limit: int = 200) -> WorkList:
        """Load previously saved works from this workspace without searching again."""
        return self.research.load_works(limit=limit)

    def load_features(
        self,
        *,
        limit: int = 200,
        model: str | None = None,
        work_ids: list[str] | None = None,
        latest_only: bool = True,
    ) -> ExtractedFeatures:
        """Load previously extracted features without re-running extraction."""
        return self.research.load_features(
            limit=limit,
            model=model,
            work_ids=work_ids,
            latest_only=latest_only,
        )

    def storage_report(self) -> dict[str, int]:
        """Return byte sizes for common workspace storage locations."""
        paths = {
            "workspace": self.root,
            "internal": self.root / ".principia",
            "database": self.db_path,
            "database_wal": self.db_path.with_name(f"{self.db_path.name}-wal"),
            "database_shm": self.db_path.with_name(f"{self.db_path.name}-shm"),
            "artifacts": self.artifacts_dir,
            "source_json": self.artifacts_dir / "source_json",
            "exports": self.artifacts_dir / "exports",
            "pdfs": self.artifacts_dir / "pdfs",
            "cache": self.artifacts_dir / "cache",
            "visible_outputs": self.outputs_dir,
        }
        return {name: path_size(path) for name, path in paths.items()}

    def compact(
        self,
        *,
        keep_source_json: int | None = None,
        remove_cache: bool = False,
        remove_pdfs: bool = False,
        remove_private_text_cache: bool = False,
    ) -> dict[str, int]:
        """Checkpoint/VACUUM SQLite and optionally prune regenerable artifacts.

        The default is non-destructive: it only shrinks SQLite WAL/free pages and keeps all
        works, extractions, generated ideas, exports, PDFs, and source JSON.
        """
        before = self.storage_report()
        if keep_source_json is not None:
            prune_directory_files(
                self.artifacts_dir / "source_json", keep=max(0, int(keep_source_json))
            )
        if remove_cache:
            remove_directory_contents(self.artifacts_dir / "cache")
        if remove_pdfs:
            remove_directory_contents(self.artifacts_dir / "pdfs")
        if remove_private_text_cache:
            self.storage.prune_source_text_cache()
        self.storage.compact()
        after = self.storage_report()
        after["reclaimed"] = max(0, before["workspace"] - after["workspace"])
        return after

    def run(
        self,
        goal: str,
        *,
        target_count: int | None = None,
        model: str | None = None,
        idea_model: str | None = None,
        compare_model: str | None = None,
        mode: str | None = None,
        user_note: str = "",
        documents: str | Path | Sequence[str | Path] | None = None,
        local_corpus_config: LocalCorpusConfig | None = None,
        allow_remote_private_content: bool | None = None,
        pipeline_config: PipelineConfig | None = None,
        sources: list[str] | None = None,
        rerank_mode: str | None = None,
        retrieval_config: RetrievalConfig | None = None,
        embedding_client: Any | None = None,
        require_target: bool | None = None,
        search_timeout: float = 12.0,
        overwrite: bool = False,
        extract_count: int | None = None,
        resume_extraction: bool = True,
        continue_on_error: bool = False,
        retain_pdfs: bool = False,
        pdf_dir: str | Path | None = None,
        max_extract_chars: int = 24_000,
        evidence_kinds: list[str] | None = None,
        evidence_work_ids: list[str] | None = None,
        evidence_feature_ids: list[str] | None = None,
        limit_per_kind: int | None = None,
        global_kind_limits: dict[str, int] | None = None,
        max_per_work: int | None = None,
        require_exact_evidence: bool | None = None,
        scidialect_config: SciDialectConfig | None = None,
        show_progress: bool = False,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
        _pipeline_control: PipelineController | None = None,
    ) -> PipelineResult:
        config = pipeline_config or PipelineConfig()
        resolved_target = int(target_count if target_count is not None else config.target_count)
        extraction_model = model or config.extraction_model
        resolved_idea_model = idea_model or (model if model is not None else config.idea_model)
        resolved_compare_model = compare_model or (
            idea_model
            if idea_model is not None
            else (model if model is not None else config.comparison_model)
        )
        resolved_mode = mode or config.mode
        resolved_rerank_mode = rerank_mode if rerank_mode is not None else config.rerank_mode
        resolved_require_target = (
            require_target if require_target is not None else config.require_target
        )
        resolved_kind_limits = (
            global_kind_limits if global_kind_limits is not None else config.global_kind_limits
        )
        resolved_max_per_work = max_per_work if max_per_work is not None else config.max_per_work
        resolved_exact_evidence = (
            require_exact_evidence
            if require_exact_evidence is not None
            else config.require_exact_evidence
        )
        private_consent = (
            self.allow_remote_private_content
            if allow_remote_private_content is None
            else bool(allow_remote_private_content)
        )
        effective_token = _pipeline_control.token if _pipeline_control is not None else cancel_token

        works = self.research.search(
            goal,
            target_count=resolved_target,
            rerank_mode=resolved_rerank_mode,
            sources=sources,
            retrieval_config=retrieval_config,
            embedding_client=embedding_client,
            require_target=resolved_require_target,
            timeout=search_timeout,
            show_progress=show_progress,
            callback=_combined_stage_callback("retrieval", callback, _pipeline_control),
            cancel_token=effective_token,
        )
        if _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "retrieval",
                f"Retrieved {works.public_count} public work(s).",
                public_works=works.public_count,
            )

        document_paths = _document_paths(documents)
        if document_paths:
            local_lists: list[WorkList] = []
            for folder in document_paths:
                local_lists.append(
                    self.research.ingest_local(
                        folder,
                        config=local_corpus_config,
                        show_progress=show_progress,
                        callback=_combined_stage_callback("ingestion", callback, _pipeline_control),
                        cancel_token=effective_token,
                    )
                )
            works = merge_public_and_local_works(works, local_lists)
            if _pipeline_control is not None:
                _pipeline_control.complete_stage(
                    "ingestion",
                    f"Ingested {works.local_count} supplemental local document(s).",
                    local_works=works.local_count,
                )
        elif _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "ingestion", "No local document folder supplied.", local_works=0
            )

        if works.local_count and not private_consent:
            try:
                remote_provider = self.llm.resolve(extraction_model).provider != "mock"
            except (AttributeError, TypeError):
                remote_provider = True
            if remote_provider:
                raise PermissionError(
                    "Local document content is private and would be transmitted to the configured remote LLM. "
                    "Pass allow_remote_private_content=True only after obtaining authorization. The provider "
                    "receives document content and portable local:// identifiers, never absolute filesystem paths."
                )

        extraction_input = works
        if extract_count is not None:
            public_items = [item for item in works.items if item.source != "local"]
            local_items = [item for item in works.items if item.source == "local"]
            public_limit = max(0, min(int(extract_count), len(public_items)))
            extraction_input = WorkList(
                query=works.query,
                items=[*public_items[:public_limit], *local_items],
                target_count=works.target_count,
                mode=works.mode,
                sources=works.sources,
                diagnostics=works.diagnostics,
                local_diagnostics=works.local_diagnostics,
                run_id=works.run_id,
            )
        features = self.research.extract(
            extraction_input,
            model=extraction_model,
            overwrite=overwrite or not resume_extraction,
            continue_on_error=continue_on_error,
            retain_pdfs=retain_pdfs,
            pdf_dir=pdf_dir,
            max_chars=max_extract_chars,
            allow_remote_private_content=private_consent,
            show_progress=show_progress,
            callback=_combined_stage_callback("extraction", callback, _pipeline_control),
            cancel_token=effective_token,
        )
        if _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "extraction",
                f"Extracted {len(features)} feature bundle(s).",
                extracted=len(features),
            )

        selection_features = features
        if works.local_count and resolved_kind_limits:
            local_ids = {item.id for item in works.items if item.source == "local"}
            ordered_features = [item for item in features.items if item.work_id in local_ids]
            ordered_features.extend(
                item for item in features.items if item.work_id not in local_ids
            )
            selection_features = features.model_copy(update={"items": ordered_features})
        selected_evidence = select_evidence(
            selection_features,
            kinds=evidence_kinds,
            work_ids=evidence_work_ids,
            feature_ids=evidence_feature_ids,
            limit_per_kind=limit_per_kind,
            global_kind_limits=resolved_kind_limits,
            max_per_work=resolved_max_per_work,
            require_exact=resolved_exact_evidence,
            user_note=user_note or goal,
        ).model_copy(update={"query": goal})
        if _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "evidence",
                f"Selected {_evidence_record_count(selected_evidence)} canonical evidence record(s).",
                evidence_records=_evidence_record_count(selected_evidence),
                evidence_works=len(selected_evidence.features),
            )

        idea = self.ideas.generate(
            selected_evidence,
            user_note=user_note or goal,
            mode=resolved_mode,
            model=resolved_idea_model,
            overwrite=overwrite,
            scidialect_config=scidialect_config,
            show_progress=show_progress,
            callback=_combined_stage_callback("generation", callback, _pipeline_control),
            cancel_token=effective_token,
        )
        if _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "generation", "Generated and validated the Idea Card.", idea_id=idea.id
            )
        comparison = self.ideas.compare(
            idea,
            features,
            model=resolved_compare_model,
            show_progress=show_progress,
            callback=_combined_stage_callback("comparison", callback, _pipeline_control),
            cancel_token=effective_token,
        )
        if _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "comparison",
                f"Compared against {len(comparison.rows)} prior idea record(s).",
                comparison_rows=len(comparison.rows),
            )
        result = PipelineResult(
            goal=goal,
            works=works,
            features=features,
            idea=idea,
            comparison=comparison,
            selected_evidence=selected_evidence,
            workspace_path=str(self.path),
        )
        export_path = self.export_result(result)
        export_reference = (
            export_path.relative_to(self.project_root).as_posix()
            if self.layout == "project"
            else str(export_path)
        )
        completed = result.model_copy(update={"export_path": export_reference})
        if _pipeline_control is not None:
            _pipeline_control.complete_stage(
                "export", "Exported portable result and validation artifacts."
            )
        return completed

    def start(
        self,
        goal: str,
        *,
        documents: str | Path | Sequence[str | Path] | None = None,
        pipeline_config: PipelineConfig | None = None,
        progress: str | None = None,
        callback: ProgressCallback | None = None,
        **run_options: Any,
    ) -> PipelineJob:
        """Start a persisted background pipeline with safe pause/resume/stop controls."""

        config = pipeline_config or PipelineConfig()
        if progress is not None:
            config = config.model_copy(update={"progress": progress})

        def runner(control: PipelineController) -> PipelineResult:
            return self.run(
                goal,
                documents=documents,
                pipeline_config=config,
                callback=callback,
                _pipeline_control=control,
                **run_options,
            )

        job = PipelineJob.start(
            self.storage,
            runner,
            operation="workspace.pipeline",
            config=config,
            callback=callback,
        )
        if config.progress != "none":
            job.display(mode=config.progress)
        return job

    def runs(self, *, limit: int = 50) -> list[RunStatus]:
        """List recent persisted parent and staged runs."""

        return list_pipeline_runs(self.storage, limit=limit)

    def status(self, run_id: str) -> RunStatus:
        return PipelineJob.attach(self.storage, run_id).status()

    def pause(self, run_id: str) -> RunStatus:
        return PipelineJob.attach(self.storage, run_id).pause()

    def resume(self, run_id: str) -> RunStatus:
        return PipelineJob.attach(self.storage, run_id).resume()

    def stop(self, run_id: str) -> RunStatus:
        return PipelineJob.attach(self.storage, run_id).stop()

    def export_result(self, result: PipelineResult) -> Path:
        if self.layout == "project":
            return self._export_project_result(result)
        export_dir = self.artifacts_dir / "exports" / result.idea.id
        export_dir.mkdir(parents=True, exist_ok=True)
        plan = build_validation_plan(result)
        payload = portable_result_payload(result, self.root)
        works_payload = portable_payload(result.works.model_dump(mode="json"), self.root)
        self._write_export_bundle(export_dir, result, plan, payload, works_payload)
        self._write_visible_export(result, export_dir, plan, payload, works_payload)
        return export_dir

    def export(
        self,
        *,
        goal: str,
        works: WorkList,
        features: ExtractedFeatures,
        idea: Idea,
        comparison: IdeaComparison,
    ) -> Path:
        result = PipelineResult(
            goal=goal,
            works=works,
            features=features,
            idea=idea,
            comparison=comparison,
            workspace_path=str(self.path),
        )
        return self.export_result(result)

    def _export_project_result(self, result: PipelineResult) -> Path:
        """Write one shared literature pool and one non-duplicating idea bundle."""

        works_payload = portable_payload(result.works.model_dump(mode="json"), self.root)
        features_payload = portable_payload(result.features.model_dump(mode="json"), self.root)
        evidence_payload = portable_payload(
            {
                "schema_version": "principia.evidence.v1",
                "query": result.selected_evidence.query,
                "records": canonical_evidence_registry(result.selected_evidence),
                "created_at": result.selected_evidence.created_at,
            },
            self.root,
        )
        (self.root / "works.json").write_text(
            json.dumps(works_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "features.json").write_text(
            json.dumps(features_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        export_dir = self.outputs_dir / result.idea.id
        export_dir.mkdir(parents=True, exist_ok=True)
        plan = build_validation_plan(result)
        idea_payload = portable_idea_payload(result.idea, self.root)
        comparison_payload = portable_payload(
            result.comparison.model_dump(mode="json"), self.root
        )
        (export_dir / "idea.json").write_text(
            json.dumps(idea_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (export_dir / "idea.md").write_text(
            portable_text(format_idea_markdown(result), self.root),
            encoding="utf-8",
        )
        (export_dir / "evidence.json").write_text(
            json.dumps(evidence_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (export_dir / "comparison.json").write_text(
            json.dumps(comparison_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        portable_plan = ValidationPlan.model_validate(
            portable_payload(plan.model_dump(mode="json"), self.root)
        )
        write_validation_plan(portable_plan, export_dir)
        result_manifest = {
            "schema_version": "principia.project_result.v1",
            "goal": portable_text(result.goal, self.root),
            "idea_id": result.idea.id,
            "workspace": {
                "manifest": "../../workspace/manifest.json",
                "works": "../../workspace/works.json",
                "features": "../../workspace/features.json",
            },
            "artifacts": {
                "idea_markdown": "idea.md",
                "idea_json": "idea.json",
                "evidence": "evidence.json",
                "comparison": "comparison.json",
                "validation_markdown": "validation_plan.md",
                "validation_json": "validation_plan.json",
            },
            "created_at": result.created_at,
        }
        (export_dir / "result.json").write_text(
            json.dumps(result_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest: dict[str, Any] = {
            "schema_version": "principia.workspace.v1",
            "goal": portable_text(result.goal, self.root),
            "counts": {
                **result.works.counts(),
                "feature_bundles": len(result.features),
                "selected_evidence_records": len(evidence_payload["records"]),
            },
            "shared_artifacts": {"works": "works.json", "features": "features.json"},
            "outputs": {result.idea.id: f"../outputs/{result.idea.id}/result.json"},
            "updated_at": result.created_at,
        }
        existing_manifest = self.root / "manifest.json"
        if existing_manifest.is_file():
            try:
                previous = json.loads(existing_manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                previous = {}
            previous_outputs = previous.get("outputs") if isinstance(previous, dict) else {}
            if isinstance(previous_outputs, dict):
                manifest["outputs"] = {**previous_outputs, **manifest["outputs"]}
        existing_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return export_dir

    def _ensure_visible_workspace(self) -> None:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        if self.layout == "project":
            readme = self.root / "README.md"
            if not readme.exists():
                readme.write_text(
                    "\n".join(
                        [
                            "# Principia Workspace",
                            "",
                            "This folder contains the reusable literature and feature pool.",
                            "Generated ideas are stored separately in `../outputs/<idea_id>/`.",
                            "Internal resumability state remains in the hidden `.principia/` folder.",
                            "",
                            "- `works.json`: shared public and local work metadata.",
                            "- `features.json`: shared LLM-extracted feature bundles.",
                            "- `manifest.json`: counts and relative artifact references.",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            index = self.outputs_dir / "README.md"
            if not index.exists():
                index.write_text(
                    "# Principia Outputs\n\nEach subfolder is one generated idea and its validation hand-off.\n",
                    encoding="utf-8",
                )
            return
        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text(
                "\n".join(
                    [
                        "# Principia Workspace",
                        "",
                        "Visible files are written to `principia_outputs/`.",
                        "Internal SQLite state and caches are stored in the hidden `.principia/` folder.",
                        "",
                        "Typical files after export:",
                        "",
                        "- `principia_outputs/latest/idea.md`",
                        "- `principia_outputs/latest/result.json`",
                        "- `principia_outputs/latest/works.json`",
                        "- `principia_outputs/latest/validation_plan.md`",
                        "- `principia_outputs/latest/validation_plan.json`",
                        "- `principia_outputs/exports/<idea_id>/...`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        index = self.outputs_dir / "README.md"
        if not index.exists():
            index.write_text(
                "\n".join(
                    [
                        "# Principia Outputs",
                        "",
                        "This visible folder mirrors the main exported artifacts from `.principia/artifacts/exports/`.",
                        "",
                        "- `latest/` contains the latest exported workflow result.",
                        "- `exports/` contains timestamp-free idea-ID folders for previous exports.",
                        "- Each export includes standalone `validation_plan.md` and `validation_plan.json` files.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

    def _write_visible_export(
        self,
        result: PipelineResult,
        hidden_export_dir: Path,
        plan: ValidationPlan,
        payload: dict[str, Any],
        works_payload: dict[str, Any],
    ) -> None:
        export_dir = self.outputs_dir / "exports" / result.idea.id
        latest_dir = self.outputs_dir / "latest"
        for target in (export_dir, latest_dir):
            target.mkdir(parents=True, exist_ok=True)
            self._write_export_bundle(target, result, plan, payload, works_payload)
            hidden_relative = hidden_export_dir.relative_to(self.root).as_posix()
            (target / "README.md").write_text(
                "\n".join(
                    [
                        f"# {portable_text(result.idea.title, self.root)}",
                        "",
                        f"Hidden canonical export: `{hidden_relative}`",
                        "",
                        "- `idea.md`: readable Idea Card.",
                        "- `result.json`: complete structured workflow result.",
                        "- `works.json`: retrieved work list.",
                        "- `validation_plan.md`: standalone human-readable validation hand-off.",
                        "- `validation_plan.json`: standalone structured validation hand-off.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

    def _write_export_bundle(
        self,
        target: Path,
        result: PipelineResult,
        plan: ValidationPlan,
        payload: dict[str, Any],
        works_payload: dict[str, Any],
    ) -> None:
        (target / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (target / "works.json").write_text(
            json.dumps(works_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (target / "idea.md").write_text(
            portable_text(format_idea_markdown(result), self.root),
            encoding="utf-8",
        )
        portable_plan = ValidationPlan.model_validate(
            portable_payload(plan.model_dump(mode="json"), self.root)
        )
        write_validation_plan(portable_plan, target)


def format_idea_markdown(result: PipelineResult) -> str:
    idea = result.idea
    lines = [f"# {idea.title}", "", f"Goal: {result.goal}", "", idea_markdown(idea).strip(), ""]
    if result.comparison.rows:
        lines.extend(
            [
                "## Comparison Highlights",
                *[
                    f"- {row.get('title', 'Prior idea')}: {row.get('essential_difference') or row.get('mechanistic_similarity')}"
                    for row in result.comparison.rows[:8]
                ],
            ]
        )
    return "\n".join(lines).strip() + "\n"


def portable_result_payload(result: PipelineResult, workspace_root: Path) -> dict[str, Any]:
    """Return a shareable result payload without machine-specific paths."""

    payload = portable_payload(result.model_dump(mode="json"), workspace_root)
    payload["workspace_path"] = "."
    payload["export_path"] = f"principia_outputs/exports/{result.idea.id}"
    return payload


def portable_idea_payload(idea: Idea, workspace_root: Path) -> dict[str, Any]:
    """Return scientific Idea Card content without internal generation traces."""

    payload = idea.model_dump(mode="json", exclude={"trace", "generation_metadata"})
    return portable_payload(payload, workspace_root)


def portable_payload(value: Any, workspace_root: Path, *, key: str = "") -> Any:
    """Recursively remove machine-local paths from a shareable payload.

    Path-named fields retain relative workspace paths for compatibility. Other
    strings are also scrubbed because provider metadata, warnings, comparison
    prose, and evidence records may embed an absolute path under an arbitrary
    key.
    """

    if isinstance(value, dict):
        return {
            item_key: portable_payload(item_value, workspace_root, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [portable_payload(item, workspace_root, key=key) for item in value]
    if isinstance(value, tuple):
        return [portable_payload(item, workspace_root, key=key) for item in value]
    if isinstance(value, str):
        if _path_field(key):
            portable_path = _portable_exact_path(value, workspace_root)
            if portable_path is not None:
                return portable_path
        return portable_text(value, workspace_root)
    return value


def _path_field(key: str) -> bool:
    normalized = str(key or "").lower()
    return normalized in {"path", "workspace", "directory"} or normalized.endswith(
        ("_path", "_dir", "_directory")
    )


_LOCAL_FILE_URI = re.compile(
    r"file:(?://)?(?:/[^\s`\"'<>]+|[A-Za-z]:\\[^\s`\"'<>]+)",
    flags=re.IGNORECASE,
)
_LOCAL_POSIX_PATH = re.compile(
    r"(?<![A-Za-z0-9:/])/(?!/)[^/\s`\"'<>]+/[^\s`\"'<>]+",
    flags=re.IGNORECASE,
)
_LOCAL_WINDOWS_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:\\)[^\s`\"'<>]+\\[^\s`\"'<>]+",
    flags=re.IGNORECASE,
)


def portable_text(value: str, workspace_root: Path) -> str:
    """Preserve useful prose while removing embedded machine-local paths."""

    exact = _portable_exact_path(value, workspace_root)
    if exact is not None:
        return exact
    root_text = str(workspace_root.expanduser().resolve())
    text = str(value).replace(root_text, ".")
    text = _LOCAL_FILE_URI.sub("[local path]", text)
    text = _LOCAL_POSIX_PATH.sub("[local path]", text)
    return _LOCAL_WINDOWS_PATH.sub("[local path]", text)


def _portable_exact_path(value: str, workspace_root: Path) -> str | None:
    """Return a portable form only when the complete string is a local path."""

    raw = str(value or "").strip()
    if not raw or "\n" in raw or "\r" in raw:
        return None
    if raw.lower().startswith("file:"):
        return Path(raw.removeprefix("file://").removeprefix("file:")).name or "[local path]"
    path = Path(raw).expanduser()
    if path.is_absolute():
        try:
            return path.resolve().relative_to(workspace_root.resolve()).as_posix()
        except (OSError, ValueError):
            return path.name or "[local path]"
    windows_path = PureWindowsPath(raw)
    if windows_path.is_absolute():
        return windows_path.name or "[local path]"
    return None


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def prune_directory_files(path: Path, *, keep: int) -> None:
    if not path.exists():
        return
    files = sorted(
        [item for item in path.iterdir() if item.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for item in files[keep:]:
        item.unlink(missing_ok=True)


def remove_directory_contents(path: Path) -> None:
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)


def _document_paths(
    documents: str | Path | Sequence[str | Path] | None,
) -> list[Path]:
    if documents is None:
        return []
    values: Sequence[str | Path]
    if isinstance(documents, (str, Path)):
        values = [documents]
    else:
        values = documents
    return [Path(value).expanduser() for value in values]


def _combined_stage_callback(
    stage: str,
    callback: ProgressCallback | None,
    control: PipelineController | None,
) -> ProgressCallback | None:
    if control is not None:
        return control.child_callback(stage)
    return callback


def _evidence_record_count(packet: Any) -> int:
    kinds = ("ideas", "principles", "takeaways", "baselines", "benchmarks", "result_facts")
    return sum(len(getattr(item, kind)) for item in packet.features for kind in kinds)


def merge_public_and_local_works(public: WorkList, local_lists: Sequence[WorkList]) -> WorkList:
    """Append every successfully parsed local document without changing the public target."""

    diagnostics = LocalCorpusDiagnostics()
    corpus_names: list[str] = []
    items = list(public.items)
    seen_ids = {item.id for item in items}
    for local in local_lists:
        local_diagnostics = local.local_diagnostics
        if local_diagnostics.corpus_name:
            corpus_names.append(local_diagnostics.corpus_name)
        diagnostics.discovered_count += local_diagnostics.discovered_count
        diagnostics.accepted_count += local_diagnostics.accepted_count
        diagnostics.cached_count += local_diagnostics.cached_count
        diagnostics.duplicate_count += local_diagnostics.duplicate_count
        diagnostics.skipped_count += local_diagnostics.skipped_count
        diagnostics.failed_count += local_diagnostics.failed_count
        diagnostics.total_bytes += local_diagnostics.total_bytes
        diagnostics.total_characters += local_diagnostics.total_characters
        diagnostics.reports.extend(local_diagnostics.reports)
        diagnostics.warnings.extend(local_diagnostics.warnings)
        for item in local.items:
            if item.id not in seen_ids:
                items.append(item)
                seen_ids.add(item.id)
    diagnostics.corpus_name = ", ".join(dict.fromkeys(corpus_names))
    diagnostics.warnings = list(dict.fromkeys(diagnostics.warnings))
    return WorkList(
        query=public.query,
        items=items,
        target_count=public.target_count,
        mode=public.mode,
        sources=list(dict.fromkeys([*public.sources, "local"])),
        diagnostics=public.diagnostics,
        local_diagnostics=diagnostics,
        run_id=public.run_id,
        created_at=public.created_at,
    )
