#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aes.monte_carlo import run_monte_carlo


def main() -> int:
    ap = argparse.ArgumentParser(description="Run AES Monte Carlo uncertainty propagation and convergence diagnostics.")
    ap.add_argument("--input-dir", default="data/processed")
    ap.add_argument("--out-dir", default="outputs")
    ap.add_argument("--seed", type=int, default=20260108)
    ap.add_argument("--draws", type=int, default=10000)
    args = ap.parse_args()
    summary, conv = run_monte_carlo(args.input_dir, args.out_dir, seed=args.seed, n=args.draws)
    print(summary.to_string(index=False))
    print(conv.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
