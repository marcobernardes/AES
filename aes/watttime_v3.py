from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

LB_PER_MWH_TO_G_PER_KWH = 453.59237 / 1000.0


def login(username: str | None = None, password: str | None = None, base_url: str = "https://api.watttime.org") -> str:
    username = username or os.getenv("WATTTIME_USER")
    password = password or os.getenv("WATTTIME_PASSWORD")
    if not username or not password:
        raise RuntimeError("WattTime credentials not found. Set WATTTIME_USER and WATTTIME_PASSWORD.")
    # WattTime v2 used /login; v3 access may still authenticate via /login.
    # Try /login first, then /v3/login to be robust across account configurations.
    for path in ["/login", "/v3/login"]:
        url = base_url.rstrip("/") + path
        r = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=60)
        if r.ok:
            data = r.json()
            token = data.get("token") or data.get("access_token")
            if token:
                return token
    raise RuntimeError(f"Could not authenticate to WattTime. Last response: {r.status_code} {r.text[:200]}")


def fetch_historical_moer(
    region: str,
    start: str,
    end: str,
    token: str,
    base_url: str = "https://api.watttime.org",
    signal_type: str = "co2_moer",
    model: str | None = None,
) -> pd.DataFrame:
    """Fetch historical MOER records from WattTime v3-style endpoint.

    The exact access entitlement and response shape depend on the WattTime account.
    This function keeps parsing flexible and normalizes the result afterwards.
    """
    params = {
        "region": region,
        "start": start,
        "end": end,
        "signal_type": signal_type,
    }
    if model:
        params["model"] = model
    headers = {"Authorization": f"Bearer {token}"}
    url = base_url.rstrip("/") + "/v3/historical"
    r = requests.get(url, params=params, headers=headers, timeout=120)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        records = data.get("data") or data.get("results") or data.get("values") or []
    elif isinstance(data, list):
        records = data
    else:
        records = []
    return pd.DataFrame(records)


def normalize_moer_to_aes_schema(
    df: pd.DataFrame,
    region_id: str = "CAISO",
    timezone: str = "America/Los_Angeles",
    source: str = "WattTime v3 historical MOER",
) -> pd.DataFrame:
    """Convert WattTime-like MOER table to AES grid_marginal_emissions.csv schema."""
    if df.empty:
        raise ValueError("WattTime MOER table is empty")
    cols = {c.lower(): c for c in df.columns}
    ts_col = None
    for candidate in ["point_time", "timestamp", "datetime", "time", "created_at"]:
        if candidate in cols:
            ts_col = cols[candidate]
            break
    if ts_col is None:
        raise ValueError(f"Could not identify WattTime timestamp column: {list(df.columns)}")

    val_col = None
    for candidate in ["value", "moer", "marginal_co2_lbs_mwh", "lb_mwh", "lbs_mwh"]:
        if candidate in cols:
            val_col = cols[candidate]
            break
    if val_col is None:
        numeric_candidates = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if not numeric_candidates:
            raise ValueError(f"Could not identify MOER value column: {list(df.columns)}")
        val_col = numeric_candidates[0]

    ts = pd.to_datetime(df[ts_col], utc=True, errors="raise")
    local = ts.dt.tz_convert(timezone).dt.tz_localize(None)
    moer = pd.to_numeric(df[val_col], errors="coerce") * LB_PER_MWH_TO_G_PER_KWH
    out = pd.DataFrame({
        "region_id": region_id,
        "timestamp_local": local,
        "moer_g_co2e_kwh": moer,
        "source": source,
    }).dropna(subset=["timestamp_local", "moer_g_co2e_kwh"])
    return out.sort_values("timestamp_local")


def aggregate_moer_hourly(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["timestamp_local"] = pd.to_datetime(d["timestamp_local"]).dt.floor("h")
    out = (
        d.groupby(["region_id", "timestamp_local"], as_index=False)
        .agg(moer_g_co2e_kwh=("moer_g_co2e_kwh", "mean"), source=("source", "first"))
    )
    return out.sort_values("timestamp_local")
