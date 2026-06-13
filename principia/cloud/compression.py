from __future__ import annotations

import gzip
from pathlib import Path


COMPRESSION = "gzip"


def compress_bytes(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


def decompress_bytes(data: bytes) -> bytes:
    return gzip.decompress(data)


def compress_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(compress_bytes(source.read_bytes()))


def decompress_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(decompress_bytes(source.read_bytes()))
