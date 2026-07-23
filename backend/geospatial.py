from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import shapefile
from pyproj import Transformer
from shapely.geometry import Point, shape as shp_shape
from shapely.ops import transform as shp_transform
from shapely.prepared import prep

from .database import GpsPoint, SessionLocal

WGS84_TO_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
MERCATOR_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
SHAPE_CRS = "EPSG:3857"
POINT_CRS = "EPSG:4326"

GEO_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "geospatial"

PLANNED_LGAS: set[str] = {"KWARE", "RABAH", "TURETA", "WAMAKKO", "WURNO", "YABO"}

_lga_shapes: list[tuple[Any, dict, Any]] = []
_ward_shapes: list[tuple[Any, dict, Any]] = []
_settlement_shapes: list[tuple[Any, dict, Any]] = []
_loaded: bool = False


def _read_shp(path: Path, name_fields: list[str]) -> list[tuple[Any, dict, Any]]:
    if not path.exists():
        return []
    reader = shapefile.Reader(str(path))
    field_names = [f[0] for f in reader.fields[1:]]
    lookup = {f.lower(): f for f in field_names}
    resolved = [lookup.get(nf.lower()) for nf in name_fields]
    result: list[tuple[Any, dict, Any]] = []
    for shape_rec in reader.shapeRecords():
        try:
            geom = shp_shape(shape_rec.shape.__geo_interface__)
        except Exception:
            continue
        rec = dict(zip(field_names, shape_rec.record))
        attrs: dict = {}
        for wanted, actual in zip(name_fields, resolved):
            attrs[wanted] = str(rec.get(actual, "")).strip() if actual else ""
        result.append((geom, attrs, prep(geom)))
    return result


def load() -> None:
    global _lga_shapes, _ward_shapes, _settlement_shapes, _loaded
    _lga_shapes = _read_shp(GEO_DIR / "lga.shp", ["lganame"])
    _ward_shapes = _read_shp(GEO_DIR / "ward.shp", ["lganame", "wardname"])
    _settlement_shapes = _read_shp(GEO_DIR / "Settlement.shp", ["lga_name", "ward_name", "settlement"])
    _loaded = True


