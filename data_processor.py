import pandas as pd
import numpy as np
import re
from datetime import datetime

DATA_PATH = 'Coverage data.xlsx'

# ─── Column name constants (from actual data) ───
COL_CONSENT = "I have been informed about SARMAAN in a language I understand. The research lead has discussed with me and I understand that my child participation is voluntary. I therefore agree to participate."
COL_LGA = "Q2. Local Government Area"
COL_WARD = "Q3.Ward"
COL_COMMUNITY = "Q4. Community Name"
COL_SETTLEMENT_TYPE = "Q5. Type of Settlement"
COL_HH_CODE = "unique_code"
COL_SUBMISSION_TIME = "_submission_time"
COL_UUID = "_uuid"
COL_RA = "confirm user and phone number"
COL_LAT = "_Q9. GPS coordinates_latitude"
COL_LNG = "_Q9. GPS coordinates_longitude"
COL_PRECISION = "_Q9. GPS coordinates_precision"
COL_CDD_VISIT = "Q86. Did someone visit your home between 15th to 20th December 2025 to offer your child or children any drug from a bottle?"
COL_DATE = "Q8. Date"

# child_infoo columns
COL_CHILD_NAME = "Q88. Child name and age ${child_idd} as at when MDA was done (15th to 20th December 2025)"
COL_CHILD_SEX = "Q89. Sex of ${child_names11}"
COL_OFFERED_AZM = "Q90. Did someone offer ${child_names11} azithromycin between 15th to 20th December 2025?"
COL_NOT_OFFERED_REASON = "Q91. Why was ${child_names11} not offered AZM?"
COL_SWALLOWED_AZM = "Q94. Did ${child_names11} swallow the AZM offered?"
COL_VACC_CARD = "Do you have a vaccination card?"
COL_CHILD_CODE = "unique_code2"

# child_info columns
COL_CHILD_AGE = "Age of child ${child_id} as at when MDA was done (15th to 20th December 2025)"
COL_IS_ELIGIBLE = "is_eligible"

# Wealth index columns (Q23-Q32)
WEALTH_COLS = [
    "Q23. Electricity", "Q24. Radio", "Q25. Television",
    "Q26. A non-mobile telephone", "Q27. Computer", "Q28. Refrigerator",
    "Q29. Chair", "Q30. Bed", "Q31. Sofa", "Q32. Cupboard"
]


# ─── Robust column resolution ───────────────────────────────────
# Kobo form labels get reworded between rounds (e.g. the MDA date range or the
# ${child_names11} → child ${child_idd} variable), which silently zeroes KPIs
# when columns are matched by exact name only. `find_col` matches on the stable
# question number ("Q86", "Q90", …) plus keyword overlap, then every matched
# column is RENAMED to its canonical constant below so the rest of the pipeline
# needs no changes.

def _norm_col(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).strip().lower())


def _words(s, min_len: int = 3) -> list[str]:
    return re.findall(r"[a-z]{%d,}" % min_len, _norm_col(s))


def _qnum(s: str) -> str | None:
    m = re.match(r"\s*(q\d+)", _norm_col(s))
    return m.group(1) if m else None


def _head(s: str) -> str:
    return _norm_col(str(s).split("/")[0].split("\\")[0])


def find_col(df, name, must_not_contain=()):
    """Find the column in `df` that best matches a (possibly reworded) label.

    - Exact normalized match wins immediately.
    - If the label carries a question number (e.g. "Q90."), only columns whose
      question head starts with that number are considered, then the one sharing
      the most words wins (ties go to the first / base question column).
    - Otherwise the column with the greatest keyword overlap is returned.
    - Columns whose names contain any `must_not_contain` fragment (e.g. the
      'Confirm…' columns, which are wiped when a Kobo record is edited) are
      never matched.
    """
    name = str(name)
    norm_target = _norm_col(name)
    qnum = _qnum(name)
    target_words = set(_words(name))
    best, best_score = None, -1
    for col in df.columns:
        col_str = str(col)
        norm = _norm_col(col_str)
        if any(ex in norm for ex in must_not_contain):
            continue
        if norm == norm_target:
            return col
        if qnum:
            head = _head(col_str)
            if not head.startswith(qnum):
                continue
            score = 500 + len(target_words & set(_words(head)))
        else:
            score = len(target_words & set(_words(col_str)))
        if score > best_score:
            best, best_score = col, score
    return best


