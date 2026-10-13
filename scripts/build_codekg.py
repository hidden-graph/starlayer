"""scripts/build_codekg.py - thin CLI wrapper for the code-KG extractor,
replacing scripts/build_code_kg.py as the maintained entry point.

Run:
    python scripts/build_codekg.py --paths packages/starlayer/starlayer/graph/model/
"""

import sys
from pathlib import Path

_PACKAGES_STARLAYER = Path(__file__).resolve().parents[1] / "packages" / "starlayer"
if str(_PACKAGES_STARLAYER) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_STARLAYER))

from starlayer.codekg.extractor.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
