from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import numpy as np

from .caiso_oasis import normalize_lmp_to_aes_schema
from .watttime_v3 import normalize_moer_to_aes_schema, aggregate_moer_hourly


def demo_raw_data(raw_dir: str | Path) -> None:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    hours = pd.date_range("2026-01-01 00:00", "2026-01-08 00:00", freq="h", inclusive="left")
    h = np.arange(len(hours))
    moer = 260 + 110*np.sin(2*np.pi*(h-16)/24) - 80*np.exp(-((h % 24)-13)**2/10)
    moer = np.clip(moer, 70, 580)
    price_mwh = 85 + 35*np.sin(2*np.pi*(h-17)/24) + 25*((h % 24 >= 18) & (h % 24 <= 21))
    price_mwh = np.clip(price_mwh, 10, None)
    pd.DataFrame({
        "point_time": hours.tz_localize("America/Los_Angeles").tz_convert("UTC"),
        "value": moer / (453.59237/1000.0),  # write lb/MWh
    }).to_csv(raw_dir / "watttime_moer.csv", index=False)
    pd.DataFrame({
        "INTERVALSTARTTIME_GMT": hours.tz_localize("America/Los_Angeles").tz_convert("UTC"),
        "LMP_PRC": price_mwh,
    }).to_csv(raw_dir / "caiso_lmp.csv", index=False)


