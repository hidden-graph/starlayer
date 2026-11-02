"""Run the code knowledge graph query tool: ``python scripts/kg.py list`` (see ``python scripts/kg.py --help``).

The tooling lives in ``tools/kg/codekg``, outside the installable package, so this puts it and the library on the path and
hands over to ``codekg.queries``.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT / "packages" / "starlayer", ROOT / "tools" / "kg"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from codekg.queries import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
