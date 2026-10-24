"""Write the API's OpenAPI spec to web/lib/openapi.json (the web app's types are built from it).

Run from api/:  uv run python scripts/export_openapi.py
No server or database needed. CI re-runs this and fails if the committed file is stale.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "web" / "lib" / "openapi.json"

spec = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
OUT.write_text(spec, encoding="utf-8", newline="\n")  # LF on Windows too, so CI's diff is clean
print(f"Wrote {OUT}")
