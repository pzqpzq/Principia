from __future__ import annotations

import argparse
import json
from typing import Any

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


if __name__ == "__main__":
    raise SystemExit(main())
