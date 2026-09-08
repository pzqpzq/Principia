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
        description="Principia local demo: mine principles, generate ideas, and serve the web UI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--compute-budget", default="API-only or one day local")
    common.add_argument("--timeline", default="1 day")
    common.add_argument("--privacy-mode", default="local only")
    common.add_argument("--target-venue", default="workshop or open-source demo")
    common.add_argument("--offline", action="store_true", help="Disable LLM and arXiv calls.")
    common.add_argument("--model-mode", choices=["auto", "efficient", "strong"], default="auto")

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

    search = sub.add_parser("principles", help="Search the local principle pool.")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=8)
    search.add_argument("--min-validation", default="L0")

    graph = sub.add_parser("graph", help="Print a compact lineage graph JSON.")
    graph.add_argument("--query", default="")
    graph.add_argument("--top-k", type=int, default=10)

    state = sub.add_parser("state", help="Print current local store counts or full JSON.")
    state.add_argument("--full", action="store_true")

    reset = sub.add_parser("reset", help="Reset the local demo store.")
    reset.add_argument("--yes", action="store_true")

    serve = sub.add_parser("serve", help="Run the local web UI and API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store()
    engine = PrincipiaEngine(store=store)

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
        data = store.read()
        if args.full:
            print_json(data)
        else:
            print_json({key: len(value) for key, value in data.items() if isinstance(value, dict) and key != "meta"})
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
