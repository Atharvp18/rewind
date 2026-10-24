"""Load the sourced IRS category rules into eligibility_items and write the readable table.

    python -m prefetch.load_irs_rules

Idempotent. Also removes the retired placeholder rows keyed by fake barcodes (upc:0000000000NN).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import common  # noqa: F401  (loads backend/.env)
from data import db
from eligibility.irs_rules import markdown_table, rule_rows

RETIRED_KEYS = ["upc:000000000001", "upc:000000000002", "upc:000000000003"]


def main() -> None:
    out = Path(__file__).parent.parent / "eligibility" / "IRS_RULES.md"
    out.write_text(markdown_table())
    print(f"wrote {out}")
    db.eligibility_delete(RETIRED_KEYS)
    rows = rule_rows(datetime.now(timezone.utc).isoformat())
    print(f"upserted {db.eligibility_bulk_insert(rows)} rule rows; removed {len(RETIRED_KEYS)} placeholder rows")


if __name__ == "__main__":
    main()
