#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from principia import Principia
from principia.cloud import load_catalog, verify_pcp

FORBIDDEN_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
FORBIDDEN_NAMES = {"abstract.txt", "full-text.txt", "normalized.txt", "paper.pdf"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    catalog = args.catalog.expanduser().resolve(strict=True)
    root = catalog.parent
    forbidden = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and (path.suffix.casefold() in FORBIDDEN_SUFFIXES or path.name.casefold() in FORBIDDEN_NAMES)
    ]
    if forbidden:
        raise SystemExit(f"forbidden source artifacts in Candidate catalog: {forbidden}")
    entries = load_catalog(catalog)
    if not entries:
        raise SystemExit("Candidate catalog contains no packages")
    with tempfile.TemporaryDirectory(prefix="principia-candidate-catalog-verify-") as temporary:
        working_directory = Path(temporary) / "working-directory"
        working_directory.mkdir()
        product = Principia.open(working_directory=working_directory)
        try:
            product.cloud.refresh_catalog(catalog)
            for entry in entries:
                if entry.content_class != "unassessed_candidates":
                    raise SystemExit(f"unexpected content class: {entry.area}")
                product.cloud.install(entry.area, version=entry.package_version)
                installed = product.cloud.installer.verify_installed(
                    entry.area, entry.package_version
                )
                verify_pcp(installed.path)
            page = product.explorer.browse(
                scope="global", evidence_status="checks_passed", limit=100
            )
            if int(page["total"]) != sum(item.principle_count for item in entries):
                raise SystemExit("installed Principle count does not match catalog")
            if any(item["human_review_status"] != "pending" for item in page["items"]):
                raise SystemExit("Candidate package incorrectly claims human review")
            for card in page["items"]:
                detail = product.search.principle(card["id"]) or {}
                references = list(detail.get("source_references") or [])
                links = [str(item.get("url") or "") for item in references]
                if not links or any(not item.startswith("https://") for item in links):
                    raise SystemExit(
                        f"packaged Principle lacks a public HTTPS paper link: {card['id']}"
                    )
        finally:
            product.close()
    receipt = {
        "schema_version": "principia-candidate-catalog-verification-v1",
        "package_count": len(entries),
        "principle_count": sum(item.principle_count for item in entries),
        "artifact_bytes": sum(item.artifact_bytes for item in entries),
        "paper_files": 0,
        "source_text_included": False,
        "status": "passed",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
