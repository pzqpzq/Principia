from __future__ import annotations

import base64
import json
import math
import os
import re
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
from .canonical import PCG_ENTRIES, apply_cloud_delta, verify_cloud_snapshot
from .models_v1 import CloudManifest, CloudSearchRequest

DEFAULT_CONTROL_URL = "https://pzqpzq.github.io/Principia/cloud/v1/latest.json"
SYNC_INTERVAL_SECONDS = 6 * 60 * 60
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

# Goal prompts are usually phrased as questions.  Feeding every grammatical
# word to an OR-based FTS query made a paper containing only "system" outrank
# the actual subject (for example, a Boltzmann paper for a multi-agent goal).
# Keep the small domain-bearing vocabulary and discard only high-frequency
# prompt scaffolding.  This list is intentionally conservative: terms such as
# ``agent``, ``reasoning`` and ``discovery`` must remain searchable.
_GOAL_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has",
    "have", "how", "i", "if", "in", "into", "is", "it", "its", "may",
    "might", "of", "on", "or", "our", "should", "system", "systems",
    "that", "the", "their", "these", "this", "those", "to", "using",
    "via", "was", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "improve", "improves", "improved",
    "improving",
}


def _query_terms(query: str) -> list[str]:
    raw = re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE)
    meaningful = [term for term in raw if len(term) > 1 and term not in _GOAL_STOP_WORDS]
    # A prompt made entirely of common words is still a valid literal search;
    # falling back is preferable to silently treating it as an empty query.
    return list(dict.fromkeys(meaningful or raw))[:30]


def _fts_query(query: str) -> str:
    terms = _query_terms(query)
    quoted = [f'"{term.replace(chr(34), "")}"' for term in terms]
    if len(quoted) <= 2:
        return " OR ".join(quoted)
    # A long research goal is a conjunction of concepts, not a bag of
    # independent words.  Permit a distinctive compound (for example
    # ``multi-agent``) on its own, otherwise require two concepts.  This keeps
    # FTS useful when embeddings are unavailable without filling the result set
    # with papers that happen to contain only "theorem" or "discovery".
    compound = [value for value, term in zip(quoted, terms, strict=True) if "-" in term]
    pairs = [
        f"({left} AND {right})"
        for index, left in enumerate(quoted)
        for right in quoted[index + 1 :]
    ]
    return " OR ".join([*compound, *pairs])


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


