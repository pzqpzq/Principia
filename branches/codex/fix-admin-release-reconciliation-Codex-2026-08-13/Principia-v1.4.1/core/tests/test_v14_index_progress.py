from __future__ import annotations

from pathlib import Path

from principia.application import Principia
from principia.local_sources import LocalCorpusIngestor


def test_local_ingestion_reports_monotonic_progress_and_stops_between_files(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "papers"
    folder.mkdir()
    for index in range(5):
        (folder / f"paper-{index}.txt").write_text(
            f"Scientific finding {index} with a reusable relation.", encoding="utf-8"
        )
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    observations: list[tuple[int, int]] = []

    def progress(completed: int, total: int, _report: object | None) -> bool:
        observations.append((completed, total))
        return completed < 3

    result = LocalCorpusIngestor(product.workspace.storage).ingest(
        folder, progress_callback=progress
    )
    assert observations == [(0, 5), (1, 5), (2, 5), (3, 5)]
    assert len(result.local_diagnostics.reports) == 3
    assert [completed for completed, _ in observations] == sorted(
        completed for completed, _ in observations
    )
