from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from principia import AdminWorkspace
from principia.api import create_app


def render() -> str:
    with tempfile.TemporaryDirectory(prefix="principia-openapi-") as temp:
        root = Path(temp)
        product = AdminWorkspace.open(root / "workspace", cloud_root=root / "cloud")
        schema = create_app(product, admin_mode=True, test_mode=True).openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "src" / "principia" / "openapi-v1.json"
    expected = render()
    actual = target.read_text(encoding="utf-8") if target.exists() else ""
    if args.check and actual != expected:
        print("OpenAPI drift detected")
        return 1
    if not args.check:
        target.write_text(expected, encoding="utf-8")
    print("OpenAPI contract is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
