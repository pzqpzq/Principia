"""Minimal isolated runner for prevalidated Principia analysis code."""

from __future__ import annotations

import json
import os
import site
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    for value in os.environ.get("PRINCIPIA_SANDBOX_SITE_PATHS", "").split(os.pathsep):
        if value:
            site.addsitedir(value)
    code_path, input_path, output_path = (Path(value) for value in sys.argv[1:])
    inputs = json.loads(input_path.read_text(encoding="utf-8"))
    namespace = {"INPUT": inputs, "RESULT": None, "__name__": "__principia_analysis__"}
    code = compile(code_path.read_text(encoding="utf-8"), code_path.name, "exec")
    exec(code, namespace, namespace)  # noqa: S102 - isolated, AST-audited analysis boundary
    result = namespace.get("RESULT")
    if not isinstance(result, dict):
        raise TypeError("analysis code must assign a JSON-object value to RESULT")
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
