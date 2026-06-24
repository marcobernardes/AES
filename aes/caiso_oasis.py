from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

import pandas as pd
import requests

OASIS_SINGLEZIP = "https://oasis.caiso.com/oasisapi/SingleZip"


def build_oasis_params(
    start_utc: str,
    end_utc: str,
    node: str,
    queryname: str = "PRC_INTVL_LMP",
    market_run_id: str = "DAM",
) -> dict:
    """Build a CAISO OASIS SingleZip parameter dictionary.

    CAISO OASIS expects UTC/GMT datetimes in the form yyyymmddThh:mmZ for many reports.
    The queryname and market_run_id remain configurable because CAISO changes report
    names and different studies need different LMP products.
    """
    def fmt(s: str) -> str:
        ts = pd.Timestamp(s)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.strftime("%Y%m%dT%H:%MZ")

    return {
        "queryname": queryname,
        "startdatetime": fmt(start_utc),
        "enddatetime": fmt(end_utc),
        "market_run_id": market_run_id,
        "node": node,
    }


def download_oasis_zip(params: dict, url: str = OASIS_SINGLEZIP, timeout: int = 120) -> bytes:
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.content


def _read_first_csv_from_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = z.namelist()
        csv_names = [n for n in names if n.lower().endswith(".csv")]
        xml_names = [n for n in names if n.lower().endswith(".xml")]
        if csv_names:
            with z.open(csv_names[0]) as f:
                return pd.read_csv(f)
        if xml_names:
            with z.open(xml_names[0]) as f:
                return parse_oasis_xml(f.read())
    raise ValueError("No CSV or XML found in CAISO OASIS zip response")


def parse_oasis_xml(content: bytes | str) -> pd.DataFrame:
    """Very tolerant XML parser for OASIS responses.

    CAISO report XML layouts vary. This parser flattens leaf elements under repeated
    report rows. If the response has no row-like records, it returns an empty DataFrame.
    """
    if isinstance(content, bytes):
        root = ET.fromstring(content)
    else:
        root = ET.fromstring(content.encode())
    rows = []
    for elem in root.iter():
        children = list(elem)
        if children and all(len(list(c)) == 0 for c in children):
            row = {}
            for c in children:
                tag = c.tag.split("}")[-1]
                row[tag] = c.text
            if len(row) > 2:
                rows.append(row)
    return pd.DataFrame(rows)


def read_oasis_response(path_or_bytes: str | Path | bytes) -> pd.DataFrame:
    if isinstance(path_or_bytes, bytes):
        return _read_first_csv_from_zip(path_or_bytes)
    path = Path(path_or_bytes)
    if path.suffix.lower() == ".zip":
        return _read_first_csv_from_zip(path.read_bytes())
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".xml":
        return parse_oasis_xml(path.read_bytes())
    raise ValueError(f"Unsupported OASIS response type: {path}")


def normalize_lmp_to_aes_schema(
    df: pd.DataFrame,
    region_id: str = "CAISO",
    timezone: str = "America/Los_Angeles",
    tariff_name: str = "CAISO_OASIS_LMP",
    source: str = "CAISO OASIS",
) -> pd.DataFrame:
    """Convert a CAISO OASIS LMP-like table to AES electricity_prices.csv schema.

    The function accepts several common OASIS column names and keeps only price rows.
    Price values are assumed to be USD/MWh and are converted to USD/kWh.
    """
    cols = {c.lower(): c for c in df.columns}
    # Common OASIS timestamp fields.
    ts_col = None
    for candidate in [
        "intervalstarttime_gmt", "interval_start_gmt", "startdatetime",
        "opr_dt", "timestamp", "time"
    ]:
        if candidate in cols:
            ts_col = cols[candidate]
            break
    if ts_col is None:
        raise ValueError(f"Could not identify timestamp column in OASIS table columns: {list(df.columns)}")

    price_col = None
    for candidate in ["lmp_prc", "mw", "price", "value", "lmp"]:
        if candidate in cols:
            price_col = cols[candidate]
            break
    if price_col is None:
        # Try first numeric column that is not hour/interval.
        numeric_candidates = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        numeric_candidates = [c for c in numeric_candidates if c.lower() not in {"opr_hr", "opr_interval"}]
        if not numeric_candidates:
            raise ValueError(f"Could not identify LMP price column in OASIS table columns: {list(df.columns)}")
        price_col = numeric_candidates[0]

    if ts_col.lower() == "opr_dt" and {"opr_hr", "opr_interval"}.issubset(set(cols.keys())):
        # OPR_HR is 1-24 in many OASIS products. Interpret as hour-ending.
        dt = pd.to_datetime(df[ts_col])
        hr = pd.to_numeric(df[cols["opr_hr"]], errors="coerce").fillna(1).astype(int) - 1
        ts = dt + pd.to_timedelta(hr, unit="h")
        if "opr_interval" in cols:
            interval = pd.to_numeric(df[cols["opr_interval"]], errors="coerce").fillna(1).astype(int) - 1
            ts = ts + pd.to_timedelta(interval * 5, unit="min")
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = pd.to_datetime(df[ts_col], utc=True, errors="raise")

    local = ts.dt.tz_convert(timezone).dt.tz_localize(None)
    price = pd.to_numeric(df[price_col], errors="coerce") / 1000.0
    out = pd.DataFrame({
        "region_id": region_id,
        "timestamp_local": local,
        "price_usd_kwh": price,
        "tariff_name": tariff_name,
        "source": source,
    }).dropna(subset=["timestamp_local", "price_usd_kwh"])
    out = out.sort_values("timestamp_local").drop_duplicates(["region_id", "timestamp_local"], keep="last")
    return out
