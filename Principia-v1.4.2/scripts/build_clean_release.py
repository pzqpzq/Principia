"""Assemble the complete local product, keeping companion tooling outside the public core."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core-v1.4.2"))
from scripts.build_clean_release import build_clean_release  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--maximum-mib", type=int, default=192)
    parser.add_argument("--public", action="store_true", help="Package the public core without local administrative tooling.")
    args = parser.parse_args()
    print(json.dumps(build_clean_release(
        args.source, args.destination, maximum_bytes=args.maximum_mib * 1024**2,
        products=("core-v1.4.2",) if args.public else ("core-v1.4.2", "principia-admin-local")), indent=2))