def populate_caiso_inputs(raw_dir: str | Path, out_dir: str | Path, demo: bool = False) -> None:
    raw_dir = Path(raw_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if demo:
        demo_raw_data(raw_dir)

    lmp_path = raw_dir / "caiso_lmp.csv"
    moer_path = raw_dir / "watttime_moer.csv"
    if not lmp_path.exists():
        raise FileNotFoundError(f"Missing {lmp_path}; run downloader or use --demo")
    if not moer_path.exists():
        raise FileNotFoundError(f"Missing {moer_path}; run downloader or use --demo")

    lmp_raw = pd.read_csv(lmp_path)
    prices = normalize_lmp_to_aes_schema(lmp_raw, region_id="CAISO", source=str(lmp_path.name))
    moer_raw = pd.read_csv(moer_path)
    if {"region_id", "timestamp_local", "moer_g_co2e_kwh"}.issubset(moer_raw.columns):
        moer = moer_raw[["region_id", "timestamp_local", "moer_g_co2e_kwh", "source"]].copy()
        moer["timestamp_local"] = pd.to_datetime(moer["timestamp_local"])
    else:
        moer = normalize_moer_to_aes_schema(moer_raw, region_id="CAISO", source=str(moer_path.name))
    moer = aggregate_moer_hourly(moer)

    # Use the common 168-hour interval.
    common = sorted(set(pd.to_datetime(prices["timestamp_local"])) & set(pd.to_datetime(moer["timestamp_local"])))
    common = common[:168]
    prices = prices[prices["timestamp_local"].isin(common)].copy()
    moer = moer[moer["timestamp_local"].isin(common)].copy()

    pd.DataFrame([{
        "region_id": "CAISO",
        "grid_operator": "California ISO / WattTime CAISO_NORTH",
        "timezone": "America/Los_Angeles",
        "source_category": "source-derived",
    }]).to_csv(out_dir / "regions.csv", index=False)

    moer.to_csv(out_dir / "grid_marginal_emissions.csv", index=False)
    prices.to_csv(out_dir / "electricity_prices.csv", index=False)

    pd.DataFrame([{
        "region_id": "CAISO",
        "average_g_co2e_kwh": 250.0,
        "source": "eGRID CAMX scenario factor",
    }]).to_csv(out_dir / "grid_average_emissions.csv", index=False)

    pd.DataFrame([
        {"fuel_id": "E85_CELLULOSIC", "pathway_name": "Cellulosic E85", "total_g_co2e_km": 95.0, "source_category": "scenario", "source": "GREET-style scenario value"},
        {"fuel_id": "E85_CORN", "pathway_name": "Corn E85", "total_g_co2e_km": 224.0, "source_category": "scenario", "source": "scenario value"},
        {"fuel_id": "E10", "pathway_name": "E10 gasoline blend", "total_g_co2e_km": 265.0, "source_category": "scenario", "source": "scenario value"},
    ]).to_csv(out_dir / "liquid_fuel_lca.csv", index=False)

    fuel_prices = []
    for ts in common:
        fuel_prices.append({"fuel_id": "E85_CELLULOSIC", "timestamp_local": ts, "price_usd_km": 0.055, "source": "scenario repeated hourly"})
        fuel_prices.append({"fuel_id": "E10", "timestamp_local": ts, "price_usd_km": 0.070, "source": "scenario repeated hourly"})
    pd.DataFrame(fuel_prices).to_csv(out_dir / "fuel_prices.csv", index=False)

    pd.DataFrame([{
        "vehicle_id": "PHEV_REP",
        "powertrain": "PHEV",
        "battery_kwh": 14.0,
        "electric_kwh_km": 0.29,
        "min_departure_soc": 0.20,
        "vehicle_prod_g_co2e_km": 0.0,
        "source_category": "scenario",
    }]).to_csv(out_dir / "vehicle_specs.csv", index=False)

    pd.DataFrame([{
        "scenario_id": "CAISO_PHEV_BALANCED",
        "region_id": "CAISO",
        "vehicle_id": "PHEV_REP",
        "w_carbon": 0.7,
        "w_cost": 0.3,
        "static_baseline_g_co2e_km": 145.0,
    }]).to_csv(out_dir / "scenarios.csv", index=False)

    events = []
    for i, ts in enumerate(common):
        # Only some hours have service demand. This keeps the profile realistic while retaining 168 event rows.
        distance = 8.0 if (7 <= ts.hour <= 9 or 16 <= ts.hour <= 19) else (2.0 if ts.hour in [12, 13, 14] else 0.5)
        events.append({
            "event_id": f"E{i+1:04d}",
            "scenario_id": "CAISO_PHEV_BALANCED",
            "timestamp_local": ts,
            "distance_km": distance,
            "initial_soc": 0.55,
        })
    pd.DataFrame(events).to_csv(out_dir / "service_events.csv", index=False)

    pd.DataFrame([
        {"parameter": "bev_energy_use_kwh_km", "base_value": 0.18, "distribution": "normal", "lower": 0.05, "mode": "", "upper": "", "cv": 0.10, "unit": "kWh/km", "source_category": "scenario"},
        {"parameter": "phev_electric_kwh_km", "base_value": 0.29, "distribution": "normal", "lower": 0.05, "mode": "", "upper": "", "cv": 0.10, "unit": "kWh/km", "source_category": "scenario"},
        {"parameter": "cellulosic_e85_g_km", "base_value": 95.0, "distribution": "triangular", "lower": 70.0, "mode": 95.0, "upper": 125.0, "cv": "", "unit": "g CO2e/km", "source_category": "scenario"},
        {"parameter": "caiso_grid_average_g_kwh", "base_value": 250.0, "distribution": "normal", "lower": 0.0, "mode": "", "upper": "", "cv": 0.15, "unit": "g CO2e/kWh", "source_category": "source-derived"},
        {"parameter": "battery_prod_kg_kwh", "base_value": 75.0, "distribution": "triangular", "lower": 50.0, "mode": 75.0, "upper": 100.0, "cv": "", "unit": "kg CO2e/kWh", "source_category": "scenario"},
        {"parameter": "vehicle_lifetime_km", "base_value": 240000.0, "distribution": "uniform", "lower": 200000.0, "mode": "", "upper": 280000.0, "cv": "", "unit": "km", "source_category": "scenario"},
        {"parameter": "equivalence_margin_g_km", "base_value": 25.0, "distribution": "fixed", "lower": "", "mode": "", "upper": "", "cv": "", "unit": "g CO2e/km", "source_category": "declared margin"},
    ]).to_csv(out_dir / "uncertainty_parameters.csv", index=False)