def _build_rules():
    rules = {
        COL_CONSENT: (COL_CONSENT, ()),
        COL_LGA: (COL_LGA, ()),
        COL_WARD: (COL_WARD, ()),
        COL_COMMUNITY: (COL_COMMUNITY, ("confirm",)),
        COL_SETTLEMENT_TYPE: (COL_SETTLEMENT_TYPE, ()),
        COL_HH_CODE: (COL_HH_CODE, ()),
        COL_SUBMISSION_TIME: (COL_SUBMISSION_TIME, ()),
        COL_UUID: (COL_UUID, ()),
        COL_RA: (COL_RA, ()),
        COL_LAT: (COL_LAT, ()),
        COL_LNG: (COL_LNG, ()),
        COL_PRECISION: (COL_PRECISION, ()),
        COL_CDD_VISIT: (COL_CDD_VISIT, ()),
        COL_DATE: (COL_DATE, ()),
    }
    for w in WEALTH_COLS:
        rules[w] = (w, ())
    return rules


COV_RULES = _build_rules()

# child_info / child_infoo have different schemas; the age field only exists in
# child_info while the Q88 "child name and age" label lives in child_infoo.
CHILD_INFO_RULES = {
    COL_CHILD_AGE: (COL_CHILD_AGE, ("q88",)),  # the Q88 label also contains "age"
    COL_IS_ELIGIBLE: (COL_IS_ELIGIBLE, ()),
}

CHILD_INFOO_RULES = {
    COL_CHILD_NAME: (COL_CHILD_NAME, ()),
    COL_CHILD_SEX: (COL_CHILD_SEX, ()),
    COL_OFFERED_AZM: (COL_OFFERED_AZM, ()),
    COL_NOT_OFFERED_REASON: (COL_NOT_OFFERED_REASON, ()),
    COL_SWALLOWED_AZM: (COL_SWALLOWED_AZM, ()),
    COL_VACC_CARD: (COL_VACC_CARD, ()),
    COL_CHILD_CODE: (COL_CHILD_CODE, ()),
    COL_IS_ELIGIBLE: (COL_IS_ELIGIBLE, ()),
}


def _resolve_columns(df, rules):
    for canon, (candidate, exclude) in rules.items():
        if canon in df.columns:
            continue
        found = find_col(df, candidate, must_not_contain=exclude)
        if found is not None:
            df.rename(columns={found: canon}, inplace=True)


def _read_sheet(path, sheet) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name=sheet, dtype=str)
    except Exception as e:
        print(f"[data_processor] could not read sheet {sheet!r}: {e}")
        return pd.DataFrame()


def load_all_data(path: str | None = None):
    path = path or DATA_PATH
    cov = _read_sheet(path, 0)
    child_info = _read_sheet(path, 'child_info')
    child_eligible = _read_sheet(path, 'child_infoo')
    _resolve_columns(cov, COV_RULES)
    _resolve_columns(child_info, CHILD_INFO_RULES)
    _resolve_columns(child_eligible, CHILD_INFOO_RULES)
    return cov, child_info, child_eligible


