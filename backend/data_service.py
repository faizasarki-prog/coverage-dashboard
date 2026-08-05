import sys
import time
import urllib.request
from datetime import datetime, timedelta
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
from . import settings  # noqa: E402

DATA_PATH: Path = _REPO_ROOT / "Coverage data.xlsx"
COMMUNITY_MAP_PATH: Path = _REPO_ROOT / "dat.csv"
CACHE_DIR: Path = _REPO_ROOT / "data" / "cache"

cov: pd.DataFrame | None = None
child_info: pd.DataFrame | None = None
child_eligible: pd.DataFrame | None = None
community_map: dict[str, dict[str, Any]] = {}
data_loaded_at: str | None = None
data_source: str = "unknown"
current_project_id: int | None = None
_last_fetched_at: datetime | None = None

# per-project loaded data, keyed by project id
_project_cache: dict[int, dict] = {}


def _project_row(project_id: int | None = None) -> dict | None:
    """Resolve a project row. Defaults to the active project (is_default, else oldest)."""
    from .database import Project, SessionLocal

    with SessionLocal() as db:
        p = None
        if project_id:
            p = db.query(Project).filter(Project.id == project_id).first()
        else:
            p = db.query(Project).filter(Project.is_default == True).first()  # noqa: E712
            if not p:
                p = db.query(Project).order_by(Project.id.asc()).first()
        if not p:
            return None
        return {
            "id": p.id,
            "name": p.name,
            "kobo_api_url": p.kobo_api_url,
            "kobo_api_token": p.kobo_api_token,
            "planning_file_path": p.planning_file_path,
        }


