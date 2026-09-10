from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import signal
import site
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..cancellation import TaskCancelled, check_cancelled

try:  # pragma: no cover - exercise differs on macOS/Linux
    import resource
    HAVE_RESOURCE = True
except ImportError:  # pragma: no cover - Windows has no resource module
    resource = None
    HAVE_RESOURCE = False

ALLOWED_IMPORTS = {
    "collections",
    "datetime",
    "duckdb",
    "itertools",
    "json",
    "math",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "statistics",
    "statsmodels",
    "xarray",
}
BANNED_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "vars",
}
BANNED_ATTRIBUTES = {
    "dump",
    "dumps",
    "fromfile",
    "load",
    "loads",
    "read_csv",
    "read_excel",
    "read_feather",
    "read_hdf",
    "read_json",
    "read_parquet",
    "save",
    "savefig",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_hdf",
    "to_json",
    "to_parquet",
    "to_pickle",
    "tofile",
}
MAX_CODE_BYTES = 100_000
MAX_LOG_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 16 * 1024 * 1024


def _sanitize_log_bytes(value: bytes, *, private_roots: list[Path]) -> bytes:
    """Remove host paths and credential-shaped values from persisted child logs."""

    text = value.decode("utf-8", errors="replace")
    roots = {
        str(path.resolve())
        for path in private_roots
        if str(path).strip()
    }
    roots.add(str(Path.home().resolve()))
    for root in sorted(roots, key=len, reverse=True):
        text = text.replace(root, "<local-path>")

    # Tracebacks and library diagnostics can reveal paths outside the explicitly
    # granted roots. Keep the error itself while removing the host locator.
    text = re.sub(r'File\s+["\'][^"\']+["\']', 'File "<local-path>"', text)
    text = re.sub(
        r'(?<![:\w])/(?:[^/\s"\'<>]+/)+[^/\s"\'<>:]+',
        "<local-path>",
        text,
    )
    text = re.sub(
        r'(?i)\b(?:authorization\s*:\s*bearer|bearer)\s+[A-Za-z0-9._~+/=-]+',
        "Bearer <redacted-secret>",
        text,
    )
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b', '<redacted-secret>', text)
    return text.encode("utf-8")[:MAX_LOG_BYTES]


