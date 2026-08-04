from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..auth import generate_invite_token, hash_password
from .. import data_service, geospatial
from ..database import AuditLog, Project, Role, User, UserLGA, get_db

PROJECT_UPLOADS_DIR: Path = Path(__file__).resolve().parent.parent.parent / "data" / "project_uploads"
PROJECT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

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
    project_ids: list[int] = []


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
    for pid in payload.project_ids or []:
        proj = db.query(Project).filter(Project.id == int(pid)).first()
        if proj:
            u.projects.append(proj)
    db.commit()
    _audit(db, None, "user.create", f"created user {email} with role {payload.role}, {len(payload.lgas or [])} LGA(s)", request)
    return {
        "id": u.id, "name": u.name, "email": u.email, "role": payload.role,
        "lgas": payload.lgas or [],
        "invite_url": f"/set-password?token={invite}" if invite else None,
    }


class LgaUpdate(BaseModel):
    lgas: list[str] = []


@router.put("/api/users/{user_id}/lgas")
def update_user_lgas(user_id: int, payload: LgaUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    db.query(UserLGA).filter(UserLGA.user_id == user_id).delete()
    for lga in payload.lgas or []:
        lga = str(lga).strip()
        if lga:
            db.add(UserLGA(user_id=user_id, lga_name=lga))
    db.commit()
    _audit(db, None, "user.lgas_update", f"user={u.email} lgas={payload.lgas}", request)
    return {"user_id": user_id, "lgas": payload.lgas or []}


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
def list_users(project_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(User).order_by(User.created_at.desc())
    if project_id:
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj:
            q = q.filter(User.projects.any(Project.id == project_id))
    users = q.all()
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


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "state": p.state,
        "is_active": p.is_active,
        "is_default": bool(p.is_default),
        "kobo_api_url": p.kobo_api_url,
        "has_kobo_token": bool(p.kobo_api_token),
        "planning_file": Path(p.planning_file_path).name if p.planning_file_path else None,
        "geospatial_zip": Path(p.geospatial_zip_path).name if p.geospatial_zip_path else None,
        "planned_lgas": [x.strip() for x in (p.planned_lgas or "").split(",") if x.strip()],
        "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
        "last_sync_rows": p.last_sync_rows,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "user_access_active": True,
    }


@router.get("/api/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.query(Project).order_by(Project.id.asc()).all()
    return [_project_to_dict(p) for p in projects]


@router.get("/api/projects/active")
def active_project(db: Session = Depends(get_db)) -> dict:
    p = db.query(Project).filter(Project.is_default == True).first()  # noqa: E712
    if not p:
        p = db.query(Project).order_by(Project.id.asc()).first()
    if not p:
        raise HTTPException(status_code=404, detail="No projects configured")
    return _project_to_dict(p)


def _save_upload(file: UploadFile, project_id: int, suffix: str) -> str:
    if not file or not file.filename:
        return None
    safe_name = Path(file.filename).name
    dst = PROJECT_UPLOADS_DIR / f"p{project_id}_{suffix}_{safe_name}"
    with dst.open("wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return str(dst)


def _load_project_data(project_id: int) -> str | None:
    """Load a project's Kobo data + geospatial and sync its GPS points.

    Uses the project's cached export when available so toggling projects is
    fast; Kobo is only re-fetched when there is no cache yet.
    Returns a warning on failure.
    """
    try:
        warning = data_service.load_data(project_id=project_id)
    except Exception as e:
        return str(e)
    try:
        geospatial.load(project_id=project_id)
        cov = getattr(data_service, "cov", None)
        if cov is not None and len(cov) > 0:
            geospatial.sync_gps_points(cov, project_id)
    except Exception as e:
        return f"data loaded, but geospatial processing failed: {e}"
    return warning


@router.post("/api/projects", status_code=201)
async def create_project(
    request: Request,
    name: str = Form(...),
    state: str = Form(...),
    kobo_api_url: str = Form(""),
    kobo_api_token: str = Form(""),
    planned_lgas: str = Form(""),
    description: str = Form(""),
    is_default: bool = Form(False),
    planning_file: UploadFile | None = File(None),
    geospatial_zip: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> dict:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    if db.query(Project).filter(Project.name == name).first():
        raise HTTPException(status_code=409, detail=f"Project '{name}' already exists")
    p = Project(
        name=name,
        state=state.strip() or None,
        description=description.strip() or None,
        kobo_api_url=kobo_api_url.strip() or None,
        kobo_api_token=kobo_api_token.strip() or None,
        planned_lgas=planned_lgas.strip() or None,
        is_active=True,
        is_default=False,
    )
    db.add(p)
    db.flush()
    if planning_file and planning_file.filename:
        p.planning_file_path = _save_upload(planning_file, p.id, "plan")
    if geospatial_zip and geospatial_zip.filename:
        p.geospatial_zip_path = _save_upload(geospatial_zip, p.id, "geo")
    if is_default:
        db.query(Project).update({Project.is_default: False})
        p.is_default = True
    db.commit()
    result = _project_to_dict(p)
    if is_default:
        result["data_warning"] = _load_project_data(p.id)
    _audit(db, None, "project.create", f"name={name} state={state}", request)
    return result


@router.post("/api/projects/{project_id}/upload")
async def upload_project_files(
    project_id: int,
    request: Request,
    planning_file: UploadFile | None = File(None),
    geospatial_zip: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> dict:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    changes = []
    if planning_file and planning_file.filename:
        p.planning_file_path = _save_upload(planning_file, p.id, "plan")
        changes.append("planning")
    if geospatial_zip and geospatial_zip.filename:
        p.geospatial_zip_path = _save_upload(geospatial_zip, p.id, "geo")
        changes.append("geospatial")
    db.commit()
    _audit(db, None, "project.upload", f"project={p.name} files={','.join(changes)}", request)
    return _project_to_dict(p)


@router.post("/api/projects/{project_id}/activate")
def activate_project(project_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    db.query(Project).update({Project.is_default: False})
    p.is_default = True
    db.commit()
    result = _project_to_dict(p)
    result["data_warning"] = _load_project_data(project_id)
    _audit(db, None, "project.activate", f"project={p.name}", request)
    return result


@router.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)) -> None:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if p.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the active project; activate another first")
    for path_attr in ("planning_file_path", "geospatial_zip_path"):
        fp = getattr(p, path_attr, None)
        if fp:
            try: Path(fp).unlink(missing_ok=True)
            except Exception: pass
    name = p.name
    db.delete(p)
    db.commit()
    _audit(db, None, "project.delete", f"project={name}", request)


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
