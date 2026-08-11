from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import data_service
from ..auth import get_current_user
from ..data_service import filter_child_eligible, filter_cov
from ..database import User

from data_processor import (
    COL_CDD_VISIT,
    COL_CHILD_SEX,
    COL_COMMUNITY,
    COL_HH_CODE,
    COL_IS_ELIGIBLE,
    COL_LAT,
    COL_LGA,
    COL_LNG,
    COL_OFFERED_AZM,
    COL_PRECISION,
    COL_RA,
    COL_SETTLEMENT_TYPE,
    COL_SUBMISSION_TIME,
    COL_SWALLOWED_AZM,
    COL_UUID,
    WEALTH_COLS,
    COL_VACC_CARD,
    COL_WARD,
)

router = APIRouter()


def _allowed_lgas(user: User) -> list[str] | None:
    """LGAs a validator may see. None means unrestricted (admins / super admins)."""
    if user.role and user.role.name == "validator":
        lgas = [ul.lga_name for ul in user.lgas]
        return lgas or None
    return None


def _scoped_community_map(allowed_lgas: list[str] | None) -> dict[str, dict[str, Any]]:
    cm = data_service.community_map
    if not allowed_lgas or not cm:
        return cm
    norm = {str(x).strip().upper() for x in allowed_lgas if str(x).strip()}
    return {k: v for k, v in cm.items() if (v.get("lga") or "").strip().upper() in norm}


def _community_name(community_map: dict[str, dict[str, Any]], code: Any) -> str:
    """Resolve a community ID (as stored in the form) to its display name from the
    uploaded planning/dat file. Never reads the 'Confirm…' columns — those are
    wiped when a record is edited on Kobo. Falls back to the raw code."""
    if code is None:
        return ""
    code_str = str(code).strip()
    if not code_str or code_str.lower() in ("nan", "none"):
        return ""
    if not community_map:
        return code_str
    info = community_map.get(code_str)
    if info:
        return str(info.get("name") or code_str).strip() or code_str
    return code_str


@router.get("/api/kpis")
def api_kpis(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, ra, allowed_lgas=allowed)
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    child_info = data_service.child_info_scoped(allowed)
    community_map = _scoped_community_map(allowed)

    kpis: dict[str, Any] = {}
    kpis["total_households"] = int(len(df))
    kpis["lgas_reached"] = int(df[COL_LGA].nunique()) if COL_LGA in df.columns else 0
    kpis["wards_reached"] = int(df[COL_WARD].nunique()) if COL_WARD in df.columns else 0
    kpis["communities_reached"] = int(df[COL_COMMUNITY].nunique()) if COL_COMMUNITY in df.columns else 0
    kpis["active_ras"] = int(df[COL_RA].nunique()) if COL_RA in df.columns else 0

    if community_map:
        kpis["total_lgas"] = len(set(v.get("lga", "") for v in community_map.values()))
        kpis["total_wards"] = len(set(v.get("ward", "") for v in community_map.values()))
        kpis["total_communities"] = len(community_map)
        kpis["coverage_target"] = int(sum(v.get("sample_count", 0) for v in community_map.values()))
    else:
        kpis["total_lgas"] = kpis["lgas_reached"]
        kpis["total_wards"] = kpis["wards_reached"]
        kpis["total_communities"] = kpis["communities_reached"]
        kpis["coverage_target"] = kpis["total_households"]

    if COL_OFFERED_AZM in ce.columns:
        kpis["offered_azm"] = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == "yes").sum())
    else:
        kpis["offered_azm"] = 0

    if COL_SWALLOWED_AZM in ce.columns:
        kpis["swallowed_azm"] = int((ce[COL_SWALLOWED_AZM].str.strip().str.lower() == "yes").sum())
    else:
        kpis["swallowed_azm"] = 0

    if COL_IS_ELIGIBLE in child_info.columns:
        kpis["eligible_children"] = int((child_info[COL_IS_ELIGIBLE] == "1").sum())
    else:
        kpis["eligible_children"] = 0

    if COL_VACC_CARD in ce.columns:
        kpis["vacc_cards"] = int((ce[COL_VACC_CARD].str.strip().str.lower() == "yes").sum())
    else:
        kpis["vacc_cards"] = 0

    if COL_IS_ELIGIBLE in child_info.columns:
        kpis["children_under_18"] = int(len(child_info))
    else:
        kpis["children_under_18"] = 0

    if COL_OFFERED_AZM in ce.columns:
        kpis["not_offered_azm"] = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == "no").sum())
    else:
        kpis["not_offered_azm"] = 0

    total_screened = kpis["eligible_children"]
    kpis["coverage_pct"] = round((kpis["total_households"] / kpis["coverage_target"] * 100) if kpis["coverage_target"] > 0 else 0, 1)
    kpis["swallow_rate"] = round((kpis["swallowed_azm"] / kpis["offered_azm"] * 100) if kpis["offered_azm"] > 0 else 0, 1)
    kpis["last_updated"] = data_service.data_loaded_at or "Not loaded"

    return kpis


@router.get("/api/charts/daily")
def api_daily(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    df = filter_cov(lga, ward, community, ra, allowed_lgas=_allowed_lgas(user))
    if COL_SUBMISSION_TIME in df.columns:
        daily = df.copy()
        daily["date"] = pd.to_datetime(daily[COL_SUBMISSION_TIME], errors="coerce").dt.date
        daily_counts = daily.groupby("date").size().reset_index(name="count").sort_values("date")
        return [{"date": str(r["date"]), "count": int(r["count"])} for _, r in daily_counts.iterrows()]
    return []


@router.get("/api/charts/gender")
def api_gender(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=_allowed_lgas(user))
    if COL_CHILD_SEX in ce.columns:
        gender_counts = ce[COL_CHILD_SEX].str.strip().str.lower().value_counts()
        return {
            "male": int(gender_counts.get("male", 0) + gender_counts.get("m", 0)),
            "female": int(gender_counts.get("female", 0) + gender_counts.get("f", 0)),
        }
    return {"male": 0, "female": 0}


@router.get("/api/charts/funnel")
def api_funnel(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    allowed = _allowed_lgas(user)
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    child_info = data_service.child_info_scoped(allowed)
    eligible_count = 0
    if COL_IS_ELIGIBLE in child_info.columns:
        eligible_count = int((child_info[COL_IS_ELIGIBLE] == "1").sum())

    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == "yes").sum()) if COL_OFFERED_AZM in ce.columns else 0
    swallowed = int((ce[COL_SWALLOWED_AZM].str.strip().str.lower() == "yes").sum()) if COL_SWALLOWED_AZM in ce.columns else 0
    total_children = int(len(child_info))
    return {
        "stages": ["Total Children", "Eligible (1-59m)", "Offered AZM", "Swallowed AZM"],
        "counts": [total_children, eligible_count, offered, swallowed],
    }


