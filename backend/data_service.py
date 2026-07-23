import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data_processor import (  # noqa: E402
    COL_COMMUNITY,
    COL_LGA,
    COL_RA,
    COL_UUID,
    COL_WARD,
    load_all_data,
)

DATA_PATH: Path = _REPO_ROOT / "Coverage data.xlsx"
COMMUNITY_MAP_PATH: Path = _REPO_ROOT / "dat.csv"

cov: pd.DataFrame | None = None
child_info: pd.DataFrame | None = None
child_eligible: pd.DataFrame | None = None
community_map: dict[str, dict[str, Any]] = {}
data_loaded_at: str | None = None
_loaded: bool = False


def load_data() -> None:
    global cov, child_info, child_eligible, community_map, data_loaded_at, _loaded
    if not _loaded:
        cov, child_info, child_eligible = load_all_data()
        _loaded = True
        data_loaded_at = datetime.now().strftime("%d %b %Y, %H:%M")
    if not community_map and COMMUNITY_MAP_PATH.exists():
        try:
            cmap = pd.read_csv(COMMUNITY_MAP_PATH, dtype=str)
            for _, row in cmap.iterrows():
                code = str(row.get("settlement_Name", "")).strip()
                if code:
                    community_map[code] = {
                        "name": str(row.get("settlement_Label", code)).strip(),
                        "sample_count": int(float(row.get("sample_count", 0) or 0)),
                        "lga": str(row.get("lga_Label", "")).strip(),
                        "ward": str(row.get("ward_Label", "")).strip(),
                    }
        except Exception:
            pass


def filter_cov(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
) -> pd.DataFrame:
    df = cov.copy()
    if lga and COL_LGA in df.columns:
        df = df[df[COL_LGA].astype(str).str.strip() == lga.strip()]
    if ward and COL_WARD in df.columns:
        df = df[df[COL_WARD].astype(str).str.strip() == ward.strip()]
    if community and COL_COMMUNITY in df.columns:
        df = df[df[COL_COMMUNITY].astype(str).str.strip() == community.strip()]
    if ra and COL_RA in df.columns:
        df = df[df[COL_RA].astype(str).str.strip() == ra.strip()]
    return df


def filter_child_eligible(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
) -> pd.DataFrame:
    if any([lga, ward, community]):
        filtered = filter_cov(lga, ward, community)
        hh_codes = filtered[COL_UUID].unique() if COL_UUID in filtered.columns else []
        if len(hh_codes) > 0 and "_uuid" in child_eligible.columns:
            return child_eligible[child_eligible["_uuid"].isin(hh_codes)]
    return child_eligible
