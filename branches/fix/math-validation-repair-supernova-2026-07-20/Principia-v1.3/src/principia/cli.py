from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .llm import MockLLMClient
from .pipeline import PipelineJob, list_pipeline_runs
from .run import RunCancelledError
from .workspace import Workspace


def print_json(data: Any) -> None:
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="principia", description="Principia v1.3.3 framework CLI")
    parser.add_argument(
        "--workspace", "-w", default=".", help="Workspace root. Defaults to current directory."
    )
    parser.add_argument(
        "--mock-llm", action="store_true", help="Use deterministic mock LLM responses."
    )
    parser.add_argument("--version", action="version", version=f"principia {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create .principia storage in the workspace.")
    status = sub.add_parser(
        "status", help="Show a run, or workspace counts when RUN_ID is omitted."
    )
    status.add_argument("run_id", nargs="?")
    runs = sub.add_parser("runs", help="List recent persisted runs.")
    runs.add_argument("--limit", type=int, default=20)
    for command, help_text in (
        ("pause", "Pause a run at its next safe boundary."),
        ("resume", "Resume a paused run."),
        ("stop", "Stop a run without scheduling another paid call."),
    ):
        control = sub.add_parser(command, help=help_text)
        control.add_argument("run_id")

    search = sub.add_parser("search", help="Search public research metadata.")
    search.add_argument("query")
    search.add_argument("--target-count", type=int, default=10)
    search.add_argument("--rerank-mode", choices=["bm25", "embedding_rerank"])
    search.add_argument(
        "--source", dest="sources", action="append", help="Explicit metadata source; repeatable."
    )
    search.add_argument(
        "--require-target", action="store_true", help="Fail instead of returning fewer works."
    )

    extract = sub.add_parser("extract", help="Search and extract features.")
    extract.add_argument("query")
    extract.add_argument("--target-count", type=int, default=5)
    extract.add_argument("--model", default="auto")
    extract.add_argument("--overwrite", action="store_true")
    extract.add_argument("--rerank-mode", choices=["bm25", "embedding_rerank"])
    extract.add_argument(
        "--source", dest="sources", action="append", help="Explicit metadata source; repeatable."
    )
    extract.add_argument(
        "--require-target", action="store_true", help="Fail instead of returning fewer works."
    )
    extract.add_argument("--continue-on-error", action="store_true")

    generate = sub.add_parser("generate", help="Search, extract, and generate one idea.")
    generate.add_argument("query")
    generate.add_argument("--target-count", type=int, default=5)
    generate.add_argument("--model", default="auto")
    generate.add_argument(
        "--mode",
        default="scidialect-evo",
        help="Generation mode (default: strict scidialect-evo).",
    )
    generate.add_argument("--user-note", default="")
    generate.add_argument("--rerank-mode", choices=["bm25", "embedding_rerank"])
    generate.add_argument(
        "--source", dest="sources", action="append", help="Explicit metadata source; repeatable."
    )
    generate.add_argument(
        "--require-target", action="store_true", help="Fail instead of returning fewer works."
    )
    generate.add_argument("--continue-on-error", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Mock output is available only through an explicit fixture choice. Live
    # extract/generate commands resolve ``auto`` through configured credentials.
    use_mock_llm = args.mock_llm or getattr(args, "model", None) == "mock"
    llm = MockLLMClient() if use_mock_llm else None
    ws = Workspace(Path(args.workspace), llm=llm)
    try:
        return _dispatch(ws, args)
    except (KeyboardInterrupt, RunCancelledError):
        recent = list_pipeline_runs(ws.storage, limit=1)
        run_id = recent[0].run_id if recent else ""
        payload = {
            "ok": False,
            "status": "interrupted",
            "run_id": run_id,
            "message": "Completed checkpoints were preserved; inspect the run before resuming.",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 130


def _dispatch(ws: Workspace, args: argparse.Namespace) -> int:
    if args.command == "init":
        print_json({"ok": True, "workspace": str(ws.path), "db_path": str(ws.db_path)})
    elif args.command == "status":
        if args.run_id:
            print_json(PipelineJob.attach(ws.storage, args.run_id).status())
        else:
            print_json(
                {"workspace": str(ws.path), "db_path": str(ws.db_path), "counts": ws.counts()}
            )
    elif args.command == "runs":
        print_json(
            {
                "runs": [
                    status.model_dump(mode="json")
                    for status in list_pipeline_runs(ws.storage, limit=args.limit)
                ]
            }
        )
    elif args.command in {"pause", "resume", "stop"}:
        job = PipelineJob.attach(ws.storage, args.run_id)
        print_json(getattr(job, args.command)())
    elif args.command == "search":
        print_json(
            ws.research.search(
                args.query,
                target_count=args.target_count,
                rerank_mode=args.rerank_mode,
                sources=args.sources,
                require_target=args.require_target,
                show_progress=True,
            )
        )
    elif args.command == "extract":
        works = ws.research.search(
            args.query,
            target_count=args.target_count,
            rerank_mode=args.rerank_mode,
            sources=args.sources,
            require_target=args.require_target,
            show_progress=True,
        )
        print_json(
            ws.research.extract(
                works,
                model=args.model,
                overwrite=args.overwrite,
                continue_on_error=args.continue_on_error,
                show_progress=True,
            )
        )
    elif args.command == "generate":
        works = ws.research.search(
            args.query,
            target_count=args.target_count,
            rerank_mode=args.rerank_mode,
            sources=args.sources,
            require_target=args.require_target,
            show_progress=True,
        )
        features = ws.research.extract(
            works,
            model=args.model,
            continue_on_error=args.continue_on_error,
            show_progress=True,
        )
        print_json(
            ws.ideas.generate(
                features,
                user_note=args.user_note,
                mode=args.mode,
                model=args.model,
                show_progress=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