@router.get("/api/charts/lga")
def api_lga_chart(user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    df = data_service.scope_cov(data_service.cov, _allowed_lgas(user)).copy()
    community_map = _scoped_community_map(_allowed_lgas(user))
    if COL_LGA not in df.columns:
        return []
    lga_data = df.groupby(COL_LGA).agg(households_reached=(COL_UUID, "nunique")).reset_index()
    lga_data.columns = ["lga", "reached"]
    if community_map:
        lga_planned: dict[str, int] = {}
        for info in community_map.values():
            lga_name = info["lga"]
            if lga_name:
                lga_planned[lga_name] = lga_planned.get(lga_name, 0) + info["sample_count"]
        lga_data["planned"] = lga_data["lga"].map(lambda x: lga_planned.get(str(x), lga_data["reached"].max()))
    else:
        lga_data["planned"] = lga_data["reached"].max()
    lga_data["pct"] = (lga_data["reached"] / lga_data["planned"] * 100).round(1)
    lga_data = lga_data.sort_values("reached", ascending=False)
    return lga_data.to_dict(orient="records")


@router.get("/api/ra-submissions")
def api_ra_submissions(lga: str | None = None, user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    df = filter_cov(lga, allowed_lgas=_allowed_lgas(user))
    if COL_RA not in df.columns:
        return []
    ra_data = df.groupby(COL_RA).size().reset_index(name="count").sort_values("count", ascending=False)
    ra_data.columns = ["ra", "count"]
    return ra_data.to_dict(orient="records")


@router.get("/api/cdd-visitation")
def api_cdd_visitation(lga: str | None = None, user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    df = filter_cov(lga, allowed_lgas=_allowed_lgas(user))
    if COL_CDD_VISIT in df.columns:
        vc = df[COL_CDD_VISIT].value_counts().reset_index()
        vc.columns = ["response", "count"]
    else:
        vc = pd.DataFrame({"response": [], "count": []})
    return vc.to_dict(orient="records")


@router.get("/api/ra-performance")
def api_ra_performance(lga: str | None = None, user: User = Depends(get_current_user)) -> dict[str, Any]:
    df = filter_cov(lga, allowed_lgas=_allowed_lgas(user))
    if COL_RA not in df.columns or COL_LGA not in df.columns:
        return {"lga_groups": {}, "summary": {"total_ras": 0, "met_target": 0, "met_pct": 0}}

    ra_lga = df.groupby([COL_RA, COL_LGA]).size().reset_index(name="count")
    ra_totals = ra_lga.groupby(COL_RA)["count"].sum().reset_index()

    MEET_PER_DAY = 7
    ABOVE_PER_DAY = 9

    def classify(c: int) -> str:
        if c < MEET_PER_DAY * 5:
            return "Below Target"
        elif c >= ABOVE_PER_DAY * 5:
            return "Above Target"
        return "Meet Target"

    ra_totals["status"] = ra_totals["count"].apply(classify)
    status_map = dict(zip(ra_totals[COL_RA], ra_totals["status"]))

    lga_groups: dict[str, Any] = {}
    for lga_name in sorted(df[COL_LGA].unique()):
        lga_rows = ra_lga[ra_lga[COL_LGA] == lga_name]
        ras: list[dict[str, Any]] = []
        for _, r in lga_rows.iterrows():
            ra_name = r[COL_RA]
            ras.append({
                "ra": ra_name,
                "count": int(r["count"]),
                "status": status_map.get(ra_name, "Meet Target"),
            })
        ras.sort(key=lambda x: x["count"], reverse=True)
        below = sum(1 for r in ras if r["status"] == "Below Target")
        meet = sum(1 for r in ras if r["status"] == "Meet Target")
        above = sum(1 for r in ras if r["status"] == "Above Target")
        lga_groups[lga_name] = {"total": len(ras), "below": below, "meet": meet, "above": above, "ras": ras}

    met_count = int((ra_totals["status"] != "Below Target").sum())
    total_ras = len(ra_totals)

    return {
        "lga_groups": lga_groups,
        "summary": {
            "total_ras": total_ras,
            "met_target": met_count,
            "met_pct": round(met_count / total_ras * 100, 1) if total_ras > 0 else 0,
        },
        "lga_list": sorted(lga_groups.keys()),
    }


@router.get("/api/dq-metrics")
def api_dq(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from data_processor import compute_dq_metrics

    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, allowed_lgas=allowed)
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    dq = compute_dq_metrics(df, data_service.child_info_scoped(allowed), ce)
    if COL_HH_CODE in df.columns:
        dup_hh = df[df.duplicated(subset=[COL_HH_CODE], keep=False)]
        dq["dup_household_count"] = int(dup_hh[COL_HH_CODE].nunique()) if len(dup_hh) > 0 else 0
    dq["active_ras"] = int(df[COL_RA].nunique()) if COL_RA in df.columns else 0
    return dq


@router.get("/api/errors-by-lga")
def api_errors_by_lga(user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    df = data_service.scope_cov(data_service.cov, _allowed_lgas(user)).copy()
    if COL_LGA not in df.columns:
        return []
    errors: list[dict[str, Any]] = []
    for lga_name in df[COL_LGA].unique():
        lga_df = df[df[COL_LGA] == lga_name]
        total = int(len(lga_df))
        dup_hh = 0
        if COL_HH_CODE in lga_df.columns:
            dup = lga_df[lga_df.duplicated(subset=[COL_HH_CODE], keep=False)]
            dup_hh = int(dup[COL_HH_CODE].nunique()) if len(dup) > 0 else 0
        mock_gps = 0
        if COL_PRECISION in lga_df.columns:
            prec = pd.to_numeric(lga_df[COL_PRECISION], errors="coerce")
            mock_gps = int((prec < 2).sum())
        stacked_gps = 0
        if COL_LAT in lga_df.columns and COL_LNG in lga_df.columns:
            gps = lga_df[[COL_LAT, COL_LNG]].dropna()
            stacked_gps = int(gps.duplicated(keep=False).sum())
        total_errors = dup_hh + mock_gps + stacked_gps
        errors.append({
            "lga": str(lga_name),
            "total": total,
            "dup_households": dup_hh,
            "mock_gps": mock_gps,
            "stacked_gps": stacked_gps,
            "total_errors": total_errors,
        })
    return errors


def _pick_col(df, candidates):
    if df is None:
        return None
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        actual = lower.get(cand.lower())
        if actual:
            return actual
        for c in df.columns:
            if cand.lower() in c.lower():
                return c
    return None


@router.get("/api/validators/flagged")
def api_validators_flagged(status: str = "pending", user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    from ..database import SessionLocal, ValidationDecision, ValidatorFlag
    allowed = _allowed_lgas(user)
    cov = data_service.scope_cov(data_service.cov, allowed)
    child = data_service.child_info_scoped(allowed)
    elig = data_service.child_eligible_scoped(allowed)
    if cov is None or cov.empty:
        return []
    with SessionLocal() as db:
        decisions = {d.record_uuid: d.status for d in db.query(ValidationDecision).all()}
        vflags_map: dict[str, list[str]] = {}
        for uuid_val, flag in db.query(ValidatorFlag.record_uuid, ValidatorFlag.flag).all():
            vflags_map.setdefault(uuid_val, []).append(flag)

    community_map = _scoped_community_map(allowed)

    col_head_name  = _pick_col(cov, ["Q11. Name of the Head of the household?", "Q11", "Head of the household"])
    col_head_gen   = _pick_col(cov, ["Q12. Gender of the Head of the household?", "Q12", "Gender of the Head"])
    col_edu        = _pick_col(cov, ["Q20. Highest education level completed", "Q20"])
    col_occ        = _pick_col(cov, ["Q21. Occupation", "Q21"])
    col_settle     = COL_SETTLEMENT_TYPE if COL_SETTLEMENT_TYPE in cov.columns else _pick_col(cov, ["Q5. Type of Settlement"])
    col_unique     = COL_HH_CODE if COL_HH_CODE in cov.columns else _pick_col(cov, ["unique_code"])
    col_total_elig = _pick_col(cov, ["total_eligible", "number of eligible children", "how many eligible"])
    col_start      = _pick_col(cov, ["start"])
    col_submitted  = COL_SUBMISSION_TIME if COL_SUBMISSION_TIME in cov.columns else _pick_col(cov, ["_submission_time", "submission_time"])
    wealth_cols    = [c for c in WEALTH_COLS if c in cov.columns]

    dup_codes: set = set()
    if col_unique:
        vc = cov[col_unique].value_counts(dropna=True)
        dup_codes = set(vc[vc > 1].index.astype(str).str.strip())

    rep_child_uuids: set = set()
    inelig_uuids: set = set()
    missing_vacc_uuids: set = set()
    children_by_uuid: dict[str, list[dict]] = {}
    if child is not None and not child.empty:
        col_child_label = _pick_col(child, ["child_label"])
        col_child_uuid  = _pick_col(child, ["_submission__uuid", "_uuid", "submission_uuid"])
        col_child_id    = _pick_col(child, ["child_id", "child_idd"])
        col_parent_idx  = _pick_col(child, ["_parent_index", "parent_index"])
        col_c_age       = _pick_col(child, ["Age of child", "age"])
        col_c_eligible  = COL_IS_ELIGIBLE if COL_IS_ELIGIBLE in child.columns else _pick_col(child, ["is_eligible"])
        col_c_vacc      = _pick_col(child, ["vaccination card", "Vaccination card image", "vaccination_card"])
        col_c_name      = _pick_col(child, ["Q88. Child name and age", "Q88"])
        col_c_sex       = _pick_col(child, ["Q89. Sex", "Q89"])
        # Repetitive child: the same child selected twice within the same household
        # submission (household identity = _parent_index).
        if col_child_uuid and col_child_id and col_parent_idx:
            key = child[col_parent_idx].astype(str).str.strip() + "|" + child[col_child_id].astype(str).str.strip()
            vc = key.value_counts()
            rep_child_uuids = set(child.loc[key.isin(vc[vc > 1].index), col_child_uuid].astype(str).str.strip())
        if col_c_age and col_c_eligible:
            ages = pd.to_numeric(child[col_c_age], errors="coerce")
            elig_num = pd.to_numeric(child[col_c_eligible], errors="coerce").fillna(0)
            inelig_mask = (ages > 59) & (elig_num >= 1)
            if col_child_uuid:
                inelig_uuids = set(child.loc[inelig_mask, col_child_uuid].astype(str).str.strip())
        if col_c_vacc and col_child_uuid:
            missing = child[col_c_vacc].isna() | (child[col_c_vacc].astype(str).str.strip() == "")
            missing_vacc_uuids = set(child.loc[missing, col_child_uuid].astype(str).str.strip())
    # Q88 name-age and Q89 sex live on the child_eligible sheet
    if elig is not None and not elig.empty:
        col_e_uuid    = _pick_col(elig, ["_submission__uuid", "_uuid"])
        col_e_name    = _pick_col(elig, ["Q88. Child name and age", "Q88"])
        col_e_sex     = _pick_col(elig, ["Q89. Sex", "Q89"])
        col_e_parent  = _pick_col(elig, ["_parent_index", "parent_index", "_index"])
        # Repeated child: the same Q88 child name + age entered twice within the
        # same household submission (household identity = _parent_index).
        if col_e_uuid and col_e_name:
            name_key = elig[col_e_name].astype(str).str.strip()
            if col_e_parent:
                name_key = elig[col_e_parent].astype(str).str.strip() + "|" + name_key
            vc = name_key.value_counts()
            if len(vc):
                rep_uuids = set(elig.loc[name_key.isin(vc[vc > 1].index), col_e_uuid].astype(str).str.strip())
                rep_child_uuids |= rep_uuids
        if col_e_uuid:
            for _, er in elig.iterrows():
                u = str(er.get(col_e_uuid, "")).strip()
                if not u:
                    continue
                children_by_uuid.setdefault(u, []).append({
                    "name_age": str(er.get(col_e_name, "")).strip() if col_e_name else "",
                    "sex":      str(er.get(col_e_sex,  "")).strip() if col_e_sex else "",
                })

    # Child Count Mismatch — reported eligible (from HH form) vs actual child rows
    actual_child_count_by_uuid: dict[str, int] = {}
    if child is not None and not child.empty:
        col_child_uuid2 = _pick_col(child, ["_submission__uuid", "_uuid", "submission_uuid"])
        if col_child_uuid2:
            gp = child.groupby(col_child_uuid2).size()
            actual_child_count_by_uuid = {str(k).strip(): int(v) for k, v in gp.items()}

    # Survey Date Consistency — form start vs submission
    def _parse_dt(v):
        try:
            return pd.to_datetime(v, errors="coerce", utc=True)
        except Exception:
            return None

    rows: list[dict[str, Any]] = []
    for _, r in cov.iterrows():
        flags = []
        uc = str(r.get(col_unique, "")).strip() if col_unique else ""
        uuid_val = str(r.get("_uuid", "")).strip() or str(r.get(COL_UUID, "")).strip() if COL_UUID in cov.columns else ""

        if col_unique and uc in dup_codes:
            flags.append("Duplicate HH ID")

        if col_edu and col_occ:
            edu = str(r.get(col_edu, "")).strip().lower()
            occ = str(r.get(col_occ, "")).strip().lower()
            if occ.startswith("professional") and edu and "more than secondary" not in edu:
                flags.append("Education/Occupation mismatch")

        if col_settle and wealth_cols:
            settle = str(r.get(col_settle, "")).strip().lower()
            yes_ct = sum(1 for c in wealth_cols if str(r.get(c, "")).strip().lower() == "yes")
            no_ct  = sum(1 for c in wealth_cols if str(r.get(c, "")).strip().lower() == "no")
            if settle == "urban" and no_ct == len(wealth_cols):
                flags.append("Settlement/Amenities mismatch")
            elif settle == "rural" and yes_ct == len(wealth_cols):
                flags.append("Settlement/Amenities mismatch")

        if uuid_val:
            if uuid_val in rep_child_uuids:
                flags.append("Repetitive Child")
            if uuid_val in inelig_uuids:
                flags.append("Non-eligible child")
            if uuid_val in missing_vacc_uuids:
                flags.append("Missing vacc card")

        # Child Count Mismatch: reported eligible vs actual child rows
        expected_children = None
        actual_children = None
        child_count_diff = None
        if col_total_elig and uuid_val:
            try:
                expected_children = int(float(str(r.get(col_total_elig, "")).strip() or 0))
                actual_children = actual_child_count_by_uuid.get(uuid_val, 0)
                child_count_diff = expected_children - actual_children
                if expected_children != actual_children:
                    flags.append("Child Count Mismatch")
            except (ValueError, TypeError):
                pass

        # Survey Date Consistency: start vs _submission_time
        form_start = None
        form_submitted = None
        form_duration_min = None
        if col_start and col_submitted:
            start_dt = _parse_dt(r.get(col_start))
            sub_dt = _parse_dt(r.get(col_submitted))
            if start_dt is not None and sub_dt is not None and pd.notna(start_dt) and pd.notna(sub_dt):
                form_start = str(start_dt)
                form_submitted = str(sub_dt)
                try:
                    diff_s = (sub_dt - start_dt).total_seconds()
                    form_duration_min = round(diff_s / 60.0, 1)
                    if diff_s < 0:
                        flags.append("Date Consistency: submitted before start")
                    elif diff_s < 300:  # < 5 minutes = implausibly quick
                        flags.append("Date Consistency: form too short (<5m)")
                    elif diff_s > 86400:  # > 24 hours
                        flags.append("Date Consistency: form spans >24h")
                except Exception:
                    pass

        record_status = decisions.get(uuid_val, "pending")
        if status and status != "all" and record_status != status:
            continue

        kids = children_by_uuid.get(uuid_val, [])
        child_name_age = "; ".join([k["name_age"] for k in kids if k["name_age"]]) or "—"
        child_sex      = "; ".join([k["sex"] for k in kids if k["sex"]]) or "—"

        system_flags = list(flags)
        added_flags = [f for f in vflags_map.get(uuid_val, []) if f not in system_flags]
        combined_flags = system_flags + added_flags

        rows.append({
            "uuid": uuid_val,
            "unique_code": uc,
            "lga": str(r.get(COL_LGA, "")).strip() if COL_LGA in cov.columns else "",
            "ward": str(r.get(COL_WARD, "")).strip() if COL_WARD in cov.columns else "",
            "community": _community_name(community_map, r.get(COL_COMMUNITY, "")) if COL_COMMUNITY in cov.columns else "",
            "ra": str(r.get(COL_RA, "")).strip() if COL_RA in cov.columns else "",
            "head_name": str(r.get(col_head_name, "")).strip() if col_head_name else "",
            "head_gender": str(r.get(col_head_gen, "")).strip() if col_head_gen else "",
            "education": str(r.get(col_edu, "")).strip() if col_edu else "",
            "occupation": str(r.get(col_occ, "")).strip() if col_occ else "",
            "settlement_type": str(r.get(col_settle, "")).strip() if col_settle else "",
            "child_name_age": child_name_age,
            "child_sex": child_sex,
            "expected_children": expected_children,
            "actual_children": actual_children,
            "child_count_diff": child_count_diff,
            "form_start": form_start,
            "form_submitted": form_submitted,
            "form_duration_minutes": form_duration_min,
            "flags": combined_flags,
            "system_flags": system_flags,
            "validator_flags": added_flags,
            "status": record_status,
        })
    rows.sort(key=lambda x: (-len(x["flags"]), x["lga"], x["ward"]))
    return rows


def _ensure_record_in_scope(user: User, record_uuid: str) -> None:
    """Raise 403 when a validator tries to act on a record outside their assigned LGAs."""
    if not user.role or user.role.name not in ("validator", "admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Not permitted")
    if user.role.name == "validator":
        allowed = _allowed_lgas(user)
        cov = data_service.scope_cov(data_service.cov, allowed)
        scoped_uuids: set = set()
        if cov is not None and not cov.empty:
            for c in ["_uuid", COL_UUID]:
                if c in cov.columns:
                    scoped_uuids |= set(cov[c].astype(str).str.strip())
        if record_uuid not in scoped_uuids:
            raise HTTPException(status_code=403, detail="Record is outside your assigned LGAs")


class ValidatorDecisionIn(__import__("pydantic").BaseModel):
    status: str
    note: str | None = None


@router.post("/api/validators/{record_uuid}/decision")
def api_validator_decision(
    record_uuid: str,
    payload: ValidatorDecisionIn,
    user: User = Depends(get_current_user),
) -> dict:
    from ..database import SessionLocal, ValidationDecision
    _ensure_record_in_scope(user, record_uuid)
    if payload.status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="status must be approved, rejected, or pending")
    with SessionLocal() as db:
        existing = db.query(ValidationDecision).filter(ValidationDecision.record_uuid == record_uuid).one_or_none()
        if existing:
            existing.status = payload.status
            existing.note = payload.note
            existing.decided_by = user.id
            existing.decided_at = datetime.utcnow()
        else:
            db.add(ValidationDecision(record_uuid=record_uuid, status=payload.status, note=payload.note, decided_by=user.id))
        db.commit()
    return {"uuid": record_uuid, "status": payload.status}


class ValidatorFlagsIn(__import__("pydantic").BaseModel):
    flags: list[str] = []
    note: str | None = None


@router.post("/api/validators/{record_uuid}/flags")
def api_validator_add_flags(
    record_uuid: str,
    payload: ValidatorFlagsIn,
    user: User = Depends(get_current_user),
) -> dict:
    """Add validator-assigned error flags to a record (system flags are never removed)."""
    from ..database import SessionLocal, ValidatorFlag
    _ensure_record_in_scope(user, record_uuid)
    added: list[str] = []
    with SessionLocal() as db:
        existing = {f.flag for f in db.query(ValidatorFlag).filter(ValidatorFlag.record_uuid == record_uuid).all()}
        for f in payload.flags:
            f = str(f).strip()
            if not f or f in existing:
                continue
            db.add(ValidatorFlag(record_uuid=record_uuid, flag=f, note=payload.note, added_by=user.id))
            existing.add(f)
            added.append(f)
        db.commit()
    return {"uuid": record_uuid, "added": added}


@router.get("/api/validators/summary")
def api_validator_summary(user: User = Depends(get_current_user)) -> dict:
    from ..database import SessionLocal, ValidationDecision
    from sqlalchemy import func
    with SessionLocal() as db:
        by_status = dict(db.query(ValidationDecision.status, func.count(ValidationDecision.id))
                         .group_by(ValidationDecision.status).all())
    all_records = api_validators_flagged(status="all", user=user)
    flagged = [r for r in all_records if r["flags"]]
    return {
        "pending": len([r for r in all_records if r["status"] == "pending"]),
        "approved": int(by_status.get("approved", 0)),
        "rejected": int(by_status.get("rejected", 0)),
        "total": len(all_records),
        "flagged": len(flagged),
    }


@router.get("/api/quality/by-enumerator")
def api_quality_by_enumerator(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    from data_processor import compute_error_log, compute_dq_metrics
    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, allowed_lgas=allowed)
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    if df is None or df.empty or COL_RA not in df.columns:
        return []
    dq = compute_dq_metrics(df, data_service.child_info_scoped(allowed), ce)
    errs = compute_error_log(df, ce, dq)
    if errs is None or errs.empty:
        return []
    err_cols = [c for c in ["Duplicate Household", "Settlement Type Mismatch", "Stacked GPS", "Mock GPS"] if c in errs.columns]
    if not err_cols:
        return []
    errs = errs.copy()
    errs["_ra"] = errs[COL_RA].astype(str).str.strip().replace({"nan": "Unknown", "": "Unknown"})
    errs["_has_error"] = errs[err_cols].sum(axis=1).gt(0).astype(int)
    totals = df.copy()
    totals["_ra"] = totals[COL_RA].astype(str).str.strip().replace({"nan": "Unknown", "": "Unknown"})
    total_by_ra = totals.groupby("_ra").size().to_dict()
    lga_by_ra: dict[str, list[str]] = {}
    if COL_LGA in totals.columns:
        lga_by_ra = {
            ra: sorted({str(x).strip() for x in grp[COL_LGA] if str(x).strip().lower() not in ("nan", "")})
            for ra, grp in totals.groupby("_ra")
        }
    agg = errs.groupby("_ra").agg({**{c: "sum" for c in err_cols}, "_has_error": "sum"}).reset_index()
    rows: list[dict[str, Any]] = []
    for _, r in agg.iterrows():
        ra = r["_ra"]
        total = int(total_by_ra.get(ra, 0))
        recs_with_error = int(r["_has_error"])
        pct = round(recs_with_error / total * 100, 1) if total else 0.0
        rows.append({
            "enumerator": ra,
            "lga": ", ".join(lga_by_ra.get(ra, [])) or "—",
            "lgas": lga_by_ra.get(ra, []),
            "total_records": total,
            "duplicate_hh": int(r.get("Duplicate Household", 0)),
            "settlement_mismatch": int(r.get("Settlement Type Mismatch", 0)),
            "stacked_gps": int(r.get("Stacked GPS", 0)),
            "mock_gps": int(r.get("Mock GPS", 0)),
            "records_with_error": recs_with_error,
            "error_pct": pct,
        })
    rows.sort(key=lambda x: (-x["error_pct"], -x["total_records"]))
    return rows


@router.get("/api/error-log")
def api_error_log(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    from data_processor import compute_dq_metrics, compute_error_log

    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, ra, allowed_lgas=allowed)
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    dq = compute_dq_metrics(df, data_service.child_info_scoped(allowed), ce)
    errors_df = compute_error_log(df, ce, dq)
    error_cols = [
        c for c in errors_df.columns
        if c not in [COL_UUID, COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_HH_CODE, COL_SETTLEMENT_TYPE, COL_LAT, COL_LNG, COL_PRECISION]
    ]
    errors_df["error_count"] = errors_df[error_cols].sum(axis=1) if len(error_cols) > 0 else 0
    errors_df = errors_df[errors_df["error_count"] > 0]
    if errors_df.empty:
        return []
    records: list[dict[str, Any]] = []
    for _, r in errors_df.head(500).iterrows():
        records.append({
            "uuid": str(r.get(COL_UUID, "")),
            "lga": str(r.get(COL_LGA, "")),
            "ward": str(r.get(COL_WARD, "")),
            "community": str(r.get(COL_COMMUNITY, "")),
            "ra": str(r.get(COL_RA, "")),
            "household_code": str(r.get(COL_HH_CODE, "")),
            "error_count": int(r["error_count"]),
        })
    return records


@router.get("/api/completion")
def api_completion(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, allowed_lgas=allowed)
    community_map = _scoped_community_map(allowed)
    if COL_LGA not in df.columns:
        return []
    completion_data = df.groupby([COL_LGA, COL_WARD, COL_COMMUNITY]).agg(
        households_reached=(COL_UUID, "nunique"),
        ras=(COL_RA, "nunique"),
    ).reset_index()
    result: list[dict[str, Any]] = []
    for _, r in completion_data.iterrows():
        code = str(r[COL_COMMUNITY]).strip()
        name = _community_name(community_map, code)
        info = community_map.get(code, {})
        planned = info.get("sample_count", 0)
        reached = int(r["households_reached"])
        status_ = "Complete" if planned > 0 and reached >= planned else "Incomplete"
        result.append({
            "lga": str(r[COL_LGA]),
            "ward": str(r[COL_WARD]),
            "community": name,
            "community_code": code,
            "planned": planned,
            "reached": reached,
            "status": status_,
            "ras": int(r["ras"]),
        })
    return result


@router.get("/api/gps-data")
def api_gps_data(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    df = filter_cov(lga, ward, community, ra, allowed_lgas=_allowed_lgas(user))
    if COL_LAT not in df.columns or COL_LNG not in df.columns:
        return []
    gps = df[[COL_LAT, COL_LNG, COL_LGA, COL_WARD, COL_RA]].dropna(subset=[COL_LAT, COL_LNG]).copy()
    gps[COL_LAT] = pd.to_numeric(gps[COL_LAT], errors="coerce")
    gps[COL_LNG] = pd.to_numeric(gps[COL_LNG], errors="coerce")
    gps = gps.dropna(subset=[COL_LAT, COL_LNG])
    result: list[dict[str, Any]] = []
    for _, r in gps.iterrows():
        result.append({
            "lat": float(r[COL_LAT]),
            "lng": float(r[COL_LNG]),
            "lga": str(r.get(COL_LGA, "")),
            "ward": str(r.get(COL_WARD, "")),
            "ra": str(r.get(COL_RA, "")),
        })
    return result


@router.get("/api/gps-summary")
def api_gps_summary(user: User = Depends(get_current_user)) -> dict[str, Any]:
    df = data_service.scope_cov(data_service.cov, _allowed_lgas(user)).copy()
    summary: dict[str, Any] = {}
    if COL_LAT in df.columns and COL_LNG in df.columns:
        gps = df[[COL_LAT, COL_LNG]].dropna()
        total_gps = len(gps)
        stacked = int(gps.duplicated(keep=False).sum())
        unique_locations = int(gps.drop_duplicates().shape[0])
        summary["total_gps_points"] = total_gps
        summary["stacked_gps"] = stacked
        summary["unique_locations"] = unique_locations
        summary["stacked_pct"] = round((stacked / total_gps * 100) if total_gps > 0 else 0, 1)
    else:
        summary = {"total_gps_points": 0, "stacked_gps": 0, "unique_locations": 0, "stacked_pct": 0}
    if COL_PRECISION in df.columns:
        prec = pd.to_numeric(df[COL_PRECISION], errors="coerce")
        summary["mock_gps"] = int((prec < 2).sum())
        summary["total_with_precision"] = int(prec.notna().sum())
    else:
        summary["mock_gps"] = 0
        summary["total_with_precision"] = 0
    return summary


@router.get("/api/validation")
def api_validation(user: User = Depends(get_current_user)) -> dict[str, Any]:
    allowed = _allowed_lgas(user)
    df = data_service.scope_cov(data_service.cov, allowed).copy()
    ci = data_service.child_info_scoped(allowed).copy()
    validation: dict[str, Any] = {}
    flags: list[dict[str, Any]] = []
    val_cols: list[str] = []

    total_records = len(df)

    dup_hh = 0
    if COL_HH_CODE in df.columns:
        dup_mask = df.duplicated(subset=[COL_HH_CODE], keep=False)
        dup_hh = int(dup_mask.sum())
        validation["dup_households"] = dup_hh
        if dup_hh > 0:
            val_cols.append("Duplicate Household IDs")
            for _, row in df[dup_mask].head(50).iterrows():
                lga = row.get(COL_LGA, "") if COL_LGA in row else ""
                ward = row.get(COL_WARD, "") if COL_WARD in row else ""
                ra = row.get(COL_RA, "") if COL_RA in row else ""
                flags.append({"type": "Duplicate Household ID", "lga": lga, "ward": ward, "ra": ra, "detail": str(row.get(COL_HH_CODE, ""))})
    else:
        validation["dup_households"] = 0

    non_eligible = 0
    if COL_IS_ELIGIBLE in ci.columns:
        ne_mask = ci[COL_IS_ELIGIBLE] == "0"
        non_eligible = int(ne_mask.sum())
        if non_eligible > 0:
            val_cols.append("Non-Eligible Children")
            for _, row in ci[ne_mask].head(50).iterrows():
                flags.append({"type": "Non-Eligible Child", "lga": "", "ward": "", "ra": "", "detail": f'Child ID: {row.get("child_id", "")}'})
    validation["non_eligible_children"] = non_eligible

    dup_children = 0
    child_name_col = None
    for c in ci.columns:
        if "name of child" in str(c).lower():
            child_name_col = c
            break
    if child_name_col and COL_HH_CODE in df.columns:
        ci_with_hh = ci.copy()
        ci_with_hh["_parent_index"] = ci_with_hh["_parent_index"].astype(str)
        df_idx = df.copy()
        df_idx["_index"] = df_idx["_index"].astype(str)
        merged = ci_with_hh.merge(df_idx[["_index", COL_HH_CODE]], left_on="_parent_index", right_on="_index", how="left")
        dup_child_mask = merged.duplicated(subset=[child_name_col, COL_HH_CODE], keep=False)
        dup_children = int(dup_child_mask.sum())
        validation["dup_children"] = dup_children
        if dup_children > 0:
            val_cols.append("Duplicate Child Records")
    else:
        validation["dup_children"] = 0

    edu_col = None
    occ_col = None
    for c in df.columns:
        if "education" in str(c).lower():
            edu_col = c
        if "occupation" in str(c).lower():
            occ_col = c
    edu_occ_flags = 0
    if edu_col and occ_col:
        edu_occ_mask = df[edu_col].notna() & df[occ_col].notna()
        edu_occ_flags = int(edu_occ_mask.sum())
        HIGH_OCC = ["professional", "manager", "teacher", "doctor", "nurse", "engineer"]
        for _, row in df[edu_occ_mask].head(50).iterrows():
            edu = str(row.get(edu_col, "")).lower().strip()
            occ = str(row.get(occ_col, "")).lower().strip()
            lga = row.get(COL_LGA, "") if COL_LGA in row else ""
            ward = row.get(COL_WARD, "") if COL_WARD in row else ""
            ra = row.get(COL_RA, "") if COL_RA in row else ""
            if any(e in edu for e in ["none", "no formal"]) and any(o in occ for o in HIGH_OCC):
                flags.append({"type": "Education vs Occupation", "lga": lga, "ward": ward, "ra": ra, "detail": f"Edu: {edu}, Occ: {occ}"})
    validation["edu_occ_flags"] = edu_occ_flags

    gender_col = None
    for c in df.columns:
        if "gender" in str(c).lower() and "head" in str(c).lower():
            gender_col = c
            break
    name_col = None
    for c in df.columns:
        if "name" in str(c).lower() and "head" in str(c).lower():
            name_col = c
            break
    gender_name_flags = 0
    if gender_col and name_col:
        gn_mask = df[gender_col].notna() & df[name_col].notna()
        gender_name_flags = int(gn_mask.sum())
    validation["gender_name_flags"] = gender_name_flags

    validation["total_records"] = total_records

    qc_cols = [c for c in df.columns if "validation" in str(c).lower() or "status" in str(c).lower() or "_status" in str(c).lower()]
    validated_count = 0
    approved_count = 0
    rejected_count = 0
    for c in qc_cols:
        vals = df[c].dropna().astype(str).str.lower()
        validated_count += int((vals != "").sum())
        approved_count += int(vals.isin(["approved", "1", "yes"]).sum())
        rejected_count += int(vals.isin(["rejected", "not_approved", "no", "0"]).sum())
    validation["validated"] = min(validated_count, total_records)
    validation["approved"] = min(approved_count, total_records)
    validation["rejected"] = min(rejected_count, total_records)
    validation["outstanding"] = max(0, total_records - validation["validated"])
    validation["flagged_records"] = len(flags)

    lga_breakdown: list[dict[str, Any]] = []
    if COL_LGA in df.columns:
        for lga in df[COL_LGA].dropna().unique():
            lga_df = df[df[COL_LGA] == lga]
            lga_total = len(lga_df)
            ward_count = lga_df[COL_WARD].nunique() if COL_WARD in lga_df.columns else 0
            ra_count = lga_df[COL_RA].nunique() if COL_RA in lga_df.columns else 0
            lga_breakdown.append({"lga": lga, "total": lga_total, "wards": ward_count, "ras": ra_count})
    validation["lga_breakdown"] = lga_breakdown

    ra_errors: list[dict[str, Any]] = []
    if COL_RA in df.columns:
        for ra in df[COL_RA].dropna().unique():
            ra_df = df[df[COL_RA] == ra]
            ra_total = len(ra_df)
            ra_err = sum(1 for f in flags if f.get("ra") == ra)
            ra_errors.append({"ra": ra, "records": ra_total, "errors": ra_err, "error_pct": round(ra_err / ra_total * 100, 1) if ra_total else 0})
    validation["ra_errors"] = sorted(ra_errors, key=lambda x: x["error_pct"], reverse=True)

    return {
        "summary": {
            "total_records": total_records,
            "validated": validation["validated"],
            "approved": validation["approved"],
            "rejected": validation["rejected"],
            "outstanding": validation["outstanding"],
            "flagged_records": validation["flagged_records"],
            "dup_households": validation["dup_households"],
            "non_eligible_children": validation["non_eligible_children"],
            "dup_children": dup_children,
            "edu_occ_flags": validation["edu_occ_flags"],
            "gender_name_flags": validation["gender_name_flags"],
            "total_ras": int(df[COL_RA].nunique()) if COL_RA in df.columns else 0,
        },
        "val_tasks": [
            {"id": "VAL-01", "name": "Education vs Occupation", "status": "Active", "flags": validation["edu_occ_flags"]},
            {"id": "VAL-02", "name": "Repetitive Child Selection", "status": "Not Started", "flags": 0},
            {"id": "VAL-03", "name": "Gender vs Name Consistency", "status": "Active", "flags": validation["gender_name_flags"]},
            {"id": "VAL-04", "name": "Child Name vs Vaccination Card", "status": "Not Started", "flags": 0},
            {"id": "VAL-05", "name": "Duplicate Household ID", "status": "Active", "flags": validation["dup_households"]},
            {"id": "VAL-06", "name": "Non-Eligible Children", "status": "Active", "flags": validation["non_eligible_children"]},
        ],
        "flags": sorted(flags, key=lambda x: x["type"])[:100],
        "lga_breakdown": lga_breakdown,
        "ra_errors": ra_errors[:50],
    }


@router.get("/api/filters")
def api_filters(user: User = Depends(get_current_user)) -> dict[str, Any]:
    from data_processor import get_lga_hierarchy, get_lga_wards_communities

    allowed = _allowed_lgas(user)
    cov = data_service.scope_cov(data_service.cov, allowed)
    community_map = _scoped_community_map(allowed)
    lga_list, ward_list, community_list, ra_list = get_lga_wards_communities(cov)
    hierarchy = get_lga_hierarchy(cov) if COL_LGA in cov.columns else {}
    communities = [
        {"code": c, "name": _community_name(community_map, c)}
        for c in community_list
    ]
    return {
        "lgas": lga_list,
        "wards": ward_list,
        "communities": communities,
        "ras": ra_list,
        "wards_by_lga": {lga: list(wards.keys()) for lga, wards in hierarchy.items()} if hierarchy else {},
        "communities_by_ward": hierarchy,
    }


@router.get("/api/supervision")
def api_supervision(
    lga: str | None = None,
    ward: str | None = None,
    settlement: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from data_processor import compute_dq_metrics, compute_error_log

    allowed = _allowed_lgas(user)
    df = data_service.scope_cov(data_service.cov, allowed).copy()
    ce = data_service.child_eligible_scoped(allowed).copy()
    dq = compute_dq_metrics(df, data_service.child_info_scoped(allowed), ce)
    errors_df = compute_error_log(df, ce, dq)
    error_cols = [
        c for c in errors_df.columns
        if c not in [COL_UUID, COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_HH_CODE, COL_SETTLEMENT_TYPE, COL_LAT, COL_LNG, COL_PRECISION]
    ]
    errors_df["error_count"] = errors_df[error_cols].sum(axis=1) if len(error_cols) > 0 else 0
    errors_df = errors_df[errors_df["error_count"] > 0]

    level = "lga"
    ranking: list[dict[str, Any]] = []
    if settlement:
        level = "settlement"
        if lga and ward and settlement:
            errs = errors_df[errors_df[COL_LGA] == lga]
            errs = errs[errs[COL_WARD] == ward]
            errs = errs[errs[COL_COMMUNITY] == settlement]
            total_records = len(df[(df[COL_LGA] == lga) & (df[COL_WARD] == ward) & (df[COL_COMMUNITY] == settlement)])
            for ra_name, g in errs.groupby(COL_RA):
                total = len(g)
                dup = int(g["Duplicate Household"].sum()) if "Duplicate Household" in g.columns else 0
                mock = int(g["Mock GPS"].sum()) if "Mock GPS" in g.columns else 0
                stacked = int(g["Stacked GPS"].sum()) if "Stacked GPS" in g.columns else 0
                score = round((total / max(total_records, 1)) * 100, 1) if total > 0 else 0
                risk = "High" if total > 5 else "Medium" if total > 0 else "Low"
                ranking.append({"name": str(ra_name), "total_records": total_records, "total_errors": total, "dup_households": dup, "mock_gps": mock, "stacked_gps": stacked, "score": score, "risk": risk})
            ranking.sort(key=lambda x: x["score"], reverse=True)
    elif ward:
        level = "ward"
        if lga and ward:
            errs = errors_df[errors_df[COL_LGA] == lga]
            errs = errs[errs[COL_WARD] == ward]
            for comm_name, g in errs.groupby(COL_COMMUNITY):
                total = int(len(g))
                total_records_for_unit = len(df[(df[COL_LGA] == lga) & (df[COL_WARD] == ward) & (df[COL_COMMUNITY] == comm_name)])
                dup = int(g["Duplicate Household"].sum()) if "Duplicate Household" in g.columns else 0
                mock = int(g["Mock GPS"].sum()) if "Mock GPS" in g.columns else 0
                stacked = int(g["Stacked GPS"].sum()) if "Stacked GPS" in g.columns else 0
                score = round((total / max(total_records_for_unit, 1)) * 100, 1)
                risk = "High" if total > 5 else "Medium" if total > 0 else "Low"
                ranking.append({"name": str(comm_name), "total_records": total_records_for_unit, "total_errors": total, "dup_households": dup, "mock_gps": mock, "stacked_gps": stacked, "score": score, "risk": risk})
            ranking.sort(key=lambda x: x["score"], reverse=True)
    elif lga:
        level = "lga"
        errs = errors_df[errors_df[COL_LGA] == lga]
        for ward_name, g in errs.groupby(COL_WARD):
            total = int(len(g))
            total_records_for_unit = len(df[(df[COL_LGA] == lga) & (df[COL_WARD] == ward_name)])
            dup = int(g["Duplicate Household"].sum()) if "Duplicate Household" in g.columns else 0
            mock = int(g["Mock GPS"].sum()) if "Mock GPS" in g.columns else 0
            stacked = int(g["Stacked GPS"].sum()) if "Stacked GPS" in g.columns else 0
            score = round((total / max(total_records_for_unit, 1)) * 100, 1)
            risk = "High" if total > 5 else "Medium" if total > 0 else "Low"
            ranking.append({"name": str(ward_name), "total_records": total_records_for_unit, "total_errors": total, "dup_households": dup, "mock_gps": mock, "stacked_gps": stacked, "score": score, "risk": risk})
        ranking.sort(key=lambda x: x["score"], reverse=True)
    else:
        if COL_LGA not in df.columns:
            return {"ranking": [], "totals": {}, "level": "lga", "breadcrumb": []}
        for lga_name, g in errors_df.groupby(COL_LGA):
            total = int(len(g))
            total_records_for_unit = int(len(df[df[COL_LGA] == lga_name]))
            dup = int(g["Duplicate Household"].sum()) if "Duplicate Household" in g.columns else 0
            mock = int(g["Mock GPS"].sum()) if "Mock GPS" in g.columns else 0
            stacked = int(g["Stacked GPS"].sum()) if "Stacked GPS" in g.columns else 0
            score = round((total / max(total_records_for_unit, 1)) * 100, 1)
            risk = "High" if score > 10 else "Medium" if score > 5 else "Low"
            ranking.append({"name": str(lga_name), "total_records": total_records_for_unit, "total_errors": total, "dup_households": dup, "mock_gps": mock, "stacked_gps": stacked, "score": score, "risk": risk})
        ranking.sort(key=lambda x: x["score"], reverse=True)

    breadcrumb: list[dict[str, Any]] = []
    if lga:
        breadcrumb.append({"label": str(lga), "lga": str(lga), "ward": None, "settlement": None})
        if ward:
            breadcrumb.append({"label": str(ward), "lga": str(lga), "ward": str(ward), "settlement": None})
            if settlement:
                breadcrumb.append({"label": str(settlement), "lga": str(lga), "ward": str(ward), "settlement": str(settlement)})

    total_records = int(len(df))
    flagged_records = int(len(errors_df))
    totals = {"total_records": total_records, "flagged_records": flagged_records}

    return {
        "ranking": ranking,
        "totals": totals,
        "level": level,
        "breadcrumb": breadcrumb,
    }


@router.get("/api/ai/insights")
def api_ai_insights(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, ra, allowed_lgas=allowed)
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    insights: list[dict[str, Any]] = []
    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == "yes").sum()) if COL_OFFERED_AZM in ce.columns else 0
    total_eligible = int(len(ce))
    cov_pct = round((offered / total_eligible * 100), 1) if total_eligible > 0 else 0
    if cov_pct >= 80:
        insights.append({"title": "Good Coverage Rate", "text": f"Coverage is at {cov_pct}%, meeting the 80% target.", "type": "success", "icon": "bi-check-circle-fill"})
    elif cov_pct >= 50:
        insights.append({"title": "Moderate Coverage", "text": f"Coverage is at {cov_pct}%. Efforts needed to reach 80% target.", "type": "warning", "icon": "bi-exclamation-triangle-fill"})
    else:
        insights.append({"title": "Low Coverage Alert", "text": f"Coverage is at {cov_pct}%. Immediate action required.", "type": "danger", "icon": "bi-bug-fill"})
    if COL_LAT in df.columns and COL_LNG in df.columns:
        gps = df[[COL_LAT, COL_LNG]].dropna()
        stacked = int(gps.duplicated(keep=False).sum())
        if stacked > 0:
            insights.append({"title": "Stacked GPS Points Detected", "text": f"{stacked} GPS points share identical coordinates, indicating possible falsification.", "type": "danger", "icon": "bi-pin-map-fill"})
    if COL_HH_CODE in df.columns:
        dup = int(df[df.duplicated(subset=[COL_HH_CODE], keep=False)][COL_HH_CODE].nunique())
        if dup > 0:
            insights.append({"title": "Duplicate Household IDs", "text": f"{dup} duplicate household IDs found. Review and resolve conflicts.", "type": "warning", "icon": "bi-house-x-fill"})
    return insights


@router.get("/api/ai/regression")
def api_ai_regression(
    lga: str | None = None,
    ward: str | None = None,
    community: str | None = None,
    ra: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    allowed = _allowed_lgas(user)
    df = filter_cov(lga, ward, community, ra, allowed_lgas=allowed)
    daily_data: dict[str, Any]
    if COL_SUBMISSION_TIME in df.columns:
        daily = df.copy()
        daily["date"] = pd.to_datetime(daily[COL_SUBMISSION_TIME], errors="coerce").dt.date
        daily_counts = daily.groupby("date").size().reset_index(name="count").sort_values("date")
        dates = [str(r["date"]) for _, r in daily_counts.iterrows()]
        counts = [int(r["count"]) for _, r in daily_counts.iterrows()]
        avg = round(sum(counts[-3:]) / 3) if len(counts) >= 3 else (counts[-1] if counts else 0)
        last_date = daily_counts["date"].iloc[-1] if len(daily_counts) > 0 else datetime.now().date()
        forecast_dates: list[str] = []
        forecast_counts: list[int] = []
        for i in range(1, 8):
            forecast_dates.append(str(last_date + timedelta(days=i)))
            forecast_counts.append(avg)
        actual_padded: list[Any] = list(counts) + [None] * 7
        forecast_padded: list[Any] = [None] * len(counts) + forecast_counts
        all_labels = dates + forecast_dates
        daily_data = {"labels": all_labels, "actual": actual_padded, "forecast": forecast_padded}
    else:
        daily_data = {"labels": [], "actual": [], "forecast": []}

    lga_trends: dict[str, Any] = {}
    if COL_LGA in df.columns and COL_SUBMISSION_TIME in df.columns:
        for lga_name in df[COL_LGA].unique():
            lga_df = df[df[COL_LGA] == lga_name]
            lga_df = lga_df.copy()
            lga_df["date"] = pd.to_datetime(lga_df[COL_SUBMISSION_TIME], errors="coerce").dt.date
            lga_daily = lga_df.groupby("date").size()
            if len(lga_daily) >= 2:
                current = int(lga_daily.iloc[-1])
                prev = int(lga_daily.iloc[-2])
                trend = round((current - prev) / max(prev, 1) * 100, 1)
            else:
                current = int(lga_daily.iloc[-1]) if len(lga_daily) > 0 else 0
                trend = 0
            lga_trends[str(lga_name)] = {"current": current, "trend": trend}

    kpis: dict[str, str] = {}
    ce = filter_child_eligible(lga, ward, community, allowed_lgas=allowed)
    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == "yes").sum()) if COL_OFFERED_AZM in ce.columns else 0
    total_eligible = int(len(ce))
    kpis["Coverage"] = f"{round((offered / max(total_eligible, 1)) * 100, 1)}%"
    kpis["Total HH"] = str(int(len(df)))
    kpis["Active RAs"] = str(int(df[COL_RA].nunique())) if COL_RA in df.columns else "0"

    return {"chart": daily_data, "kpis": kpis, "lga_trends": lga_trends}


@router.get("/api/ai/anomaly")
def api_ai_anomaly(lga: str | None = None, user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    df = filter_cov(lga, allowed_lgas=_allowed_lgas(user))
    anomalies: list[dict[str, Any]] = []
    if COL_LAT in df.columns and COL_LNG in df.columns:
        gps = df[[COL_LAT, COL_LNG]].dropna()
        stacked = int(gps.duplicated(keep=False).sum())
        if stacked > 0:
            anomalies.append({"title": "Stacked GPS Coordinates", "description": f"{stacked} records share identical GPS coordinates.", "severity": "high", "location": str(lga) if lga else "All", "date": ""})
    if COL_RA in df.columns:
        ra_counts = df[COL_RA].value_counts()
        avg = ra_counts.mean()
        for ra, count in ra_counts.items():
            if count > avg * 2:
                anomalies.append({"title": f"High Submission Count: {ra}", "description": f"{count} submissions vs average {avg:.0f}.", "severity": "medium", "location": str(ra), "date": ""})
    return anomalies


@router.post("/api/ai/chat")
def api_ai_chat(
    payload: dict = Body(default={}),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    from data_processor import compute_dq_metrics

    allowed = _allowed_lgas(user)
    cov = data_service.scope_cov(data_service.cov, allowed)
    child_info = data_service.child_info_scoped(allowed)
    ce = data_service.child_eligible_scoped(allowed)

    msg = (payload.get("message") or "").strip().lower()
    total_hh = int(len(cov))
    total_lga = int(cov[COL_LGA].nunique()) if COL_LGA in cov.columns else 0
    total_ra = int(cov[COL_RA].nunique()) if COL_RA in cov.columns else 0
    total_wards = int(cov[COL_WARD].nunique()) if COL_WARD in cov.columns else 0
    total_communities = int(cov[COL_COMMUNITY].nunique()) if COL_COMMUNITY in cov.columns else 0
    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == "yes").sum()) if COL_OFFERED_AZM in ce.columns else 0
    swallowed = int((ce[COL_SWALLOWED_AZM].str.strip().str.lower() == "yes").sum()) if COL_SWALLOWED_AZM in ce.columns else 0
    eligible = int((child_info[COL_IS_ELIGIBLE] == "1").sum()) if COL_IS_ELIGIBLE in child_info.columns else 0
    cov_pct = round((offered / max(eligible, 1)) * 100, 1)

    reply = ""
    if "coverage" in msg or "percentage" in msg:
        reply = f"The overall AZM coverage rate is {cov_pct}% ({offered} of {eligible} eligible children were offered AZM)."
    elif "lga" in msg and ("top" in msg or "most" in msg):
        if COL_LGA in cov.columns:
            top = cov[COL_LGA].value_counts().index[0]
            reply = f"The LGA with the most submissions is {top}."
        else:
            reply = "LGA data is not available."
    elif "quality" in msg or "issue" in msg:
        dq = compute_dq_metrics(cov, child_info, ce)
        issues: list[str] = []
        if dq.get("dup_household_count", 0) > 0:
            issues.append(f"{dq['dup_household_count']} duplicate households")
        if dq.get("mock_gps", 0) > 0:
            issues.append(f"{dq['mock_gps']} mock GPS points")
        if dq.get("stacked_gps", 0) > 0:
            issues.append(f"{dq['stacked_gps']} stacked GPS points")
        if issues:
            reply = f'Data quality issues found: {", ".join(issues)}.'
        else:
            reply = "No major data quality issues found."
    elif "eligible" in msg or "child" in msg:
        reply = f"There are {eligible} eligible children (1-59 months) recorded in the survey."
    elif "household" in msg or "hh" in msg:
        reply = f"A total of {total_hh} households were surveyed across {total_lga} LGAs, {total_wards} wards, and {total_communities} communities."
    elif "ra" in msg or "assistant" in msg or "enumerator" in msg:
        reply = f"There are {total_ra} active research assistants in the field."
    elif "swallow" in msg:
        rate = round((swallowed / max(offered, 1)) * 100, 1)
        reply = f"{swallowed} of {offered} children who were offered AZM swallowed it ({rate}% swallow rate)."
    else:
        reply = f"I can tell you about coverage ({cov_pct}%), top LGAs, data quality issues, eligible children, households, RAs, or swallow rates. Try asking a specific question."
    return {"reply": reply}


@router.get("/api/summary")
def api_summary(user: User = Depends(get_current_user)) -> dict[str, int]:
    allowed = _allowed_lgas(user)
    cov = data_service.scope_cov(data_service.cov, allowed)
    child_info = data_service.child_info_scoped(allowed)
    child_eligible = data_service.child_eligible_scoped(allowed)
    total_hh = int(len(cov))
    total_lga = int(cov[COL_LGA].nunique()) if COL_LGA in cov.columns else 0
    total_ra = int(cov[COL_RA].nunique()) if COL_RA in cov.columns else 0
    total_children = int(len(child_eligible))
    eligible = int((child_info[COL_IS_ELIGIBLE] == "1").sum()) if COL_IS_ELIGIBLE in child_info.columns else 0
    offered = int((child_eligible[COL_OFFERED_AZM].str.strip().str.lower() == "yes").sum()) if COL_OFFERED_AZM in child_eligible.columns else 0
    return {
        "total_households": total_hh,
        "total_lgas": total_lga,
        "total_ras": total_ra,
        "total_children": total_children,
        "eligible_children": eligible,
        "offered_azm": offered,
    }
