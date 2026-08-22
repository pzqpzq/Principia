from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import shutil
import ssl
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import certifi
import httpx

from .._sqlite import connect_sqlite
from ..domain.hashing import file_sha256
from ..models import utc_now
from ..search_semantics import literal_query_terms, semantic_query_groups
from .canonical import PCG_ENTRIES, RecordKind, apply_cloud_delta, verify_cloud_snapshot
from .models_v1 import CloudManifest, CloudSearchRequest

DEFAULT_CONTROL_URL = "https://github.com/pzqpzq/Principia/releases/latest/download/latest.json"
SYNC_INTERVAL_SECONDS = 6 * 60 * 60
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


def _manifest_generation(manifest: CloudManifest | None) -> int:
    """Return the Cloud schema generation carried by a verified manifest."""

    if manifest is None:
        return 0
    return 2 if manifest.schema_version == "principia-global-manifest-v2" else 1


def _query_terms(query: str) -> list[str]:
    return literal_query_terms(query, limit=30)


def _fts_query(query: str) -> str:
    terms = _query_terms(query)
    quote = lambda term: f'"{term.replace(chr(34), "")}"'  # noqa: E731
    quoted = [quote(term) for term in terms]
    if not quoted:
        return ""

    clauses: list[str] = []
    groups = semantic_query_groups(terms)[:5]
    group_queries = [
        "(" + " OR ".join(quote(term) for term in sorted(group)[:10]) + ")" for group in groups
    ]
    # Cross-concept matches provide the offline semantic path.  For example,
    # an agent-team expression must intersect a proof/deduction expression for
    # a multi-agent theorem-proving goal; a generic agent paper is not enough.
    for index, left in enumerate(group_queries):
        for right in group_queries[index + 1 :]:
            clauses.append(f"({left} AND {right})")

    covered = set().union(*groups) if groups else set()
    unmatched = [term for term in terms if term not in covered]
    # A query whose meaningful terms all name one scientific concept (for
    # example "theorem proving") should match synonyms within that concept.
    # Keep mixed goals strict: "LLM post-training" must still require the
    # unmatched post-training term instead of degrading to generic LLM search.
    if len(group_queries) == 1 and not unmatched:
        clauses.append(group_queries[0])
    for group_query in group_queries:
        for term in unmatched[:6]:
            clauses.append(f"({group_query} AND {quote(term)})")

    if len(quoted) == 1:
        clauses.extend(quoted)
    else:
        clauses.extend(
            f"({left} AND {right})"
            for index, left in enumerate(quoted)
            for right in quoted[index + 1 :]
        )
    # A hyphenated term is only a complete search when it is the sole concept.
    # Adding it as a stand-alone OR clause in a multi-concept query made
    # ``LLM post-training`` equivalent to ``LLM OR post-training``.  Paper-first
    # expansion then surfaced every Principle linked to generic LLM papers.
    if len(quoted) == 1 and "-" in terms[0]:
        clauses.append(quoted[0])
    return " OR ".join(list(dict.fromkeys(clauses))[:160])


def _semantic_row_sort_key(
    row: dict[str, Any], query: str, identifier: str
) -> tuple[float, int, float, str]:
    """Prefer candidates covering the goal's leading scientific concept.

    SQLite BM25 still provides the within-concept ordering.  This small,
    deterministic layer prevents a secondary word such as ``theorem`` from
    placing an unrelated mathematical paper above the leading topic (for
    example ``multi-agent``) when vectors are unavailable.
    """

    haystack = " ".join(
        str(row.get(field) or "")
        for field in (
            "title",
            "abstract",
            "venue",
            "authors_json",
            "institutions_json",
            "area",
            "claim",
            "tags_json",
            "payload_json",
        )
    ).casefold()
    normalized_haystack = haystack.replace("_", " ").replace("-", " ")

    def contains(term: str) -> bool:
        return term in haystack or term.replace("-", " ") in normalized_haystack

    groups = semantic_query_groups(query)
    group_score = sum(
        (3.0 if index == 0 else 1.0)
        for index, group in enumerate(groups)
        if any(contains(term) for term in group)
    )
    literal_hits = sum(1 for term in _query_terms(query) if contains(term))
    return (
        -group_score,
        -literal_hits,
        float(row.get("lexical_rank") or 0.0),
        str(row.get(identifier) or ""),
    )


def _encode_offset(offset: int) -> str:
    return base64.urlsafe_b64encode(str(max(0, offset)).encode()).decode().rstrip("=")


def _decode_offset(cursor: str) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return max(0, int(base64.urlsafe_b64decode(padded).decode()))
    except Exception as exc:
        raise ValueError("invalid Global Cloud cursor") from exc


def _public_work_url(work: dict[str, Any]) -> str:
    """Project one durable public paper URL from a canonical Work record.

    Canonical v1 Works use ``landing_url`` and ``source_urls`` while legacy
    Explorer records used ``url``.  Keeping the projection here prevents UI
    clients from having to understand every identifier representation.
    """

    for key in ("source_url", "landing_url", "url"):
        value = str(work.get(key) or "").strip()
        if value.startswith("https://"):
            return value
    for value in work.get("source_urls") or []:
        candidate = str(value or "").strip()
        if candidate.startswith("https://"):
            return candidate
    for key, template in (
        ("doi", "https://doi.org/{value}"),
        ("arxiv_id", "https://arxiv.org/abs/{value}"),
        ("pmid", "https://pubmed.ncbi.nlm.nih.gov/{value}/"),
        ("pmcid", "https://www.ncbi.nlm.nih.gov/pmc/articles/{value}/"),
    ):
        value = str(work.get(key) or "").strip()
        if value:
            return template.format(value=value)
    return ""


_PLACEHOLDER_INTERPRETATIONS = {
    "study bound",
    "study-bound",
    "study_bound",
    "limited to reported conditions",
}


