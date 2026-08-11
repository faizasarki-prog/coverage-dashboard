"""One-time migration: copy the existing SQLite database into PostgreSQL.

Run from the project root (with .env present so DATABASE_URL resolves):

    python scripts/migrate_to_postgres.py [--src sqlite:///./admin.db]

Source defaults to the repo's SQLite admin.db; destination defaults to the
DATABASE_URL in .env (the PostgreSQL server).

Notes:
- Creates the PostGIS extension and the full schema on the destination.
- Copies each table only if the destination table is empty (idempotent).
- Rows that violate a foreign key (orphaned legacy rows) are skipped so the
  migration never aborts on legacy data.
- gps_points rows get a PostGIS geom derived from their lat/lng columns.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData, Table, create_engine, select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

# FK-safe copy order (parents before children).
TABLE_ORDER = [
    "permissions",
    "roles",
    "projects",
    "users",
    "role_permissions",
    "user_projects",
    "user_lgas",
    "validator_lga_assignments",
    "audit_logs",
    "validation_decisions",
    "validator_flags",
    "app_settings",
    "gps_points",
]


def _insert_rows(conn, t_dst: Table, rows: list[dict]) -> tuple[int, int]:
    """Insert rows one-by-one inside savepoints; return (inserted, skipped)."""
    inserted = 0
    skipped = 0
    for r in rows:
        try:
            with conn.begin_nested():
                conn.execute(t_dst.insert(), r)
            inserted += 1
        except IntegrityError:
            skipped += 1
    return inserted, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy SQLite data into PostgreSQL.")
    ap.add_argument("--src", default="sqlite:///./admin.db", help="Source SQLite URL.")
    ap.add_argument("--dst", default=None, help="PostgreSQL URL (default: DATABASE_URL).")
    args = ap.parse_args()

    dst_url = args.dst or os.environ.get("DATABASE_URL")
    if not dst_url:
        print("No destination database. Set DATABASE_URL or pass --dst.")
        return 1

    from backend.database import Base

    src = create_engine(args.src, connect_args={"check_same_thread": False})
    dst = create_engine(dst_url)

    print("[migrate] enabling PostGIS on destination ...")
    with dst.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=dst)

    src_meta = MetaData()
    dst_meta = MetaData()
    src_tables: dict[str, Table | None] = {}
    dst_tables: dict[str, Table | None] = {}
    for name in TABLE_ORDER:
        try:
            src_tables[name] = Table(name, src_meta, autoload_with=src)
        except Exception:
            src_tables[name] = None
        try:
            dst_tables[name] = Table(name, dst_meta, autoload_with=dst)
        except Exception:
            dst_tables[name] = None

    total = 0
    copied_tables: list[str] = []
    with dst.begin() as conn:
        for name in TABLE_ORDER:
            t_src = src_tables.get(name)
            t_dst = dst_tables.get(name)
            if t_src is None or t_dst is None:
                continue
            existing = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            if existing:
                print(f"[migrate] {name}: skipped (already has {existing} rows)")
                continue
            with src.connect() as sconn:
                rows = [dict(r) for r in sconn.execute(select(t_src)).mappings().all()]
            if not rows:
                print(f"[migrate] {name}: nothing to copy")
                continue
            common = [c.name for c in t_src.columns if c.name in t_dst.columns]
            if name == "gps_points" and "geom" in t_dst.columns and "lat" in t_src.columns and "lng" in t_src.columns:
                rows = [
                    {k: r[k] for k in common if k != "geom"}
                    | {"geom": f"SRID=4326;POINT({r['lng']} {r['lat']})"}
                    for r in rows
                ]
            else:
                rows = [{k: r[k] for k in common} for r in rows]
            inserted, skipped = _insert_rows(conn, t_dst, rows)
            print(f"[migrate] {name}: copied {inserted} rows" + (f" (skipped {skipped} FK-orphaned)" if skipped else ""))
            total += inserted
            if inserted:
                copied_tables.append(name)

        # Advance each copied table's id sequence past the highest migrated id so
        # future inserts (users, projects, decisions, ...) never collide.
        for name in copied_tables:
            t_dst = dst_tables.get(name)
            if t_dst is None or "id" not in t_dst.columns:
                continue
            seq = conn.execute(text(
                "SELECT pg_get_serial_sequence(:t, 'id')"
            ), {"t": name}).scalar()
            if seq:
                conn.execute(text(
                    "SELECT setval(:seq, (SELECT COALESCE(MAX(id), 1) FROM {}))".format(name)
                ), {"seq": seq})
    print(f"[migrate] done. {total} rows copied in total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
