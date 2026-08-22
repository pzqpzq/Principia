from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

from principia_retrieval.embeddings import SiliconFlowEmbeddingClient

from .._version import __version__
from ..application.facade import Principia
from ..cloud import CloudSearchRequest, ResearchGoalRunRequest
from ..domain import JobRecord
from ..providers import ModelPolicy, ProviderRequestError
from .models import (
    AreaSuggestionCreateRequest,
    AreaSuggestionEditRequest,
    AreaVersionRequest,
    CandidateDisplayEditRequest,
    CatalogRefreshRequest,
    CollectionEditRequest,
    DiscoveryRequest,
    ErrorBody,
    ErrorEnvelope,
    GraphResponse,
    JobListResponse,
    LibraryCollectionsResponse,
    LibrarySummaryResponse,
    LiteratureAcquisitionRequest,
    LiteratureDiscoveryRequest,
    LiteratureSearchRequest,
    LiteratureSelectionRequest,
    LocalExtractionRequest,
    LocalSourceResponse,
    LocalSourcesResponse,
    ManagedSourceRequest,
    PinRequest,
    PotentialRelationsRequest,
    PotentialRelationsResponse,
    PrincipleCardPage,
    PrincipleGraphViewResponse,
    PrincipleRelationsResponse,
    ProviderCredentialRequest,
    ResearchArtifactCreateRequest,
    ResearchGraphMutationRequest,
    ResearchProjectCreateRequest,
    ResearchProjectUpdateRequest,
    ResearchSessionCreateRequest,
    ResearchSessionUpdateRequest,
    ScenarioCreateRequest,
    ScenarioEventRequest,
    SourceDocumentPage,
    SourceImportRequest,
    SourceLocationDisclosureRequest,
    SourceRegistrationRequest,
    StorageLayoutDisclosureResponse,
    StorageLayoutRevealRequest,
    VirtualPrincipleGenerateRequest,
    VirtualPrincipleGenerationResponse,
    VirtualPrincipleSaveRequest,
    WorkingDirectoryResponse,
    WorkingDirectorySwitchRequest,
)

MAX_JSON_BODY = 1024 * 1024


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid.uuid4().hex))


