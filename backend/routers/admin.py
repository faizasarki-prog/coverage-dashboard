from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..auth import generate_invite_token, hash_password
from ..database import AuditLog, Project, Role, User, UserLGA, get_db

router = APIRouter()


def _audit(db: Session, actor_id: int | None, action: str, details: str, request: Request) -> None:
    ip = request.client.host if request.client else None
    db.add(AuditLog(actor_id=actor_id, action=action, details=details, ip_address=ip))
    db.commit()


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: str
    password: str | None = None
    lgas: list[str] = []


@router.post("/api/users", status_code=201)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail=f"User {email} already exists")
    role = db.query(Role).filter(Role.name == payload.role).first()
    if not role:
        raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")
    invite = None
    if payload.password:
        pwd_hash = hash_password(payload.password)
        must_change = False
    else:
        pwd_hash = hash_password(generate_invite_token())
        invite = generate_invite_token()
        must_change = True
    u = User(
        name=payload.name.strip(),
        email=email,
        password_hash=pwd_hash,
        role_id=role.id,
        is_active=True,
        must_change_password=must_change,
        invite_token=invite,
    )
    db.add(u)
    db.flush()
    for lga in payload.lgas or []:
        lga = str(lga).strip()
        if lga:
            db.add(UserLGA(user_id=u.id, lga_name=lga))
    db.commit()
    _audit(db, None, "user.create", f"created user {email} with role {payload.role}, {len(payload.lgas or [])} LGA(s)", request)
    return {
        "id": u.id, "name": u.name, "email": u.email, "role": payload.role,
        "lgas": payload.lgas or [],
        "invite_url": f"/set-password?token={invite}" if invite else None,
    }


@router.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)) -> None:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    email = u.email
    db.query(UserLGA).filter(UserLGA.user_id == user_id).delete()
    db.delete(u)
    db.commit()
    _audit(db, None, "user.delete", f"deleted user {email}", request)


@router.get("/api/users")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    users = db.query(User).order_by(User.created_at.desc()).all()
    out: list[dict] = []
    for u in users:
        role_name = u.role.name if u.role else None
        lgas = [ul.lga_name for ul in db.query(UserLGA).filter(UserLGA.user_id == u.id).all()]
        projects = [{"id": p.id, "name": p.name} for p in getattr(u, "projects", [])]
        out.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": role_name,
            "is_active": u.is_active,
            "lgas": lgas,
            "projects": projects,
            "default_project_id": getattr(u, "active_project_id", None),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "has_password": bool(u.password_hash),
        })
    return out


@router.get("/api/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.query(Project).order_by(Project.id.asc()).all()
    return [{
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "user_access_active": True,
    } for p in projects]


@router.get("/api/audit-log")
def list_audit(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    out: list[dict] = []
    for r in rows:
        user_label = None
        if r.actor_id:
            u = db.query(User).filter(User.id == r.actor_id).first()
            user_label = u.name if u else f"#{r.actor_id}"
        out.append({
            "id": r.id,
            "user": user_label,
            "action": r.action,
            "details": r.details,
            "ip": r.ip_address,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out