def _norm(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip().upper()


def _point_in(shapes: list[tuple[Any, dict, Any]], lat: float, lng: float) -> dict | None:
    if not shapes:
        return None
    x, y = WGS84_TO_MERCATOR.transform(lng, lat)
    pt = Point(x, y)
    for _geom, attrs, prep_geom in shapes:
        if prep_geom.contains(pt):
            return attrs
    return None


def find_lga(lat: float, lng: float) -> str | None:
    hit = _point_in(_lga_shapes, lat, lng)
    return hit["lganame"] if hit else None


def find_ward(lat: float, lng: float) -> tuple[str | None, str | None]:
    hit = _point_in(_ward_shapes, lat, lng)
    return (hit["lganame"], hit["wardname"]) if hit else (None, None)


def find_settlement(lat: float, lng: float) -> tuple[str | None, str | None, str | None]:
    hit = _point_in(_settlement_shapes, lat, lng)
    return (hit["lga_name"], hit["ward_name"], hit["settlement"]) if hit else (None, None, None)


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        actual = lower_map.get(cand.lower())
        if actual:
            return actual
    return None


def rebuild_gps_points_table(cov: pd.DataFrame) -> dict:
    if not _loaded:
        load()

    lat_col = _pick_column(cov, ["_Q9. GPS coordinates_latitude"])
    lng_col = _pick_column(cov, ["_Q9. GPS coordinates_longitude"])
    if not lat_col or not lng_col:
        return {"status": "no_gps_columns", "count": 0}

    lga_col = _pick_column(cov, ["Confirm your LGA", "Q2. Local Government Area"])
    ward_col = _pick_column(cov, ["Confirm your ward", "Q3.Ward", "Q3. Ward"])
    community_col = _pick_column(cov, ["Confirm your community", "Q4. Community Name"])
    uuid_col = _pick_column(cov, ["_uuid", "uuid"])
    ra_col = _pick_column(cov, ["Q1. Research Assistant", "researcher_id"])

    df = cov.dropna(subset=[lat_col, lng_col]).copy()
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lng_col] = pd.to_numeric(df[lng_col], errors="coerce")
    df = df.dropna(subset=[lat_col, lng_col])

    session = SessionLocal()
    try:
        session.query(GpsPoint).delete()
        session.commit()

        rows: list[GpsPoint] = []
        for _, r in df.iterrows():
            lat = float(r[lat_col])
            lng = float(r[lng_col])
            rep_lga = str(r[lga_col]).strip() if lga_col and pd.notna(r.get(lga_col)) else None
            rep_ward = str(r[ward_col]).strip() if ward_col and pd.notna(r.get(ward_col)) else None
            rep_comm = str(r[community_col]).strip() if community_col and pd.notna(r.get(community_col)) else None

            m_lga = find_lga(lat, lng)
            m_ward_lga, m_ward = find_ward(lat, lng)
            _sl_lga, _sl_ward, m_settlement = find_settlement(lat, lng)

            rows.append(GpsPoint(
                uuid=str(r[uuid_col]).strip() if uuid_col and pd.notna(r.get(uuid_col)) else None,
                ra=str(r[ra_col]).strip() if ra_col and pd.notna(r.get(ra_col)) else None,
                lat=lat, lng=lng,
                reported_lga=rep_lga, reported_ward=rep_ward, reported_community=rep_comm,
                matched_lga=m_lga, matched_ward=m_ward, matched_settlement=m_settlement,
                in_lga=bool(m_lga), in_ward=bool(m_ward), in_settlement=bool(m_settlement),
                lga_match=bool(m_lga and rep_lga and _norm(m_lga) == _norm(rep_lga)),
                ward_match=bool(m_ward and rep_ward and _norm(m_ward) == _norm(rep_ward)),
                settlement_match=bool(m_settlement and rep_comm and _norm(m_settlement) == _norm(rep_comm)),
            ))

        for i in range(0, len(rows), 500):
            session.bulk_save_objects(rows[i:i + 500])
            session.commit()
        return {"status": "ok", "count": len(rows)}
    finally:
        session.close()


def summary() -> dict:
    session = SessionLocal()
    try:
        from sqlalchemy import func
        total = session.query(func.count(GpsPoint.id)).scalar() or 0
        outside_lga = session.query(func.count(GpsPoint.id)).filter(GpsPoint.in_lga == False).scalar() or 0  # noqa: E712
        outside_ward = session.query(func.count(GpsPoint.id)).filter(GpsPoint.in_ward == False).scalar() or 0  # noqa: E712
        outside_settlement = session.query(func.count(GpsPoint.id)).filter(GpsPoint.in_settlement == False).scalar() or 0  # noqa: E712
        lga_mismatch = session.query(func.count(GpsPoint.id)).filter(GpsPoint.in_lga == True, GpsPoint.lga_match == False).scalar() or 0  # noqa: E712
        ward_mismatch = session.query(func.count(GpsPoint.id)).filter(GpsPoint.in_ward == True, GpsPoint.ward_match == False).scalar() or 0  # noqa: E712
        settlement_mismatch = session.query(func.count(GpsPoint.id)).filter(GpsPoint.in_settlement == True, GpsPoint.settlement_match == False).scalar() or 0  # noqa: E712
        return {
            "total": total,
            "outside_lga": outside_lga,
            "outside_ward": outside_ward,
            "outside_settlement": outside_settlement,
            "lga_mismatch": lga_mismatch,
            "ward_mismatch": ward_mismatch,
            "settlement_mismatch": settlement_mismatch,
            "shapes_loaded": {
                "lga": len(_lga_shapes),
                "ward": len(_ward_shapes),
                "settlement": len(_settlement_shapes),
            },
            "planned_lgas": sorted(PLANNED_LGAS),
            "crs": {"shapes": SHAPE_CRS, "points": POINT_CRS, "aligned_via": "pyproj"},
        }
    finally:
        session.close()


