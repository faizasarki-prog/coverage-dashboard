from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_optional_user, hash_password, verify_password
from ..database import AuditLog, User, get_db

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class SetPasswordRequest(BaseModel):
    token: str = ""
    current_password: str = ""
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
        "project_ids": project_ids,
        "active_project_id": user.active_project_id,
        "redirect": "/admin",
        "must_change_password": user.must_change_password,
    }


@router.post("/api/set-password")
@limiter.limit("20/minute")
def set_password(
    request: Request,
    body: SetPasswordRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Set a password via an invite link token, or for a signed-in user whose
    password must change."""
    from datetime import datetime

    if len(body.password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if body.token.strip():
        user = db.query(User).filter(User.invite_token == body.token.strip()).one_or_none()
        if not user:
            _audit(db, None, "invite.complete_failed", "unknown_token", request)
            raise HTTPException(status_code=400, detail="This invitation link is invalid. Ask your administrator for a new one.")
        if user.invite_expires_at and user.invite_expires_at < datetime.utcnow():
            _audit(db, user.id, "invite.complete_failed", "expired_token", request)
            raise HTTPException(status_code=400, detail="This invitation link has expired. Ask your administrator for a new one.")
        if not user.must_change_password and not user.invite_token:
            raise HTTPException(status_code=400, detail="This invitation link has already been used.")
        user.password_hash = hash_password(body.password)
        user.must_change_password = False
        user.invite_token = None
        user.invite_expires_at = None
        db.commit()
        _audit(db, user.id, "invite.complete", "password set", request)
        return {"ok": True, "email": user.email}

    if not user:
        raise HTTPException(status_code=401, detail="Missing invite token or authentication")
    if not user.must_change_password:
        raise HTTPException(status_code=400, detail="Your password does not need to change.")
    if not verify_password(body.current_password or "", user.password_hash):
        _audit(db, user.id, "password.change_failed", "wrong_current_password", request)
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    user.password_hash = hash_password(body.password)
    user.must_change_password = False
    db.commit()
    _audit(db, user.id, "password.change", "password changed", request)
    return {"ok": True, "email": user.email}
