from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "frozen_corpus.py"
SPEC = importlib.util.spec_from_file_location("principia_frozen_corpus", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CAMPAIGN_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_v142_acceptance_campaign.py"
sys.path.insert(0, str(CAMPAIGN_SCRIPT.parent))
CAMPAIGN_SPEC = importlib.util.spec_from_file_location(
    "principia_acceptance_campaign", CAMPAIGN_SCRIPT
)
assert CAMPAIGN_SPEC is not None and CAMPAIGN_SPEC.loader is not None
CAMPAIGN_MODULE = importlib.util.module_from_spec(CAMPAIGN_SPEC)
CAMPAIGN_SPEC.loader.exec_module(CAMPAIGN_MODULE)


def _corpus(tmp_path: Path) -> tuple[Path, Path]:
    numbered = tmp_path / "numbered"
    numbered.mkdir()
    for index in range(1, 21):
        scenario = numbered / f"{index:02d}_scenario"
        scenario.mkdir()
        (scenario / "payload.txt").write_text(f"scenario {index}\n", encoding="utf-8")
    tj = tmp_path / "TJ-SHD"
    tj.mkdir()
    (tj / "payload.txt").write_text("frozen science\n", encoding="utf-8")
    return numbered, tj


def test_v2_finder_metadata_is_telemetry_not_an_integrity_gate(tmp_path: Path) -> None:
    numbered, tj = _corpus(tmp_path)
    receipt = tmp_path / "receipt.json"
    assert MODULE.create(numbered, receipt, schema="v2", tj_root=tj) == 0
    (numbered / "01_scenario" / ".DS_Store").write_bytes(b"Finder changed this")
    (tj / ".DS_Store").write_bytes(b"and this")
    assert MODULE.verify(numbered, receipt, tj_root=tj) == 0


def test_acceptance_campaign_uses_the_same_non_gating_finder_policy(tmp_path: Path) -> None:
    numbered, tj = _corpus(tmp_path)
    expected = MODULE.scan_v2(numbered, tj)
    (numbered / "01_scenario" / ".DS_Store").write_bytes(b"new Finder telemetry")
    (tj / ".DS_Store").write_bytes(b"more Finder telemetry")

    digests = CAMPAIGN_MODULE._assert_frozen(numbered, tj, expected)
    assert digests["numbered_01_20"]["content_digest"] == expected["roots"][0][
        "content_digest"
    ]

    (numbered / "01_scenario" / "payload.txt").write_text(
        "critical scientific content changed\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="frozen corpus mismatch"):
        CAMPAIGN_MODULE._assert_frozen(numbered, tj, expected)


def test_v2_still_gates_critical_files_and_rejects_symlinks(tmp_path: Path) -> None:
    numbered, tj = _corpus(tmp_path)
    receipt = tmp_path / "receipt.json"
    assert MODULE.create(numbered, receipt, schema="v2", tj_root=tj) == 0
    payload = numbered / "01_scenario" / "payload.txt"
    payload.write_text("scientific content changed\n", encoding="utf-8")
    assert MODULE.verify(numbered, receipt, tj_root=tj) == 1

    payload.write_text("scenario 1\n", encoding="utf-8")
    link = numbered / "01_scenario" / ".DS_Store"
    link.symlink_to(payload)
    with pytest.raises(ValueError, match="non-regular"):
        MODULE.scan_v2(numbered, tj)
