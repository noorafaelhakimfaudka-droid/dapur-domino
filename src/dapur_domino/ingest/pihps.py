"""PIHPS Nasional (Bank Indonesia) data fetcher and schema parser."""

from __future__ import annotations

import json
import ssl
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from dapur_domino.ingest.manifest import record_raw_artifact, write_bytes_immutable

BASE_URL = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga"
USER_AGENT = "dapur-domino-research/0.1 (non-commercial academic portfolio)"
MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MiB safety cap for 8 GB RAM budget
LICENSE_NOTE = (
    "PIHPS Nasional - Bank Indonesia (Hak Cipta © PIHPS Nasional; "
    "ketentuan penggunaan rinci belum dibaca terpisah)."
)

# Verified 10 commodity categories from GetRefCommodityAndCategory (2026-11-18).
PIHPS_CATEGORIES: dict[str, str] = {
    "cat_1": "Beras",
    "cat_2": "Daging Ayam",
    "cat_3": "Daging Sapi",
    "cat_4": "Telur Ayam",
    "cat_5": "Bawang Merah",
    "cat_6": "Bawang Putih",
    "cat_7": "Cabai Merah",
    "cat_8": "Cabai Rawit",
    "cat_9": "Minyak Goreng",
    "cat_10": "Gula Pasir",
}

METADATA_KEYS = {"no", "name", "level"}