class GlobalCloudSnapshotStore:
    """Verified, atomically activated local projection of the GitHub Cloud release."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve() / "global-v1"
        self.releases_dir = self.root / "releases"
        self.downloads_dir = self.root / "downloads"
        self.state_path = self.root / "state.json"
        self.active_path = self.root / "active.json"
        self._sync_lock = threading.Lock()
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
            "embedding_contract": manifest.embedding_contract if manifest else "",
            "vectors_complete": bool(manifest and manifest.vectors_complete),
            "last_checked_at": state.get("last_checked_at") or "",
            "last_error": state.get("last_error") or "",
            "stale": bool(state.get("last_error")),
            "control_url": state.get("control_url") or os.getenv(
                "PRINCIPIA_GLOBAL_CONTROL_URL", DEFAULT_CONTROL_URL
            ),
            "syncing": self._sync_lock.locked(),
        }

    def install_snapshot(
        self,
        snapshot: str | Path,
        *,
        expected_sha256: str = "",
        keep: int = 5,
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
            [path for path in self.releases_dir.iterdir() if path.is_dir() and not path.name.startswith(".")],
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
            if not force and state.get("last_checked_epoch"):
                elapsed = time.time() - float(state["last_checked_epoch"])
                if elapsed < SYNC_INTERVAL_SECONDS:
                    return {**self.status(), "outcome": "not_due"}
            headers = {"Accept": "application/json"}
            if state.get("etag"):
                headers["If-None-Match"] = str(state["etag"])
            context = ssl.create_default_context(cafile=certifi.where())
            with httpx.Client(verify=context, timeout=20.0, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 304:
                    self._atomic_json(
                        self.state_path,
                        {**state, "control_url": url, "last_checked_at": now,
                         "last_checked_epoch": time.time(), "last_error": ""},
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
                        {"schema_version": "principia-global-sync-state-v1", "control_url": url,
                         "etag": response.headers.get("etag", ""), "last_checked_at": now,
                         "last_checked_epoch": time.time(), "last_error": ""},
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
                temporary = self.downloads_dir / f"{release_id}.{'pcd' if download_kind == 'delta' else 'pcg'}.partial"
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
                    with zipfile.ZipFile(active_snapshot, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                        for name in sorted(PCG_ENTRIES):
                            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                            info.compress_type = zipfile.ZIP_DEFLATED
                            info.external_attr = (0o100644 & 0xFFFF) << 16
                            archive.writestr(info, (active["release_root"] / name).read_bytes())
                    installation_source = self.downloads_dir / f"{release_id}.pcg.partial"
                    apply_cloud_delta(active_snapshot, temporary, installation_source)
                    active_snapshot.unlink(missing_ok=True)
                    expected_full = str(latest.get("snapshot_sha256") or "")
                    if expected_full and file_sha256(installation_source) != expected_full:
                        raise ValueError("Global Cloud delta output digest mismatch")
                    digest = expected_full
                outcome = self.install_snapshot(installation_source, expected_sha256=digest)
                temporary.unlink(missing_ok=True)
                if installation_source != temporary:
                    installation_source.unlink(missing_ok=True)
                self._atomic_json(
                    self.state_path,
                    {"schema_version": "principia-global-sync-state-v1", "control_url": url,
                     "etag": response.headers.get("etag", ""), "last_checked_at": now,
                     "last_checked_epoch": time.time(), "last_error": ""},
                )
                return {**outcome, "outcome": "updated", "transport": download_kind}
        except Exception as exc:
            self._atomic_json(
                self.state_path,
                {**state, "schema_version": "principia-global-sync-state-v1",
                 "control_url": url, "last_checked_at": now,
                 "last_checked_epoch": time.time(), "last_error": type(exc).__name__},
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
        return [dict(row) for row in rows]

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
            if entity == "paper":
                path = active["release_root"] / "work-vectors.f16"
                count = manifest.work_count
                ordinal_table, current_table, identifier = (
                    "work_vector_ordinals", "current_works", "work_id"
                )
            else:
                path = active["release_root"] / "principle-vectors.f16"
                count = manifest.principle_count
                ordinal_table, current_table, identifier = (
                    "principle_vector_ordinals", "current_principles", "principle_id"
                )
            vectors = np.memmap(
                path,
                dtype=np.float16,
                mode="r",
                shape=(count, manifest.vector_dimensions),
            )
            # Multiplication promotes one bounded block at a time; the full matrix
            # remains memory-mapped and is never copied into process memory.
            candidates: list[tuple[float, int]] = []
            block = 2048
            for start in range(0, count, block):
                # NumPy's float16 matmul is scalar and disproportionately slow
                # on common Intel Macs. Convert one bounded mmap block to
                # float32 so BLAS can scan it efficiently; the full vector file
                # remains mapped and is never materialized in process memory.
                vector_block = np.asarray(
                    vectors[start : start + block], dtype=np.float32
                )
                scores = vector_block @ query
                candidates.extend((float(score), start + index) for index, score in enumerate(scores))
            candidates.sort(key=lambda item: (-item[0], item[1]))
            chosen = candidates[: max(1, min(limit, count))]
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
        vector = self._vector_rows("paper", query_vector, limit=max(limit, request.paper_cohort * 2))
        if not vector:
            return lexical[:limit], "fts"
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
        self, query: str, *, limit: int, offset: int = 0, areas: list[str] | None = None
    ) -> list[dict[str, Any]]:
        area_filter = ""
        area_values: list[Any] = []
        if areas:
            area_filter = f" AND p.area IN ({','.join('?' for _ in areas)})"
            area_values = list(areas)
        with self._connect() as conn:
            if _query_terms(query):
                rows = conn.execute(
                    f"""
                    SELECT p.*, bm25(principle_fts) lexical_rank
                    FROM principle_fts JOIN current_principles p USING(principle_id)
                    WHERE principle_fts MATCH ? AND p.status='active' {area_filter}
                    ORDER BY lexical_rank, p.principle_id LIMIT ? OFFSET ?
                    """,
                    (_fts_query(query), *area_values, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT p.*, 0.0 lexical_rank FROM current_principles p "
                    f"WHERE p.status='active' {area_filter} ORDER BY p.updated_at DESC, p.principle_id LIMIT ? OFFSET ?",
                    (*area_values, limit, offset),
                ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _rrf(rows: list[dict[str, Any]], identifier: str) -> dict[str, float]:
        return {str(row[identifier]): 1.0 / (60 + rank) for rank, row in enumerate(rows, start=1)}

    def search(
        self,
        request: CloudSearchRequest,
        *,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        if not self.active():
            return {"items": [], "next_cursor": None, "total": 0, "facets": {},
                    "ranking_mode": "unavailable", "release_id": ""}
        offset = _decode_offset(request.cursor)
        if request.entity == "paper":
            rows, ranking_mode = self._hybrid_works(
                request, limit=request.limit + 1, query_vector=query_vector
            )
            items = [self._work_item(row) for row in rows[: request.limit]]
            return {
                "items": items,
                "next_cursor": _encode_offset(offset + request.limit) if len(rows) > request.limit else None,
                "total": self._work_count(request),
                "facets": self.facets(),
                "ranking_mode": ranking_mode,
                "release_id": self.status()["release_id"],
            }
        if request.entity == "principle":
            return self._paper_first_principles(request, query_vector=query_vector)
        paper_result = self.search(
            request.model_copy(update={"entity": "paper", "limit": request.limit}),
            query_vector=query_vector,
        )
        principle_result = self._paper_first_principles(
            request.model_copy(update={"entity": "principle", "cursor": "", "limit": request.limit}),
            query_vector=query_vector,
        )
        items = [*paper_result["items"], *principle_result["items"]]
        items.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("id") or "")))
        return {**principle_result, "items": items[: request.limit], "entity": "all"}

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
                rows = conn.execute(
                    f"""
                    SELECT p.*, pw.work_id, pw.role, w.title matched_paper_title,
                           w.landing_url matched_paper_url
                    FROM principle_work pw
                    JOIN current_principles p ON p.principle_id=pw.principle_id
                     AND p.revision=pw.principle_revision
                    JOIN current_works w USING(work_id)
                    WHERE pw.work_id IN ({placeholders}) AND p.status='active'
                    ORDER BY p.principle_id, pw.work_id
                    """,
                    ids,
                ).fetchall()
            for row in rows:
                item = linked.setdefault(
                    str(row["principle_id"]),
                    {**dict(row), "matched_papers": [], "paper_score": 0.0},
                )
                item["paper_score"] = max(item["paper_score"], paper_scores.get(str(row["work_id"]), 0))
                # A Principle can have multiple evidence locators in one Work.
                # Search cards link the paper once; the detail endpoint retains
                # every locator for provenance inspection.
                if not any(
                    paper["work_id"] == row["work_id"]
                    for paper in item["matched_papers"]
                ):
                    item["matched_papers"].append(
                        {"work_id": row["work_id"], "title": row["matched_paper_title"],
                         "url": row["matched_paper_url"], "role": row["role"]}
                    )
        direct = self._lexical_principles(
            request.query,
            limit=max(request.paper_cohort, request.limit * 4),
            areas=request.areas,
        )
        vector_principles = self._vector_rows(
            "principle", query_vector, limit=max(request.paper_cohort, request.limit * 4)
        )
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
                key: value for key, value in linked.items() if str(value.get("area") or "") in request.areas
            }
        ranked = sorted(linked.values(), key=lambda row: (-float(row["score"]), str(row["principle_id"])))
        page = ranked[offset : offset + request.limit]
        items = [self._principle_item(row) for row in page]
        return {
            "items": items,
            "next_cursor": _encode_offset(offset + request.limit) if offset + request.limit < len(ranked) else None,
            "total": len(ranked),
            "facets": self.facets(),
            "ranking_mode": f"paper_first_{paper_mode}" if not vector_principles else "paper_first_hybrid_rrf",
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
        }

    @staticmethod
    def _principle_item(row: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        return {
            "id": row["principle_id"], "entity": "principle", "source": "global",
            "score": float(row.get("score") or 0), "match_path": row.get("match_path") or "direct",
            "matched_papers": row.get("matched_papers") or [], **payload,
        }

    def work(self, work_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM current_works WHERE work_id=?", (work_id,)).fetchone()
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
                    kind = "exact" if current.get("content_digest") == proposed.get("content_digest") else "strong_id"
                    return {"kind": kind, "match": current, "reason": field}
            title = " ".join(str(proposed.get("title") or "").casefold().split())
            if title:
                row = conn.execute(
                    "SELECT payload_json FROM current_works WHERE lower(trim(title))=? LIMIT 1",
                    (title,),
                ).fetchone()
                if row:
                    return {"kind": "ambiguous", "match": json.loads(row[0]), "reason": "title_only"}
        return {"kind": "new", "match": None, "reason": "no_match"}

    def match_principle(self, proposed: dict[str, Any]) -> dict[str, Any]:
        if not self.active():
            return {"kind": "new", "match": None, "similarity": 0.0, "reason": "cloud_unavailable"}
        principle_id = str(proposed.get("principle_id") or "")
        content_digest = str(proposed.get("content_digest") or "")
        with self._connect() as conn:
            if principle_id:
                row = conn.execute(
                    "SELECT payload_json FROM current_principles WHERE principle_id=?", (principle_id,)
                ).fetchone()
                if row:
                    current = json.loads(row[0])
                    return {
                        "kind": "exact" if current.get("content_digest") == content_digest else "strong_id",
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
                    return {"kind": "exact", "match": json.loads(row[0]), "similarity": 1.0, "reason": "content_digest"}
        query = " ".join([str(proposed.get("title") or ""), str(proposed.get("claim") or "")])
        candidates = self._lexical_principles(query, limit=3)
        if candidates:
            proposed_terms = set(_query_terms(query.casefold()))
            best = candidates[0]
            current = json.loads(best["payload_json"])
            current_terms = set(_query_terms(f"{current.get('title','')} {current.get('claim','')}".casefold()))
            similarity = len(proposed_terms & current_terms) / max(1, len(proposed_terms | current_terms))
            if similarity >= 0.75:
                return {"kind": "ambiguous", "match": current, "similarity": similarity, "reason": "semantic_near_duplicate"}
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
                SELECT pw.payload_json link_json, w.payload_json work_json
                FROM principle_work pw JOIN current_works w USING(work_id)
                WHERE pw.principle_id=? AND pw.principle_revision=(
                    SELECT MAX(revision) FROM principles WHERE principle_id=?
                ) ORDER BY pw.work_id, pw.role
                """,
                (principle_id, principle_id),
            ).fetchall()
            relations = conn.execute(
                "SELECT payload_json FROM relations WHERE source_principle_id=? AND status='active' "
                "ORDER BY relation_id, revision DESC",
                (principle_id,),
            ).fetchall()
        payload = json.loads(row[0])
        payload["source_references"] = [
            {**json.loads(item["work_json"]), **json.loads(item["link_json"])} for item in references
        ]
        payload["relations"] = [json.loads(item[0]) for item in relations]
        payload["source"] = "global"
        return payload

    def principle_revisions(self, principle_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM principles WHERE principle_id=? ORDER BY revision DESC",
                (principle_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def facets(self) -> dict[str, Any]:
        with self._connect() as conn:
            years = [dict(row) for row in conn.execute(
                "SELECT year value, COUNT(*) count FROM current_works WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC LIMIT 100"
            )]
            venues = [dict(row) for row in conn.execute(
                "SELECT venue value, COUNT(*) count FROM current_works WHERE venue!='' GROUP BY venue ORDER BY count DESC, venue LIMIT 100"
            )]
            areas = [dict(row) for row in conn.execute(
                "SELECT area value, COUNT(*) count FROM current_principles WHERE status='active' GROUP BY area ORDER BY count DESC, area LIMIT 100"
            )]
        return {"years": years, "venues": venues, "areas": areas}

    def browse_principles(self, *, query: str = "", area: str = "", limit: int = 24, page: int = 1) -> dict[str, Any]:
        request = CloudSearchRequest(
            entity="principle", query=query, limit=limit, cursor=_encode_offset((max(1, page) - 1) * limit)
        )
        result = self.search(request)
        if area:
            result["items"] = [item for item in result["items"] if item.get("area") == area]
            result["total"] = len(result["items"])
        return result
