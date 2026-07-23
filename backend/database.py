from datetime import datetime
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from . import settings

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_projects = Table(
    "user_projects",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    permissions = relationship("Permission", secondary=role_permissions, backref="roles")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    invite_token = Column(String(128), nullable=True, index=True)
    invite_expires_at = Column(DateTime, nullable=True)
    active_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    role = relationship("Role")
    projects = relationship("Project", secondary=user_projects, backref="users")
    lgas = relationship("UserLGA", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserLGA(Base):
    __tablename__ = "user_lgas"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lga_name = Column(String(200), nullable=False)
    user = relationship("User", back_populates="lgas")


class ValidatorLGAAssignment(Base):
    __tablename__ = "validator_lga_assignments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lga_name = Column(String(200), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class GpsPoint(Base):
    __tablename__ = "gps_points"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(64), index=True)
    ra = Column(Text, nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    reported_lga = Column(Text, nullable=True)
    reported_ward = Column(Text, nullable=True)
    reported_community = Column(Text, nullable=True)
    matched_lga = Column(Text, nullable=True)
    matched_ward = Column(Text, nullable=True)
    matched_settlement = Column(Text, nullable=True)
    in_lga = Column(Boolean, default=False, nullable=False)
    in_ward = Column(Boolean, default=False, nullable=False)
    in_settlement = Column(Boolean, default=False, nullable=False)
    lga_match = Column(Boolean, default=False, nullable=False)
    ward_match = Column(Boolean, default=False, nullable=False)
    settlement_match = Column(Boolean, default=False, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


ROLES_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ["view_dashboard", "manage_users", "configure_project", "validate_data", "upload_data"],
    "admin": ["view_dashboard", "validate_data", "upload_data"],
    "validator": ["view_dashboard", "validate_data"],
    "public": ["view_dashboard"],
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _run_sqlite_migrations() -> None:
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    additions: list[tuple[str, str, str]] = [
        ("users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0"),
        ("users", "invite_token", "VARCHAR(128)"),
        ("users", "invite_expires_at", "DATETIME"),
        ("users", "active_project_id", "INTEGER"),
    ]
    with engine.begin() as conn:
        for table, col, ddl in additions:
            exists_rows = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
            ), {"t": table}).fetchone()
            if not exists_rows:
                continue
            if not _sqlite_column_exists(conn, table, col):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def _seed_roles_and_permissions(db: Session) -> dict[str, Role]:
    all_perms: set[str] = {p for perms in ROLES_PERMISSIONS.values() for p in perms}
    perm_objects: dict[str, Permission] = {}
    for pname in all_perms:
        existing = db.query(Permission).filter(Permission.name == pname).one_or_none()
        if not existing:
            existing = Permission(name=pname)
            db.add(existing)
            db.flush()
        perm_objects[pname] = existing

    role_objects: dict[str, Role] = {}
    for rname, perms in ROLES_PERMISSIONS.items():
        role = db.query(Role).filter(Role.name == rname).one_or_none()
        if not role:
            role = Role(name=rname)
            db.add(role)
            db.flush()
        current_perm_names = {p.name for p in role.permissions}
        for pname in perms:
            if pname not in current_perm_names:
                role.permissions.append(perm_objects[pname])
        role_objects[rname] = role
    db.commit()
    return role_objects


def _seed_super_admin(db: Session, roles: dict[str, Role]) -> None:
    from .auth import hash_password

    email = settings.SUPER_ADMIN_EMAIL.strip().lower()
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing:
        return
    admin = User(
        name="Super Admin",
        email=email,
        password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
        role_id=roles["super_admin"].id,
        is_active=True,
        must_change_password=False,
    )
    db.add(admin)
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations()
    with SessionLocal() as db:
        roles = _seed_roles_and_permissions(db)
        _seed_super_admin(db, roles)