def _readable_principle_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project migration placeholders into useful, evidence-bounded prose.

    The v1 literature migration intentionally retained ``study_bound`` as a
    conservative scope marker.  It is valuable machine state but a poor human
    interpretation.  Keep canonical records immutable and improve only the
    runtime projection using the record's own conditions and boundary.
    """

    projected = dict(payload)
    raw = str(projected.get("interpretation") or "").strip()
    if raw.casefold().replace("_", " ") not in {
        value.replace("_", " ") for value in _PLACEHOLDER_INTERPRETATIONS
    }:
        return projected

    conditions = [
        str(value).strip()
        for value in projected.get("conditions") or []
        if str(value).strip()
    ]
    boundary = [
        str(value).strip()
        for value in projected.get("boundary") or []
        if str(value).strip()
    ]
    applications = [
        str(value).strip()
        for value in projected.get("applications") or []
        if str(value).strip()
    ]
    if conditions:
        interpretation = "Apply this result only when " + "; ".join(conditions[:4]) + "."
    elif applications:
        interpretation = "This result can inform " + "; ".join(applications[:3]) + "."
    else:
        interpretation = "Treat this as a scoped scientific result, not a universal rule."
    if boundary:
        interpretation += " " + boundary[0]
    elif not conditions:
        interpretation += " Transfer beyond the reported system remains unestablished."
    projected["interpretation"] = interpretation
    return projected


class GlobalCloudSnapshotStore:
    """Verified, atomically activated local projection of the GitHub Cloud release."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve() / "global-v1"
        self.releases_dir = self.root / "releases"
        self.downloads_dir = self.root / "downloads"
        self.state_path = self.root / "state.json"
        self.active_path = self.root / "active.json"
        self._sync_lock = threading.Lock()
        self._vector_cache_lock = threading.Lock()
        self._vector_rank_cache: dict[
            tuple[str, str, int, str], tuple[tuple[float, int], ...]
        ] = {}
        for path in (self.root, self.releases_dir, self.downloads_dir):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _json(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _atomic_json(self, path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def active(self) -> dict[str, Any]:
        pointer = self._json(self.active_path)
        release_id = str(pointer.get("release_id") or "")
        release_root = self.releases_dir / release_id if release_id else Path()
        database = release_root / "cloud.sqlite" if release_id else Path()
        manifest_path = release_root / "manifest.json" if release_id else Path()
        if not release_id or not database.is_file() or not manifest_path.is_file():
            return {}
        try:
            manifest = CloudManifest.model_validate_json(manifest_path.read_bytes())
        except Exception:
            return {}
        return {
            "release_id": release_id,
            "release_root": release_root,
            "database": database,
            "manifest": manifest,
            "activated_at": pointer.get("activated_at") or "",
        }

    def status(self) -> dict[str, Any]:
        active = self.active()
        state = self._json(self.state_path)
        manifest = active.get("manifest")
        return {
            "schema_version": "principia-global-status-v1",
            "available": bool(active),
            "release_id": manifest.release_id if manifest else "",
            "commit_sha": manifest.commit_sha if manifest else "",
            "content_digest": manifest.content_digest if manifest else "",
            "updated_at": manifest.created_at if manifest else "",
            "activated_at": active.get("activated_at") or "",
            "snapshot_bytes": manifest.snapshot_bytes if manifest else 0,
            "work_count": manifest.work_count if manifest else 0,
            "principle_count": manifest.principle_count if manifest else 0,
            "principle_revision_count": manifest.principle_revision_count if manifest else 0,
            "principle_work_count": manifest.principle_work_count if manifest else 0,
            "relation_count": manifest.relation_count if manifest else 0,
            "meta_principle_count": manifest.meta_principle_count if manifest else 0,
            "meta_principle_revision_count": (
                manifest.meta_principle_revision_count if manifest else 0
            ),
            "literature_principle_count": manifest.principle_count if manifest else 0,
            "total_principle_count": (
                (manifest.total_principle_count or manifest.principle_count) if manifest else 0
            ),
            "total_principle_revision_count": (
                (manifest.total_principle_revision_count or manifest.principle_revision_count)
                if manifest
                else 0
            ),
            "foundation_link_count": manifest.foundation_link_count if manifest else 0,
            "foundation_assessment_count": (
                manifest.foundation_assessment_count if manifest else 0
            ),
            "foundation_gap_count": manifest.foundation_gap_count if manifest else 0,
            "area_count": manifest.area_count if manifest else 0,
            "embedding_contract": manifest.embedding_contract if manifest else "",
            "vectors_complete": bool(manifest and manifest.vectors_complete),
            "last_checked_at": state.get("last_checked_at") or "",
            "last_error": state.get("last_error") or "",
            "stale": bool(state.get("last_error")),
            "control_url": state.get("control_url")
            or os.getenv("PRINCIPIA_GLOBAL_CONTROL_URL", DEFAULT_CONTROL_URL),
            "syncing": self._sync_lock.locked(),
        }

    def install_snapshot(
        self,
        snapshot: str | Path,
        *,
        expected_sha256: str = "",
        keep: int = 5,
        rollback_release_id: str = "",
    ) -> dict[str, Any]:
        source = Path(snapshot).expanduser().resolve()
        manifest = verify_cloud_snapshot(source, expected_sha256=expected_sha256)
        target = self.releases_dir / manifest.release_id
        build = Path(tempfile.mkdtemp(prefix=f".{manifest.release_id}.", dir=self.releases_dir))
        try:
            with zipfile.ZipFile(source) as archive:
                archive.extractall(build)
            installed_manifest = manifest.model_copy(
                update={
                    "snapshot_sha256": expected_sha256 or file_sha256(source),
                    "snapshot_bytes": source.stat().st_size,
                }
            )
            (build / "manifest.json").write_text(
                json.dumps(
                    installed_manifest.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(build / "cloud.sqlite", 0o600)
            if target.exists():
                shutil.rmtree(target)
            os.replace(build, target)
        except BaseException:
            shutil.rmtree(build, ignore_errors=True)
            raise
        previous = self.active().get("release_id") or ""
        requested_rollback = str(rollback_release_id or "").strip()
        if requested_rollback:
            rollback_root = self.releases_dir / requested_rollback
            if not (rollback_root / "cloud.sqlite").is_file() or not (
                rollback_root / "manifest.json"
            ).is_file():
                raise ValueError(
                    f"rollback release is not installed and verified: {requested_rollback}"
                )
            previous = requested_rollback
        self._atomic_json(
            self.active_path,
            {
                "schema_version": "principia-global-active-v1",
                "release_id": installed_manifest.release_id,
                "previous_release_id": previous,
                "activated_at": utc_now(),
            },
        )
        releases = sorted(
            [
                path
                for path in self.releases_dir.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        protected = {installed_manifest.release_id, previous}
        for old in releases[max(1, int(keep)) :]:
            if old.name not in protected:
                shutil.rmtree(old, ignore_errors=True)
        return self.status()

    def rollback(self) -> dict[str, Any]:
        pointer = self._json(self.active_path)
        previous = str(pointer.get("previous_release_id") or "")
        if not previous or not (self.releases_dir / previous / "cloud.sqlite").is_file():
            raise ValueError("no verified previous Global Cloud snapshot is available")
        current = str(pointer.get("release_id") or "")
        self._atomic_json(
            self.active_path,
            {
                "schema_version": "principia-global-active-v1",
                "release_id": previous,
                "previous_release_id": current,
                "activated_at": utc_now(),
            },
        )
        return self.status()

    def sync(self, *, control_url: str | None = None, force: bool = False) -> dict[str, Any]:
        if not self._sync_lock.acquire(blocking=False):
            return {**self.status(), "outcome": "already_syncing"}
        url = control_url or os.getenv("PRINCIPIA_GLOBAL_CONTROL_URL", DEFAULT_CONTROL_URL)
        state = self._json(self.state_path)
        now = utc_now()
        try:
            active_release_id = str(self.active().get("release_id") or "")
            state_release_id = str(state.get("release_id") or "")
            cache_matches_state = bool(active_release_id and state_release_id == active_release_id)
            if not force and cache_matches_state and state.get("last_checked_epoch"):
                elapsed = time.time() - float(state["last_checked_epoch"])
                if elapsed < SYNC_INTERVAL_SECONDS:
                    return {**self.status(), "outcome": "not_due"}
            headers = {"Accept": "application/json"}
            active_before_request = self.active()
            cached_release_id = str(state.get("release_id") or "")
            # An ETag is valid only for the snapshot generation recorded with
            # it.  If another process/test changed the active pointer, fetch
            # the control document again so the verified release is restored.
            if (
                not force
                and state.get("etag")
                and active_before_request
                and cached_release_id == str(active_before_request["release_id"])
            ):
                headers["If-None-Match"] = str(state["etag"])
            context = ssl.create_default_context(cafile=certifi.where())
            with httpx.Client(verify=context, timeout=20.0, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 304:
                    self._atomic_json(
                        self.state_path,
                        {
                            **state,
                            "control_url": url,
                            "last_checked_at": now,
                            "last_checked_epoch": time.time(),
                            "last_error": "",
                            "release_id": cached_release_id,
                        },
                    )
                    return {**self.status(), "outcome": "current"}
                response.raise_for_status()
                latest = response.json()
                release_id = str(latest.get("release_id") or "")
                snapshot_url = str(latest.get("snapshot_url") or latest.get("full_url") or "")
                digest = str(latest.get("snapshot_sha256") or "")
                if not release_id or not snapshot_url.startswith("https://") or len(digest) != 64:
                    raise ValueError("Global Cloud control manifest is incomplete")
                active = self.active()
                if active and active["release_id"] == release_id:
                    self._atomic_json(
                        self.state_path,
                        {
                            "schema_version": "principia-global-sync-state-v1",
                            "control_url": url,
                            "etag": response.headers.get("etag", ""),
                            "last_checked_at": now,
                            "last_checked_epoch": time.time(),
                            "last_error": "",
                            "release_id": release_id,
                        },
                    )
                    return {**self.status(), "outcome": "current"}
                download_url = snapshot_url
                download_kind = "full"
                delta = latest.get("delta") if isinstance(latest.get("delta"), dict) else {}
                full_size = int(latest.get("snapshot_bytes") or 0)
                if (
                    active
                    and str(delta.get("base_release_id") or "") == active["release_id"]
                    and str(delta.get("url") or "").startswith("https://")
                    and int(delta.get("bytes") or 0) > 0
                    and full_size > 0
                    and int(delta["bytes"]) < full_size * 0.4
                ):
                    download_url = str(delta["url"])
                    digest = str(delta.get("sha256") or "")
                    download_kind = "delta"
                temporary = (
                    self.downloads_dir
                    / f"{release_id}.{'pcd' if download_kind == 'delta' else 'pcg'}.partial"
                )
                with client.stream("GET", download_url) as download:
                    download.raise_for_status()
                    size = 0
                    with temporary.open("wb") as handle:
                        for chunk in download.iter_bytes():
                            size += len(chunk)
                            if size > MAX_DOWNLOAD_BYTES:
                                raise ValueError("Global Cloud download exceeds its size limit")
                            handle.write(chunk)
                if file_sha256(temporary) != digest:
                    raise ValueError("Global Cloud download digest mismatch")
                installation_source = temporary
                if download_kind == "delta":
                    active_snapshot = self.downloads_dir / f"{active['release_id']}.active.pcg"
                    with zipfile.ZipFile(
                        active_snapshot, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
                    ) as archive:
                        for name in sorted(PCG_ENTRIES):
                            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                            info.compress_type = zipfile.ZIP_DEFLATED
                            info.external_attr = (0o100644 & 0xFFFF) << 16
                            archive.writestr(info, (active["release_root"] / name).read_bytes())
                    installation_source = self.downloads_dir / f"{release_id}.pcg.partial"
                    apply_cloud_delta(active_snapshot, temporary, installation_source)
                    active_snapshot.unlink(missing_ok=True)
                    # The locally rebuilt SQLite snapshot may differ bytewise
                    # across SQLite versions while remaining logically equal.
                    # `apply_cloud_delta` verifies the target logical digest;
                    # installation then verifies this local archive's own hash.
                    digest = file_sha256(installation_source)
                candidate_manifest = verify_cloud_snapshot(
                    installation_source, expected_sha256=digest
                )
                active_manifest = active.get("manifest") if active else None
                if _manifest_generation(candidate_manifest) < _manifest_generation(
                    active_manifest
                ):
                    # The public pointer can legitimately lag a locally staged
                    # schema transition. Background synchronization must never
                    # replace a newer verified schema with an older release.
                    # Explicit rollback remains available through ``rollback``.
                    temporary.unlink(missing_ok=True)
                    if installation_source != temporary:
                        installation_source.unlink(missing_ok=True)
                    self._atomic_json(
                        self.state_path,
                        {
                            "schema_version": "principia-global-sync-state-v1",
                            "control_url": url,
                            "etag": response.headers.get("etag", ""),
                            "last_checked_at": now,
                            "last_checked_epoch": time.time(),
                            "last_error": "",
                            "release_id": str(active.get("release_id") or ""),
                            "remote_release_id": candidate_manifest.release_id,
                            "update_ignored_reason": "schema_downgrade_blocked",
                        },
                    )
                    return {
                        **self.status(),
                        "outcome": "schema_downgrade_blocked",
                        "remote_release_id": candidate_manifest.release_id,
                    }
                outcome = self.install_snapshot(installation_source, expected_sha256=digest)
                temporary.unlink(missing_ok=True)
                if installation_source != temporary:
                    installation_source.unlink(missing_ok=True)
                self._atomic_json(
                    self.state_path,
                    {
                        "schema_version": "principia-global-sync-state-v1",
                        "control_url": url,
                        "etag": response.headers.get("etag", ""),
                        "last_checked_at": now,
                        "last_checked_epoch": time.time(),
                        "last_error": "",
                        "release_id": release_id,
                    },
                )
                return {**outcome, "outcome": "updated", "transport": download_kind}
        except Exception as exc:
            self._atomic_json(
                self.state_path,
                {
                    **state,
                    "schema_version": "principia-global-sync-state-v1",
                    "control_url": url,
                    "last_checked_at": now,
                    "last_checked_epoch": time.time(),
                    "last_error": type(exc).__name__,
                },
            )
            raise
        finally:
            self._sync_lock.release()

    def start_background_sync(self) -> bool:
        if os.getenv("PRINCIPIA_DISABLE_GLOBAL_SYNC") == "1" or os.getenv("PYTEST_CURRENT_TEST"):
            return False
        thread = threading.Thread(
            target=self._background_sync,
            name="principia-global-sync",
            daemon=True,
        )
        thread.start()
        return True

    def _background_sync(self) -> None:
        try:
            self.sync()
        except Exception:
            pass

    def _connect(self) -> Any:
        active = self.active()
        if not active:
            raise FileNotFoundError("no verified Global Cloud snapshot is installed")
        conn = connect_sqlite(f"file:{active['database']}?mode=ro", uri=True)
        conn.row_factory = __import__("sqlite3").Row
        return conn

    @staticmethod
    def _table_exists(conn: Any, name: str) -> bool:
        return bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
                (name,),
            ).fetchone()
        )

    @staticmethod
    def _column_exists(conn: Any, table: str, name: str) -> bool:
        return any(str(row[1]) == name for row in conn.execute(f"PRAGMA table_info({table})"))

    def canonical_records(
        self, *, include_extended: bool = False
    ) -> dict[RecordKind, list[dict[str, Any]]]:
        """Return canonical payloads from the active verified snapshot.

        A reviewed publication extends the release that was actually pinned,
        never a potentially stale JSON fixture bundled with the application.
        """

        with self._connect() as conn:
            tables: dict[RecordKind, str] = {
                "works": "works",
                "principles": "principles",
                "principle-work": "principle_work",
                "relations": "relations",
            }
            if include_extended and self._table_exists(conn, "foundation_links"):
                tables.update(
                    {
                        "foundation-links": "foundation_links",
                        "foundation-assessments": "foundation_assessments",
                        "foundation-gaps": "foundation_gaps",
                    }
                )
            output: dict[RecordKind, list[dict[str, Any]]] = {}
            if include_extended and self._column_exists(conn, "principles", "principle_class"):
                output["meta-principles"] = []
            for kind, table in tables.items():
                output[kind] = []
                for row in conn.execute(
                    f"SELECT payload_json FROM {table} ORDER BY payload_json"
                ).fetchall():
                    payload = json.loads(row[0])
                    if kind == "principles" and payload.get("canonical_area"):
                        payload["area"] = payload.pop("canonical_area")
                    if payload.get("principle_class") == "meta":
                        if not include_extended:
                            continue
                        output["meta-principles"].append(payload)
                        continue
                    output[kind].append(payload)
            return output

    def _work_filters(self, request: CloudSearchRequest, alias: str = "w") -> tuple[str, list[Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if request.year_from is not None:
            clauses.append(f"{alias}.year>=?")
            values.append(request.year_from)
        if request.year_to is not None:
            clauses.append(f"{alias}.year<=?")
            values.append(request.year_to)
        if request.venues:
            clauses.append(f"{alias}.venue IN ({','.join('?' for _ in request.venues)})")
            values.extend(request.venues)
        if request.institutions:
            for institution in request.institutions:
                clauses.append(f"{alias}.institutions_json LIKE ?")
                values.append(f"%{institution}%")
        if request.full_text_status:
            clauses.append(f"{alias}.full_text_status=?")
            values.append(request.full_text_status)
        for field, low, high in (
            ("page_count", request.page_min, request.page_max),
            ("pdf_bytes", request.pdf_bytes_min, request.pdf_bytes_max),
        ):
            if low is not None:
                clauses.append(f"{alias}.{field}>=?")
                values.append(low)
            if high is not None:
                clauses.append(f"{alias}.{field}<=?")
                values.append(high)
        return (" AND " + " AND ".join(clauses)) if clauses else "", values

    def _lexical_works(self, request: CloudSearchRequest, *, limit: int) -> list[dict[str, Any]]:
        offset = _decode_offset(request.cursor)
        filters, values = self._work_filters(request)
        with self._connect() as conn:
            if _query_terms(request.query):
                rows = conn.execute(
                    f"""
                    SELECT w.*, bm25(work_fts) lexical_rank
                    FROM work_fts JOIN current_works w USING(work_id)
                    WHERE work_fts MATCH ? {filters}
                    ORDER BY lexical_rank, w.work_id LIMIT ? OFFSET ?
                    """,
                    (_fts_query(request.query), *values, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT w.*, 0.0 lexical_rank FROM current_works w WHERE 1=1 {filters} "
                    "ORDER BY w.updated_at DESC, w.work_id LIMIT ? OFFSET ?",
                    (*values, limit, offset),
                ).fetchall()
        items = [dict(row) for row in rows]
        if request.query and semantic_query_groups(request.query):
            items.sort(key=lambda row: _semantic_row_sort_key(row, request.query, "work_id"))
        return items

    def _work_count(self, request: CloudSearchRequest) -> int:
        filters, values = self._work_filters(request)
        with self._connect() as conn:
            if _query_terms(request.query):
                row = conn.execute(
                    f"SELECT COUNT(*) FROM work_fts JOIN current_works w USING(work_id) "
                    f"WHERE work_fts MATCH ? {filters}",
                    (_fts_query(request.query), *values),
                ).fetchone()
            else:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM current_works w WHERE 1=1 {filters}", values
                ).fetchone()
        return int(row[0])

    def _vector_rows(
        self,
        entity: str,
        query_vector: list[float] | None,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        active = self.active()
        manifest = active.get("manifest")
        if not query_vector or not manifest or not manifest.vectors_complete:
            return []
        if len(query_vector) != manifest.vector_dimensions:
            raise ValueError("query embedding dimension does not match the Cloud contract")
        try:
            import numpy as np

            query = np.asarray(query_vector, dtype=np.float32)
            norm = float(np.linalg.norm(query))
            if not math.isfinite(norm) or norm <= 0:
                raise ValueError("query embedding must be finite and non-zero")
            query /= norm
            cache_key = (
                manifest.release_id,
                entity,
                int(limit),
                hashlib.sha256(query.tobytes()).hexdigest(),
            )
            if entity == "paper":
                path = active["release_root"] / "work-vectors.f16"
                count = manifest.work_count
                ordinal_table, current_table, identifier = (
                    "work_vector_ordinals",
                    "current_works",
                    "work_id",
                )
            else:
                path = active["release_root"] / "principle-vectors.f16"
                count = manifest.total_principle_count or manifest.principle_count
                ordinal_table, current_table, identifier = (
                    "principle_vector_ordinals",
                    "current_principles",
                    "principle_id",
                )
            with self._vector_cache_lock:
                cached = self._vector_rank_cache.get(cache_key)
            if cached is None:
                vectors = np.memmap(
                    path,
                    dtype=np.float16,
                    mode="r",
                    shape=(count, manifest.vector_dimensions),
                )
                # Promote one bounded mmap window for BLAS.  The 32 MiB window
                # keeps the source file memory-mapped while avoiding the severe
                # per-block overhead of float16 scalar matmul on Intel Macs.
                candidates: list[tuple[float, int]] = []
                block = 8192
                for start in range(0, count, block):
                    vector_block = np.asarray(
                        vectors[start : start + block], dtype=np.float32
                    )
                    scores = vector_block @ query
                    candidates.extend(
                        (float(score), start + index) for index, score in enumerate(scores)
                    )
                candidates.sort(key=lambda item: (-item[0], item[1]))
                chosen = candidates[: max(1, min(limit, count))]
                with self._vector_cache_lock:
                    self._vector_rank_cache[cache_key] = tuple(chosen)
                    while len(self._vector_rank_cache) > 16:
                        self._vector_rank_cache.pop(next(iter(self._vector_rank_cache)))
            else:
                chosen = list(cached)
            if not chosen:
                return []
            ordinals = [ordinal for _, ordinal in chosen]
            placeholders = ",".join("?" for _ in ordinals)
            with self._connect() as conn:
                rows = conn.execute(
                    f"SELECT c.*, o.ordinal FROM {ordinal_table} o JOIN {current_table} c "
                    f"USING({identifier}) WHERE o.ordinal IN ({placeholders})",
                    ordinals,
                ).fetchall()
            by_ordinal = {int(row["ordinal"]): dict(row) for row in rows}
            return [
                {**by_ordinal[ordinal], "vector_score": score}
                for score, ordinal in chosen
                if ordinal in by_ordinal
            ]
        except ImportError:
            return []

    def _hybrid_works(
        self,
        request: CloudSearchRequest,
        *,
        limit: int,
        query_vector: list[float] | None,
    ) -> tuple[list[dict[str, Any]], str]:
        lexical = self._lexical_works(request, limit=max(limit, request.paper_cohort))
        vector = self._vector_rows(
            "paper", query_vector, limit=max(limit, request.paper_cohort * 2)
        )
        if not vector:
            mode = (
                "conceptual_fts"
                if request.query and semantic_query_groups(request.query)
                else "fts"
            )
            return lexical[:limit], mode
        filters, values = self._work_filters(request)
        vector_ids = [str(row["work_id"]) for row in vector]
        placeholders = ",".join("?" for _ in vector_ids)
        with self._connect() as conn:
            eligible = {
                str(row[0])
                for row in conn.execute(
                    f"SELECT w.work_id FROM current_works w WHERE w.work_id IN ({placeholders}) {filters}",
                    (*vector_ids, *values),
                )
            }
        vector = [row for row in vector if str(row["work_id"]) in eligible]
        scores: dict[str, float] = {}
        rows_by_id: dict[str, dict[str, Any]] = {}
        for ranking in (lexical, vector):
            for rank, row in enumerate(ranking, start=1):
                identifier = str(row["work_id"])
                scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (60 + rank)
                rows_by_id.setdefault(identifier, row)
        ordered = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))
        return [
            {**rows_by_id[identifier], "rrf_score": scores[identifier]}
            for identifier in ordered[:limit]
        ], "hybrid_rrf"

    def _lexical_principles(
        self,
        query: str,
        *,
        limit: int,
        offset: int = 0,
        areas: list[str] | None = None,
        principle_class: str = "literature",
    ) -> list[dict[str, Any]]:
        area_filter = ""
        area_values: list[Any] = []
        if areas:
            area_filter = f" AND p.area IN ({','.join('?' for _ in areas)})"
            area_values = list(areas)
        with self._connect() as conn:
            class_filter = ""
            class_values: list[Any] = []
            class_supported = self._column_exists(
                conn, "current_principles", "principle_class"
            )
            if not class_supported and principle_class != "literature":
                return []
            if class_supported:
                class_filter = " AND p.principle_class=?"
                class_values.append(principle_class)
            if _query_terms(query):
                rows = conn.execute(
                    f"""
                    SELECT p.*, bm25(principle_fts) lexical_rank
                    FROM principle_fts JOIN current_principles p USING(principle_id)
                    WHERE principle_fts MATCH ? AND p.status='active' {area_filter} {class_filter}
                    ORDER BY lexical_rank, p.principle_id LIMIT ? OFFSET ?
                    """,
                    (_fts_query(query), *area_values, *class_values, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT p.*, 0.0 lexical_rank FROM current_principles p "
                    f"WHERE p.status='active' {area_filter} {class_filter} ORDER BY p.updated_at DESC, p.principle_id LIMIT ? OFFSET ?",
                    (*area_values, *class_values, limit, offset),
                ).fetchall()
        items = [dict(row) for row in rows]
        if query and semantic_query_groups(query):
            items.sort(key=lambda row: _semantic_row_sort_key(row, query, "principle_id"))
        return items

    @staticmethod
    def _rrf(rows: list[dict[str, Any]], identifier: str) -> dict[str, float]:
        return {str(row[identifier]): 1.0 / (60 + rank) for rank, row in enumerate(rows, start=1)}

    def _direct_principle_search(
        self,
        request: CloudSearchRequest,
        *,
        principle_class: str,
        query_vector: list[float] | None,
    ) -> dict[str, Any]:
        offset = _decode_offset(request.cursor)
        if not _query_terms(request.query):
            with self._connect() as conn:
                class_supported = self._column_exists(conn, "current_principles", "principle_class")
                if not class_supported and principle_class != "literature":
                    return {
                        "items": [],
                        "next_cursor": None,
                        "total": 0,
                        "facets": self.facets(),
                        "ranking_mode": "browse",
                        "release_id": self.status()["release_id"],
                    }
                class_clause = " AND principle_class=?" if class_supported else ""
                class_values: list[Any] = [principle_class] if class_supported else []
                area_clause = ""
                area_values: list[Any] = []
                if request.areas:
                    area_clause = f" AND area IN ({','.join('?' for _ in request.areas)})"
                    area_values = list(request.areas)
                total = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM current_principles WHERE status='active'"
                        f"{class_clause}{area_clause}",
                        (*class_values, *area_values),
                    ).fetchone()[0]
                )
                rows = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT * FROM current_principles WHERE status='active'"
                        f"{class_clause}{area_clause} ORDER BY updated_at DESC, principle_id "
                        "LIMIT ? OFFSET ?",
                        (*class_values, *area_values, request.limit + 1, offset),
                    ).fetchall()
                ]
            return {
                "items": [self._principle_item(row) for row in rows[: request.limit]],
                "next_cursor": (
                    _encode_offset(offset + request.limit) if len(rows) > request.limit else None
                ),
                "total": total,
                "facets": self.facets(),
                "ranking_mode": "browse",
                "release_id": self.status()["release_id"],
            }
        candidate_limit = max(request.paper_cohort, offset + request.limit * 4)
        lexical = self._lexical_principles(
            request.query,
            limit=candidate_limit,
            areas=request.areas,
            principle_class=principle_class,
        )
        vector = [
            row
            for row in self._vector_rows("principle", query_vector, limit=candidate_limit * 2)
            if str(row.get("principle_class") or "literature") == principle_class
        ]
        scores = self._rrf(lexical, "principle_id")
        by_id = {str(row["principle_id"]): row for row in lexical}
        for identifier, score in self._rrf(vector, "principle_id").items():
            scores[identifier] = scores.get(identifier, 0.0) + score
        for row in vector:
            by_id.setdefault(str(row["principle_id"]), row)
        ranked = [
            {**by_id[identifier], "score": scores[identifier], "match_path": "direct"}
            for identifier in sorted(scores, key=lambda value: (-scores[value], value))
        ]
        page = ranked[offset : offset + request.limit]
        return {
            "items": [self._principle_item(row) for row in page],
            "next_cursor": (
                _encode_offset(offset + request.limit)
                if offset + request.limit < len(ranked)
                else None
            ),
            "total": len(ranked),
            "facets": self.facets(),
            "ranking_mode": "hybrid_rrf" if vector else "conceptual_fts",
            "release_id": self.status()["release_id"],
        }

    def search(
        self,
        request: CloudSearchRequest,
        *,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        if not self.active():
            return {
                "items": [],
                "next_cursor": None,
                "total": 0,
                "facets": {},
                "ranking_mode": "unavailable",
                "release_id": "",
            }
        offset = _decode_offset(request.cursor)
        if request.entity == "paper":
            rows, ranking_mode = self._hybrid_works(
                request, limit=request.limit + 1, query_vector=query_vector
            )
            items = [self._work_item(row) for row in rows[: request.limit]]
            return {
                "items": items,
                "next_cursor": _encode_offset(offset + request.limit)
                if len(rows) > request.limit
                else None,
                "total": self._work_count(request),
                "facets": self.facets(),
                "ranking_mode": ranking_mode,
                "release_id": self.status()["release_id"],
            }
        if request.entity == "meta_principle":
            return self._direct_principle_search(
                request, principle_class="meta", query_vector=query_vector
            )
        if request.entity == "principle":
            # An empty query means browse the complete active Cloud.  Running
            # paper-first retrieval here would silently cap the atlas to the
            # Principles linked from the default 100-paper cohort.
            if not _query_terms(request.query):
                return self._direct_principle_search(
                    request, principle_class="literature", query_vector=query_vector
                )
            return self._paper_first_principles(request, query_vector=query_vector)
        # `all` is a single ranked result set, so its cursor must be applied
        # after papers and Principles have been merged.  Applying the cursor
        # independently to papers (and resetting it for Principles) duplicated
        # rows on later pages and reported only the Principle subtotal.
        combined_limit = offset + request.limit
        paper_result = self.search(
            request.model_copy(update={"entity": "paper", "cursor": "", "limit": combined_limit}),
            query_vector=query_vector,
        )
        principle_result = self._paper_first_principles(
            request.model_copy(
                update={"entity": "principle", "cursor": "", "limit": combined_limit}
            ),
            query_vector=query_vector,
        )
        meta_result = self._direct_principle_search(
            request.model_copy(
                update={"entity": "meta_principle", "cursor": "", "limit": combined_limit}
            ),
            principle_class="meta",
            query_vector=query_vector,
        )
        items: list[dict[str, Any]] = []
        # Entity-specific scores are not numerically comparable (Work RRF,
        # paper-expanded Principle relevance, and direct Meta FTS/vector
        # relevance). Fuse the three ranked lists once more so an `all` query
        # cannot bury every paper beneath a different score scale.
        for entity_order, result in enumerate((paper_result, principle_result, meta_result)):
            for rank, item in enumerate(result["items"], start=1):
                items.append(
                    {
                        **item,
                        "cross_entity_score": 1.0 / (60 + rank),
                        "_entity_order": entity_order,
                    }
                )
        items.sort(
            key=lambda item: (
                -float(item["cross_entity_score"]),
                int(item["_entity_order"]),
                -float(item.get("score") or 0),
                str(item.get("id") or ""),
            )
        )
        for item in items:
            item.pop("_entity_order", None)
        total = (
            int(paper_result["total"]) + int(principle_result["total"]) + int(meta_result["total"])
        )
        page = items[offset : offset + request.limit]
        return {
            **principle_result,
            "items": page,
            "next_cursor": (
                _encode_offset(offset + request.limit) if offset + request.limit < total else None
            ),
            "total": total,
            "entity": "all",
        }

    def _paper_first_principles(
        self,
        request: CloudSearchRequest,
        *,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        offset = _decode_offset(request.cursor)
        papers, paper_mode = self._hybrid_works(
            request.model_copy(update={"cursor": ""}),
            limit=request.paper_cohort,
            query_vector=query_vector,
        )
        paper_scores = self._rrf(papers, "work_id")
        linked: dict[str, dict[str, Any]] = {}
        if papers:
            ids = [str(row["work_id"]) for row in papers]
            placeholders = ",".join("?" for _ in ids)
            with self._connect() as conn:
                class_supported = self._column_exists(
                    conn, "current_principles", "principle_class"
                )
                class_clause = " AND p.principle_class='literature'" if class_supported else ""
                # The class/status index is excellent for browsing but causes
                # SQLite to scan all literature Principles before applying the
                # small matched-Work cohort. Pin this expansion to the identity
                # index so `principle_work(work_id, principle_id)` drives it.
                principle_index = " INDEXED BY idx_current_principles_id" if class_supported else ""
                rows = conn.execute(
                    f"""
                    SELECT p.*, pw.work_id, pw.role, w.title matched_paper_title,
                           w.payload_json matched_paper_json
                    FROM principle_work pw
                    JOIN current_principles p{principle_index}
                     ON p.principle_id=pw.principle_id
                     AND p.revision=pw.principle_revision
                    JOIN current_works w USING(work_id)
                    WHERE pw.work_id IN ({placeholders}) AND p.status='active' {class_clause}
                    ORDER BY p.principle_id, pw.work_id
                    """,
                    ids,
                ).fetchall()
            for row in rows:
                item = linked.setdefault(
                    str(row["principle_id"]),
                    {**dict(row), "matched_papers": [], "paper_score": 0.0},
                )
                item["paper_score"] = max(
                    item["paper_score"], paper_scores.get(str(row["work_id"]), 0)
                )
                # A Principle can have multiple evidence locators in one Work.
                # Search cards link the paper once; the detail endpoint retains
                # every locator for provenance inspection.
                if not any(paper["work_id"] == row["work_id"] for paper in item["matched_papers"]):
                    matched_paper = json.loads(row["matched_paper_json"])
                    item["matched_papers"].append(
                        {
                            "work_id": row["work_id"],
                            "title": row["matched_paper_title"],
                            "url": _public_work_url(matched_paper),
                            "role": row["role"],
                        }
                    )
        direct = self._lexical_principles(
            request.query,
            limit=max(request.paper_cohort, request.limit * 4),
            areas=request.areas,
        )
        vector_principles = [
            row
            for row in self._vector_rows(
                "principle", query_vector, limit=max(request.paper_cohort, request.limit * 4)
            )
            if str(row.get("principle_class") or "literature") == "literature"
        ]
        direct_scores = self._rrf(direct, "principle_id")
        if vector_principles:
            for principle_id, value in self._rrf(vector_principles, "principle_id").items():
                direct_scores[principle_id] = direct_scores.get(principle_id, 0.0) + value
            direct_by_id = {str(row["principle_id"]): row for row in direct}
            for row in vector_principles:
                direct_by_id.setdefault(str(row["principle_id"]), row)
            direct = [
                direct_by_id[identifier]
                for identifier in sorted(
                    direct_by_id,
                    key=lambda identifier: (-direct_scores.get(identifier, 0), identifier),
                )
            ]
        for principle_id, item in linked.items():
            item["score"] = item["paper_score"] * 0.6 + direct_scores.get(principle_id, 0) * 0.4
            item["match_path"] = "paper_first"
        if len(linked) < offset + request.limit:
            for row in direct:
                principle_id = str(row["principle_id"])
                if principle_id in linked:
                    continue
                linked[principle_id] = {
                    **row,
                    "matched_papers": [],
                    "score": direct_scores[principle_id] * 0.4,
                    "match_path": "fallback_direct",
                }
        if request.areas:
            linked = {
                key: value
                for key, value in linked.items()
                if str(value.get("area") or "") in request.areas
            }
        ranked = sorted(
            linked.values(), key=lambda row: (-float(row["score"]), str(row["principle_id"]))
        )
        page = ranked[offset : offset + request.limit]
        items = [self._principle_item(row) for row in page]
        return {
            "items": items,
            "next_cursor": _encode_offset(offset + request.limit)
            if offset + request.limit < len(ranked)
            else None,
            "total": len(ranked),
            "facets": self.facets(),
            "ranking_mode": f"paper_first_{paper_mode}"
            if not vector_principles
            else "paper_first_hybrid_rrf",
            "release_id": self.status()["release_id"],
        }

    @staticmethod
    def _work_item(row: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        return {
            "id": row["work_id"],
            "entity": "paper",
            "score": float(row.get("rrf_score") or row.get("vector_score") or 0),
            **payload,
            "source_url": _public_work_url(payload),
        }

    @staticmethod
    def _principle_item(row: dict[str, Any]) -> dict[str, Any]:
        payload = _readable_principle_payload(json.loads(row["payload_json"]))
        principle_class = str(payload.get("principle_class") or "literature")
        return {
            "id": row["principle_id"],
            "entity": "principle",
            "source": "global",
            "record_kind": "meta_principle" if principle_class == "meta" else "ordinary",
            "principle_class": principle_class,
            "score": float(row.get("score") or 0),
            "match_path": row.get("match_path") or "direct",
            "matched_papers": row.get("matched_papers") or [],
            **payload,
        }

    def work(self, work_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM current_works WHERE work_id=?", (work_id,)
            ).fetchone()
            if not row:
                return None
            links = conn.execute(
                "SELECT principle_id, principle_revision, role, page, section, evidence_digest "
                "FROM principle_work WHERE work_id=? ORDER BY principle_id, principle_revision",
                (work_id,),
            ).fetchall()
        return {**json.loads(row[0]), "linked_principles": [dict(item) for item in links]}

    def work_revisions(self, work_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM works WHERE work_id=? ORDER BY revision DESC",
                (work_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def match_work(self, proposed: dict[str, Any]) -> dict[str, Any]:
        if not self.active():
            return {"kind": "new", "match": None, "reason": "cloud_unavailable"}
        strong = [
            (field, str(proposed.get(field) or "").strip().casefold())
            for field in ("doi", "arxiv_id", "pmid", "pmcid", "openalex_id", "semantic_scholar_id")
            if str(proposed.get(field) or "").strip()
        ]
        with self._connect() as conn:
            for field, value in strong:
                row = conn.execute(
                    f"SELECT payload_json FROM current_works WHERE lower({field})=? LIMIT 1",
                    (value,),
                ).fetchone()
                if row:
                    current = json.loads(row[0])
                    kind = (
                        "exact"
                        if current.get("content_digest") == proposed.get("content_digest")
                        else "strong_id"
                    )
                    return {"kind": kind, "match": current, "reason": field}
            title = " ".join(str(proposed.get("title") or "").casefold().split())
            if title:
                row = conn.execute(
                    "SELECT payload_json FROM current_works WHERE lower(trim(title))=? LIMIT 1",
                    (title,),
                ).fetchone()
                if row:
                    return {
                        "kind": "ambiguous",
                        "match": json.loads(row[0]),
                        "reason": "title_only",
                    }
        return {"kind": "new", "match": None, "reason": "no_match"}

    def match_principle(self, proposed: dict[str, Any]) -> dict[str, Any]:
        if not self.active():
            return {"kind": "new", "match": None, "similarity": 0.0, "reason": "cloud_unavailable"}
        principle_id = str(proposed.get("principle_id") or "")
        content_digest = str(proposed.get("content_digest") or "")
        with self._connect() as conn:
            if principle_id:
                row = conn.execute(
                    "SELECT payload_json FROM current_principles WHERE principle_id=?",
                    (principle_id,),
                ).fetchone()
                if row:
                    current = json.loads(row[0])
                    return {
                        "kind": "exact"
                        if current.get("content_digest") == content_digest
                        else "strong_id",
                        "match": current,
                        "similarity": 1.0,
                        "reason": "principle_id",
                    }
            if content_digest:
                row = conn.execute(
                    "SELECT payload_json FROM current_principles WHERE content_digest=? LIMIT 1",
                    (content_digest,),
                ).fetchone()
                if row:
                    return {
                        "kind": "exact",
                        "match": json.loads(row[0]),
                        "similarity": 1.0,
                        "reason": "content_digest",
                    }
        query = " ".join([str(proposed.get("title") or ""), str(proposed.get("claim") or "")])
        candidates = self._lexical_principles(query, limit=3)
        if candidates:
            proposed_terms = set(_query_terms(query.casefold()))
            best = candidates[0]
            current = json.loads(best["payload_json"])
            current_terms = set(
                _query_terms(f"{current.get('title', '')} {current.get('claim', '')}".casefold())
            )
            similarity = len(proposed_terms & current_terms) / max(
                1, len(proposed_terms | current_terms)
            )
            if similarity >= 0.75:
                return {
                    "kind": "ambiguous",
                    "match": current,
                    "similarity": similarity,
                    "reason": "semantic_near_duplicate",
                }
        return {"kind": "new", "match": None, "similarity": 0.0, "reason": "no_match"}

    def principle(self, principle_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM current_principles WHERE principle_id=?", (principle_id,)
            ).fetchone()
            if not row:
                return None
            references = conn.execute(
                """
                SELECT pw.work_id, pw.role, pw.page, pw.section,
                       pw.evidence_digest, w.payload_json work_json
                FROM principle_work pw JOIN current_works w USING(work_id)
                WHERE pw.principle_id=? AND pw.principle_revision=(
                    SELECT MAX(revision) FROM principles WHERE principle_id=?
                ) ORDER BY pw.work_id, pw.role, pw.page, pw.section, pw.evidence_digest
                """,
                (principle_id, principle_id),
            ).fetchall()
            relations = conn.execute(
                "SELECT payload_json, CASE WHEN source_principle_id=? THEN 'outgoing' ELSE 'incoming' END orientation "
                "FROM relations WHERE (source_principle_id=? OR target_principle_id=?) "
                "AND status IN ('active','proposed') ORDER BY relation_id, revision DESC",
                (principle_id, principle_id, principle_id),
            ).fetchall()
            foundation_links: list[Any] = []
            foundation_assessment: Any = None
            linked_children: list[Any] = []
            if self._table_exists(conn, "foundation_links"):
                foundation_links = conn.execute(
                    "SELECT fl.payload_json link_json, mp.payload_json meta_json "
                    "FROM foundation_links fl JOIN current_principles mp "
                    "ON mp.principle_id=fl.meta_principle_id "
                    "WHERE fl.principle_id=? AND fl.status!='retired' "
                    "ORDER BY fl.confidence DESC, fl.link_id",
                    (principle_id,),
                ).fetchall()
                foundation_assessment = conn.execute(
                    "SELECT payload_json FROM foundation_assessments WHERE principle_id=? "
                    "ORDER BY revision DESC LIMIT 1",
                    (principle_id,),
                ).fetchone()
                linked_children = conn.execute(
                    "SELECT fl.payload_json link_json, p.payload_json principle_json "
                    "FROM foundation_links fl JOIN current_principles p "
                    "ON p.principle_id=fl.principle_id "
                    "WHERE fl.meta_principle_id=? AND fl.status!='retired' "
                    "ORDER BY fl.confidence DESC, fl.link_id",
                    (principle_id,),
                ).fetchall()
        payload = _readable_principle_payload(json.loads(row[0]))
        # A Principle may have many page/section evidence anchors in the same
        # paper.  Public sources are Works, not anchors: projecting one source
        # card per principle_work row made a single paper appear dozens of
        # times.  Aggregate every anchor under its unique Work identity while
        # retaining the complete evidence locator history for inspection.
        public_sources: dict[str, dict[str, Any]] = {}
        for item in references:
            work = json.loads(item["work_json"])
            work_id = str(item["work_id"] or work.get("work_id") or "")
            source = public_sources.setdefault(
                work_id,
                {
                    **work,
                    "work_id": work_id,
                    "source_url": _public_work_url(work),
                    "roles": [],
                    "evidence_anchors": [],
                },
            )
            role = str(item["role"] or "evidence")
            if role not in source["roles"]:
                source["roles"].append(role)
            anchor = {
                "role": role,
                "page": item["page"],
                "section": str(item["section"] or ""),
                "evidence_digest": str(item["evidence_digest"] or ""),
            }
            if anchor not in source["evidence_anchors"]:
                source["evidence_anchors"].append(anchor)
        payload["source_references"] = [
            {
                **source,
                "role": source["roles"][0] if source["roles"] else "evidence",
                "evidence_anchor_count": len(source["evidence_anchors"]),
            }
            for _, source in sorted(public_sources.items())
        ]
        payload["relations"] = [
            {**json.loads(item[0]), "orientation": item["orientation"]} for item in relations
        ]
        payload["foundations"] = [
            {
                "link": json.loads(item["link_json"]),
                "meta_principle": json.loads(item["meta_json"]),
            }
            for item in foundation_links
        ]
        payload["foundation_assessment"] = (
            json.loads(foundation_assessment[0]) if foundation_assessment else None
        )
        payload["linked_children"] = [
            {
                "link": json.loads(item["link_json"]),
                "principle": json.loads(item["principle_json"]),
            }
            for item in linked_children
        ]
        payload["source"] = "global"
        payload["record_kind"] = (
            "meta_principle" if payload.get("principle_class") == "meta" else "ordinary"
        )
        return payload

    def foundations(self, principle_id: str) -> dict[str, Any] | None:
        principle = self.principle(principle_id)
        if principle is None:
            return None
        return {
            "principle_id": principle_id,
            "principle_class": principle.get("principle_class") or "literature",
            "assessment": principle.get("foundation_assessment"),
            "foundations": principle.get("foundations") or [],
            "linked_children": principle.get("linked_children") or [],
        }

    def principle_revisions(self, principle_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM principles WHERE principle_id=? ORDER BY revision DESC",
                (principle_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def facets(self) -> dict[str, Any]:
        with self._connect() as conn:
            years = [
                dict(row)
                for row in conn.execute(
                    "SELECT year value, COUNT(*) count FROM current_works WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC LIMIT 100"
                )
            ]
            venues = [
                dict(row)
                for row in conn.execute(
                    "SELECT venue value, COUNT(*) count FROM current_works WHERE venue!='' GROUP BY venue ORDER BY count DESC, venue LIMIT 100"
                )
            ]
            areas = [
                dict(row)
                for row in conn.execute(
                    "SELECT area value, COUNT(*) count FROM current_principles WHERE status='active' GROUP BY area ORDER BY count DESC, area LIMIT 100"
                )
            ]
            classes = (
                [
                    dict(row)
                    for row in conn.execute(
                        "SELECT principle_class value, COUNT(*) count FROM current_principles "
                        "WHERE status='active' GROUP BY principle_class ORDER BY principle_class"
                    )
                ]
                if self._column_exists(conn, "current_principles", "principle_class")
                else [{"value": "literature", "count": sum(int(row["count"]) for row in areas)}]
            )
        return {"years": years, "venues": venues, "areas": areas, "principle_classes": classes}

    def graph_viewport(
        self,
        *,
        min_x: float = -10_000,
        max_x: float = 10_000,
        min_y: float = -10_000,
        max_y: float = 10_000,
        zoom: float = 1.0,
        areas: list[str] | None = None,
        query: str = "",
        limit: int = 2_500,
    ) -> dict[str, Any]:
        """Return a bounded WebGL projection for one settled camera viewport."""

        with self._connect() as conn:
            if not self._table_exists(conn, "graph_nodes"):
                fallback = self._direct_principle_search(
                    CloudSearchRequest(entity="principle", query=query, limit=min(limit, 200)),
                    principle_class="literature",
                    query_vector=None,
                )
                return {
                    "lod": "card",
                    "nodes": fallback["items"],
                    "edges": [],
                    "areas": [],
                    "release_id": self.status()["release_id"],
                    "truncated": fallback["total"] > len(fallback["items"]),
                }
            if zoom <= 0.18 and not query:
                clauses = ""
                values: list[Any] = []
                if areas:
                    clauses = f" WHERE area IN ({','.join('?' for _ in areas)})"
                    values.extend(areas)
                rows = conn.execute(
                    "SELECT * FROM graph_areas" + clauses + " ORDER BY area", values
                ).fetchall()
                return {
                    "lod": "area",
                    "nodes": [
                        {
                            "id": f"area:{row['area']}",
                            "record_kind": "area",
                            "area": row["area"],
                            "title": row["display_name"],
                            "x": row["center_x"],
                            "y": row["center_y"],
                            "size": max(18, min(58, 16 + math.sqrt(row["principle_count"]) * 2.5)),
                            "principle_count": row["principle_count"],
                            "meta_count": row["meta_count"],
                        }
                        for row in rows
                    ],
                    "edges": [],
                    "areas": [dict(row) for row in rows],
                    "release_id": self.status()["release_id"],
                    "truncated": False,
                }
            area_clause = ""
            values = [max_x, min_x, max_y, min_y]
            if areas:
                area_clause = f" AND n.area IN ({','.join('?' for _ in areas)})"
                values.extend(areas)
            query_clause = ""
            if _query_terms(query):
                query_clause = " AND n.principle_id IN (SELECT principle_id FROM principle_fts WHERE principle_fts MATCH ?)"
                values.append(_fts_query(query))
            rows = conn.execute(
                "WITH viewport_nodes AS ("
                "SELECT n.*, ROW_NUMBER() OVER (PARTITION BY n.principle_class, n.area "
                "ORDER BY n.principle_id) AS class_rank "
                "FROM graph_nodes n "
                "WHERE EXISTS (SELECT 1 FROM graph_node_rtree r WHERE r.ordinal=n.ordinal "
                "AND r.min_x<=? AND r.max_x>=? AND r.min_y<=? AND r.max_y>=?) "
                f"{area_clause}{query_clause}) "
                "SELECT n.*, p.title, p.claim, p.maturity, p.stability, p.review_status "
                "FROM viewport_nodes n JOIN current_principles p USING(principle_id) "
                "ORDER BY n.class_rank * CASE WHEN n.principle_class='meta' THEN 3 ELSE 1 END, "
                "n.principle_class, n.principle_id LIMIT ?",
                (*values, limit + 1),
            ).fetchall()
            visible = rows[:limit]
            ids = [str(row["principle_id"]) for row in visible]
            edge_rows: list[dict[str, Any]] = []
            if ids:
                # A temporary primary-key set lets SQLite test both endpoints
                # without parsing two 2,500-value IN lists or materializing an
                # oversized outgoing neighborhood.  The render index provides
                # deterministic foundation-first traversal and the degree cap
                # keeps the WebGL transfer bounded.
                conn.execute(
                    "CREATE TEMP TABLE visible_graph_nodes("
                    "principle_id TEXT PRIMARY KEY) WITHOUT ROWID"
                )
                conn.executemany(
                    "INSERT INTO visible_graph_nodes VALUES (?)",
                    ((principle_id,) for principle_id in ids),
                )
                # Dense overview tiles need roughly one stable edge per dot;
                # closer views retain at least 500 edges, which is over three
                # per node at the 160-card rendering ceiling.
                edge_limit = min(3_000, max(80, int(len(ids) * 1.15)))
                edge_rows = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT e.* FROM graph_edges e "
                        "WHERE EXISTS (SELECT 1 FROM visible_graph_nodes s "
                        "WHERE s.principle_id=e.source_principle_id) "
                        "AND EXISTS (SELECT 1 FROM visible_graph_nodes t "
                        "WHERE t.principle_id=e.target_principle_id) "
                        "ORDER BY e.edge_class, e.edge_id LIMIT ?",
                        (edge_limit,),
                    ).fetchall()
                ]
            lod = "dot" if zoom < 0.45 else "title" if zoom < 1.1 else "card"
            nodes = []
            for row in visible:
                nodes.append(
                    {
                        "id": row["principle_id"],
                        "record_kind": (
                            "meta_principle" if row["principle_class"] == "meta" else "ordinary"
                        ),
                        "principle_class": row["principle_class"],
                        "area": row["area"],
                        "title": row["title"] if lod != "dot" else "",
                        "claim": row["claim"] if lod == "card" else "",
                        "maturity": row["maturity"],
                        "stability": row["stability"],
                        "review_status": row["review_status"] or "unassessed",
                        "x": row["x"],
                        "y": row["y"],
                        "size": 13 if row["principle_class"] == "meta" else 8,
                    }
                )
            return {
                "lod": lod,
                "nodes": nodes,
                "edges": edge_rows,
                "areas": [],
                "release_id": self.status()["release_id"],
                "truncated": len(rows) > limit,
            }

    def principle_edges(
        self, principle_ids: list[str], *, limit: int = 10_000
    ) -> list[dict[str, Any]]:
        """Return snapshot relationships whose two endpoints are visible.

        Session graphs persist their own membership and positions, but the
        scientific relationships continue to come from the pinned verified
        Cloud snapshot. Fetching through the indexed source neighborhood keeps
        this O(E_visible) instead of generating client-side all-pairs edges.
        """

        identifiers = list(dict.fromkeys(str(value) for value in principle_ids if value))
        if not identifiers:
            return []
        with self._connect() as conn:
            if not self._table_exists(conn, "graph_edges"):
                return []
            placeholders = ",".join("?" for _ in identifiers)
            candidate_limit = min(40_000, max(2_000, len(identifiers) * 12))
            candidates = conn.execute(
                "SELECT * FROM graph_edges WHERE source_principle_id IN ("
                f"{placeholders}) LIMIT ?",
                (*identifiers, candidate_limit),
            ).fetchall()
        visible = set(identifiers)
        rows = [
            dict(row)
            for row in candidates
            if str(row["target_principle_id"]) in visible
        ]
        rows.sort(
            key=lambda row: (
                0 if row["edge_class"] == "foundation" else 1,
                str(row["edge_id"]),
            )
        )
        return rows[: max(1, min(limit, 10_000))]

    def browse_principles(
        self, *, query: str = "", area: str = "", limit: int = 24, page: int = 1
    ) -> dict[str, Any]:
        request = CloudSearchRequest(
            entity="principle",
            query=query,
            limit=limit,
            cursor=_encode_offset((max(1, page) - 1) * limit),
        )
        result = self.search(request)
        if area:
            result["items"] = [item for item in result["items"] if item.get("area") == area]
            result["total"] = len(result["items"])
        return result
