from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .llm import MockLLMClient
from .workspace import Workspace


def print_json(data: Any) -> None:
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="principia", description="Principia V1.3 framework CLI")
    parser.add_argument("--workspace", "-w", default=".", help="Workspace root. Defaults to current directory.")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM responses.")
    parser.add_argument("--version", action="version", version=f"principia {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create .principia storage in the workspace.")
    sub.add_parser("status", help="Show local workspace counts.")

    search = sub.add_parser("search", help="Search public research metadata.")
    search.add_argument("query")
    search.add_argument("--target-count", type=int, default=10)
    search.add_argument("--rerank-mode", choices=["bm25", "embedding_rerank"])

    extract = sub.add_parser("extract", help="Search and extract features.")
    extract.add_argument("query")
    extract.add_argument("--target-count", type=int, default=5)
    extract.add_argument("--model", default="mock")
    extract.add_argument("--overwrite", action="store_true")
    extract.add_argument("--rerank-mode", choices=["bm25", "embedding_rerank"])

    generate = sub.add_parser("generate", help="Search, extract, and generate one idea.")
    generate.add_argument("query")
    generate.add_argument("--target-count", type=int, default=5)
    generate.add_argument("--model", default="mock")
    generate.add_argument("--mode", default="calculus")
    generate.add_argument("--user-note", default="")
    generate.add_argument("--rerank-mode", choices=["bm25", "embedding_rerank"])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    llm = MockLLMClient() if args.mock_llm else None
    ws = Workspace(Path(args.workspace), llm=llm)
    if args.command == "init":
        print_json({"ok": True, "workspace": str(ws.path), "db_path": str(ws.db_path)})
    elif args.command == "status":
        print_json({"workspace": str(ws.path), "db_path": str(ws.db_path), "counts": ws.counts()})
    elif args.command == "search":
        print_json(ws.research.search(args.query, target_count=args.target_count, rerank_mode=args.rerank_mode, show_progress=True))
    elif args.command == "extract":
        works = ws.research.search(args.query, target_count=args.target_count, rerank_mode=args.rerank_mode, show_progress=True)
        print_json(ws.research.extract(works, model=args.model, overwrite=args.overwrite, show_progress=True))
    elif args.command == "generate":
        works = ws.research.search(args.query, target_count=args.target_count, rerank_mode=args.rerank_mode, show_progress=True)
        features = ws.research.extract(works, model=args.model, show_progress=True)
        print_json(ws.ideas.generate(features, user_note=args.user_note, mode=args.mode, model=args.model, show_progress=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
