#!/usr/bin/env python3
"""Convenience wrapper so you can run the validator from the repo root:

    python3 tools/validate.py                                  # full book
    python3 tools/validate.py reader/my-course.collection.xml
    python3 tools/validate.py reader/my-course.collection.xml --orphans

Equivalent to `python3 -m oscompile.validate ...` run from inside tools/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oscompile.validate import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
