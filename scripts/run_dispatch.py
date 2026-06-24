#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aes.dispatch import run_dispatch


def main() -> int:
    ap = argparse.ArgumentParser(description="Run AES dispatch model.")
    ap.add_argument("--input-dir", default="data/processed")
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args()
    out = run_dispatch(args.input_dir, args.out_dir)
    print(f"Wrote dispatch for {len(out)} events to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
