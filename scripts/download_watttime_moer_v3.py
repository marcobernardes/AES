#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aes.watttime_v3 import login, fetch_historical_moer, normalize_moer_to_aes_schema, aggregate_moer_hourly


def main() -> int:
    ap = argparse.ArgumentParser(description="Download WattTime v3 historical MOER and convert to AES grid_marginal_emissions.csv schema.")
    ap.add_argument("--region", default="CAISO_NORTH")
    ap.add_argument("--region-id", default="CAISO")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--base-url", default="https://api.watttime.org")
    ap.add_argument("--signal-type", default="co2_moer")
    ap.add_argument("--model", default=None)
    ap.add_argument("--hourly", action="store_true", default=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    token = login(base_url=args.base_url)
    raw = fetch_historical_moer(args.region, args.start, args.end, token, base_url=args.base_url, signal_type=args.signal_type, model=args.model)
    aes = normalize_moer_to_aes_schema(raw, region_id=args.region_id, source=f"WattTime v3 historical {args.region} {args.signal_type}")
    if args.hourly:
        aes = aggregate_moer_hourly(aes)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    aes.to_csv(out, index=False)
    print(f"Wrote {len(aes)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
