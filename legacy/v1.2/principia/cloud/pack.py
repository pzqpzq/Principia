from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .compression import compress_bytes, decompress_bytes
from .ids import canonical_json, sha256_hex


PCZ_MAGIC = b"PCZ1\n"


@dataclass(frozen=True)
class PackEntry:
    record_id: str
    record_type: str
    pack_id: str
    block_id: str
    offset: int
    length: int
    checksum: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "pack_id": self.pack_id,
            "block_id": self.block_id,
            "offset": self.offset,
            "length": self.length,
            "checksum": self.checksum,
        }


def record_id_for(record: dict[str, Any]) -> str:
    for key in (
        "work_id",
        "work_version_id",
        "extraction_run_id",
        "concept_id",
        "relation_id",
        "evidence_id",
        "operation_id",
        "record_id",
    ):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    raise ValueError("Cloud record has no stable id field")


def write_pack(path: Path, records: Iterable[dict[str, Any]], *, pack_id: str, record_type: str, records_per_block: int = 128) -> list[PackEntry]:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[PackEntry] = []
    offset = 0
    block: list[dict[str, Any]] = []
    with path.open("wb") as fh:
        fh.write(PCZ_MAGIC)
        offset += len(PCZ_MAGIC)
        for record in records:
            block.append(record)
            if len(block) >= records_per_block:
                offset = _write_block(fh, block, entries, pack_id=pack_id, record_type=record_type, offset=offset)
                block = []
        if block:
            _write_block(fh, block, entries, pack_id=pack_id, record_type=record_type, offset=offset)
    return entries


def _write_block(fh, block: list[dict[str, Any]], entries: list[PackEntry], *, pack_id: str, record_type: str, offset: int) -> int:
    raw = "\n".join(canonical_json(record) for record in block).encode("utf-8") + b"\n"
    compressed = compress_bytes(raw)
    checksum = sha256_hex(compressed)
    block_id = f"{pack_id}-block-{len(entries):08d}"
    fh.write(compressed)
    length = len(compressed)
    for record in block:
        entries.append(
            PackEntry(
                record_id=record_id_for(record),
                record_type=str(record.get("record_type") or record_type),
                pack_id=pack_id,
                block_id=block_id,
                offset=offset,
                length=length,
                checksum=checksum,
            )
        )
    return offset + length


def read_block(path: Path, *, offset: int, length: int, checksum: str = "") -> list[dict[str, Any]]:
    with path.open("rb") as fh:
        if offset == 0:
            magic = fh.read(len(PCZ_MAGIC))
            if magic != PCZ_MAGIC:
                raise ValueError(f"{path} is not a Principia cloud pack")
        fh.seek(offset)
        compressed = fh.read(length)
    if checksum and sha256_hex(compressed) != checksum:
        raise ValueError(f"Checksum mismatch for block in {path}")
    raw = decompress_bytes(compressed).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def read_record(path: Path, *, record_id: str, offset: int, length: int, checksum: str = "") -> dict[str, Any] | None:
    for record in read_block(path, offset=offset, length=length, checksum=checksum):
        if record_id_for(record) == record_id:
            return record
    return None
