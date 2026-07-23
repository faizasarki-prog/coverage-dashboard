from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..auth import create_access_token, verify_password
from ..database import AuditLog, User, get_db

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


def _audit(
    db: Session,
    actor_id: int | None,
    action: str,
    details: str,
    request: Request,
) -> None:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    row = AuditLog(
        actor_id=actor_id,
        action=action,
        details=details,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(row)
    db.commit()


@router.post("/api/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).one_or_none()

    if not user:
        _audit(db, None, "login_failed", f"unknown_email={email}", request)
        return {
            "access_token": None,
            "token_type": None,
            "error": "invalid_credentials",
            "message": "Invalid email or password.",
        }

    if not verify_password(body.password, user.password_hash):
        _audit(db, user.id, "login_failed", "bad_password", request)
        return {
            "access_token": None,
            "token_type": None,
            "error": "invalid_credentials",
            "message": "Invalid email or password.",
        }

    if not user.is_active:
        _audit(db, user.id, "login_revoked", "inactive_user", request)
        return {
            "access_revoked": True,
            "revoke_scope": "global",
            "name": user.name,
            "email": user.email,
            "message": "Your access has been revoked. Contact an administrator.",
        }

    role_name = user.role.name if user.role else "public"
    permissions = [p.name for p in user.role.permissions] if user.role else []
    lgas = [ul.lga_name for ul in user.lgas]
    project_ids = [p.id for p in user.projects]

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=role_name,
        permissions=permissions,
        lgas=lgas,
        project_ids=project_ids,
    )
    _audit(db, user.id, "login_success", f"role={role_name}", request)

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role_name,
        "name": user.name,
        "email": user.email,
        "permissions": permissions,
        "lgas": lgas,
        "active_project_id": user.active_project_id,
        "redirect": "/admin",
        "must_change_password": user.must_change_password,
    }