class _TLS12Adapter(HTTPAdapter):
    """HTTPAdapter capping TLS at 1.2 for BI IIS compatibility while keeping full cert checks."""

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any,
    ) -> None:
        ctx = ssl.create_default_context()
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        pool_kwargs["ssl_context"] = ctx
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def _http_get_bytes(
    url: str,
    params: dict[str, str] | None = None,
    *,
    timeout_sec: float = 30.0,
) -> bytes:
    """Perform a bounded GET request with explicit User-Agent and JSON validation."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with requests.Session() as session:
        session.mount("https://www.bi.go.id", _TLS12Adapter())
        resp = session.get(url, params=params, headers=headers, timeout=timeout_sec)
    resp.raise_for_status()
    content = resp.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Response from {url} exceeded {MAX_RESPONSE_BYTES} bytes")
    # Validate JSON structure before accepting raw payload.
    parsed = json.loads(content.decode("utf-8"))
    if not isinstance(parsed, dict) or "data" not in parsed:
        raise ValueError(f"Unexpected PIHPS JSON payload from {url}: missing 'data' key")
    return content


def parse_pihps_price(raw_val: Any) -> float | None:
    """Parse a PIHPS price string (e.g. '58,450' or '-') into a float IDR/kg or None."""
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
        val = float(raw_val)
        if val < 0:
            raise ValueError(f"Negative price not allowed: {val}")
        return val
    text = str(raw_val).strip()
    if text in {"", "-", "N/A", "null"}:
        return None
    cleaned = text.replace(",", "")
    val = float(cleaned)
    if val < 0:
        raise ValueError(f"Negative price not allowed: {raw_val}")
    return val


def parse_pihps_date(key: str) -> date:
    """Parse a PIHPS date column key in DD/MM/YYYY format."""
    return datetime.strptime(key.strip(), "%d/%m/%Y").date()


def parse_pihps_grid_records(
    payload: dict[str, Any],
    *,
    mode: str,
    comcat_id: str | None = None,
    province_id: str | None = None,
    price_type_id: int = 1,
) -> list[dict[str, Any]]:
    """Convert a PIHPS GetGridDataDaerah or GetGridDataKomoditas payload into long records.

    Args:
        payload: Parsed JSON dict containing 'data' list.
        mode: Either 'daerah' (rows are commodities) or 'komoditas' (rows are regions).
        comcat_id: Optional category/commodity ID for 'komoditas' mode.
        province_id: Optional province ID for 'daerah' mode.
        price_type_id: PIHPS price type ID (1=Pasar Tradisional, etc.).

    Returns:
        List of normalized record dicts with date, entity name, hierarchy level, and price_idr.
    """
    if mode not in {"daerah", "komoditas"}:
        raise ValueError(f"mode must be 'daerah' or 'komoditas', got {mode!r}")

    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("Payload 'data' field must be a list")

    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Expected row dict, got {type(row).__name__}")
        entity_name = str(row.get("name", "")).strip()
        level = row.get("level")
        row_no = str(row.get("no", "")).strip()

        for key, raw_val in row.items():
            if key in METADATA_KEYS:
                continue
            obs_date = parse_pihps_date(key)
            price = parse_pihps_price(raw_val)
            records.append(
                {
                    "date": obs_date.isoformat(),
                    "mode": mode,
                    "price_type_id": price_type_id,
                    "comcat_id": comcat_id,
                    "province_id": province_id,
                    "row_no": row_no,
                    "entity_name": entity_name,
                    "level": level,
                    "price_idr": price,
                }
            )
    return records


def fetch_and_save_pihps_references(
    raw_dir: Path,
    manifest_path: Path,
    *,
    sleep_sec: float = 0.5,
) -> dict[str, Path]:
    """Fetch PIHPS reference tables (provinces, commodities, price types) and record hashes."""
    endpoints = {
        "ref_provinces.json": f"{BASE_URL}/GetRefProvince",
        "ref_commodities.json": f"{BASE_URL}/GetRefCommodityAndCategory",
        "ref_price_types.json": f"{BASE_URL}/GetRefPriceType",
    }
    saved: dict[str, Path] = {}
    for filename, url in endpoints.items():
        data = _http_get_bytes(url)
        rel_path = Path("prices") / "references" / filename
        target, sha256 = write_bytes_immutable(raw_dir, rel_path, data)
        record_raw_artifact(
            manifest_path,
            raw_dir,
            rel_path,
            source_id="D1_PIHPS",
            source_url=url,
            license_note=LICENSE_NOTE,
            sha256=sha256,
            size_bytes=len(data),
            metadata={"kind": "reference"},
        )
        saved[filename] = target
        time.sleep(sleep_sec)
    return saved


def fetch_and_save_pihps_grid(
    raw_dir: Path,
    manifest_path: Path,
    *,
    mode: str,
    start_date: str,
    end_date: str,
    comcat_id: str,
    province_id: str = "",
    price_type_id: int = 1,
    show_kota: bool = True,
    rel_filename: str,
    allow_refresh: bool = False,
) -> Path:
    """Fetch a PIHPS grid endpoint slice and store it immutably with manifest tracking."""
    if mode == "daerah":
        endpoint = f"{BASE_URL}/GetGridDataDaerah"
        params = {
            "price_type_id": str(price_type_id),
            "comcat_id": comcat_id,
            "province_id": province_id,
            "regency_id": "",
            "market_id": "",
            "tipe_laporan": "1",
            "start_date": start_date,
            "end_date": end_date,
        }
    elif mode == "komoditas":
        endpoint = f"{BASE_URL}/GetGridDataKomoditas"
        params = {
            "price_type_id": str(price_type_id),
            "comcat_id": comcat_id,
            "province_id": province_id,
            "regency_id": "",
            "showKota": "true" if show_kota else "false",
            "showPasar": "false",
            "tipe_laporan": "1",
            "start_date": start_date,
            "end_date": end_date,
        }
    else:
        raise ValueError(f"Unsupported mode: {mode!r}")

    data = _http_get_bytes(endpoint, params=params)
    rel_path = Path("prices") / rel_filename
    target, sha256 = write_bytes_immutable(raw_dir, rel_path, data, allow_refresh=allow_refresh)
    record_raw_artifact(
        manifest_path,
        raw_dir,
        rel_path,
        source_id="D1_PIHPS",
        source_url=endpoint,
        license_note=LICENSE_NOTE,
        sha256=sha256,
        size_bytes=len(data),
        metadata={"mode": mode, "params": params},
        allow_refresh=allow_refresh,
    )
    return target
