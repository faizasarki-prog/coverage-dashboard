# Product Requirements Document (PRD)
## SARMAAN II Coverage Survey Dashboard — Sokoto, Nigeria

---

## 1. Executive Summary

**Project:** SARMAAN II (Safety and Antimicrobial Resistance of Mass Administration of Azithromycin in Children 1–59 Months)

**Purpose:** Build an interactive dashboard to monitor household and child-level coverage, data quality, geographic validation, and completion status for the MDA coverage survey conducted in Sokoto State, Nigeria (December 2025).

**Audience:** Programme Managers, Data Analysts, GIS Analysts, Validators, Field Coordinators

---

## 2. Goals & Objectives

1. **Monitor Coverage Progress** — Track household submissions, child eligibility, AZM offering/swallowing rates, and geographic reach (LGA/Ward/Community).
2. **Ensure Data Quality** — Detect duplicate households, duplicate child selections, mock GPS, stacked GPS, settlement type mismatches, and ineligible children.
3. **Track Completion** — Compare planned vs. reached LGAs, settlements, and households using uploaded target files.
4. **GIS Validation** — Detect stacked GPS points, mock GPS locations, and out-of-boundary geolocation.
5. **Field Team Performance** — Monitor submissions per Research Assistant and CDD visitation.

---

## 3. Data Sources

| Source | Description | Rows | Columns |
|--------|-------------|------|---------|
| `Coverage data.xlsx` — SARMAAN II C3 SOKOTO COVERAGE | Main household survey data | ~1,706 | 313 |
| `Coverage data.xlsx` — child_info | Child demographics & eligibility | ~4,048 | 18 |
| `Coverage data.xlsx` — child_infoo | Eligible child drug administration details | ~2,961 | 85 |
| `Coverage data.xlsx` — net_repeat | Mosquito net usage data | ~2,425 | 38 |

---

## 4. User Stories & Requirements

### 4.1 Demography KPIs (DEMO)

| ID | Requirement | DAX / Logic | Priority |
|----|-------------|-------------|----------|
| DEMO-01 | Total Households Covered | Count consents = "Yes" | High |
| DEMO-02 | Total Children < 18 Years | Count children where age < 18 | High |
| DEMO-03 | Eligible Children (1–59 Months) | Count children in eligible age range | High |
| DEMO-04 | Children Offered AZM | Count where offered = "Yes" | High |
| DEMO-05 | Children Not Offered AZM | Count where offered = "No" | High |
| DEMO-06 | Children Who Swallowed AZM | Count where swallowed = "Yes" | High |
| DEMO-07 | Vaccination Cards Available | Count where card = "Yes" | High |
| DEMO-08 | Total LGAs Reached | Unique count of LGA | High |
| DEMO-09 | Total Wards Reached | Unique count of Ward | High |
| DEMO-10 | Total Communities Reached | Unique count of Community | High |
| DEMO-11 | Households Visited per Implementation Day | Bar/Line chart grouped by submission date | High |
| DEMO-12 | Submissions per Research Assistant | Bar chart grouped by enumerator | High |
| DEMO-13 | Visitation by CDD for MDA | Chart grouped by CDD visitation | High |

### 4.2 Completion Tracking (COMP)

| ID | Requirement | Logic | Priority |
|----|-------------|-------|----------|
| COMP-01 | LGA Planned vs Reached | Compare target list vs actual submissions | High |
| COMP-02 | Settlement Completion Table | Compare target vs actual per settlement | High |

### 4.3 GIS Analysis (GIS)

| ID | Requirement | Logic | Priority |
|----|-------------|-------|----------|
| GIS-01 | Stacked GPS Point Detection | Detect identical/near-identical GPS coordinates | High |
| GIS-02 | Mock GPS Detection | Flag records with precision < 2 | High |
| GIS-03 | Geolocation Outside LGA | Spatial join with LGA boundaries | Medium |
| GIS-04 | Geolocation Outside Ward | Spatial join with Ward boundaries | Medium |

### 4.4 Data Quality Checks (DQ)

| ID | Requirement | Logic | Priority |
|----|-------------|-------|----------|
| DQ-01 | Duplicate Household Detection | Count duplicate unique household codes | High |
| DQ-02 | Repeated Child Selection | Detect same child selected twice in a household | High |
| DQ-03 | Active Research Assistants | Unique enumerator count | High |
| DQ-04 | Ineligible Child Detection | Children outside 1–59 months flagged | High |
| DQ-05 | Duplicate Child Detection | Duplicate child unique identifiers | High |
| DQ-06 | Settlement Type Mismatch | Wealth index vs settlement type inconsistency | High |
| DQ-07 | Form Validation Status | Overall pass/fail per record | High |
| DQ-08 | Error Summary by LGA | Grouped error counts by LGA | High |
| DQ-09 | Error Log by RA | Detailed error log table per enumerator | High |

