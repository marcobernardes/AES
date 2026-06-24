#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aes.schemas import write_manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate AES input CSV files and write a run manifest.")
    ap.add_argument("--input-dir", default="data/processed")
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args()
    manifest = write_manifest(args.input_dir, args.out_dir)
    print(json.dumps({"ok": manifest["validation"]["ok"], "errors": manifest["validation"]["errors"], "warnings": manifest["validation"]["warnings"]}, indent=2))
    return 0 if manifest["validation"]["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