def _aggregate_stats() -> dict:
    session = SessionLocal()
    try:
        from sqlalchemy import func
        lga_pts = dict(session.query(GpsPoint.matched_lga, func.count(GpsPoint.id))
                       .filter(GpsPoint.matched_lga.isnot(None))
                       .group_by(GpsPoint.matched_lga).all())
        ward_pts: dict = {}
        for lga, ward, cnt in session.query(GpsPoint.matched_lga, GpsPoint.matched_ward, func.count(GpsPoint.id))\
                .filter(GpsPoint.matched_lga.isnot(None), GpsPoint.matched_ward.isnot(None))\
                .group_by(GpsPoint.matched_lga, GpsPoint.matched_ward).all():
            ward_pts[(_norm(lga), _norm(ward))] = cnt
        visited_settlements: set = set()
        for lga, ward, sname in session.query(GpsPoint.matched_lga, GpsPoint.matched_ward, GpsPoint.matched_settlement)\
                .filter(GpsPoint.matched_settlement.isnot(None)).all():
            visited_settlements.add((_norm(lga), _norm(ward), _norm(sname)))
        reported_lgas = {_norm(x) for x, in session.query(GpsPoint.reported_lga).filter(GpsPoint.reported_lga.isnot(None)).distinct().all()}
        reported_wards = {(_norm(l), _norm(w)) for l, w in session.query(GpsPoint.reported_lga, GpsPoint.reported_ward)
                          .filter(GpsPoint.reported_lga.isnot(None), GpsPoint.reported_ward.isnot(None)).distinct().all()}
        reported_settlements = {(_norm(l), _norm(w), _norm(s)) for l, w, s in session.query(GpsPoint.reported_lga, GpsPoint.reported_ward, GpsPoint.reported_community)
                                .filter(GpsPoint.reported_community.isnot(None)).distinct().all()}
        return {
            "lga_pts": {_norm(k): v for k, v in lga_pts.items()},
            "ward_pts": ward_pts,
            "visited_settlements": visited_settlements,
            "reported_lgas": reported_lgas,
            "reported_wards": reported_wards,
            "reported_settlements": reported_settlements,
        }
    finally:
        session.close()


def _lga_total_settlements(lga_name: str) -> int:
    n = _norm(lga_name)
    return sum(1 for _g, a, _p in _settlement_shapes if _norm(a.get("lga_name")) == n)


def boundaries_as_geojson(level: str = "lga") -> dict:
    stats = _aggregate_stats()
    features: list[dict] = []

    if level == "lga":
        total_settle_by_lga: dict = {}
        visited_settle_by_lga: dict = {}
        for _g, a, _p in _settlement_shapes:
            n = _norm(a.get("lga_name"))
            total_settle_by_lga[n] = total_settle_by_lga.get(n, 0) + 1
        for (lga, _ward, _s) in stats["visited_settlements"]:
            visited_settle_by_lga[lga] = visited_settle_by_lga.get(lga, 0) + 1

        for geom, attrs, _p in _lga_shapes:
            name = attrs.get("lganame", "")
            n = _norm(name)
            pts = stats["lga_pts"].get(n, 0)
            has_data = n in stats["reported_lgas"] or pts > 0
            is_planned = n in PLANNED_LGAS
            total_s = total_settle_by_lga.get(n, 0)
            visited_s = visited_settle_by_lga.get(n, 0)
            pct = round((visited_s / total_s * 100), 1) if total_s > 0 else 0.0
            try:
                wgs = shp_transform(MERCATOR_TO_WGS84.transform, geom)
                features.append({
                    "type": "Feature",
                    "geometry": wgs.__geo_interface__,
                    "properties": {
                        "lganame": name,
                        "has_data": has_data,
                        "is_planned": is_planned,
                        "points": pts,
                        "total_settlements": total_s,
                        "visited_settlements": visited_s,
                        "coverage_pct": pct,
                    },
                })
            except Exception:
                continue

    elif level == "ward":
        total_settle_by_ward: dict = {}
        visited_settle_by_ward: dict = {}
        for _g, a, _p in _settlement_shapes:
            k = (_norm(a.get("lga_name")), _norm(a.get("ward_name")))
            total_settle_by_ward[k] = total_settle_by_ward.get(k, 0) + 1
        for (lga, ward, _s) in stats["visited_settlements"]:
            k = (lga, ward)
            visited_settle_by_ward[k] = visited_settle_by_ward.get(k, 0) + 1

        for geom, attrs, _p in _ward_shapes:
            lga = attrs.get("lganame", "")
            ward = attrs.get("wardname", "")
            key = (_norm(lga), _norm(ward))
            pts = stats["ward_pts"].get(key, 0)
            in_reported = key in stats["reported_wards"] or pts > 0
            if not in_reported:
                continue
            total_s = total_settle_by_ward.get(key, 0)
            visited_s = visited_settle_by_ward.get(key, 0)
            pct = round((visited_s / total_s * 100), 0) if total_s > 0 else 0
            try:
                wgs = shp_transform(MERCATOR_TO_WGS84.transform, geom)
                features.append({
                    "type": "Feature",
                    "geometry": wgs.__geo_interface__,
                    "properties": {
                        "lganame": lga,
                        "wardname": ward,
                        "points": pts,
                        "total_settlements": total_s,
                        "visited_settlements": visited_s,
                        "visited_pct": int(pct),
                        "has_data": True,
                    },
                })
            except Exception:
                continue

    elif level == "settlement":
        for geom, attrs, _p in _settlement_shapes:
            lga = attrs.get("lga_name", "")
            ward = attrs.get("ward_name", "")
            sname = attrs.get("settlement", "")
            key = (_norm(lga), _norm(ward), _norm(sname))
            in_reported = key in stats["reported_settlements"]
            visited = key in stats["visited_settlements"]
            if not in_reported and not visited:
                continue
            try:
                wgs = shp_transform(MERCATOR_TO_WGS84.transform, geom)
                features.append({
                    "type": "Feature",
                    "geometry": wgs.__geo_interface__,
                    "properties": {
                        "lganame": lga,
                        "wardname": ward,
                        "settlement": sname,
                        "visited": visited,
                    },
                })
            except Exception:
                continue

    return {"type": "FeatureCollection", "features": features}


