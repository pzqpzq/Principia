from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any, Literal


class ClosingSQLiteConnection(sqlite3.Connection):
    """A transaction context that also releases its database descriptor.

    ``sqlite3.Connection.__exit__`` commits or rolls back, but deliberately leaves
    the connection open. Principia uses short-lived repository transactions, so a
    request-heavy runtime must close the connection when the ``with`` block ends.
    Direct callers retain the normal Connection API and may close it themselves.
    """

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            super().__exit__(exc_type, exc_value, traceback)
            return False
        finally:
            self.close()


def connect_sqlite(
    database: str | Path,
    *args: Any,
    **kwargs: Any,
) -> sqlite3.Connection:
    """Open a SQLite connection that closes after a transaction context."""

    if "factory" in kwargs:
        raise TypeError("Principia's SQLite connection factory cannot be overridden")
    return sqlite3.connect(database, *args, factory=ClosingSQLiteConnection, **kwargs)
