from __future__ import annotations

import argparse
import json
import sys
import time
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
    parser = argparse.ArgumentParser(prog="principia", description="Principia v1.4.1 framework CLI")
    parser.add_argument(
        "--workspace",
        "-w",
        default=None,
        help="Legacy workspace root. New v1.4 product commands prefer --working-directory.",
    )
    parser.add_argument(
        "--mock-llm", action="store_true", help="Use deterministic mock LLM responses."
    )
    parser.add_argument("--version", action="version", version=f"principia {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    open_command = sub.add_parser("open", help="Launch the local Principles application.")
    open_command.add_argument("--workspace", dest="command_workspace")
    open_command.add_argument(
        "--working-directory",
        help="Recommended: create/use workspace/ and local_data/ under this directory.",
    )
    open_command.add_argument("--port", type=int, default=0)
    open_command.add_argument("--no-browser", action="store_true")
    open_command.add_argument("--cloud-root")
    open_command.add_argument(
        "--package-library",
        help="Shared principle-packages directory used by every working directory.",
    )

    admin = sub.add_parser("admin", help="Launch the isolated Admin application.")
    admin.add_argument("--workspace", dest="command_workspace")
    admin.add_argument("--working-directory")
    admin.add_argument("--port", type=int, default=0)
    admin.add_argument("--no-browser", action="store_true")
    admin.add_argument("--cloud-root")
    admin.add_argument("--package-library")

    doctor = sub.add_parser("doctor", help="Inspect the local v1.4 runtime without secrets.")
    doctor.add_argument("--workspace", dest="command_workspace")
    doctor.add_argument("--working-directory")
    doctor.add_argument("--json", action="store_true", dest="doctor_json")
    doctor.add_argument("--cloud-root")
    doctor.add_argument("--package-library")

    cloud = sub.add_parser("cloud", help="Manage immutable Global Principle packages.")
    cloud.add_argument("--workspace", dest="command_workspace")
    cloud.add_argument("--working-directory")
    cloud.add_argument("--cloud-root")
    cloud.add_argument("--package-library")
    cloud_sub = cloud.add_subparsers(dest="cloud_command", required=True)
    cloud_sub.add_parser("list")
    for name in ("install", "update"):
        action = cloud_sub.add_parser(name)
        action.add_argument("area")
        action.add_argument("--version")
        action.add_argument("--catalog", required=True)
    verify = cloud_sub.add_parser("verify")
    verify.add_argument("area")
    verify.add_argument("--version")
    pin = cloud_sub.add_parser("pin")
    pin.add_argument("area")
    pin.add_argument("version")
    pin.add_argument("--remove", action="store_true")
    rollback = cloud_sub.add_parser("rollback")
    rollback.add_argument("area")

    local = sub.add_parser("local", help="Run privacy-explicit Local Discovery.")
    local.add_argument("--workspace", dest="command_workspace")
    local.add_argument("--working-directory")
    local.add_argument("--cloud-root")
    local.add_argument("--package-library")
    local_sub = local.add_subparsers(dest="local_command", required=True)
    literature_search = local_sub.add_parser(
        "search", help="Search public scholarly metadata and preview a Local literature dataset."
    )
    literature_search.add_argument("--goal", required=True)
    literature_search.add_argument("--target-count", type=int, default=20)
    discover = local_sub.add_parser("discover")
    source_group = discover.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--folder")
    source_group.add_argument("--search-id")
    discover.add_argument("--goal")
    discover.add_argument("--area", default="local-discovery")
    discover.add_argument("--policy", choices=["local", "remote", "no_llm"], required=True)
    discover.add_argument("--provider", default="siliconflow")
    discover.add_argument("--model", default="deepseek-ai/DeepSeek-V4-Flash")
    discover.add_argument("--base-url", default="https://api.siliconflow.com/v1")
    discover.add_argument("--confirm-remote-egress", action="store_true")

    showcase = sub.add_parser(
        "showcase", help="Export or import a paper-free, path-free Local Principles showcase."
    )
    showcase.add_argument("--workspace", dest="command_workspace")
    showcase.add_argument("--working-directory")
    showcase.add_argument("--cloud-root")
    showcase.add_argument("--package-library")
    showcase_sub = showcase.add_subparsers(dest="showcase_command", required=True)
    showcase_export = showcase_sub.add_parser("export")
    showcase_export.add_argument("output")
    showcase_import = showcase_sub.add_parser("import")
    showcase_import.add_argument("source")

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
    resolved_workspace = getattr(args, "command_workspace", None) or args.workspace
    if args.command in {"open", "admin", "doctor", "cloud", "local", "showcase"}:
        working_directory = getattr(args, "working_directory", None)
        if not working_directory and not resolved_workspace:
            parser.error(
                f"{args.command} requires --working-directory PATH "
                "(or explicit --workspace PATH for legacy compatibility)"
            )
        return _dispatch_v14(
            None if working_directory else Path(resolved_workspace),
            args,
            working_directory=(Path(working_directory) if working_directory else None),
        )
    # Mock output is available only through an explicit fixture choice. Live
    # extract/generate commands resolve ``auto`` through configured credentials.
    use_mock_llm = args.mock_llm or getattr(args, "model", None) == "mock"
    llm = MockLLMClient() if use_mock_llm else None
    ws = Workspace(Path(args.workspace or "."), llm=llm)
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


def _dispatch_v14(
    workspace: Path | None,
    args: argparse.Namespace,
    *,
    working_directory: Path | None = None,
) -> int:
    from .application import AdminWorkspace, Principia
    from .local.portable import PortablePrincipleLibrary
    from .providers import ModelPolicy

    cloud_root = getattr(args, "cloud_root", None)
    package_library = getattr(args, "package_library", None)
    if args.command == "admin":
        admin_product = AdminWorkspace.open(
            workspace,
            working_directory=working_directory,
            cloud_root=cloud_root,
            package_library=package_library,
        )
        admin_product.open_ui(port=args.port, browser=not args.no_browser)
        return 0
    product = Principia.open(
        workspace,
        working_directory=working_directory,
        cloud_root=cloud_root,
        package_library=package_library,
    )
    if args.command == "open":
        product.open_ui(port=args.port, browser=not args.no_browser)
        return 0
    if args.command == "doctor":
        print_json(product.diagnostics())
        return 0
    if args.command == "showcase":
        library = PortablePrincipleLibrary(product.workspace.storage, product.repository)
        if args.showcase_command == "export":
            print_json(library.export(args.output))
        else:
            print_json(library.import_showcase(args.source))
        return 0
    if args.command == "cloud":
        if args.cloud_command == "list":
            print_json({"areas": product.cloud.areas()})
        elif args.cloud_command in {"install", "update"}:
            product.cloud.refresh_catalog(args.catalog)
            print_json(product.cloud.install(args.area, version=args.version))
        elif args.cloud_command == "verify":
            verified = product.cloud.installer.verify_installed(args.area, args.version)
            print_json(
                {
                    "area": verified.manifest.area,
                    "version": verified.manifest.package_version,
                    "artifact_sha256": verified.artifact_sha256,
                    "status": "verified",
                }
            )
        elif args.cloud_command == "pin":
            product.cloud.registry.pin(args.area, args.version, pinned=not args.remove)
            print_json({"area": args.area, "version": args.version, "pinned": not args.remove})
        elif args.cloud_command == "rollback":
            print_json(
                {
                    "area": args.area,
                    "version": product.cloud.installer.rollback(args.area),
                    "status": "active",
                }
            )
        return 0
    if args.command == "local" and args.local_command == "search":
        print_json(
            product.local.search_papers(
                args.goal, area="", target_count=args.target_count
            )
        )
        return 0
    if args.command == "local" and args.local_command == "discover":
        if args.policy == "no_llm":
            policy = ModelPolicy(mode="no_llm")
        else:
            policy = ModelPolicy(
                mode=args.policy,
                provider=args.provider,
                model=args.model,
                base_url=args.base_url,
                remote_egress_confirmed=args.confirm_remote_egress,
            )
        if args.search_id:
            job = product.local.start_literature_discovery(
                search_id=args.search_id,
                policy=policy,
            )
        else:
            if not args.goal:
                raise ValueError("--goal is required with --folder")
            registered = product.local.register_source(args.folder)
            job = product.local.start(
                source_id=registered["source_id"],
                goal=args.goal,
                area=args.area,
                policy=policy,
            )
        while job.state not in {"succeeded", "failed", "cancelled", "interrupted"}:
            time.sleep(0.1)
            job = product.local.get(job.job_id) or job
        print_json(job)
        return 0 if job.state == "succeeded" else 1
    raise ValueError(f"unsupported v1.4 command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
