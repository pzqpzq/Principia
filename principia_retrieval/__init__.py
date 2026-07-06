"""Source-tree shim for the shared v1.3 retrieval package."""

from __future__ import annotations

from pathlib import Path

_shared_dir = Path(__file__).resolve().parents[1] / "Principia-v1.3" / "src" / "principia_retrieval"
__path__ = [str(_shared_dir), *__path__]  # type: ignore[name-defined]
_shared_init = _shared_dir / "__init__.py"
exec(compile(_shared_init.read_text(encoding="utf-8"), str(_shared_init), "exec"), globals())
