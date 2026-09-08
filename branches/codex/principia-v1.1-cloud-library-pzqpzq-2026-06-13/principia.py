#!/usr/bin/env python3
import sys

if sys.version_info < (3, 9):
    raise SystemExit("Principia v1 requires Python 3.9 or newer. Python 3.12 is recommended.")

from principia.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
