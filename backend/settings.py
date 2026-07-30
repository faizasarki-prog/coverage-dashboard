import os
from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError(
        "SECRET_KEY environment variable is required and must be at least 32 bytes."
    )

SUPER_ADMIN_EMAIL: str = os.environ.get("SUPER_ADMIN_EMAIL", "admin@ehealthnigeria.org")
SUPER_ADMIN_PASSWORD: str = os.environ.get("SUPER_ADMIN_PASSWORD", "changeme-in-prod-abc123!")

DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./admin.db")

_origins_raw: str = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _origins_raw.split(",") if o.strip()]

ENABLE_DOCS: bool = os.environ.get("ENABLE_DOCS", "false").lower() in ("1", "true", "yes")

ACCESS_TOKEN_TTL_SECONDS: int = 8 * 60 * 60
JWT_ALGORITHM: str = "HS256"

# Kobo data source — projects fetched via API instead of a local Excel file.
# Each entry: {"name": "Sokoto Coverage", "url": "...", "cache": "sokoto.xlsx"}.
# For now a single project is configured via env; more can be added as the
# programme expands to other states.
KOBO_API_TOKEN: str = os.environ.get("KOBO_API_TOKEN", "").strip()
KOBO_DATA_URL: str = os.environ.get(
    "KOBO_DATA_URL",
    "https://kf.kobotoolbox.org/api/v2/assets/aC7agtm3my3Rfq4m4kYaF7/export-settings/esq4pbxk8MMWxBoGSPq5yMu/data.xlsx",
).strip()
KOBO_REFRESH_MINUTES: int = int(os.environ.get("KOBO_REFRESH_MINUTES", "60"))
