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


def load_all_data():
    cov = pd.read_excel(DATA_PATH, sheet_name=0, dtype=str)
    child_info = pd.read_excel(DATA_PATH, sheet_name='child_info', dtype=str)
    child_eligible = pd.read_excel(DATA_PATH, sheet_name='child_infoo', dtype=str)
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
    rep_child_count = 0
    if COL_CHILD_CODE in child_eligible.columns and COL_HH_CODE in child_eligible.columns:
        dup_child_hh = child_eligible[child_eligible.duplicated(subset=[COL_HH_CODE, COL_CHILD_CODE], keep=False)]
        rep_child_count = int(len(dup_child_hh))
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

    # DQ-05: Duplicate Child Detection
    if COL_CHILD_CODE in child_eligible.columns:
        dup_child = child_eligible[child_eligible.duplicated(subset=[COL_CHILD_CODE], keep=False)]
        dq['dup_children'] = len(dup_child)
        dq['dup_child_count'] = int(dup_child[COL_CHILD_CODE].nunique()) if len(dup_child) > 0 else 0
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
