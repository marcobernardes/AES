from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np


def _norm(vals):
    vals = np.array(vals, dtype=float)
    den = vals.max() - vals.min()
    if den <= 1e-12:
        return np.zeros_like(vals)
    return (vals - vals.min()) / (den + 1e-12)


def run_dispatch(input_dir: str | Path, out_dir: str | Path) -> pd.DataFrame:
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = pd.read_csv(input_dir / "scenarios.csv")
    vehicles = pd.read_csv(input_dir / "vehicle_specs.csv")
    events = pd.read_csv(input_dir / "service_events.csv", parse_dates=["timestamp_local"])
    moer = pd.read_csv(input_dir / "grid_marginal_emissions.csv", parse_dates=["timestamp_local"])
    prices = pd.read_csv(input_dir / "electricity_prices.csv", parse_dates=["timestamp_local"])
    fuels = pd.read_csv(input_dir / "liquid_fuel_lca.csv")
    fuel_prices = pd.read_csv(input_dir / "fuel_prices.csv", parse_dates=["timestamp_local"])

    rows = []
    for _, ev in events.iterrows():
        sc = scenarios.loc[scenarios["scenario_id"] == ev["scenario_id"]].iloc[0]
        veh = vehicles.loc[vehicles["vehicle_id"] == sc["vehicle_id"]].iloc[0]
        region = sc["region_id"]
        ts = ev["timestamp_local"]

        em = moer[(moer["region_id"] == region) & (moer["timestamp_local"] == ts)]
        pr = prices[(prices["region_id"] == region) & (prices["timestamp_local"] == ts)]
        if em.empty or pr.empty:
            rows.append({
                "event_id": ev["event_id"], "timestamp_local": ts, "selected_action": "NO_DATA",
                "reason": "missing emissions or price record", "emissions_g_co2e_km": np.nan,
                "cost_usd_km": np.nan, "distance_km": ev["distance_km"],
            })
            continue
        moer_g = float(em.iloc[0]["moer_g_co2e_kwh"])
        price_kwh = float(pr.iloc[0]["price_usd_kwh"])

        actions = []
        # Electric action feasible if initial SOC exceeds min. This proof model does not solve a full charging queue.
        if ev["initial_soc"] >= veh["min_departure_soc"]:
            c = moer_g * veh["electric_kwh_km"] + veh.get("vehicle_prod_g_co2e_km", 0.0)
            k = price_kwh * veh["electric_kwh_km"]
            actions.append({"action": "ELECTRIC", "carbon": c, "cost": k, "reason": "feasible electric operation"})

        e85 = fuels.loc[fuels["fuel_id"] == "E85_CELLULOSIC"].iloc[0]
        fp = fuel_prices[(fuel_prices["fuel_id"] == "E85_CELLULOSIC") & (fuel_prices["timestamp_local"] == ts)]
        fuel_cost = float(fp.iloc[0]["price_usd_km"]) if not fp.empty else 0.055
        actions.append({"action": "E85_CELLULOSIC", "carbon": float(e85["total_g_co2e_km"]), "cost": fuel_cost, "reason": "compatible liquid fuel"})

        carb_norm = _norm([a["carbon"] for a in actions])
        cost_norm = _norm([a["cost"] for a in actions])
        scores = sc["w_carbon"] * carb_norm + sc["w_cost"] * cost_norm
        j = int(np.argmin(scores))
        chosen = actions[j]

        rows.append({
            "event_id": ev["event_id"],
            "timestamp_local": ts,
            "scenario_id": ev["scenario_id"],
            "region_id": region,
            "selected_action": chosen["action"],
            "reason": chosen["reason"],
            "emissions_g_co2e_km": chosen["carbon"],
            "cost_usd_km": chosen["cost"],
            "distance_km": ev["distance_km"],
            "moer_g_co2e_kwh": moer_g,
            "price_usd_kwh": price_kwh,
            "objective_score": scores[j],
            "rejected_actions": ";".join(a["action"] for i, a in enumerate(actions) if i != j),
        })

    out = pd.DataFrame(rows)
    out.to_csv(out_dir / "event_dispatch.csv", index=False)

    good = out.dropna(subset=["emissions_g_co2e_km"])
    mean_weighted = (good["emissions_g_co2e_km"] * good["distance_km"]).sum() / good["distance_km"].sum()
    static = float(scenarios.iloc[0]["static_baseline_g_co2e_km"])
    reduction = 100.0 * (static - mean_weighted) / static
    summary = pd.DataFrame([{
        "scenario_id": scenarios.iloc[0]["scenario_id"],
        "events": len(out),
        "mean_aes_g_co2e_km_distance_weighted": mean_weighted,
        "static_baseline_g_co2e_km": static,
        "reduction_percent": reduction,
        "electric_fraction_events": float((good["selected_action"] == "ELECTRIC").mean()),
    }])
    summary.to_csv(out_dir / "dispatch_summary.csv", index=False)
    return out
