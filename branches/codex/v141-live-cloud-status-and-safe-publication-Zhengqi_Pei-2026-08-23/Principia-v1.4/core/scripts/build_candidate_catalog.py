#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from principia import Principia
from principia.cloud import CandidatePackageBuilder, CandidatePackageSpec


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build verified paper-free Candidate Principle packages from folder collections."
    )
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-version", default="1.0.0")
    parser.add_argument(
        "--collection",
        action="append",
        nargs=3,
        metavar=("SOURCE_ID", "PACKAGE_ID", "DISPLAY_NAME"),
        required=True,
    )
    args = parser.parse_args()
    product = Principia.open(working_directory=args.working_directory)
    try:
        receipt = CandidatePackageBuilder(
            product.workspace.storage, product.repository
        ).build(
            args.output,
            specs=[CandidatePackageSpec(*item) for item in args.collection],
            package_version=args.package_version,
        )
    finally:
        product.close()
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
