"""Write web/business.json from business.toml, so the browser demo shows exactly the bot's services.

    python tools/export_web_config.py
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    data = tomllib.loads((ROOT / "business.toml").read_text(encoding="utf-8"))
    out = ROOT / "web" / "business.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", out.relative_to(ROOT), file=sys.stderr)


if __name__ == "__main__":
    main()