@dataclass(frozen=True)
class SandboxAudit:
    available: bool
    isolated: bool
    fallback_required: bool
    code_digest: str
    ast_digest: str
    violations: tuple[str, ...]
    elapsed_seconds: float = 0.0
    return_code: int | None = None
    timed_out: bool = False
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    max_resident_bytes: int = 0
    memory_limit_bytes: int = 0
    memory_limit_kind: str = ""
    output_bytes: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnalysisSandbox:
    """AST-audited Python execution behind the host's verified isolation layer."""

    def __init__(
        self,
        *,
        python_executable: Path | None = None,
        wall_timeout_seconds: int = 300,
        address_space_bytes: int = 4 * 1024 * 1024 * 1024,
    ) -> None:
        self.python_executable = Path(python_executable or sys.executable).absolute()
        framework_python = (
            Path(sys.base_prefix) / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
        )
        self.launch_executable = (
            framework_python if sys.platform == "darwin" and framework_python.is_file()
            else self.python_executable
        )
        self.site_paths = [Path(value).resolve() for value in site.getsitepackages()]
        self.wall_timeout_seconds = max(1, int(wall_timeout_seconds))
        self.address_space_bytes = max(512 * 1024 * 1024, int(address_space_bytes))
        self.sandbox_executable = shutil.which("sandbox-exec") if sys.platform == "darwin" else None

    @property
    def available(self) -> bool:
        return bool(self.sandbox_executable and self.python_executable.is_file())

    def audit(self, code: str) -> SandboxAudit:
        encoded = code.encode("utf-8")
        code_digest = hashlib.sha256(encoded).hexdigest()
        violations: list[str] = []
        if len(encoded) > MAX_CODE_BYTES:
            violations.append("code exceeds the 100 kB limit")
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            violations.append(f"syntax error at line {exc.lineno or 0}")
            tree = ast.Module(body=[], type_ignores=[])
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [str(node.module or "")]
                )
                for name in names:
                    root = name.split(".", 1)[0]
                    if root not in ALLOWED_IMPORTS:
                        violations.append(f"import is not allowed: {root or '<relative>'}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                    violations.append(f"call is not allowed: {node.func.id}")
                if isinstance(node.func, ast.Attribute) and node.func.attr in BANNED_ATTRIBUTES:
                    violations.append(f"I/O method is not allowed: {node.func.attr}")
            elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                violations.append("dunder attribute access is not allowed")
            elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id != "__name__":
                violations.append("dunder names are not allowed")
        normalized_ast = ast.dump(tree, annotate_fields=True, include_attributes=False).encode()
        return SandboxAudit(
            available=self.available,
            isolated=False,
            fallback_required=not self.available or bool(violations),
            code_digest=code_digest,
            ast_digest=hashlib.sha256(normalized_ast).hexdigest(),
            violations=tuple(dict.fromkeys(violations)),
        )

    @staticmethod
    def _profile_literal(path: Path) -> str:
        return str(path).replace("\\", "\\\\").replace('"', '\\"')

    def _sandbox_profile(self, *, artifact_root: Path, read_roots: list[Path]) -> str:
        readable = {
            Path("/System"),
            Path("/usr"),
            Path("/Library"),
            self.python_executable.parent.parent,
            self.launch_executable.parent.parent,
            Path(__file__).resolve().parent,
            artifact_root,
            *self.site_paths,
            *(path.resolve() for path in read_roots),
        }
        rules = [
            "(version 1)",
            "(deny default)",
            '(import "system.sb")',
            f'(allow process-exec (literal "{self._profile_literal(self.launch_executable)}"))',
            "(deny process-fork)",
            "(deny network*)",
            "(allow sysctl-read)",
            "(allow mach-lookup)",
        ]
        for path in sorted(readable, key=lambda value: str(value)):
            rules.append(f'(allow file-read* (subpath "{self._profile_literal(path)}"))')
        rules.append(
            f'(allow file-write* (subpath "{self._profile_literal(artifact_root)}"))'
        )
        return "\n".join(rules)

    def _limits(self) -> None:
        if not HAVE_RESOURCE:  # pragma: no cover - Windows sandbox is unavailable
            return

        def set_soft(kind: int, value: int) -> None:
            _, hard = resource.getrlimit(kind)
            resource.setrlimit(kind, (min(value, hard), hard))

        set_soft(resource.RLIMIT_CORE, 0)
        set_soft(resource.RLIMIT_NOFILE, 128)
        set_soft(resource.RLIMIT_FSIZE, 256 * 1024 * 1024)
        # Leave the child CPU clock one second beyond the parent wall clock so
        # the parent normally owns timeout termination. If the CPU guard wins
        # a scheduling race, ``run`` still classifies SIGXCPU as a timeout.
        set_soft(resource.RLIMIT_CPU, self.wall_timeout_seconds + 1)
        # Darwin's Python framework maps a very large reserved address range,
        # causing RLIMIT_AS reductions to fail before exec. The parent runner
        # still enforces the wall/output limits and the sandbox denies fork;
        # other platforms retain the hard address-space boundary.
        if hasattr(resource, "RLIMIT_AS") and sys.platform != "darwin":
            set_soft(resource.RLIMIT_AS, self.address_space_bytes)
        # macOS accounts RLIMIT_NPROC per user, so lowering it below the user's
        # already-running process count fails before the sandbox launches. The
        # sandbox profile itself denies process-fork; retain RLIMIT_NPROC as a
        # second layer on platforms where it has per-process utility.
        if hasattr(resource, "RLIMIT_NPROC") and sys.platform != "darwin":
            set_soft(resource.RLIMIT_NPROC, 1)

    @staticmethod
    def _resident_bytes(process_id: int) -> int:
        """Return a child RSS sample without granting the child new access."""

        try:
            completed = subprocess.run(
                ["/bin/ps", "-o", "rss=", "-p", str(process_id)],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return max(0, int((completed.stdout or "0").strip() or 0) * 1024)
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0

    def run(
        self,
        *,
        code: str,
        inputs: dict[str, Any],
        artifact_root: Path,
        read_roots: list[Path] | None = None,
        seed: int = 0,
    ) -> tuple[dict[str, Any] | None, SandboxAudit]:
        initial = self.audit(code)
        if initial.fallback_required:
            return None, initial
        artifact_root = artifact_root.resolve()
        artifact_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        code_path = artifact_root / "analysis.py"
        input_path = artifact_root / "input.json"
        output_path = artifact_root / "result.json"
        stdout_path = artifact_root / "stdout.log"
        stderr_path = artifact_root / "stderr.log"
        audit_path = artifact_root / "sandbox-audit.json"
        code_path.write_text(code, encoding="utf-8")
        input_path.write_text(json.dumps(inputs, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        profile = self._sandbox_profile(
            artifact_root=artifact_root,
            read_roots=list(read_roots or []),
        )
        runner = Path(__file__).resolve().with_name("sandbox_runner.py")
        command = [
            str(self.sandbox_executable),
            "-p",
            profile,
            str(self.launch_executable),
            "-I",
            str(runner),
            str(code_path),
            str(input_path),
            str(output_path),
        ]
        environment = {
            "PATH": str(self.python_executable.parent),
            "PYTHONHASHSEED": str(seed & 0xFFFFFFFF),
            "MPLCONFIGDIR": str(artifact_root / "matplotlib"),
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "PRINCIPIA_SANDBOX_SITE_PATHS": os.pathsep.join(str(path) for path in self.site_paths),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
        started = time.monotonic()
        check_cancelled()
        cancelled = False
        timed_out = False
        memory_exceeded = False
        max_resident_bytes = 0
        return_code: int | None = None
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env=environment,
                cwd=artifact_root,
                preexec_fn=self._limits,
            )
            deadline = started + self.wall_timeout_seconds
            while process.poll() is None:
                try:
                    check_cancelled()
                except TaskCancelled:
                    cancelled = True
                    process.kill()
                    break
                if sys.platform == "darwin":
                    resident = self._resident_bytes(process.pid)
                    max_resident_bytes = max(max_resident_bytes, resident)
                    if resident > self.address_space_bytes:
                        memory_exceeded = True
                        process.kill()
                        break
                if time.monotonic() >= deadline:
                    timed_out = True
                    process.kill()
                    break
                time.sleep(0.1)
            return_code = process.wait(timeout=10)
        if return_code == -signal.SIGXCPU:
            timed_out = True
        elapsed = time.monotonic() - started
        private_roots = [
            artifact_root,
            Path(__file__).resolve().parents[3],
            runner,
            self.python_executable,
            self.launch_executable,
            *self.site_paths,
            *(Path(path) for path in (read_roots or [])),
        ]
        stdout_bytes = _sanitize_log_bytes(
            stdout_path.read_bytes()[:MAX_LOG_BYTES],
            private_roots=private_roots,
        )
        stderr_bytes = _sanitize_log_bytes(
            stderr_path.read_bytes()[:MAX_LOG_BYTES],
            private_roots=private_roots,
        )
        # Always replace the raw child logs, even when they were below the cap:
        # a short traceback is the most common place a local path leaks.
        stdout_path.write_bytes(stdout_bytes)
        stderr_path.write_bytes(stderr_bytes)
        result: dict[str, Any] | None = None
        violations = list(initial.violations)
        if return_code == 0 and output_path.is_file() and output_path.stat().st_size <= MAX_RESULT_BYTES:
            try:
                value = json.loads(output_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    result = value
                else:
                    violations.append("sandbox result was not a JSON object")
            except (OSError, json.JSONDecodeError):
                violations.append("sandbox result was not valid JSON")
        elif cancelled:
            violations.append("analysis cancelled")
        elif timed_out:
            violations.append("analysis timed out")
        elif memory_exceeded:
            violations.append("analysis exceeded the 4 GiB resident-memory guard")
        else:
            violations.append("analysis process failed")
        output_bytes = output_path.stat().st_size if output_path.is_file() else 0
        audit = SandboxAudit(
            available=True,
            isolated=True,
            fallback_required=result is None,
            code_digest=initial.code_digest,
            ast_digest=initial.ast_digest,
            violations=tuple(violations),
            elapsed_seconds=round(elapsed, 3),
            return_code=return_code,
            timed_out=timed_out,
            stdout_sha256=hashlib.sha256(stdout_bytes).hexdigest(),
            stderr_sha256=hashlib.sha256(stderr_bytes).hexdigest(),
            max_resident_bytes=max_resident_bytes,
            memory_limit_bytes=self.address_space_bytes,
            memory_limit_kind=(
                "resident_set_guard" if sys.platform == "darwin" else "address_space_rlimit"
            ),
            output_bytes=output_bytes,
        )
        audit_path.write_text(
            json.dumps(audit.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if cancelled:
            raise TaskCancelled()
        return result, audit
