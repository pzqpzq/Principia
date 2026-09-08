"""Principia v1 local-first principle memory package."""

import sys

if sys.version_info < (3, 9):
    raise RuntimeError("Principia v1 requires Python 3.9 or newer. Python 3.12 is recommended.")

__version__ = "1.0.0"
