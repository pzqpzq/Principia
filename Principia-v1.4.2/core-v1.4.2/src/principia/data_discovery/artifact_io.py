"""Atomic export copies that use filesystem copy-on-write when available."""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile
from pathlib import Path


def copy_artifact(source: Path, destination: Path) -> None:
    """Keep exports independently editable without duplicating APFS extents.

    A hard link is deliberately unsuitable: editing an exported report must
    never modify its canonical evidence. Unsupported filesystems use a copy.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".export-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        cloned = False
        if sys.platform == "darwin":
            temporary.unlink()
            libc = ctypes.CDLL(None, use_errno=True)
            clone = getattr(libc, "clonefile", None)
            if clone is not None:
                clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
                clone.restype = ctypes.c_int
                cloned = clone(os.fsencode(source), os.fsencode(temporary), 0) == 0
        if not cloned:
            shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
