from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import data_service, geospatial, settings
from .database import init_db
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
        geospatial.load()
        cov = getattr(data_service, "cov", None)
        if cov is not None:
            geospatial.rebuild_gps_points_table(cov)
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


@app.get("/dashboard-legacy", response_class=HTMLResponse)
def dashboard_legacy() -> str:
    return (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")


@app.get("/api/geo/summary")
def geo_summary() -> dict:
    return geospatial.summary()


@app.get("/api/geo/flagged")
def geo_flagged(limit: int = 500) -> list[dict]:
    return geospatial.flagged_points(limit=limit)


@app.get("/api/geo/boundaries")
def geo_boundaries(level: str = "lga") -> dict:
    return geospatial.boundaries_as_geojson(level)


@app.get("/api/geo/lga-stats")
def geo_lga_stats() -> list[dict]:
    return geospatial.lga_stats()


@app.get("/api/geo/ward-stats")
def geo_ward_stats(lga: str) -> list[dict]:
    return geospatial.ward_stats(lga)


@app.get("/api/geo/settlement-stats")
def geo_settlement_stats(lga: str, ward: str) -> list[dict]:
    return geospatial.settlement_stats(lga, ward)


@app.get("/api/geo/points")
def geo_points() -> list[dict]:
    return geospatial.all_points()


@app.get("/api/login-stats")
def login_stats() -> dict:
    from sqlalchemy import func
    from .database import AuditLog, SessionLocal
    with SessionLocal() as db:
        count = db.query(func.count(AuditLog.id)).filter(AuditLog.action == "login_success").scalar() or 0
    return {"count": int(count)}
