"""Start this source version with shared dependencies and its own blank user workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path


def runtime_root(core: Path) -> Path:
    # A changed dependency contract gets a separate runtime; source edits reuse it.
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            raise SystemExit("Run this launcher with Python 3.11+, or install tomli for Python 3.10.") from None
    project = tomllib.loads((core / "pyproject.toml").read_text())["project"]
    contract = {"dependencies": project["dependencies"], "optional": project["optional-dependencies"]}
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()[:16]
    base = Path.home() / "Library/Application Support/Principia" if sys.platform == "darwin" else Path.home() / ".local/share/Principia"
    return base / "runtimes" / f"python-{platform.machine()}-{digest}"


def main() -> None:
    formal = Path(__file__).resolve().parents[1]
    core = formal / "core-v1.4.2"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8142)
    parser.add_argument("--working-directory", type=Path, default=formal / "runtime/user-workspace")
    parser.add_argument("--credential-env", type=Path, help="Optional explicitly supplied credential file; never copied.")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    candidates = [core / ".venv/bin/python", runtime_root(core) / "bin/python"]
    interpreter = next((path for path in candidates if path.is_file()), None)
    if interpreter is None:
        raise SystemExit("Install dependencies first: create core-v1.4.2/.venv, then pip install '.[asd,local]' from core-v1.4.2.")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(core / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PRINCIPIA_SOURCE_ROOT"] = str(core)
    launch = ["open", "--working-directory", str(args.working_directory.resolve()), "--port", str(args.port)]
    if not args.browser:
        launch.append("--no-browser")
    code = "import sys; "
    if args.credential_env:
        code += "from principia.providers.token_budget import load_credential_environment; from pathlib import Path; load_credential_environment(Path(sys.argv.pop(1))); "
    code += "from principia.cli import main; raise SystemExit(main(sys.argv[1:]))"
    credentials = [str(args.credential_env.resolve())] if args.credential_env else []
    os.chdir(core)
    os.execve(str(interpreter), [str(interpreter), "-c", code, *credentials, *launch], environment)


if __name__ == "__main__":
    main()
