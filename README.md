# SARMAAN II Coverage Survey Dashboard

Interactive monitoring dashboard for the **SARMAAN II** (Safety and Antimicrobial Resistance of Mass Administration of Azithromycin in Children 1–59 Months) coverage survey

Built with Flask, vanilla HTML/CSS/JS, and Chart.js. Designed for Programme Managers, Data Analysts, GIS Analysts, Validators, and Field Coordinators.

---

## Features

- **Home** — Hero coverage dial, KPI cards, daily household chart, CDD visitation chart
- **Completion** — Planned vs reached communities/LGAs, settlement completion table
- **Quality Checks** — 7 data-quality metric cards (duplicates, ineligible children, GPS, validation) + LGA error chart + RA error log
- **Supervision** — RA performance table, stacked bar chart of offered/swallowed/declined AZM
- **Geospatial** — Leaflet map of survey points, stacked GPS detection, mock GPS detection
- **AI / Analytics** — Coverage insights, risk scorecards, model-ready export
- **Validators** — Validation checks table, per-RA error summary

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.9+ | Recommended: 3.11 |
| pip | latest | |
| Git | latest | |
| Docker *(optional)* | 24+ | For containerised deployment |

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/<your-org>/sarmaan-coverage-dashboard.git
cd sarmaan-coverage-dashboard
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Place the data file

Copy `Coverage data.xlsx` into the project root (same directory as `coverage_app.py`). This file is **not committed** — it contains sensitive survey data.

The community mapping file `dat.csv` is also required in the root (maps settlement codes to human-readable names and planned sample counts).

### 4. Run the app

**Option A — Flask directly:**

```bash
python coverage_app.py
```

The server starts on `http://localhost:5000`. Open that URL in your browser.

**Option B — Docker:**

```bash
docker build -t sarmaan-dashboard .
docker run -p 5000:5000 sarmaan-dashboard
```

### 5. Open in browser

Navigate to `http://localhost:5000`.

---

## Project Structure

```
.
├── coverage_app.py              # Flask server — routes, API endpoints, data loading
├── data_processor.py            # Data processing — KPIs, charts, DQ metrics, completion
├── app.py                       # Legacy Dash app (not actively used)
├── Coverage data.xlsx           # Source survey data (3 sheets)
├── dat.csv                      # Community mapping — settlement codes → names + sample counts
├── PRD_SARMAAN_Coverage_Dashboard.md  # Product requirements document
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container build
└── templates/
    └── dashboard.html           # Single-file app — HTML + CSS (inline) + JS (inline)
```

---

## Data Sources

The Excel workbook has three sheets used by the dashboard:

| Sheet | Description | Approx. rows |
|-------|-------------|--------------|
| `SARMAAN II C3 SOKOTO COVERAGE` | Main household survey | ~1,700 |
| `child_info` | Child demographics & eligibility | ~4,000 |
| `child_infoo` | Eligible child drug administration | ~2,960 |

`dat.csv` provides a community-level mapping:

| Column | Description |
|--------|-------------|
| `settlement_Label` | Human-readable community name |
| `settlement_Name` | Numeric settlement code |
| `sample_count` | Planned household target |
| `lga_Label` | Local Government Area |
| `ward_Label` | Ward |

---

## API Endpoints

All endpoints return JSON. Filters are optional query params (`?lga=X&ward=Y&community=Z`).

| Endpoint | Description |
|----------|-------------|
| `/api/kpis` | Coverage KPIs — total HH, eligible children, offered/swallowed AZM |
| `/api/completion` | Planned vs reached per community + per-LGA summary |
| `/api/charts/daily` | Daily household submissions |
| `/api/charts/lga` | Per-LGA planned vs reached bar chart |
| `/api/charts/cascade` | AZM cascade — eligible → offered → swallowed |
| `/api/charts/cdd` | CDD visitation breakdown |
| `/api/dq-metrics` | Quality check metrics (7 cards) |
| `/api/errors-by-lga` | Error breakdown per LGA |
| `/api/error-log` | Detailed error log per record |
| `/api/ra-performance` | Research assistant submission counts |
| `/api/ra-stacked` | Offered / swallowed / declined per RA |
| `/api/geospatial` | Survey point coordinates + flags |
| `/api/validation` | Validation check statuses |
| `/api/insights` | AI-generated coverage insights |
| `/api/insights/generate` | Regenerate insights |
| `/api/export` | Export processed data as CSV |

---

## Design System

All CSS is inlined in `templates/dashboard.html` within a `<style>` tag. Design tokens are defined as CSS custom properties at `:root`.

Typography: **Fraunces** (headings), **IBM Plex Sans** (body), **IBM Plex Mono** (labels).

| Token | Value |
|-------|-------|
| Ink (dark green) | `#163628` |
| Gold | `#D9A441` |
| Sand (background) | `#F6F1E4` |
| Olive (accent) | `#3B6B4C` |
| Red (flag) | `#B23A3A` |

---

## Contributing

1. Create a feature branch from `main`.
2. Make changes. Only restyle the presentation layer — do not modify data-fetching or API logic without discussion.
3. Run the app locally and verify all pages render correctly.
4. Open a PR with a clear description of changes.

### Code conventions

- CSS uses custom properties (tokens) defined at `:root` in the `<style>` block of `dashboard.html`. Use them instead of hardcoding colours.
- All JavaScript is inlined in `dashboard.html` in a `<script>` tag — vanilla JS, no build step, no frameworks. Keep it that way.
- Flask templates are Jinja2 but currently only `dashboard.html` exists.
- API endpoints are in `coverage_app.py`; data processing lives in `data_processor.py`.

---

## Licence

Internal use only — SARMAAN II study team.
