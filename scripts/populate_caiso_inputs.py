#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aes.populate import populate_caiso_inputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Populate AES real-data CSV files for a CAISO-only proof-of-method run.")
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--out-dir", default="data/processed")
    ap.add_argument("--demo", action="store_true", help="Generate deterministic offline demo raw data before populating inputs.")
    args = ap.parse_args()
    populate_caiso_inputs(args.raw_dir, args.out_dir, demo=args.demo)
    print(f"Populated AES inputs in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
