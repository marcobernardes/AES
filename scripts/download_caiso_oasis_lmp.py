#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aes.caiso_oasis import build_oasis_params, download_oasis_zip, read_oasis_response, normalize_lmp_to_aes_schema


def main() -> int:
    ap = argparse.ArgumentParser(description="Download CAISO OASIS LMP data and convert to AES electricity_prices.csv schema.")
    ap.add_argument("--start", required=True, help="Start datetime/date. Interpreted as UTC if no offset is supplied.")
    ap.add_argument("--end", required=True, help="End datetime/date. Interpreted as UTC if no offset is supplied.")
    ap.add_argument("--node", required=True, help="CAISO pricing node or trading hub.")
    ap.add_argument("--queryname", default="PRC_INTVL_LMP", help="CAISO OASIS queryname/report.")
    ap.add_argument("--market-run-id", default="DAM", help="CAISO market_run_id, e.g., DAM, RTM, RTPD depending on report.")
    ap.add_argument("--region-id", default="CAISO")
    ap.add_argument("--out", required=True)
    ap.add_argument("--save-raw-zip", default=None)
    args = ap.parse_args()

    params = build_oasis_params(args.start, args.end, args.node, args.queryname, args.market_run_id)
    content = download_oasis_zip(params)
    if args.save_raw_zip:
        Path(args.save_raw_zip).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_raw_zip).write_bytes(content)
    raw = read_oasis_response(content)
    aes = normalize_lmp_to_aes_schema(raw, region_id=args.region_id, source=f"CAISO OASIS {args.queryname}/{args.market_run_id}/{args.node}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    aes.to_csv(out, index=False)
    print(f"Wrote {len(aes)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
