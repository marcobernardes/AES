from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "regions.csv": ["region_id", "grid_operator", "timezone", "source_category"],
    "grid_marginal_emissions.csv": ["region_id", "timestamp_local", "moer_g_co2e_kwh", "source"],
    "grid_average_emissions.csv": ["region_id", "average_g_co2e_kwh", "source"],
    "electricity_prices.csv": ["region_id", "timestamp_local", "price_usd_kwh", "tariff_name", "source"],
    "liquid_fuel_lca.csv": ["fuel_id", "pathway_name", "total_g_co2e_km", "source_category", "source"],
    "fuel_prices.csv": ["fuel_id", "timestamp_local", "price_usd_km", "source"],
    "vehicle_specs.csv": [
        "vehicle_id", "powertrain", "battery_kwh", "electric_kwh_km",
        "min_departure_soc", "vehicle_prod_g_co2e_km", "source_category"
    ],
    "scenarios.csv": ["scenario_id", "region_id", "vehicle_id", "w_carbon", "w_cost", "static_baseline_g_co2e_km"],
    "service_events.csv": ["event_id", "scenario_id", "timestamp_local", "distance_km", "initial_soc"],
    "uncertainty_parameters.csv": [
        "parameter", "base_value", "distribution", "lower", "mode", "upper",
        "cv", "unit", "source_category"
    ],
}

TIMESTAMP_FILES = {
    "grid_marginal_emissions.csv": ["timestamp_local"],
    "electricity_prices.csv": ["timestamp_local"],
    "fuel_prices.csv": ["timestamp_local"],
    "service_events.csv": ["timestamp_local"],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in TIMESTAMP_FILES.get(path.name, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="raise")
    return df


def validate_input_dir(input_dir: str | Path) -> dict:
    input_dir = Path(input_dir)
    report = {"ok": True, "files": {}, "errors": [], "warnings": []}
    for filename, cols in REQUIRED_COLUMNS.items():
        path = input_dir / filename
        item = {"exists": path.exists()}
        if not path.exists():
            report["ok"] = False
            report["errors"].append(f"Missing required file: {filename}")
            report["files"][filename] = item
            continue
        try:
            df = read_csv(path)
            item["rows"] = int(len(df))
            item["sha256"] = sha256_file(path)
            missing = [c for c in cols if c not in df.columns]
            if missing:
                report["ok"] = False
                report["errors"].append(f"{filename}: missing columns {missing}")
            item["columns"] = list(df.columns)
            item["missing_required"] = missing
            for c in cols:
                if c in df.columns and df[c].isna().any():
                    report["warnings"].append(f"{filename}: required column {c} contains missing values")
            for tcol in TIMESTAMP_FILES.get(filename, []):
                if tcol in df.columns:
                    item[f"{tcol}_min"] = str(df[tcol].min())
                    item[f"{tcol}_max"] = str(df[tcol].max())
                    dup = df.duplicated(subset=[c for c in ["region_id", "scenario_id", "fuel_id", tcol] if c in df.columns]).sum()
                    if dup:
                        report["warnings"].append(f"{filename}: {dup} duplicate key/timestamp rows")
        except Exception as exc:
            report["ok"] = False
            report["errors"].append(f"{filename}: {exc}")
        report["files"][filename] = item

    # Check common timestamps for the implemented dispatch stream.
    try:
        em = read_csv(input_dir / "grid_marginal_emissions.csv")
        pr = read_csv(input_dir / "electricity_prices.csv")
        ev = read_csv(input_dir / "service_events.csv")
        common = set(em["timestamp_local"].astype(str)) & set(pr["timestamp_local"].astype(str)) & set(ev["timestamp_local"].astype(str))
        report["common_dispatch_timestamps"] = len(common)
        if len(common) == 0:
            report["ok"] = False
            report["errors"].append("No common timestamps among emissions, prices, and service events")
    except Exception as exc:
        report["warnings"].append(f"Could not compute common timestamp coverage: {exc}")

    return report


def write_manifest(input_dir: str | Path, out_dir: str | Path) -> dict:
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = validate_input_dir(input_dir)
    manifest = {
        "package": "aes_caiso_repro_package",
        "version": "0.3.0",
        "date_convention": "2026-01-01 00:00 through 2026-01-08 00:00 Pacific time = 168 hourly records, not 18 January",
        "validation": report,
    }
    (out_dir / "input_validation_report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
