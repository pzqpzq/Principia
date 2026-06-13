from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .cloud.compactor import compact_contributions, export_snapshot
from .cloud.contribution import log_upload_status, prepare_contribution, upload_status
from .cloud.crawler import plan_crawl
from .cloud.manifest import CloudManifestClient
from .cloud.resolver import CloudResolver
from .cloud.search import CloudSearch
from .cloud.validator import validate_contribution_file, validate_manifest
from .engine import PrincipiaEngine
from .server import run_server
from .storage import Store


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def parse_constraints(args: argparse.Namespace) -> dict[str, str]:
    return {
        "compute_budget": args.compute_budget,
        "timeline": args.timeline,
        "privacy_mode": args.privacy_mode,
        "target_venue": args.target_venue,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="principia",
        description="Principia v1: local-first global principle memory and lineage-backed idea generation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--compute-budget", default="API-only or one day local")
    common.add_argument("--timeline", default="1 day")
    common.add_argument("--privacy-mode", default="local only")
    common.add_argument("--target-venue", default="workshop or open-source prototype")
    common.add_argument("--offline", action="store_true", help="Disable LLM and arXiv calls.")
    common.add_argument("--model-mode", default="auto")

    research = sub.add_parser("research", parents=[common], help="Run v1 research ingestion for a project.")
    research.add_argument("query")
    research.add_argument("--project-id", default="default")
    research.add_argument("--target-works", type=int, default=50)

    retrieve = sub.add_parser("retrieve", help="Run independent v1 concept retrieval.")
    retrieve.add_argument("query")
    retrieve.add_argument("--project-id", default="default")
    retrieve.add_argument("--types", default="existed_idea,principle,takeaway_message,benchmark,baseline")
    retrieve.add_argument("--limit-per-type", type=int, default=12)

    migrate = sub.add_parser("migrate", help="Migrate legacy bucket data into normalized v1 memory.")
    migrate.add_argument("--source-db", default="")
    migrate.add_argument("--project-id", default="default")

    symbols = sub.add_parser("symbols", help="Print the v1 symbol table.")
    symbols.add_argument("--namespace", default="global")
    symbols.add_argument("--limit", type=int, default=200)

    lineage = sub.add_parser("lineage", help="Print a v1 idea lineage graph.")
    lineage.add_argument("idea_id")

    ingest = sub.add_parser("ingest", parents=[common], help="Collect related works and mine PrincipleCards.")
    ingest.add_argument("query")
    ingest.add_argument("--max-works", type=int, default=6)

    generate = sub.add_parser("generate", parents=[common], help="Generate IdeaCards from the local principle pool.")
    generate.add_argument("query")
    generate.add_argument("--max-works", type=int, default=6)
    generate.add_argument("--paper-count", type=int, default=None)
    generate.add_argument("--ideas", type=int, default=4)
    generate.add_argument("--min-validation", default="L0")
    generate.add_argument("--source-mode", choices=["online", "local"], default="online")
    generate.add_argument("--no-persist-sources", action="store_true")
    generate.add_argument("--mode", choices=["standard", "principia-calculus"], default="standard")

    search = sub.add_parser("principles", help="Search the local principle pool.")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=8)
    search.add_argument("--min-validation", default="L0")

    graph = sub.add_parser("graph", help="Print a compact lineage graph JSON.")
    graph.add_argument("--query", default="")
    graph.add_argument("--top-k", type=int, default=10)

    state = sub.add_parser("state", help="Print current local store counts or full JSON.")
    state.add_argument("--full", action="store_true")
    state.add_argument("--v1", action="store_true")

    export = sub.add_parser("export", help="Export a markdown or PDF report.")
    export.add_argument("query")
    export.add_argument("--format", choices=["markdown", "pdf"], default="markdown")
    export.add_argument("--language", default="en")
    export.add_argument("--model-mode", default="auto")

    reset = sub.add_parser("reset", help="Reset the local Principia store.")
    reset.add_argument("--yes", action="store_true")

    serve = sub.add_parser("serve", help="Run the local web UI and API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8790)

    cloud = sub.add_parser("cloud", help="Principia Cloud Library commands.")
    cloud_sub = cloud.add_subparsers(dest="cloud_command", required=True)

    cloud_stats = cloud_sub.add_parser("stats", help="Print cloud manifest/cache stats.")
    cloud_stats.add_argument("--manifest", default="")

    cloud_manifest = cloud_sub.add_parser("manifest", help="Print the current cloud manifest.")
    cloud_manifest.add_argument("--refresh", action="store_true")
    cloud_manifest.add_argument("--manifest", default="")

    cloud_resolve = cloud_sub.add_parser("resolve", help="Resolve candidate works against the Cloud Library.")
    cloud_resolve.add_argument("--input", required=True)
    cloud_resolve.add_argument("--model-key", required=True)
    cloud_resolve.add_argument("--project-id", default="default")
    cloud_resolve.add_argument("--no-hydrate", action="store_true")

    cloud_prefetch = cloud_sub.add_parser("prefetch", help="Search/prefetch Cloud Library route shards.")
    cloud_prefetch.add_argument("--query", default="")
    cloud_prefetch.add_argument("--limit", type=int, default=100)
    cloud_prefetch.add_argument("--model-key", default="")

    cloud_export = cloud_sub.add_parser("export-snapshot", help="Export local SQLite memory as cloud release assets.")
    cloud_export.add_argument("--db", default="")
    cloud_export.add_argument("--out", required=True)
    cloud_export.add_argument("--limit", type=int, default=0)
    cloud_export.add_argument("--work-shards", type=int, default=256)
    cloud_export.add_argument("--concept-shards", type=int, default=64)

    cloud_validate = cloud_sub.add_parser("validate-contribution", help="Validate a contribution JSON file.")
    cloud_validate.add_argument("path")

    cloud_upload = cloud_sub.add_parser("upload", help="Prepare or mark a PR-export upload.")
    cloud_upload.add_argument("path", nargs="?")
    cloud_upload.add_argument("--mode", default="normal")
    cloud_upload.add_argument("--model-key", default="")
    cloud_upload.add_argument("--work-id", action="append", default=[])
    cloud_upload.add_argument("--prepare", action="store_true")

    cloud_crawl = cloud_sub.add_parser("crawl", help="Build an admin crawler dry-run plan.")
    cloud_crawl.add_argument("--venues", default="ICLR,NeurIPS,ICML")
    cloud_crawl.add_argument("--years", default="2024-2026")
    cloud_crawl.add_argument("--topics", default="")
    cloud_crawl.add_argument("--priority-rules", default="venue,recency,topic")
    cloud_crawl.add_argument("--max-papers", type=int, default=100)
    cloud_crawl.add_argument("--model-key", default="")
    cloud_crawl.add_argument("--dry-run", action="store_true")

    cloud_compact = cloud_sub.add_parser("compact", help="Compact contribution files into a validation report.")
    cloud_compact.add_argument("--input", required=True)
    cloud_compact.add_argument("--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store()
    engine = PrincipiaEngine(store=store)

    if args.command == "research":
        print_json(
            engine.v1_research_project(
                args.project_id,
                goal_text=args.query,
                model_mode=args.model_mode,
                target_works=args.target_works,
            )
        )
        return 0

    if args.command == "retrieve":
        concept_types = [item.strip() for item in args.types.split(",") if item.strip()]
        print_json(
            engine.v1_retrieve_concepts(
                args.query,
                field_id=args.project_id,
                concept_types=concept_types,
                limit_per_type=args.limit_per_type,
            )
        )
        return 0

    if args.command == "migrate":
        if args.source_db:
            print_json(engine.migrate_sqlite_to_v1_memory(args.source_db, project_id=args.project_id))
        else:
            print_json(engine.migrate_to_v1_memory(project_id=args.project_id))
        return 0

    if args.command == "symbols":
        print_json(engine.v1_symbols_table(namespace=args.namespace, limit=args.limit))
        return 0

    if args.command == "lineage":
        print_json(engine.v1_idea_lineage(args.idea_id))
        return 0

    if args.command == "ingest":
        print_json(
            engine.ingest_principles(
                args.query,
                max_works=args.max_works,
                constraints=parse_constraints(args),
                offline=args.offline,
                model_mode=args.model_mode,
            )
        )
        return 0

    if args.command == "generate":
        if args.mode == "principia-calculus":
            print_json(
                engine.v1_symbolic_generate(
                    field_id="default",
                    goal_text=args.query,
                    selected_refs=[],
                    user_note="",
                    model_mode=args.model_mode,
                    offline=args.offline,
                )
            )
            return 0
        print_json(
            engine.generate_ideas(
                args.query,
                max_ideas=args.ideas,
                max_works=args.max_works,
                paper_count=args.paper_count,
                min_validation=args.min_validation,
                constraints=parse_constraints(args),
                offline=args.offline,
                model_mode=args.model_mode,
                source_mode=args.source_mode,
                persist_sources=not args.no_persist_sources,
            )
        )
        return 0

    if args.command == "principles":
        print_json(store.search_principles(args.query, top_k=args.top_k, min_validation=args.min_validation))
        return 0

    if args.command == "graph":
        print_json(engine.build_graph(query=args.query, top_k=args.top_k))
        return 0

    if args.command == "state":
        if args.v1:
            print_json(engine.global_store.counts())
            return 0
        data = store.read()
        if args.full:
            print_json(data)
        else:
            print_json({key: len(value) for key, value in data.items() if isinstance(value, dict) and key != "meta"})
        return 0

    if args.command == "cloud":
        if args.cloud_command == "stats":
            client = CloudManifestClient(Path(args.manifest) if args.manifest else None)
            print_json(client.stats())
            return 0
        if args.cloud_command == "manifest":
            client = CloudManifestClient(Path(args.manifest) if args.manifest else None)
            manifest = client.load_manifest(refresh=args.refresh)
            print_json({"manifest": manifest, "validation": validate_manifest(manifest) if manifest.get("snapshot_id") else {"ok": True, "errors": []}})
            return 0
        if args.cloud_command == "resolve":
            candidates = json.loads(Path(args.input).read_text(encoding="utf-8"))
            if isinstance(candidates, dict):
                candidates = candidates.get("candidates") or candidates.get("items") or []
            print_json(
                {
                    "items": CloudResolver(store).resolve_batch(
                        list(candidates),
                        args.model_key,
                        hydrate=not args.no_hydrate,
                        project_id=args.project_id,
                    )
                }
            )
            return 0
        if args.cloud_command == "prefetch":
            print_json(CloudSearch(CloudResolver(store)).search(args.query, limit=args.limit, model_key=args.model_key))
            return 0
        if args.cloud_command == "export-snapshot":
            db_path = Path(args.db) if args.db else store.path
            print_json(
                export_snapshot(
                    db_path,
                    Path(args.out),
                    limit=args.limit or None,
                    work_shards=args.work_shards,
                    concept_shards=args.concept_shards,
                )
            )
            return 0
        if args.cloud_command == "validate-contribution":
            print_json(validate_contribution_file(Path(args.path)))
            return 0
        if args.cloud_command == "upload":
            if args.prepare:
                print_json(
                    prepare_contribution(
                        store.path,
                        store.path.parent / "artifacts" / "cloud" / "contributions",
                        model_key=args.model_key,
                        work_ids=list(args.work_id or []),
                        upload_mode=args.mode,
                    )
                )
            elif args.path:
                print_json(log_upload_status(store.path, contribution_path=args.path, status="prepared", upload_mode=args.mode))
            else:
                print_json(upload_status(store.path))
            return 0
        if args.cloud_command == "crawl":
            years = _parse_years(args.years)
            venues = [item.strip() for item in args.venues.split(",") if item.strip()]
            topics = [item.strip() for item in args.topics.split(",") if item.strip()]
            priority_rules = [item.strip() for item in args.priority_rules.split(",") if item.strip()]
            print_json(plan_crawl(venues=venues, years=years, topics=topics, priority_rules=priority_rules, max_papers=args.max_papers, model_key=args.model_key, dry_run=True))
            return 0
        if args.cloud_command == "compact":
            print_json(compact_contributions(Path(args.input), Path(args.out)))
            return 0

    if args.command == "export":
        filename, body, content_type = engine.export_report(
            args.query,
            language=args.language,
            model_mode=args.model_mode,
            fmt=args.format,
        )
        print_json({"filename": filename, "content_type": content_type, "bytes": len(body)})
        return 0

    if args.command == "reset":
        if not args.yes:
            parser.error("reset requires --yes")
        store.reset()
        print_json({"ok": True, "message": "Local store reset."})
        return 0

    if args.command == "serve":
        run_server(host=args.host, port=args.port)
        return 0

    parser.error("Unknown command")
    return 2


def _parse_years(value: str) -> list[int]:
    text = str(value or "").strip()
    if "-" in text:
        left, right = text.split("-", 1)
        start, end = int(left), int(right)
        return list(range(start, end + 1))
    return [int(item.strip()) for item in text.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