def _issue_counts_by(group_cols: list, filters: list = None) -> dict:
    from sqlalchemy import func, or_, and_
    session = SessionLocal()
    try:
        base = session.query(*group_cols, func.count(GpsPoint.id))
        if filters:
            for f in filters:
                base = base.filter(f)
        totals: dict = {}
        for row in base.group_by(*group_cols).all():
            key = tuple(_norm(row[i]) for i in range(len(group_cols)))
            totals[key] = row[-1]

        issue_q = session.query(*group_cols, func.count(GpsPoint.id))
        if filters:
            for f in filters:
                issue_q = issue_q.filter(f)
        issue_q = issue_q.filter(or_(
            GpsPoint.in_lga == False,  # noqa: E712
            GpsPoint.in_ward == False,
            GpsPoint.in_settlement == False,
        ))
        issues: dict = {}
        for row in issue_q.group_by(*group_cols).all():
            key = tuple(_norm(row[i]) for i in range(len(group_cols)))
            issues[key] = row[-1]

        dup_key = func.lower(func.trim(func.cast(GpsPoint.lat, __import__("sqlalchemy").String))) + "|" + func.lower(func.trim(func.cast(GpsPoint.lng, __import__("sqlalchemy").String)))
        dup_counts = dict(session.query(dup_key.label("k"), func.count(GpsPoint.id)).group_by("k").all())
        dup_set = {k for k, c in dup_counts.items() if c > 1}
        return {"totals": totals, "issues": issues, "dup_set": dup_set}
    finally:
        session.close()


