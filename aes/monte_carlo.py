from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def _draw(row, rng, n):
    dist = str(row["distribution"]).lower()
    base = float(row["base_value"])
    lower = row.get("lower", np.nan)
    upper = row.get("upper", np.nan)
    mode = row.get("mode", np.nan)
    cv = row.get("cv", np.nan)
    lower = np.nan if pd.isna(lower) or lower == "" else float(lower)
    upper = np.nan if pd.isna(upper) or upper == "" else float(upper)
    mode = np.nan if pd.isna(mode) or mode == "" else float(mode)
    cv = np.nan if pd.isna(cv) or cv == "" else float(cv)

    if dist == "fixed":
        return np.full(n, base)
    if dist == "normal":
        sd = abs(base * cv)
        x = rng.normal(base, sd, size=n)
        if not np.isnan(lower):
            x = np.maximum(x, lower)
        if not np.isnan(upper):
            x = np.minimum(x, upper)
        return x
    if dist == "uniform":
        return rng.uniform(lower, upper, size=n)
    if dist == "triangular":
        return rng.triangular(lower, mode if not np.isnan(mode) else base, upper, size=n)
    raise ValueError(f"Unsupported distribution: {dist}")


def run_monte_carlo(input_dir: str | Path, out_dir: str | Path, seed: int = 20260108, n: int = 10000) -> tuple[pd.DataFrame, pd.DataFrame]:
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    params = pd.read_csv(input_dir / "uncertainty_parameters.csv")
    rng = np.random.default_rng(seed)
    draws = {row["parameter"]: _draw(row, rng, n) for _, row in params.iterrows()}

    # Practical-equivalence example: BEV CAISO total vs cellulosic E85.
    bev_e = draws.get("bev_energy_use_kwh_km")
    grid = draws.get("caiso_grid_average_g_kwh")
    batt = draws.get("battery_prod_kg_kwh")
    life = draws.get("vehicle_lifetime_km")
    e85 = draws.get("cellulosic_e85_g_km")
    if any(x is None for x in [bev_e, grid, batt, life, e85]):
        raise ValueError("Required Monte Carlo parameters are missing")
    bev_total = bev_e * grid + (75.0 * batt * 1000.0 / life)
    diff = bev_total - e85
    margins = [10.0, 25.0, 40.0]
    summary_rows = [{
        "metric": "BEV_CAISO_g_co2e_km",
        "mean": float(np.mean(bev_total)),
        "p05": float(np.quantile(bev_total, 0.05)),
        "p50": float(np.quantile(bev_total, 0.50)),
        "p95": float(np.quantile(bev_total, 0.95)),
        "seed": seed,
        "draws": n,
    }, {
        "metric": "E85_cellulosic_g_co2e_km",
        "mean": float(np.mean(e85)),
        "p05": float(np.quantile(e85, 0.05)),
        "p50": float(np.quantile(e85, 0.50)),
        "p95": float(np.quantile(e85, 0.95)),
        "seed": seed,
        "draws": n,
    }, {
        "metric": "BEV_minus_E85_g_co2e_km",
        "mean": float(np.mean(diff)),
        "p05": float(np.quantile(diff, 0.05)),
        "p50": float(np.quantile(diff, 0.50)),
        "p95": float(np.quantile(diff, 0.95)),
        "seed": seed,
        "draws": n,
    }]
    for m in margins:
        summary_rows.append({
            "metric": f"Pr_abs_diff_lt_{m:g}_g_km",
            "mean": float(np.mean(np.abs(diff) < m)),
            "p05": np.nan, "p50": np.nan, "p95": np.nan,
            "seed": seed, "draws": n,
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_dir / "monte_carlo_summary.csv", index=False)

    conv_rows = []
    full_mean = np.mean(diff)
    for k in [1000, 2500, 5000, n]:
        d = diff[:k]
        conv_rows.append({
            "draws": k,
            "metric": "BEV_minus_E85_g_co2e_km",
            "mean": float(np.mean(d)),
            "std": float(np.std(d, ddof=1)),
            "p05": float(np.quantile(d, 0.05)),
            "p50": float(np.quantile(d, 0.50)),
            "p95": float(np.quantile(d, 0.95)),
            "delta_mean_vs_full": float(np.mean(d) - full_mean),
        })
    conv = pd.DataFrame(conv_rows)
    conv.to_csv(out_dir / "mc_convergence.csv", index=False)
    return summary, conv