def _error(
    request: Request,
    *,
    status: int,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            category=category,
            message=message,
            retryable=retryable,
            request_id=_request_id(request),
            details=details or {},
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def create_app(
    principia: Principia,
    *,
    bound_port: int | None = None,
    test_mode: bool = False,
    configure_router: Callable[[FastAPI, APIRouter, Principia], None] | None = None,
    ui_root_override: Path | None = None,
    extra_spa_routes: set[str] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Principia Local API",
        version=__version__,
        docs_url="/api/docs" if test_mode else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.principia = principia
    app.state.session_token = secrets.token_urlsafe(32)
    app.state.bound_port = bound_port
    allowed_hosts = {"127.0.0.1", "localhost", "[::1]"}
    if test_mode:
        allowed_hosts.add("testserver")

    @app.middleware("http")
    async def security_and_request_context(request: Request, call_next: Any) -> Any:
        request.state.request_id = request.headers.get("X-Principia-Request-ID") or uuid.uuid4().hex
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        if host not in allowed_hosts:
            return _error(
                request,
                status=400,
                code="invalid_host",
                category="security",
                message="Request Host is not an allowed loopback host.",
            )
        origin = request.headers.get("origin")
        if origin:
            allowed_origins = {
                f"http://127.0.0.1:{bound_port}",
                f"http://localhost:{bound_port}",
            }
            if test_mode:
                allowed_origins.add("http://testserver")
            if origin.rstrip("/") not in allowed_origins:
                return _error(
                    request,
                    status=403,
                    code="invalid_origin",
                    category="security",
                    message="Request Origin does not match the Principia runtime.",
                )
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            if request.headers.get("X-Principia-Session") != app.state.session_token:
                return _error(
                    request,
                    status=403,
                    code="invalid_session",
                    category="security",
                    message="Mutation session token is missing or invalid.",
                )
            body = await request.body()
            if len(body) > MAX_JSON_BODY:
                return _error(
                    request,
                    status=413,
                    code="body_too_large",
                    category="security",
                    message="JSON request body exceeds the 1 MiB limit.",
                )
        response = await call_next(request)
        response.headers["X-Principia-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        safe_errors = [
            {
                "type": item.get("type", "validation_error"),
                "loc": item.get("loc", ()),
                "msg": item.get("msg", "Invalid value"),
            }
            for item in exc.errors()
        ]
        return _error(
            request,
            status=422,
            code="request_validation_failed",
            category="contract",
            message="The request did not match the Principia API contract.",
            details={"errors": safe_errors},
        )

    @app.exception_handler(KeyError)
    async def missing_data_error(request: Request, exc: KeyError) -> JSONResponse:
        return _error(
            request,
            status=404,
            code="not_found",
            category="data",
            message=str(exc).strip("'"),
        )

    @app.exception_handler(PermissionError)
    async def permission_error(request: Request, exc: PermissionError) -> JSONResponse:
        return _error(
            request,
            status=403,
            code="operation_rejected",
            category="security",
            message=str(exc),
        )

    @app.exception_handler(ValueError)
    async def integrity_error(request: Request, exc: ValueError) -> JSONResponse:
        return _error(
            request,
            status=409,
            code="operation_rejected",
            category="integrity",
            message=str(exc),
        )

    @app.exception_handler(ProviderRequestError)
    async def provider_request_error(request: Request, exc: ProviderRequestError) -> JSONResponse:
        status = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
        return _error(
            request,
            status=status,
            code="provider_request_failed",
            category=exc.category,
            message=str(exc),
            retryable=exc.retryable,
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        return _error(
            request,
            status=500,
            code="internal_error",
            category="runtime",
            message="Principia could not complete the request.",
            retryable=True,
        )

    router = APIRouter(prefix="/api/v1")
    working_directory_lock = threading.RLock()
    query_embedding_lock = threading.RLock()
    query_embedding_cache: dict[tuple[str, str, str], list[float]] = {}

    def cloud_query_embedding(query: str) -> tuple[list[float] | None, str]:
        """Embed one public search query when the active Cloud can use it.

        The bounded in-memory cache prevents Explorer facets and Graph/Card
        toggles from paying for the same query repeatedly.  Principle contents
        never enter this request; releases without vectors use the deterministic
        conceptual FTS path instead.
        """

        normalized = " ".join(str(query or "").split())
        status = principia.global_cloud.status()
        if not normalized or not bool(status.get("vectors_complete")):
            return None, "cloud_vectors_unavailable"
        cache_key = (
            str(principia.workspace.working_directory_root),
            str(status.get("release_id") or ""),
            normalized.casefold(),
        )
        with query_embedding_lock:
            cached = query_embedding_cache.get(cache_key)
        if cached is not None:
            return list(cached), ""
        try:
            profile = principia.local.provider_profile("siliconflow")
            key = principia.local.credentials.api_key("siliconflow")
            if not key:
                return None, "embedding_credential_unavailable"
            vector = SiliconFlowEmbeddingClient(
                api_key=key,
                base_url=profile.base_url,
                dimensions=1024,
                timeout=15,
                max_retries=1,
            ).embed([normalized])[0]
            with query_embedding_lock:
                query_embedding_cache[cache_key] = list(vector)
                while len(query_embedding_cache) > 64:
                    query_embedding_cache.pop(next(iter(query_embedding_cache)))
            return vector, ""
        except Exception as exc:  # noqa: BLE001
            return None, type(exc).__name__

    def working_directory_response(*, switched: bool) -> WorkingDirectoryResponse:
        layout = principia.local.storage_layout_disclosure()
        summary = principia.repository.library_summary()
        empty = not any(
            int(summary[key])
            for key in (
                "research_goal_count",
                "source_count",
                "document_count",
                "principle_count",
                "needs_revalidation_count",
                "quarantined_count",
            )
        )
        root = Path(str(layout["working_directory"]))
        return WorkingDirectoryResponse(
            **{
                key: layout[key]
                for key in ("working_directory", "workspace", "local_data", "principles")
            },
            display_name=root.name or str(root),
            package_library=(
                str(principia.package_library_root)
                if principia.package_library_root is not None
                else None
            ),
            switched=switched,
            empty=empty,
        )

    def switch_working_directory(path: str) -> WorkingDirectoryResponse:
        nonlocal principia
        try:
            target = Path(path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("the selected working directory does not exist") from exc
        if not target.is_dir():
            raise ValueError("the selected working directory is not a folder")
        with working_directory_lock:
            if target == principia.workspace.working_directory_root:
                return working_directory_response(switched=False)
            active_jobs = principia.repository.active_jobs()
            if active_jobs:
                raise ValueError(
                    "finish, pause, or cancel active operations before switching working directory"
                )
            replacement = Principia.open(
                working_directory=target,
                package_library=principia.package_library_root,
            )
            previous = principia
            principia = replacement
            app.state.principia = replacement
            previous.close()
            return working_directory_response(switched=True)

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @router.get("/runtime")
    def runtime() -> dict[str, Any]:
        return {
            "version": __version__,
            "demo_mode": principia.diagnostics()["demo_mode"],
            "routes": ["research", "library", "map", "local"],
            "graph": {"default_nodes": 60, "soft_limit": 150, "hard_limit": 500},
        }

    @router.post("/runtime/working-directory/disclosure")
    def disclose_working_directory(response: Response) -> WorkingDirectoryResponse:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return working_directory_response(switched=False)

    @router.get("/runtime/working-directory/picker")
    def working_directory_picker_capability() -> dict[str, Any]:
        return principia.local.picker_capability()

    @router.post("/runtime/working-directory/choose")
    def choose_working_directory() -> WorkingDirectoryResponse:
        return switch_working_directory(principia.local.choose_working_directory())

    @router.post("/runtime/working-directory/switch")
    def set_working_directory(
        payload: WorkingDirectorySwitchRequest,
    ) -> WorkingDirectoryResponse:
        return switch_working_directory(payload.path)

    @router.get("/providers")
    def providers() -> dict[str, Any]:
        return {"profiles": [principia.local.provider_profile().model_dump(mode="json")]}

    @router.put("/provider-profiles/{provider_id}/credential")
    def save_provider_credential(
        provider_id: str, payload: ProviderCredentialRequest
    ) -> dict[str, Any]:
        metadata = principia.local.save_provider_credential(
            provider_id, payload.api_key.get_secret_value()
        )
        return {"provider_id": provider_id, **metadata}

    @router.delete("/provider-profiles/{provider_id}/credential")
    def delete_provider_credential(provider_id: str) -> dict[str, Any]:
        metadata = principia.local.delete_provider_credential(provider_id)
        return {"provider_id": provider_id, **metadata}

    @router.post("/provider-profiles/{provider_id}/test")
    def test_provider_connection(provider_id: str) -> dict[str, Any]:
        return principia.local.test_provider_connection(provider_id)

    @router.get("/diagnostics")
    def diagnostics() -> dict[str, Any]:
        return principia.diagnostics()

    @router.get("/cloud/status")
    def cloud_status() -> dict[str, Any]:
        return principia.global_cloud.status()

    @router.post("/cloud/sync", status_code=202)
    def cloud_sync(force: bool = False) -> dict[str, Any]:
        return principia.global_cloud.sync(force=force)

    @router.post("/cloud/rollback")
    def cloud_rollback() -> dict[str, Any]:
        return principia.global_cloud.rollback()

    @router.post("/cloud/search")
    def cloud_search(payload: CloudSearchRequest) -> dict[str, Any]:
        query_vector, embedding_error = cloud_query_embedding(payload.query)
        result = principia.global_cloud.search(payload, query_vector=query_vector)
        if embedding_error and embedding_error != "cloud_vectors_unavailable":
            result["degraded_reason"] = embedding_error
            result["ranking_mode"] = str(result["ranking_mode"]) + "_degraded"
        return result

    @router.get("/cloud/works/{work_id}/revisions")
    def cloud_work_revisions(work_id: str) -> dict[str, Any]:
        items = principia.global_cloud.work_revisions(work_id)
        if not items:
            raise KeyError(work_id)
        return {"items": items}

    @router.get("/cloud/works/{work_id}")
    def cloud_work(work_id: str) -> dict[str, Any]:
        item = principia.global_cloud.work(work_id)
        if item is None:
            raise KeyError(work_id)
        return item

    @router.get("/cloud/principles/{principle_id}/revisions")
    def cloud_principle_revisions(principle_id: str) -> dict[str, Any]:
        items = principia.global_cloud.principle_revisions(principle_id)
        if not items:
            raise KeyError(principle_id)
        return {"items": items}

    @router.get("/cloud/principles/{principle_id}/foundations")
    def cloud_principle_foundations(principle_id: str) -> dict[str, Any]:
        item = principia.global_cloud.foundations(principle_id)
        if item is None:
            raise KeyError(principle_id)
        return item

    @router.get("/cloud/principles/{principle_id}")
    def cloud_principle(principle_id: str) -> dict[str, Any]:
        item = principia.global_cloud.principle(principle_id)
        if item is None:
            raise KeyError(principle_id)
        return item

    @router.get("/cloud/meta-principles/{principle_id}/revisions")
    def cloud_meta_principle_revisions(principle_id: str) -> dict[str, Any]:
        items = principia.global_cloud.principle_revisions(principle_id)
        if not items or any(item.get("principle_class") != "meta" for item in items):
            raise KeyError(principle_id)
        return {"items": items}

    @router.get("/cloud/meta-principles/{principle_id}")
    def cloud_meta_principle(principle_id: str) -> dict[str, Any]:
        item = principia.global_cloud.principle(principle_id)
        if item is None or item.get("principle_class") != "meta":
            raise KeyError(principle_id)
        return item

    @router.get("/cloud/graph/viewport")
    def cloud_graph_viewport(
        min_x: float = Query(default=-10_000),
        max_x: float = Query(default=10_000),
        min_y: float = Query(default=-10_000),
        max_y: float = Query(default=10_000),
        zoom: float = Query(default=1.0, ge=0.01, le=100),
        areas: str = "",
        q: str = Query(default="", max_length=4_000),
        limit: int = Query(default=2_500, ge=1, le=2_500),
    ) -> dict[str, Any]:
        if min_x >= max_x or min_y >= max_y:
            raise ValueError("invalid graph viewport bounds")
        return principia.global_cloud.graph_viewport(
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            zoom=zoom,
            areas=[value for value in areas.split(",") if value],
            query=q,
            limit=limit,
        )

    @router.get("/library/summary")
    def library_summary() -> LibrarySummaryResponse:
        return LibrarySummaryResponse.model_validate(principia.repository.library_summary())

    @router.post("/research-goal-runs", status_code=202)
    def start_research_goal_run(
        payload: ResearchGoalRunRequest,
        egress_confirmed: bool = False,
    ) -> dict[str, Any]:
        return principia.goal_runs.start(payload, egress_confirmed=egress_confirmed)

    @router.get("/research-goal-runs/latest")
    def latest_research_goal_run() -> dict[str, Any]:
        return principia.goal_runs.latest() or {}

    @router.get("/research-goal-runs/{run_id}/results")
    def research_goal_run_results(
        run_id: str,
        membership: Literal["global", "local", "combined"] = "combined",
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        if principia.goal_runs.detail(run_id) is None:
            raise KeyError(run_id)
        return principia.goal_runs.results(run_id, membership, limit=limit, offset=offset)

    @router.get("/research-goal-runs/{run_id}/events")
    def research_goal_run_events(run_id: str, after: int = 0) -> dict[str, Any]:
        item = principia.goal_runs.detail(run_id)
        if item is None:
            raise KeyError(run_id)
        return {"items": principia.repository.job_events(item["job_id"], after=after)}

    @router.post("/research-goal-runs/{run_id}/cancel")
    def cancel_research_goal_run(run_id: str) -> dict[str, Any]:
        return principia.goal_runs.cancel(run_id)

    @router.get("/research-goal-runs/{run_id}")
    def research_goal_run(run_id: str) -> dict[str, Any]:
        item = principia.goal_runs.detail(run_id)
        if item is None:
            raise KeyError(run_id)
        return item

    @router.get("/research-projects")
    def research_projects(include_archived: bool = False) -> dict[str, Any]:
        return {"items": principia.research_sessions.projects(include_archived=include_archived)}

    @router.post("/research-projects", status_code=201)
    def create_research_project(payload: ResearchProjectCreateRequest) -> dict[str, Any]:
        return principia.research_sessions.create_project(payload.title)

    @router.patch("/research-projects/{project_id}")
    def update_research_project(
        project_id: str, payload: ResearchProjectUpdateRequest
    ) -> dict[str, Any]:
        return principia.research_sessions.update_project(
            project_id, title=payload.title, archived=payload.archived
        )

    @router.delete("/research-projects/{project_id}")
    def delete_research_project(project_id: str) -> dict[str, Any]:
        return principia.research_sessions.delete_project(project_id)

    @router.get("/research-sessions")
    def research_sessions(
        project_id: str | None = None, include_archived: bool = False
    ) -> dict[str, Any]:
        return {
            "items": principia.research_sessions.sessions(
                project_id=project_id, include_archived=include_archived
            )
        }

    @router.post("/research-sessions", status_code=202)
    def create_research_session(
        payload: ResearchSessionCreateRequest,
        egress_confirmed: bool = False,
    ) -> dict[str, Any]:
        return principia.research_sessions.create(
            payload.run,
            title=payload.title,
            project_id=payload.project_id,
            egress_confirmed=egress_confirmed,
        )

    @router.get("/research-sessions/{session_id}")
    def research_session(session_id: str) -> dict[str, Any]:
        item = principia.research_sessions.detail(session_id)
        if item is None:
            raise KeyError(session_id)
        return item

    @router.patch("/research-sessions/{session_id}")
    def update_research_session(
        session_id: str, payload: ResearchSessionUpdateRequest
    ) -> dict[str, Any]:
        project_id: str | None | object = (
            payload.project_id if "project_id" in payload.model_fields_set else ...
        )
        return principia.research_sessions.update_session(
            session_id,
            title=payload.title,
            project_id=project_id,
            archived=payload.archived,
            expected_revision=payload.expected_revision,
        )

    @router.delete("/research-sessions/{session_id}")
    def delete_research_session(
        session_id: str, expected_revision: int = Query(ge=1)
    ) -> dict[str, Any]:
        return principia.research_sessions.delete_session(
            session_id, expected_revision=expected_revision
        )

    @router.post("/research-sessions/{session_id}/runs", status_code=202)
    def start_research_session_run(
        session_id: str,
        payload: ResearchGoalRunRequest,
        egress_confirmed: bool = False,
    ) -> dict[str, Any]:
        return principia.research_sessions.start_run(
            session_id, payload, egress_confirmed=egress_confirmed
        )

    @router.get("/research-sessions/{session_id}/results")
    def research_session_results(
        session_id: str,
        membership: Literal["global", "local", "combined", "meta"] = "combined",
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return principia.research_sessions.results(
            session_id, membership, limit=limit, offset=offset
        )

    @router.get("/research-sessions/{session_id}/events")
    def research_session_events(session_id: str, after: int = 0) -> dict[str, Any]:
        item = principia.research_sessions.detail(session_id)
        if item is None:
            raise KeyError(session_id)
        active = item.get("active_run") or {}
        return {
            "items": principia.repository.job_events(str(active.get("job_id") or ""), after=after)
            if active
            else []
        }

    @router.get("/research-sessions/{session_id}/graph")
    def research_session_graph(session_id: str) -> dict[str, Any]:
        return principia.research_sessions.graph(session_id)

    @router.patch("/research-sessions/{session_id}/graph")
    def mutate_research_session_graph(
        session_id: str, payload: ResearchGraphMutationRequest
    ) -> dict[str, Any]:
        return principia.research_sessions.mutate_graph(
            session_id,
            payload.operations,
            expected_revision=payload.expected_revision,
        )

    @router.get("/research-sessions/{session_id}/artifacts")
    def research_session_artifacts(session_id: str) -> dict[str, Any]:
        return {"items": principia.research_sessions.artifacts(session_id)}

    @router.post("/research-sessions/{session_id}/artifacts", status_code=201)
    def create_research_session_artifact(
        session_id: str, payload: ResearchArtifactCreateRequest
    ) -> dict[str, Any]:
        return principia.research_sessions.save_artifact(session_id, payload.kind, payload.payload)

    @router.delete("/research-sessions/{session_id}/artifacts/{artifact_id}")
    def delete_research_session_artifact(session_id: str, artifact_id: str) -> dict[str, Any]:
        return principia.research_sessions.delete_artifact(session_id, artifact_id)

    @router.delete("/research-sessions/{session_id}/virtual-principles/{virtual_id}")
    def delete_research_session_virtual_principle(
        session_id: str, virtual_id: str, candidate_id: str = ""
    ) -> dict[str, Any]:
        return principia.research_sessions.delete_virtual_principle(
            session_id, virtual_id, candidate_id=candidate_id
        )

    @router.get("/library/collections")
    def library_collections(
        kind: str = Query(pattern="^(research_goal|area|source)$"),
        include_archived: bool = False,
    ) -> LibraryCollectionsResponse:
        return LibraryCollectionsResponse.model_validate(
            {
                "kind": kind,
                "items": principia.repository.library_collections(
                    kind, include_archived=include_archived
                ),
                "explanation": (
                    "Research Goals, Areas, and Private Folders are overlapping views "
                    "over the same Local Principle corpus."
                ),
            }
        )

    @router.patch("/library/collections/{kind}/{collection_id:path}")
    def edit_library_collection(
        kind: Literal["research_goal", "area", "source"],
        collection_id: str,
        payload: CollectionEditRequest,
    ) -> dict[str, Any]:
        if kind == "source":
            return principia.local.rename_source(collection_id, payload.title)
        return principia.repository.update_collection(kind, collection_id, payload.title)

    @router.delete("/library/collections/{kind}/{collection_id:path}")
    def archive_library_collection(
        kind: Literal["research_goal", "area", "source"], collection_id: str
    ) -> dict[str, Any]:
        if kind == "source":
            return principia.local.disconnect_source(collection_id)
        return principia.repository.archive_collection(kind, collection_id)

    @router.post("/library/collections/{kind}/{collection_id:path}/restore")
    def restore_library_collection(
        kind: Literal["research_goal", "source"], collection_id: str
    ) -> dict[str, Any]:
        if kind == "source":
            return principia.local.restore_source(collection_id)
        return principia.repository.restore_collection(kind, collection_id)

    @router.get("/areas")
    def areas() -> dict[str, Any]:
        return {
            "areas": principia.cloud.areas(),
            "catalog_configured": bool(principia.cloud.catalog),
        }

    @router.post("/areas/catalog/refresh")
    def refresh_catalog(payload: CatalogRefreshRequest) -> dict[str, Any]:
        entries = principia.cloud.refresh_catalog(payload.path)
        return {"areas": [entry.model_dump(mode="json") for entry in entries]}

    @router.post("/areas/{area}/install")
    def install_area(area: str, payload: AreaVersionRequest) -> dict[str, Any]:
        return principia.cloud.install(area, version=payload.version)

    @router.post("/areas/{area}/update")
    def update_area(area: str, payload: AreaVersionRequest) -> dict[str, Any]:
        return principia.cloud.install(area, version=payload.version)

    @router.post("/areas/{area}/verify")
    def verify_area(area: str, payload: AreaVersionRequest) -> dict[str, Any]:
        verified = principia.cloud.installer.verify_installed(area, payload.version)
        return {
            "area": area,
            "version": verified.manifest.package_version,
            "artifact_sha256": verified.artifact_sha256,
            "status": "verified",
        }

    @router.post("/areas/{area}/pin")
    def pin_area(area: str, payload: PinRequest) -> dict[str, Any]:
        principia.cloud.registry.pin(area, payload.version, pinned=payload.pinned)
        return {"area": area, "version": payload.version, "pinned": payload.pinned}

    @router.post("/areas/{area}/rollback")
    def rollback_area(area: str) -> dict[str, Any]:
        return {
            "area": area,
            "version": principia.cloud.installer.rollback(area),
            "status": "active",
        }

    @router.get("/principles/search")
    def search_principles(
        q: str = Query(min_length=1, max_length=1000),
        scope: Literal["global", "local", "combined"] = "combined",
        area: str = "",
        goal_id: str = "",
        source_id: str = "",
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return {
            "items": principia.search.search(
                q,
                scope=scope,
                area=area,
                goal_id=goal_id,
                source_id=source_id,
                limit=limit,
            ),
            "next_cursor": None,
        }  # type: ignore[arg-type]

    @router.get("/principles", response_model=PrincipleCardPage)
    def browse_principles(
        q: str = Query(default="", max_length=1000),
        scope: Literal["global", "local", "combined"] = "local",
        area: str = Query(default="", max_length=80),
        package_id: str = Query(default="", max_length=80),
        goal_id: str = Query(default="", max_length=160),
        source_id: str = Query(default="", max_length=160),
        goal_run_id: str = Query(default="", max_length=160),
        claim_type: str = Query(default="", max_length=80),
        evidence_status: str = Query(default="checks_passed", max_length=80),
        human_review: str = Query(default="", max_length=80),
        minimum_supporting_papers: int = Query(default=0, ge=0, le=10_000),
        has_reliability: bool | None = None,
        has_influence: bool | None = None,
        known_contradictions: bool | None = None,
        virtual_only: bool = False,
        sort: Literal[
            "relevance", "updated", "reliability", "influence", "supporting_papers", "title"
        ] = "updated",
        limit: int = Query(default=24, ge=1, le=100),
        cursor: str | None = None,
        page: int = Query(default=1, ge=1, le=1_000_000),
    ) -> PrincipleCardPage:
        query_vector, _ = (
            cloud_query_embedding(q) if q and scope in {"global", "combined"} else (None, "")
        )
        return PrincipleCardPage.model_validate(
            principia.explorer.browse(
                scope=scope,
                query=q,
                area=area,
                package_id=package_id,
                goal_id=goal_id,
                source_id=source_id,
                goal_run_id=goal_run_id,
                claim_type=claim_type,
                evidence_status=evidence_status,
                human_review=human_review,
                minimum_supporting_papers=minimum_supporting_papers,
                has_reliability=has_reliability,
                has_influence=has_influence,
                known_contradictions=known_contradictions,
                virtual_only=virtual_only,
                sort=sort,
                limit=limit,
                cursor=cursor,
                page=page,
                page_mode=True,
                query_vector=query_vector,
            )
        )

    @router.get("/principles/{principle_id}/relations", response_model=PrincipleRelationsResponse)
    def principle_relations(principle_id: str) -> PrincipleRelationsResponse:
        return PrincipleRelationsResponse.model_validate(principia.explorer.relations(principle_id))

    @router.get("/principles/graph", response_model=PrincipleGraphViewResponse)
    def principle_graph_view(
        scope: Literal["local", "global", "combined"] = "local",
        q: str = "",
        area: str = "",
        package_id: str = "",
        goal_id: str = "",
        source_id: str = "",
        goal_run_id: str = Query(default="", max_length=160),
        claim_type: str = "",
        evidence_status: str = "checks_passed",
        human_review: str = "",
        minimum_supporting_papers: int = Query(default=0, ge=0),
        has_reliability: bool | None = None,
        has_influence: bool | None = None,
        known_contradictions: bool | None = None,
        virtual_only: bool = False,
        sort: Literal[
            "relevance", "updated", "reliability", "influence", "supporting_papers", "title"
        ] = "updated",
        limit: int = Query(default=120, ge=1, le=200),
        page: int = Query(default=1, ge=1, le=1_000_000),
    ) -> PrincipleGraphViewResponse:
        query_vector, _ = (
            cloud_query_embedding(q) if q and scope in {"global", "combined"} else (None, "")
        )
        return PrincipleGraphViewResponse.model_validate(
            principia.explorer.graph_view(
                scope=scope,
                query=q,
                area=area,
                package_id=package_id,
                goal_id=goal_id,
                source_id=source_id,
                goal_run_id=goal_run_id,
                claim_type=claim_type,
                evidence_status=evidence_status,
                human_review=human_review,
                minimum_supporting_papers=minimum_supporting_papers,
                has_reliability=has_reliability,
                has_influence=has_influence,
                known_contradictions=known_contradictions,
                virtual_only=virtual_only,
                sort=sort,
                limit=limit,
                page=page,
                query_vector=query_vector,
            )
        )

    @router.post(
        "/principles/potential-relations",
        response_model=PotentialRelationsResponse,
    )
    def potential_principle_relations(
        request: PotentialRelationsRequest,
    ) -> PotentialRelationsResponse:
        return PotentialRelationsResponse.model_validate(
            principia.explorer.potential_relations(request.principle_ids)
        )

    @router.post(
        "/principles/virtual-principles/generate",
        response_model=VirtualPrincipleGenerationResponse,
    )
    def generate_virtual_principles(
        request: VirtualPrincipleGenerateRequest,
    ) -> VirtualPrincipleGenerationResponse:
        return VirtualPrincipleGenerationResponse.model_validate(
            principia.virtual_principles.generate(
                principle_ids=request.principle_ids,
                provider_profile_id=request.provider_profile_id,
                model=request.model,
                egress_confirmed=request.egress_confirmed,
                requested_count=request.requested_count,
                research_direction=request.research_direction,
            )
        )

    @router.post("/principles/virtual-principles/save")
    def save_virtual_principle(request: VirtualPrincipleSaveRequest) -> dict[str, Any]:
        return principia.virtual_principles.save(
            request.proposal,
            provider=request.provider,
            model=request.model,
            trace=request.trace,
        )

    @router.get("/relation-metrics/status")
    def relation_metric_status() -> dict[str, Any]:
        return principia.repository.relation_metric_status()

    @router.post("/relation-metrics/rebuild", status_code=202)
    def rebuild_relation_metrics() -> JobRecord:
        return principia.relations.start_rebuild()

    @router.get("/principles/{principle_id:path}")
    def principle_detail(principle_id: str) -> dict[str, Any]:
        item = principia.search.principle(principle_id)
        if item is None:
            raise KeyError(principle_id)
        return item

    @router.get("/graph/neighborhood")
    def graph_neighborhood(
        seed_id: str,
        scope: Literal["global", "local", "combined"] = "combined",
        depth: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=60, ge=1, le=500),
        include_shared_evidence: bool = False,
    ) -> GraphResponse:
        return GraphResponse.model_validate(
            principia.graph.neighborhood(
                seed_id,
                scope=scope,
                depth=depth,
                limit=limit,
                include_shared_evidence=include_shared_evidence,
            )
        )  # type: ignore[arg-type]

    @router.get("/graph/overview")
    def graph_overview(
        scope: Literal["global", "local", "combined"] = "local",
        area: str = "",
        goal_id: str = "",
        source_id: str = "",
        collection_id: str = "",
        include_shared_evidence: bool = False,
        limit: int = Query(default=60, ge=1, le=500),
    ) -> GraphResponse:
        return GraphResponse.model_validate(
            principia.graph.overview(
                scope=scope,
                area=area,
                goal_id=goal_id,
                source_id=source_id,
                collection_id=collection_id,
                include_shared_evidence=include_shared_evidence,
                limit=limit,
            )
        )  # type: ignore[arg-type]

    @router.get("/local/sources")
    def local_sources() -> LocalSourcesResponse:
        return LocalSourcesResponse.model_validate({"sources": principia.local.list_sources()})

    @router.post("/local/sources")
    def register_local_source(payload: SourceRegistrationRequest) -> dict[str, Any]:
        return principia.local.register_source(payload.path)

    @router.post("/local/sources/managed")
    def create_managed_local_source(payload: ManagedSourceRequest) -> dict[str, Any]:
        return principia.local.create_managed_source(
            name=payload.name,
            goal=payload.goal,
            area=payload.area,
            parent=payload.parent,
        )

    @router.post("/local/sources/location-disclosures")
    def disclose_local_source_locations(
        payload: SourceLocationDisclosureRequest, response: Response
    ) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return {"items": principia.local.source_location_disclosures(payload.source_ids)}

    @router.post("/local/storage-layout/disclosure")
    def disclose_storage_layout(response: Response) -> StorageLayoutDisclosureResponse:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return StorageLayoutDisclosureResponse.model_validate(
            principia.local.storage_layout_disclosure()
        )

    @router.post("/local/storage-layout/reveal")
    def reveal_storage_layout(payload: StorageLayoutRevealRequest) -> dict[str, Any]:
        return principia.local.reveal_storage_path(payload.target)

    @router.get("/local/sources/{source_id}")
    def local_source_detail(source_id: str) -> LocalSourceResponse:
        return LocalSourceResponse.model_validate(principia.local.source_detail(source_id))

    @router.post("/local/sources/{source_id}/indexes", status_code=202)
    def index_local_source(source_id: str) -> dict[str, Any]:
        return principia.local.start_source_index(source_id).model_dump(mode="json")

    @router.get("/local/sources/{source_id}/documents")
    def local_source_documents(
        source_id: str,
        q: str = Query(default="", max_length=1000),
        extractable: bool | None = None,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str = "",
    ) -> SourceDocumentPage:
        return SourceDocumentPage.model_validate(
            principia.local.source_documents(
                source_id,
                query=q,
                extractable=extractable,
                limit=limit,
                cursor=cursor,
            )
        )

    @router.post("/local/sources/{source_id}/reveal")
    def reveal_local_source(source_id: str) -> dict[str, Any]:
        return principia.local.reveal_source(source_id)

    @router.post("/local/sources/{source_id}/imports")
    def import_local_files(source_id: str, payload: SourceImportRequest) -> dict[str, Any]:
        return principia.local.sources.import_paths(source_id, payload.paths)

    @router.get("/local/folder-picker")
    def folder_picker_capability() -> dict[str, Any]:
        return principia.local.picker_capability()

    @router.post("/local/folder-picker")
    def choose_folder() -> dict[str, Any]:
        return principia.local.register_source(principia.local.choose_folder())

    @router.post("/local/folder-picker/multiple")
    def choose_folders() -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        jobs: list[dict[str, Any]] = []
        for folder in principia.local.choose_folders():
            source = principia.local.register_source(folder)
            sources.append(source)
            jobs.append(
                principia.local.start_source_index(str(source["source_id"])).model_dump(mode="json")
            )
        return {"sources": sources, "jobs": jobs}

    @router.post("/local/discoveries")
    def start_discovery(payload: DiscoveryRequest) -> dict[str, Any]:
        requested = payload.policy
        api_key: str | None = None
        if requested.mode == "no_llm":
            policy = ModelPolicy(mode="no_llm")
        else:
            # This deprecated endpoint historically accepted a client-supplied
            # OpenAI-compatible URL.  Never combine such a URL with credentials
            # owned by the server process: resolve the provider origin entirely
            # from the server-owned profile instead.
            if requested.mode != "remote" or requested.provider != "siliconflow":
                raise ValueError(
                    "the compatibility discovery endpoint supports only the "
                    "server-owned SiliconFlow profile or no_llm"
                )
            _, policy, api_key = principia.local.provider_configuration(
                "siliconflow",
                requested.model,
                egress_confirmed=requested.remote_egress_confirmed,
            )
        return principia.local.start(
            source_id=payload.source_id,
            goal=payload.goal,
            area=payload.area,
            policy=policy,
            api_key=api_key,
        ).model_dump(mode="json")

    @router.get("/local/literature-searches")
    def literature_searches() -> dict[str, Any]:
        return {"items": principia.local.list_literature_searches()}

    @router.post("/local/literature-searches", status_code=202)
    def create_literature_search(payload: LiteratureSearchRequest) -> dict[str, Any]:
        return principia.local.start_literature_search(
            payload.query,
            target_count=payload.target_count,
            semantic_ranking=payload.semantic_ranking,
            source_id=payload.source_id,
        ).model_dump(mode="json")

    @router.patch("/local/literature-searches/{search_id}/selection")
    def update_literature_selection(
        search_id: str, payload: LiteratureSelectionRequest
    ) -> dict[str, Any]:
        return principia.local.update_literature_selection(search_id, payload.work_ids)

    @router.post("/local/literature-searches/{search_id}/acquisitions")
    def start_literature_acquisition(
        search_id: str, payload: LiteratureAcquisitionRequest
    ) -> dict[str, Any]:
        return principia.local.start_literature_acquisition(
            search_id=search_id,
            source_id=payload.source_id,
            folder_name=payload.folder_name,
            work_ids=payload.work_ids or None,
        ).model_dump(mode="json")

    @router.post("/local/literature-searches/{search_id}/discoveries")
    def start_literature_discovery(
        search_id: str, payload: LiteratureDiscoveryRequest
    ) -> dict[str, Any]:
        api_key: str | None = None
        if payload.policy == "no_llm":
            policy = ModelPolicy(mode="no_llm")
        else:
            _, policy, api_key = principia.local.provider_configuration(
                payload.provider_profile_id,
                payload.model,
                egress_confirmed=payload.egress_confirmed,
            )
        return principia.local.start_literature_discovery(
            search_id=search_id, policy=policy, limits=payload.limits, api_key=api_key
        ).model_dump(mode="json")

    @router.get("/local/literature-searches/{search_id}")
    def literature_search_detail(search_id: str) -> dict[str, Any]:
        item = principia.local.literature_search(search_id)
        if item is None:
            raise KeyError(search_id)
        return item

    @router.get("/local/datasets")
    def local_datasets() -> dict[str, Any]:
        return {"items": principia.repository.list_datasets()}

    @router.get("/local/datasets/{dataset_id}/works")
    def local_dataset_works(dataset_id: str) -> dict[str, Any]:
        return {"items": principia.repository.dataset_works(dataset_id)}

    @router.get("/local/extractions")
    def local_extractions() -> dict[str, Any]:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in principia.repository.list_jobs(kind="local_extraction")
            ]
        }

    @router.post("/local/extractions")
    def start_local_extraction(payload: LocalExtractionRequest) -> dict[str, Any]:
        api_key: str | None = None
        if payload.policy == "no_llm":
            policy = ModelPolicy(mode="no_llm")
        else:
            _, policy, api_key = principia.local.provider_configuration(
                payload.provider_profile_id,
                payload.model,
                egress_confirmed=payload.egress_confirmed,
            )
        return principia.local.start_extraction(
            source_id=payload.source_id,
            source_revision=payload.source_revision,
            document_ids=payload.document_ids,
            selection_mode=payload.selection_mode,
            goal_id=payload.context.research_goal_id or payload.goal_id,
            goal=payload.context.research_focus or payload.goal,
            area=payload.area,
            policy=policy,
            limits=payload.limits,
            api_key=api_key,
        ).model_dump(mode="json")

    @router.get("/local/discoveries")
    def local_discoveries() -> dict[str, Any]:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in principia.repository.list_jobs(kind="literature_discovery")
            ]
        }

    @router.get("/local/discoveries/{discovery_id}")
    def local_discovery_detail(discovery_id: str) -> dict[str, Any]:
        item = principia.repository.get_job(discovery_id)
        if item is None or item.kind != "literature_discovery":
            raise KeyError(discovery_id)
        return item.model_dump(mode="json")

    @router.get("/local/candidates")
    def local_candidates(
        q: str = Query(default="", max_length=1000),
        area: str = "",
        assessment: str = "",
        eligibility: str = "eligible",
        discovery_id: str = "",
        dataset_id: str = "",
        goal_id: str = "",
        source_id: str = "",
        quality_state: str = "eligible",
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str = "",
    ) -> dict[str, Any]:
        return principia.repository.browse_candidates(
            query=q,
            area=area,
            assessment=assessment,
            eligibility=eligibility,
            discovery_id=discovery_id,
            dataset_id=dataset_id,
            goal_id=goal_id,
            source_id=source_id,
            quality_state=quality_state,
            limit=limit,
            cursor=cursor,
        )

    @router.get("/local/candidates/{candidate_id}")
    def local_candidate_detail(candidate_id: str) -> dict[str, Any]:
        item = principia.repository.candidate_detail(candidate_id)
        if item is None:
            raise KeyError(candidate_id)
        return item

    @router.patch("/local/candidates/{candidate_id}")
    def edit_local_candidate(
        candidate_id: str, payload: CandidateDisplayEditRequest
    ) -> dict[str, Any]:
        return principia.repository.update_candidate_display(candidate_id, payload.title)

    @router.delete("/local/candidates/{candidate_id}")
    def archive_local_candidate(candidate_id: str) -> dict[str, Any]:
        return principia.repository.archive_candidate(candidate_id)

    @router.post("/local/candidates/{candidate_id}/restore")
    def restore_local_candidate(candidate_id: str) -> dict[str, Any]:
        return principia.repository.restore_candidate(candidate_id)

    @router.get("/local/candidates/{candidate_id}/area-suggestions")
    def candidate_area_suggestions(candidate_id: str) -> dict[str, Any]:
        return {"items": principia.repository.candidate_area_suggestions(candidate_id)}

    @router.post("/local/candidates/{candidate_id}/area-suggestions")
    def create_candidate_area_suggestion(
        candidate_id: str, payload: AreaSuggestionCreateRequest
    ) -> dict[str, Any]:
        return principia.repository.set_candidate_area(
            candidate_id,
            payload.area,
            state="suggested",
            provenance="user",
            rationale=payload.rationale,
        )

    @router.post("/local/candidates/{candidate_id}/area-suggestions/{area}/accept")
    def accept_candidate_area_suggestion(candidate_id: str, area: str) -> dict[str, Any]:
        return principia.repository.set_candidate_area(
            candidate_id,
            area,
            state="confirmed",
            provenance="user",
            rationale="Accepted by user",
        )

    @router.post("/local/candidates/{candidate_id}/area-suggestions/{area}/reject")
    def reject_candidate_area_suggestion(candidate_id: str, area: str) -> dict[str, Any]:
        return principia.repository.set_candidate_area(
            candidate_id,
            area,
            state="rejected",
            provenance="user",
            rationale="Rejected by user",
        )

    @router.patch("/local/candidates/{candidate_id}/area-suggestions/{area}")
    def edit_candidate_area_suggestion(
        candidate_id: str, area: str, payload: AreaSuggestionEditRequest
    ) -> dict[str, Any]:
        principia.repository.set_candidate_area(
            candidate_id,
            area,
            state="rejected",
            provenance="user_edit",
            rationale=f"Replaced with {payload.new_area}",
        )
        return principia.repository.set_candidate_area(
            candidate_id,
            payload.new_area,
            state="suggested",
            provenance="user_edit",
            rationale=payload.rationale,
        )

    @router.get("/works/{work_id}/principles")
    def work_principles(work_id: str) -> dict[str, Any]:
        return {"items": principia.repository.work_candidates(work_id)}

    @router.get("/works/{work_id}")
    def work_detail(work_id: str) -> dict[str, Any]:
        item = principia.repository.work_detail(work_id)
        if item is None:
            raise KeyError(work_id)
        return item

    @router.get("/jobs/{job_id}/events")
    def job_events(job_id: str, after: int = 0) -> dict[str, Any]:
        return {"items": principia.repository.job_events(job_id, after=after)}

    @router.get("/jobs/{job_id}/stream")
    async def job_event_stream(job_id: str, request: Request) -> StreamingResponse:
        if principia.repository.get_job(job_id) is None:
            raise KeyError(job_id)
        try:
            initial_after = max(0, int(request.headers.get("Last-Event-ID", "0") or 0))
        except ValueError:
            initial_after = 0

        async def events() -> Any:
            after = initial_after
            last_heartbeat = time.monotonic()
            # A defensive reconnect interval prevents a browser EventSource
            # from hot-looping when a connection ends between state updates.
            yield "retry: 15000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                rows = principia.repository.job_events(job_id, after=after, limit=100)
                for item in rows:
                    after = int(item["sequence"])
                    yield (
                        f"id: {after}\n"
                        f"event: {item['event_type']}\n"
                        f"data: {json.dumps(item, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    )
                record = principia.repository.get_job(job_id)
                if record is None:
                    return
                if record.state in {"succeeded", "failed", "cancelled", "interrupted"} and not rows:
                    # Some orphan reconciliation transitions update the durable
                    # job record without an append-only event.  Emit one final
                    # state notification so the client refreshes its job list
                    # and closes the EventSource instead of reconnecting forever.
                    terminal = {
                        "job_id": record.job_id,
                        "state": record.state,
                        "stage": record.stage,
                        "progress": record.progress,
                    }
                    yield (
                        f"event: {record.state}\n"
                        f"data: {json.dumps(terminal, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    )
                    return
                now = time.monotonic()
                if now - last_heartbeat >= 15:
                    yield f": heartbeat {int(now)}\n\n"
                    last_heartbeat = now
                await asyncio.sleep(0.5)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/jobs/{job_id}/units")
    def job_units(job_id: str) -> dict[str, Any]:
        if principia.repository.get_job(job_id) is None:
            raise KeyError(job_id)
        return {"items": principia.repository.list_job_units(job_id)}

    @router.get("/jobs")
    def jobs(kind: str = "", limit: int = Query(default=50, ge=1, le=100)) -> JobListResponse:
        return JobListResponse(items=principia.repository.list_jobs(kind=kind, limit=limit))

    @router.get("/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        record = principia.local.get(job_id)
        if record is None:
            raise KeyError(job_id)
        return record.model_dump(mode="json")

    @router.post("/jobs/{job_id}/pause")
    def pause_job(job_id: str) -> dict[str, Any]:
        return principia.local.pause(job_id).model_dump(mode="json")

    @router.post("/jobs/{job_id}/resume")
    def resume_job(job_id: str) -> dict[str, Any]:
        return principia.local.continue_job(job_id).model_dump(mode="json")

    @router.post("/jobs/{job_id}/retry-failed")
    def retry_failed_job(job_id: str) -> dict[str, Any]:
        return principia.local.retry_failed(job_id).model_dump(mode="json")

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        return principia.local.cancel(job_id).model_dump(mode="json")

    @router.get("/scenarios")
    def scenarios() -> dict[str, Any]:
        return {"scenarios": [item.model_dump(mode="json") for item in principia.scenarios.list()]}

    @router.post("/scenarios")
    def create_scenario(payload: ScenarioCreateRequest) -> dict[str, Any]:
        return principia.scenarios.create(
            payload.name, parent_scenario_id=payload.parent_scenario_id
        ).model_dump(mode="json")

    @router.post("/scenarios/{scenario_id:path}/events")
    def append_scenario_event(scenario_id: str, payload: ScenarioEventRequest) -> dict[str, Any]:
        return principia.scenarios.append(
            scenario_id, payload.event_type, payload.payload
        ).model_dump(mode="json")

    @router.get("/scenarios/{scenario_id:path}/replay")
    def replay_scenario(scenario_id: str) -> dict[str, Any]:
        return principia.scenarios.replay(scenario_id)

    @router.get("/scenarios/{scenario_id:path}/diff")
    def diff_scenario(scenario_id: str) -> dict[str, Any]:
        return principia.scenarios.diff(scenario_id)

    @router.post("/scenarios/{scenario_id:path}/branch")
    def branch_scenario(scenario_id: str, payload: ScenarioCreateRequest) -> dict[str, Any]:
        return principia.scenarios.create(payload.name, parent_scenario_id=scenario_id).model_dump(
            mode="json"
        )

    @router.get("/scenarios/compare")
    def compare_scenarios(left: str, right: str) -> dict[str, Any]:
        return principia.scenarios.compare(left, right)

    @router.delete("/scenarios/{scenario_id:path}")
    def discard_scenario(scenario_id: str) -> dict[str, Any]:
        principia.scenarios.discard(scenario_id)
        return {"scenario_id": scenario_id, "status": "discarded"}

    if configure_router is not None:
        configure_router(app, router, principia)
    app.include_router(router)

    ui_root = ui_root_override or (Path(__file__).resolve().parents[1] / "ui_dist")
    assets_root = ui_root / "assets"

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    def static_asset(asset_path: str) -> FileResponse:
        candidate = (assets_root / asset_path).resolve()
        if assets_root.resolve() not in candidate.parents or not candidate.is_file():
            raise KeyError(asset_path)
        return FileResponse(candidate)

    def index_html() -> HTMLResponse:
        index_path = ui_root / "index.html"
        if index_path.exists():
            html = index_path.read_text(encoding="utf-8")
        else:
            html = "<!doctype html><html><body><main>Principia UI assets are missing.</main></body></html>"
        html = html.replace("__PRINCIPIA_SESSION__", app.state.session_token)
        return HTMLResponse(
            html,
            headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
        )

    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        return index_html()

    @app.get("/{route:path}", include_in_schema=False)
    def spa(route: str) -> HTMLResponse:
        first = route.split("/", 1)[0]
        routes = {"research", "library", "map", "local", "legacy"} | (extra_spa_routes or set())
        if first not in routes:
            raise KeyError(route)
        return index_html()

    return app
