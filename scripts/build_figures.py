#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def main() -> int:
    ap = argparse.ArgumentParser(description="Build simple reproducibility figures from AES outputs.")
    ap.add_argument("--input-dir", default="outputs")
    ap.add_argument("--out-dir", default="figures")
    args = ap.parse_args()
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dispatch = pd.read_csv(input_dir / "event_dispatch.csv", parse_dates=["timestamp_local"])
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(dispatch["timestamp_local"], dispatch["moer_g_co2e_kwh"])
    ax.set_ylabel("MOER (g CO$_2$e/kWh)")
    ax.set_xlabel("Time")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_dir / "caiso_moer_timeseries.png", dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 3.5))
    dispatch["selected_action"].value_counts().plot(kind="bar", ax=ax)
    ax.set_ylabel("Event count")
    ax.set_xlabel("Selected AES action")
    fig.tight_layout()
    fig.savefig(out_dir / "dispatch_action_counts.png", dpi=200)
    plt.close(fig)
    print(f"Wrote figures to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