### 4.5 Validation Checks (VAL)

| ID | Requirement | Priority |
|----|-------------|----------|
| VAL-01 | Education vs Occupation Consistency | High |
| VAL-02 | Repetitive Child Selection per Household | High |
| VAL-03 | Gender vs Name Consistency | High |
| VAL-04 | Child Name vs Vaccination Card Check | High |
| VAL-05 | Household ID Duplicate Flag | High |
| VAL-06 | Non-Eligible Children Flag | High |

---

## 5. Dashboard Structure (Proposed)

```
┌──────────────────────────────────────────────────────────────┐
│  HEADER: SARMAAN II — Coverage Survey Dashboard (Sokoto)     │
├──────────┬───────────────────────────────────────────────────┤
│ SIDEBAR  │  MAIN CONTENT AREA                                │
│          │                                                   │
│ □ Home   │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐       │
│ □ Demo-  │  │ KPI  │ │ KPI  │ │ KPI  │ │ KPI  │ │ KPI  │       │
│   graphy │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘       │
│ □ Com-   │                                                   │
│   pletion│  ┌─────────────────┐ ┌─────────────────┐         │
│ □ GIS    │  │    Chart 1      │ │    Chart 2      │         │
│ □ Data   │  │ (Daily HH)      │ │ (Submissions    │         │
│   Quality│  │                 │ │  per RA)        │         │
│ □ Vali-  │  └─────────────────┘ └─────────────────┘         │
│   dation │                                                   │
│          │  ┌─────────────────────────────────────┐         │
│          │  │        Data Table / Map              │         │
│          │  └─────────────────────────────────────┘         │
└──────────┴───────────────────────────────────────────────────┘
```

---

## 6. KPIs (Summary Cards)

| KPI | Description | Source Column(s) |
|-----|-------------|------------------|
| Total Households | Count of consenting households | Consent field |
| Eligible Children | Children 1–59 months | `is_eligible` flag |
| Children Offered AZM | Children offered the drug | Q90 field |
| Children Swallowed AZM | Children who swallowed | Q94 field |
| LGAs Reached | Unique LGAs | Q2. Local Government Area |
| Wards Reached | Unique wards | Q3.Ward |
| Communities Reached | Unique communities | Q4. Community Name |
| Vaccination Cards | Cards available | Vaccination card field |
| Active RAs | Active research assistants | `confirm user and phone number` |
| Duplicate HHs | Duplicate households | `unique_code` |
| Data Quality Flags | Total records with issues | Multiple DQ flags |

---

## 7. Charts & Visualizations

| Chart | Type | X-Axis | Y-Axis | Section |
|-------|------|--------|--------|---------|
| Households per Day | Bar/Line | Submission date | Count of UUID | Demography |
| Submissions per RA | Bar | Enumerator name | Count of UUID | Demography |
| CDD Visitation | Bar | CDD visit (Yes/No) | Count | Demography |
| Planned vs Reached | Bar | LGA name | Count | Completion |
| Errors by LGA | Bar | LGA | Error count | Data Quality |
| GPS Distribution | Scatter | Longitude | Latitude | GIS |

---

## 8. Filters / Slicers

- **Date Range** (submission date)
- **LGA** (dropdown)
- **Ward** (dropdown)
- **Community** (dropdown)
- **Research Assistant** (dropdown)
- **Settlement Type** (Urban/Rural)
- **Validation Status** (Valid / Flagged)

---

## 9. Tech Stack (Recommended)

| Component | Technology |
|-----------|------------|
| Framework | Python Dash / Plotly |
| Data Processing | pandas |
| Charts | Plotly Express / Plotly Graph Objects |
| Styling | Bootstrap or Dash Bootstrap Components |
| Deployment | Local / Flask server |

---

## 10. Milestones

| Phase | Deliverable | Timeline |
|-------|-------------|----------|
| 1 | Data processing & cleaning | Week 1 |
| 2 | KPI cards & filters | Week 2 |
| 3 | Charts & visualizations | Week 3 |
| 4 | GIS & validation sections | Week 4 |
| 5 | Testing & deployment | Week 5 |

---

## 11. Stakeholders

| Role | Name |
|------|------|
| Product Owner / PM | Faiza Mukhtar |
| Data Analyst | Faiza Mukhtar |
| GIS Analyst | Faiza Mukhtar |
| Validator | Faiza Mukhtar |

---

*Document generated from Process_Document.xlsx — coverage_survey sheet*