def lga_stats() -> list[dict]:
    stats = _aggregate_stats()
    from sqlalchemy import func
    session = SessionLocal()
    try:
        rows_pts = session.query(GpsPoint).all()
    finally:
        session.close()

    dup_key_map: dict = {}
    for r in rows_pts:
        k = (round(r.lat, 6), round(r.lng, 6))
        dup_key_map[k] = dup_key_map.get(k, 0) + 1
    def _is_dup(r):
        return dup_key_map.get((round(r.lat, 6), round(r.lng, 6)), 0) > 1

    total_by_lga: dict = {}
    issues_by_lga: dict = {}
    for r in rows_pts:
        lkey = _norm(r.reported_lga) or _norm(r.matched_lga)
        if not lkey:
            continue
        total_by_lga[lkey] = total_by_lga.get(lkey, 0) + 1
        if _is_dup(r) or not r.in_lga or not r.in_ward or not r.in_settlement:
            issues_by_lga[lkey] = issues_by_lga.get(lkey, 0) + 1

    rows: list[dict] = []
    for _g, a, _p in _lga_shapes:
        name = a.get("lganame", "")
        n = _norm(name)
        pts = total_by_lga.get(n, 0)
        iss = issues_by_lga.get(n, 0)
        issues_pct = round((iss / pts * 100), 0) if pts else 0
        rows.append({
            "name": name,
            "points": pts,
            "issues": iss,
            "issues_pct": int(issues_pct),
            "has_data": (n in stats["reported_lgas"]) or pts > 0,
            "is_planned": n in PLANNED_LGAS,
        })
    rows.sort(key=lambda r: (not r["is_planned"], r["name"].lower()))
    return rows


def _wards_or_settlements(level: str, lga: str, ward: str | None = None) -> list[dict]:
    session = SessionLocal()
    try:
        q = session.query(GpsPoint).filter(GpsPoint.reported_lga.isnot(None))
        rows = [r for r in q.all() if _norm(r.reported_lga) == _norm(lga)]
    finally:
        session.close()
    if ward:
        rows = [r for r in rows if _norm(r.reported_ward) == _norm(ward)]

    dup_map: dict = {}
    for r in rows:
        k = (round(r.lat, 6), round(r.lng, 6))
        dup_map[k] = dup_map.get(k, 0) + 1

    buckets: dict = {}
    for r in rows:
        key_val = r.reported_ward if level == "ward" else r.reported_community
        if not key_val:
            continue
        key = _norm(key_val)
        b = buckets.setdefault(key, {"name": str(key_val).strip(), "points": 0, "issues": 0})
        b["points"] += 1
        is_dup = dup_map.get((round(r.lat, 6), round(r.lng, 6)), 0) > 1
        if is_dup or not r.in_lga or not r.in_ward or not r.in_settlement:
            b["issues"] += 1

    out: list[dict] = []
    for b in buckets.values():
        pct = round(b["issues"] / b["points"] * 100, 0) if b["points"] else 0
        b["issues_pct"] = int(pct)
        out.append(b)
    out.sort(key=lambda x: x["name"].lower())
    return out


def ward_stats(lga: str) -> list[dict]:
    return _wards_or_settlements("ward", lga)


def settlement_stats(lga: str, ward: str) -> list[dict]:
    return _wards_or_settlements("settlement", lga, ward)


def all_points() -> list[dict]:
    session = SessionLocal()
    try:
        rows = session.query(GpsPoint).all()
        return [{
            "lat": r.lat, "lng": r.lng,
            "reported_lga": r.reported_lga,
            "reported_ward": r.reported_ward,
            "reported_community": r.reported_community,
            "matched_lga": r.matched_lga,
            "matched_ward": r.matched_ward,
            "matched_settlement": r.matched_settlement,
            "in_lga": r.in_lga,
            "in_ward": r.in_ward,
            "in_settlement": r.in_settlement,
            "ra": r.ra,
        } for r in rows]
    finally:
        session.close()


def flagged_points(limit: int = 500) -> list[dict]:
    session = SessionLocal()
    try:
        q = session.query(GpsPoint).filter(
            (GpsPoint.in_lga == False) |  # noqa: E712
            (GpsPoint.in_ward == False) |
            (GpsPoint.in_settlement == False) |
            (GpsPoint.lga_match == False) |
            (GpsPoint.ward_match == False) |
            (GpsPoint.settlement_match == False)
        ).limit(limit).all()
        return [{
            "id": p.id,
            "uuid": p.uuid,
            "ra": p.ra,
            "lat": p.lat,
            "lng": p.lng,
            "reported_lga": p.reported_lga,
            "reported_ward": p.reported_ward,
            "reported_community": p.reported_community,
            "matched_lga": p.matched_lga,
            "matched_ward": p.matched_ward,
            "matched_settlement": p.matched_settlement,
            "in_lga": p.in_lga,
            "in_ward": p.in_ward,
            "in_settlement": p.in_settlement,
        } for p in q]
    finally:
        session.close()
