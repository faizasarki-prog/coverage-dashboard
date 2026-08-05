from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import data_service, geospatial, settings
from .auth import get_current_user
from .database import User, init_db
from .routers.auth import limiter as auth_limiter
from .routers.admin import router as admin_router
from .routers.auth import router as auth_router
from .routers.data import router as data_router

BASE_DIR: Path = Path(__file__).resolve().parent.parent
TEMPLATES_DIR: Path = BASE_DIR / "templates"
STATIC_DIR: Path = BASE_DIR / "static"
FRONTEND_DIST: Path = BASE_DIR / "frontend_dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    data_service.load_data()
    try:
        geospatial.load(project_id=data_service.current_project_id)
        cov = getattr(data_service, "cov", None)
        if cov is not None and len(cov) > 0:
            geospatial.sync_gps_points(cov, data_service.current_project_id)
    except Exception as e:
        print(f"[geospatial] skipped: {e}")
    yield


_docs_url = "/docs" if settings.ENABLE_DOCS else None
_redoc_url = "/redoc" if settings.ENABLE_DOCS else None
_openapi_url = "/openapi.json" if settings.ENABLE_DOCS else None

app = FastAPI(
    title="Coverage Dashboard",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_REACT_INDEX = FRONTEND_DIST / "index.html"
_REACT_ASSETS = FRONTEND_DIST / "assets"
if _REACT_INDEX.exists() and _REACT_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(_REACT_ASSETS)), name="react_assets")

app.include_router(data_router)
app.include_router(auth_router)
app.include_router(admin_router)


def _serve_react_or(fallback_path: Path) -> str:
    if _REACT_INDEX.exists():
        return _REACT_INDEX.read_text(encoding="utf-8")
    return fallback_path.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _serve_react_or(TEMPLATES_DIR / "dashboard.html")


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return _serve_react_or(STATIC_DIR / "login.html")


@app.get("/set-password", response_class=HTMLResponse)
def set_password_page() -> str:
    page = STATIC_DIR / "set_password.html"
    return page.read_text(encoding="utf-8") if page.exists() else login_page()


@app.get("/dashboard-legacy", response_class=HTMLResponse)
def dashboard_legacy() -> str:
    return (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")


def _geo_lgas(user: User) -> list[str] | None:
    if user.role and user.role.name == "validator":
        lgas = [ul.lga_name for ul in user.lgas]
        return lgas or None
    return None


@app.get("/api/geo/summary")
def geo_summary(user: User = Depends(get_current_user)) -> dict:
    return geospatial.summary(lgas=_geo_lgas(user))


@app.get("/api/geo/flagged")
def geo_flagged(limit: int = 500, user: User = Depends(get_current_user)) -> list[dict]:
    return geospatial.flagged_points(limit=limit, lgas=_geo_lgas(user))


@app.get("/api/geo/boundaries")
def geo_boundaries(level: str = "lga", user: User = Depends(get_current_user)) -> dict:
    return geospatial.boundaries_as_geojson(level, lgas=_geo_lgas(user))


@app.get("/api/geo/lga-stats")
def geo_lga_stats(user: User = Depends(get_current_user)) -> list[dict]:
    return geospatial.lga_stats(lgas=_geo_lgas(user))


@app.get("/api/geo/ward-stats")
def geo_ward_stats(lga: str, user: User = Depends(get_current_user)) -> list[dict]:
    return geospatial.ward_stats(lga, lgas=_geo_lgas(user))


@app.get("/api/geo/settlement-stats")
def geo_settlement_stats(lga: str, ward: str, user: User = Depends(get_current_user)) -> list[dict]:
    return geospatial.settlement_stats(lga, ward, lgas=_geo_lgas(user))


@app.get("/api/geo/points")
def geo_points(user: User = Depends(get_current_user)) -> list[dict]:
    return geospatial.all_points(lgas=_geo_lgas(user))


@app.get("/api/geo/issues-by-ra")
def geo_issues_by_ra(user: User = Depends(get_current_user)) -> list[dict]:
    return geospatial.issues_by_ra(lgas=_geo_lgas(user))


@app.get("/api/data/status")
def data_status(user: User = Depends(get_current_user)) -> dict:
    if not user.role or user.role.name not in ("super_admin", "admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not permitted")
    proj = data_service._project_row()
    return {
        "source": data_service.data_source,
        "loaded_at": data_service.data_loaded_at,
        "project": proj["name"] if proj else None,
        "project_id": proj["id"] if proj else None,
        "kobo_url": (proj or {}).get("kobo_api_url") or settings.KOBO_DATA_URL,
        "kobo_token_set": bool((proj or {}).get("kobo_api_token") or settings.KOBO_API_TOKEN),
    }


@app.post("/api/data/refresh")
def data_refresh(user: User = Depends(get_current_user)) -> dict:
    if not user.role or user.role.name not in ("super_admin", "admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not permitted")
    warning = data_service.load_data(force_refresh=True)
    try:
        cov = getattr(data_service, "cov", None)
        if cov is not None and len(cov) > 0:
            geospatial.load(project_id=data_service.current_project_id)
            geospatial.sync_gps_points(cov, data_service.current_project_id, force=True)
    except Exception as e:
        print(f"[geospatial] rebuild after refresh failed: {e}")
    return {
        "status": "ok",
        "source": data_service.data_source,
        "loaded_at": data_service.data_loaded_at,
        "rows": int(len(data_service.cov)) if data_service.cov is not None else 0,
        "warning": warning,
    }


@app.get("/api/login-stats")
def login_stats() -> dict:
    from sqlalchemy import func
    from .database import AuditLog, SessionLocal
    with SessionLocal() as db:
        count = db.query(func.count(AuditLog.id)).filter(AuditLog.action == "login_success").scalar() or 0
    return {"count": int(count)}