def compute_kpis(cov, child_info, child_eligible):
    kpis = {}

    # DEMO-01: Total Households Covered (count consent = "Yes")
    consent_col = COL_CONSENT
    kpis['total_households'] = int(cov[consent_col].notna().sum()) if consent_col in cov.columns else int(len(cov))

    # DEMO-02: Total Children Less Than 18 Years
    if COL_CHILD_AGE in child_info.columns:
        ages = pd.to_numeric(child_info[COL_CHILD_AGE], errors='coerce')
        kpis['children_under_18'] = int((ages < 18).sum())
    else:
        kpis['children_under_18'] = 0

    # DEMO-03: Eligible Children (1-59 Months)
    if COL_IS_ELIGIBLE in child_info.columns:
        kpis['eligible_children'] = int((child_info[COL_IS_ELIGIBLE] == '1').sum())
    else:
        kpis['eligible_children'] = 0

    # DEMO-04: Children Offered AZM
    if COL_OFFERED_AZM in child_eligible.columns:
        kpis['offered_azm'] = int((child_eligible[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum())
    else:
        kpis['offered_azm'] = 0

    # DEMO-05: Children Not Offered AZM
    if COL_OFFERED_AZM in child_eligible.columns:
        kpis['not_offered_azm'] = int((child_eligible[COL_OFFERED_AZM].str.strip().str.lower() == 'no').sum())
    else:
        kpis['not_offered_azm'] = 0

    # DEMO-06: Children Who Swallowed AZM
    if COL_SWALLOWED_AZM in child_eligible.columns:
        kpis['swallowed_azm'] = int((child_eligible[COL_SWALLOWED_AZM].str.strip().str.lower() == 'yes').sum())
    else:
        kpis['swallowed_azm'] = 0

    # DEMO-07: Vaccination Cards Available
    if COL_VACC_CARD in child_eligible.columns:
        kpis['vacc_cards'] = int((child_eligible[COL_VACC_CARD].str.strip().str.lower() == 'yes').sum())
    else:
        kpis['vacc_cards'] = 0

    # DEMO-08: Total LGAs Reached
    if COL_LGA in cov.columns:
        kpis['lgas_reached'] = int(cov[COL_LGA].nunique())
    else:
        kpis['lgas_reached'] = 0

    # DEMO-09: Total Wards Reached
    if COL_WARD in cov.columns:
        kpis['wards_reached'] = int(cov[COL_WARD].nunique())
    else:
        kpis['wards_reached'] = 0

    # DEMO-10: Total Communities Reached
    if COL_COMMUNITY in cov.columns:
        kpis['communities_reached'] = int(cov[COL_COMMUNITY].nunique())
    else:
        kpis['communities_reached'] = 0

    return kpis


def compute_chart_data(cov, child_eligible):
    charts = {}

    # DEMO-11: Households Visited per Implementation Day
    if COL_SUBMISSION_TIME in cov.columns:
        daily = cov.copy()
        daily['date'] = pd.to_datetime(daily[COL_SUBMISSION_TIME], errors='coerce').dt.date
        daily_counts = daily.groupby('date').size().reset_index(name='count')
        daily_counts = daily_counts.sort_values('date')
        charts['daily_hh'] = daily_counts
    else:
        charts['daily_hh'] = pd.DataFrame({'date': [], 'count': []})

    # DEMO-12: Submissions per Research Assistant
    ra_data = cov.groupby(COL_RA).size().reset_index(name='count').sort_values('count', ascending=False)
    charts['submissions_per_ra'] = ra_data

    # DEMO-13: Visitation by CDD for MDA
    if COL_CDD_VISIT in cov.columns:
        cdd = cov[COL_CDD_VISIT].value_counts().reset_index()
        cdd.columns = ['response', 'count']
        charts['cdd_visitation'] = cdd
    else:
        charts['cdd_visitation'] = pd.DataFrame({'response': [], 'count': []})

    # AZM Funnel: Eligible -> Offered -> Swallowed
    funnel_data = {
        'stage': ['Eligible Children', 'Offered AZM', 'Swallowed AZM'],
        'count': [
            int((child_eligible[COL_OFFERED_AZM].notna() | child_eligible[COL_SWALLOWED_AZM].notna()).sum()) if COL_OFFERED_AZM in child_eligible.columns else 0,
            int((child_eligible[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_OFFERED_AZM in child_eligible.columns else 0,
            int((child_eligible[COL_SWALLOWED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_SWALLOWED_AZM in child_eligible.columns else 0
        ]
    }
    # More accurate: eligible count from child_info
    charts['azm_funnel'] = funnel_data

    return charts


def compute_dq_metrics(cov, child_info, child_eligible):
    dq = {}

    # DQ-01: Duplicate Household Detection
    dup_hh = cov[cov.duplicated(subset=[COL_HH_CODE], keep=False)] if COL_HH_CODE in cov.columns else pd.DataFrame()
    dq['dup_households'] = len(dup_hh)
    dq['dup_household_count'] = int(dup_hh[COL_HH_CODE].nunique()) if len(dup_hh) > 0 else 0

    # DQ-02: Repeated Child Selection (same child selected twice in same household)
    # Child rows live on the child_eligible sheet and only carry a per-household
    # sequential code (unique_code2). The household identity is derived either from
    # a household code column on the sheet itself or by joining child_eligible's
    # _parent_index back to the household's _index -> unique_code on the cov sheet.
    # A child is repeated if the same child code appears twice, or if the same
    # Q88 child name + age is entered twice, within the same household.
    rep_child_count = 0
    rep_mask: pd.Series | None = None
    if COL_CHILD_CODE in child_eligible.columns or COL_CHILD_NAME in child_eligible.columns:
        ce = child_eligible.copy()
        # Household identity: the submission uuid uniquely identifies one filled
        # questionnaire, so a child repeated across two submissions of the same
        # household is a duplicate-child-ID case (DQ-05), not a repeated
        # selection within the same questionnaire.
        ident: pd.Series | None = None
        for cand in ("_submission__uuid", "_submission_meta/rootUuid", "_uuid"):
            if cand in ce.columns:
                ident = ce[cand].astype(str).str.strip()
                break
        if ident is None and COL_HH_CODE in ce.columns:
            ident = ce[COL_HH_CODE].astype(str).str.strip()
        if ident is None and "_parent_index" in ce.columns and COL_HH_CODE in cov.columns and "_index" in cov.columns:
            idx2code = dict(
                zip(pd.to_numeric(cov["_index"], errors="coerce"),
                    cov[COL_HH_CODE].astype(str).str.strip())
            )
            pidx = pd.to_numeric(ce["_parent_index"], errors="coerce")
            ident = pidx.map(idx2code).fillna(ce["_parent_index"].astype(str).str.strip())
        if ident is not None:
            rep_mask = pd.Series(False, index=ce.index)
            if COL_CHILD_CODE in ce.columns:
                rep_mask = rep_mask | (ident + "|" + ce[COL_CHILD_CODE].astype(str).str.strip()).duplicated(keep=False)
            if COL_CHILD_NAME in ce.columns:
                rep_mask = rep_mask | (ident + "|" + ce[COL_CHILD_NAME].astype(str).str.strip()).duplicated(keep=False)
            rep_child_count = int(rep_mask.sum())
    dq['rep_child_selection'] = rep_child_count

    # DQ-03: Active Research Assistants
    if COL_RA in cov.columns:
        dq['active_ras'] = int(cov[COL_RA].nunique())
    else:
        dq['active_ras'] = 0

    # DQ-04: Ineligible Child Detection — parse age from Q88, flag >= 60 months
    ineligible_count = 0
    if COL_CHILD_NAME in child_eligible.columns:
        ages = child_eligible[COL_CHILD_NAME].astype(str).str.strip()
        age_nums = ages.str.extract(r'(\d+)\s*month', flags=re.IGNORECASE)[0]
        age_numeric = pd.to_numeric(age_nums, errors='coerce')
        ineligible_count = int((age_numeric >= 60).sum())
    dq['ineligible_children'] = ineligible_count

    # DQ-05: Duplicate Child Detection — the same child ID (unique_code2)
    # submitted more than once anywhere in the dataset, regardless of household.
    if COL_CHILD_CODE in child_eligible.columns:
        codes = child_eligible[COL_CHILD_CODE].astype(str).str.strip().replace({"nan": "", "None": ""})
        dup_vals = codes[codes != ""].value_counts()
        dup_ids = dup_vals[dup_vals > 1].index
        dup_child = child_eligible[codes.isin(dup_ids)].copy()
        dq['dup_children'] = int(len(dup_child))
        dq['dup_child_count'] = int(len(dup_ids))
    else:
        dq['dup_children'] = 0
        dq['dup_child_count'] = 0

    # DQ-06: Settlement Type Mismatch (DAX-based logic)
    mismatch_count = 0
    mismatch_records = pd.DataFrame()
    if all(c in cov.columns for c in WEALTH_COLS + [COL_SETTLEMENT_TYPE]):
        wealth_df = cov[WEALTH_COLS + [COL_SETTLEMENT_TYPE, COL_UUID, COL_HH_CODE, COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA]].copy()
        for col in WEALTH_COLS:
            wealth_df[col] = wealth_df[col].str.strip().str.lower()
        wealth_df['yes_count'] = (wealth_df[WEALTH_COLS] == 'yes').sum(axis=1)
        wealth_df['no_count'] = (wealth_df[WEALTH_COLS] == 'no').sum(axis=1)
        wealth_df['is_urban'] = wealth_df[COL_SETTLEMENT_TYPE].str.strip().str.lower() == 'urban'
        wealth_df['is_rural'] = wealth_df[COL_SETTLEMENT_TYPE].str.strip().str.lower() == 'rural'
        wealth_df['mismatch'] = (
            (wealth_df['is_urban'] & (wealth_df['no_count'] == 10)) |
            (wealth_df['is_rural'] & (wealth_df['yes_count'] == 10))
        )
        mismatch_count = int(wealth_df['mismatch'].sum())
        mismatch_records = wealth_df[wealth_df['mismatch']].copy()
    dq['settlement_mismatch'] = mismatch_count

    # GIS-01: Stacked GPS Point Detection
    stacked = 0
    if COL_LAT in cov.columns and COL_LNG in cov.columns:
        gps = cov[[COL_LAT, COL_LNG, COL_UUID]].dropna(subset=[COL_LAT, COL_LNG])
        stacked = int(gps.duplicated(subset=[COL_LAT, COL_LNG], keep=False).sum())
    dq['stacked_gps'] = stacked

    # GIS-02: Mock GPS Detection (precision < 2)
    mock_gps = 0
    if COL_PRECISION in cov.columns:
        prec = pd.to_numeric(cov[COL_PRECISION], errors='coerce')
        mock_gps = int((prec < 2).sum())
    dq['mock_gps'] = mock_gps

    # DQ-07: Form Validation Status (records with validation/status issues or not validated)
    qc_cols = [c for c in cov.columns if 'validation' in str(c).lower() or 'status' in str(c).lower() or '_status' in str(c).lower()]
    validation_issues = 0
    for c in qc_cols:
        vals = cov[c].dropna().astype(str).str.lower()
        validation_issues += int(vals.isin(['rejected', 'not_approved', 'no', '0']).sum())
    dq['form_validation_issues'] = validation_issues

    # DQ-07: Overall flagged records
    total_flags = dq['dup_households'] + dq['settlement_mismatch'] + dq['stacked_gps'] + dq['mock_gps']
    dq['total_flagged'] = total_flags

    # DQ-08: Child Count Mismatch — the reported number of eligible children on the
    # household form (total_eligible) vs the actual count of eligible child rows on
    # the child_info sheet (is_eligible == 1) linked to that submission.
    child_count_mismatch = 0
    if child_info is not None and not child_info.empty:
        elig_col = None
        for cand in (COL_IS_ELIGIBLE, "is_eligible"):
            if cand in child_info.columns:
                elig_col = cand
                break
        uuid_col = next((c for c in ("_submission__uuid", "_uuid") if c in child_info.columns), None)
        total_col = next((c for c in ("total_eligible", "number of eligible children", "how many eligible")
                          if c in cov.columns), None)
        hh_uuid_col = next((c for c in (COL_UUID, "_uuid") if c in cov.columns), None)
        if elig_col and uuid_col and total_col and hh_uuid_col:
            elig_num = pd.to_numeric(child_info[elig_col], errors="coerce")
            count_src = child_info.loc[elig_num == 1] if elig_num.notna().any() else child_info
            actual = {str(k).strip(): int(v) for k, v in count_src.groupby(uuid_col).size().items()}
            expected = pd.to_numeric(cov[total_col], errors="coerce").fillna(0)
            uuids = cov[hh_uuid_col].astype(str).str.strip()
            child_count_mismatch = int(sum(
                1 for u, e in zip(uuids, expected) if int(e) != actual.get(u, 0)
            ))
    dq['child_count_mismatch'] = child_count_mismatch

    return dq


def compute_completion_data(cov):
    """COMP-01: LGA-level summary"""
    lga_summary = cov.groupby(COL_LGA).agg(
        households_reached=(COL_UUID, 'nunique'),
        wards=(COL_WARD, 'nunique'),
        communities=(COL_COMMUNITY, 'nunique'),
        settlements=(COL_SETTLEMENT_TYPE, lambda x: x.nunique())
    ).reset_index()
    lga_summary.columns = ['LGA', 'Households Reached', 'Wards', 'Communities', 'Settlement Types']
    return lga_summary


def compute_error_log(cov, child_eligible, dq_metrics):
    """DQ-09: Error Log by Research Assistant"""
    if COL_RA not in cov.columns:
        return pd.DataFrame()

    # Build error flags per record
    errors = cov[[COL_UUID, COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_HH_CODE,
                  COL_SETTLEMENT_TYPE, COL_LAT, COL_LNG, COL_PRECISION]].copy()

    # Settlement mismatch flag
    if all(c in cov.columns for c in WEALTH_COLS):
        wealth_df = cov[WEALTH_COLS].copy()
        for col in WEALTH_COLS:
            wealth_df[col] = wealth_df[col].str.strip().str.lower()
        yes_count = (wealth_df == 'yes').sum(axis=1)
        no_count = (wealth_df == 'no').sum(axis=1)
        is_urban = cov[COL_SETTLEMENT_TYPE].str.strip().str.lower() == 'urban'
        is_rural = cov[COL_SETTLEMENT_TYPE].str.strip().str.lower() == 'rural'
        errors['Settlement Type Mismatch'] = ((is_urban & (no_count == 10)) | (is_rural & (yes_count == 10))).astype(int)
    else:
        errors['Settlement Type Mismatch'] = 0

    # Duplicate HH flag
    if COL_HH_CODE in cov.columns:
        dup_codes = cov[COL_HH_CODE].value_counts()
        dup_codes = dup_codes[dup_codes > 1].index
        errors['Duplicate Household'] = cov[COL_HH_CODE].isin(dup_codes).astype(int)
    else:
        errors['Duplicate Household'] = 0

    # Mock GPS
    if COL_PRECISION in cov.columns:
        prec = pd.to_numeric(cov[COL_PRECISION], errors='coerce')
        errors['Mock GPS'] = (prec < 2).astype(int)
    else:
        errors['Mock GPS'] = 0

    # Stacked GPS
    if COL_LAT in cov.columns and COL_LNG in cov.columns:
        gps_dup = errors.duplicated(subset=[COL_LAT, COL_LNG], keep=False)
        errors['Stacked GPS'] = gps_dup.astype(int)
    else:
        errors['Stacked GPS'] = 0

    return errors


def get_lga_wards_communities(cov):
    """Get hierarchy for filters"""
    lga_list = sorted(cov[COL_LGA].dropna().unique()) if COL_LGA in cov.columns else []
    ward_list = sorted(cov[COL_WARD].dropna().unique()) if COL_WARD in cov.columns else []
    community_list = sorted(cov[COL_COMMUNITY].dropna().unique()) if COL_COMMUNITY in cov.columns else []
    ra_list = sorted(cov[COL_RA].dropna().unique()) if COL_RA in cov.columns else []
    return lga_list, ward_list, community_list, ra_list


def get_lga_hierarchy(cov):
    """Build LGA -> {Ward -> [Communities]} hierarchy for cascading filters"""
    if COL_LGA not in cov.columns or COL_WARD not in cov.columns:
        return {}
    hierarchy = {}
    for _, row in cov.dropna(subset=[COL_LGA, COL_WARD]).iterrows():
        lga = str(row[COL_LGA]).strip()
        ward = str(row[COL_WARD]).strip() if COL_WARD in row else ''
        community = str(row[COL_COMMUNITY]).strip() if COL_COMMUNITY in row and pd.notna(row[COL_COMMUNITY]) else ''
        if lga not in hierarchy:
            hierarchy[lga] = {}
        if ward and ward not in hierarchy[lga]:
            hierarchy[lga][ward] = []
        if community and ward:
            if community not in hierarchy[lga][ward]:
                hierarchy[lga][ward].append(community)
    # Sort
    for lga in hierarchy:
        hierarchy[lga] = dict(sorted(hierarchy[lga].items()))
        for ward in hierarchy[lga]:
            hierarchy[lga][ward] = sorted(hierarchy[lga][ward])
    return hierarchy