def _fetch_kobo_xlsx(url: str, token: str | None, dest: Path) -> bool:
    """Download a Kobo export to `dest` with retries. Returns True on success."""
    global _last_fetched_at
    if not url:
        return False
    last_err: Exception | None = None
    for attempt in range(3):
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Token {token}")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                content = resp.read()
            if len(content) < 1024:
                raise RuntimeError("response too small (export still processing?)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            _last_fetched_at = datetime.now()
            return True
        except Exception as e:
            last_err = e
            print(f"[kobo] fetch attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    print(f"[kobo] fetch failed after retries: {last_err}")
    return False


def _empty_cache(source: str) -> dict:
    """A per-project cache entry with no data (Kobo unavailable / unconfigured)."""
    return {
        "loaded": True,
        "cov": pd.DataFrame(),
        "child_info": pd.DataFrame(),
        "child_eligible": pd.DataFrame(),
        "source": source,
        "loaded_at": None,
    }


def _apply_cache(cache: dict) -> None:
    global cov, child_info, child_eligible, data_loaded_at, data_source
    cov = cache.get("cov")
    child_info = cache.get("child_info")
    child_eligible = cache.get("child_eligible")
    data_source = cache.get("source", "unknown")
    data_loaded_at = cache.get("loaded_at")


def _load_from_file(dest: Path, source: str) -> dict:
    cov_, child_info_, child_eligible_ = load_all_data(str(dest))
    return {
        "loaded": True,
        "cov": cov_,
        "child_info": child_info_,
        "child_eligible": child_eligible_,
        "source": source,
        "loaded_at": datetime.now().strftime("%d %b %Y, %H:%M"),
    }


def _update_sync_stats(pid: int, cache: dict) -> None:
    try:
        from .database import Project, SessionLocal

        with SessionLocal() as db:
            p = db.query(Project).filter(Project.id == pid).first()
            if p:
                p.last_synced_at = datetime.now()
                p.last_sync_rows = int(len(cache["cov"])) if cache["cov"] is not None else 0
                db.commit()
    except Exception as e:
        print(f"[data] could not update sync stats: {e}")


def load_data(force_refresh: bool = False, project_id: int | None = None) -> str | None:
    """Load data for a project (default: the active project).

    The module globals ALWAYS switch to that project's dataset:
    - Kobo is fetched when `force_refresh` is set or the project has no cached
      export yet.
    - Otherwise the project's cached export is loaded (fast, for toggling).
    - If a fetch fails, the project's last cached export is used instead.

    Returns a warning string when Kobo failed and cached/empty data was used.
    """
    global community_map, current_project_id
    proj = _project_row(project_id)
    if not proj:
        raise RuntimeError("No projects configured. Create a project in the Admin panel first.")
    pid = proj["id"]
    current_project_id = pid
    cache = _project_cache.setdefault(pid, {})
    if force_refresh:
        cache = {}
        _project_cache[pid] = {}

    warning: str | None = None
    if not cache.get("loaded"):
        url = proj["kobo_api_url"] or settings.KOBO_DATA_URL
        token = proj["kobo_api_token"] or settings.KOBO_API_TOKEN
        dest = CACHE_DIR / f"p{pid}.xlsx"

        if not url:
            cache = _empty_cache("unconfigured")
            print(f"[data] project {pid} ({proj['name']}) has no Kobo URL configured; data not loaded")
        else:
            tried_fetch = force_refresh or not dest.exists()
            fetched = _fetch_kobo_xlsx(url, token, dest) if tried_fetch else False
            if fetched:
                cache = _load_from_file(dest, "kobo_api")
                _update_sync_stats(pid, cache)
            elif dest.exists():
                try:
                    cache = _load_from_file(dest, "kobo_cache")
                except Exception as e:
                    print(f"[data] could not read cached export {dest}: {e}")
                    cache = _empty_cache("error")
                    warning = f"Could not read this project's data file: {e}"
                else:
                    if tried_fetch:
                        warning = "Kobo API fetch failed; showing last cached data for this project."
            else:
                cache = _empty_cache("error")
                warning = "Kobo API fetch failed and no cached data exists for this project."
        _project_cache[pid] = cache
        _apply_cache(cache)
    else:
        _apply_cache(cache)

    _load_community_map(proj)
    return warning


def _load_community_map_from(path: Path) -> dict[str, dict[str, Any]]:
    """Parse a planning/dat file (CSV or Excel) into a community map keyed by the
    settlement code (ID) → {name, sample_count, lga, ward}. The Kobo export stores
    the community *ID* (e.g. "70311") in the form; the name is derived from this
    uploaded file so it survives form edits."""
    cm: dict[str, dict[str, Any]] = {}
    if not path or not path.exists():
        return cm
    try:
        table: pd.DataFrame | None = None
        try:
            table = pd.read_csv(path, dtype=str)
        except Exception:
            table = pd.read_excel(path, dtype=str)
        if table is None or table.empty:
            return cm
    except Exception as e:
        print(f"[data] could not parse community map {path}: {e}")
        return cm
    for _, row in table.iterrows():
        code = str(row.get("settlement_Name", "")).strip()
        if not code:
            continue
        cm[code] = {
            "name": str(row.get("settlement_Label", code)).strip(),
            "sample_count": int(float(row.get("sample_count", 0) or 0)),
            "lga": str(row.get("lga_Label", "")).strip(),
            "ward": str(row.get("ward_Label", "")).strip(),
        }
    return cm


def _load_community_map(proj: dict | None = None) -> None:
    """Load the community map for a project: its uploaded planning file when one
    exists, otherwise the repo-level dat.csv (the default/Sokoto map)."""
    global community_map
    plan_path = (proj or {}).get("planning_file_path") or ""
    if plan_path:
        cm = _load_community_map_from(Path(plan_path))
        if cm:
            community_map = cm
            return
    community_map = _load_community_map_from(COMMUNITY_MAP_PATH)


def _norm_lgas(lgas: list[str] | None) -> set[str]:
    if not lgas:
        return set()
    return {str(x).strip().upper() for x in lgas if str(x).strip()}


def scope_cov(df: pd.DataFrame, allowed_lgas: list[str] | None = None) -> pd.DataFrame:
    """Restrict a coverage (cov) DataFrame to the allowed LGAs."""
    if df is None or not allowed_lgas:
        return df
    norm = _norm_lgas(allowed_lgas)
    if COL_LGA not in df.columns:
        return df.iloc[0:0].copy()
    return df[df[COL_LGA].astype(str).str.strip().str.upper().isin(norm)]


def _scope_child_df(df: pd.DataFrame | None, allowed_lgas: list[str] | None) -> pd.DataFrame | None:
    """Restrict a child sheet to households in the allowed LGAs via its submission uuid."""
    if df is None or not allowed_lgas:
        return df
    uuid_col = next((c for c in ("_submission__uuid", "_uuid", "_submission__uuid") if c in df.columns), None)
    if uuid_col is None:
        return df
    hh_codes = filter_cov(allowed_lgas=allowed_lgas)[COL_UUID].astype(str).str.strip().unique() if COL_UUID in cov.columns else []
    if len(hh_codes) == 0:
        return df.iloc[0:0].copy()
    return df[df[uuid_col].astype(str).str.strip().isin(hh_codes)]


def filter_cov(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    allowed_lgas: list[str] | None = None,
) -> pd.DataFrame:
    df = cov.copy()
    if allowed_lgas:
        df = scope_cov(df, allowed_lgas)
    if lga and COL_LGA in df.columns:
        df = df[df[COL_LGA].astype(str).str.strip() == lga.strip()]
    if ward and COL_WARD in df.columns:
        df = df[df[COL_WARD].astype(str).str.strip() == ward.strip()]
    if community and COL_COMMUNITY in df.columns:
        df = df[df[COL_COMMUNITY].astype(str).str.strip() == community.strip()]
    if ra and COL_RA in df.columns:
        df = df[df[COL_RA].astype(str).str.strip() == ra.strip()]
    return df


def child_info_scoped(allowed_lgas: list[str] | None = None) -> pd.DataFrame:
    return _scope_child_df(child_info, allowed_lgas)


def child_eligible_scoped(allowed_lgas: list[str] | None = None) -> pd.DataFrame:
    return _scope_child_df(child_eligible, allowed_lgas)


def filter_child_eligible(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    allowed_lgas: list[str] | None = None,
) -> pd.DataFrame:
    filtered = filter_cov(lga, ward, community, allowed_lgas=allowed_lgas)
    if COL_UUID not in filtered.columns or "_uuid" not in child_eligible.columns:
        return child_eligible
    hh_codes = filtered[COL_UUID].astype(str).str.strip().unique()
    if len(hh_codes) == 0:
        if allowed_lgas or any([lga, ward, community]):
            return child_eligible.iloc[0:0].copy()
        return child_eligible
    return child_eligible[child_eligible["_uuid"].astype(str).str.strip().isin(hh_codes)]
