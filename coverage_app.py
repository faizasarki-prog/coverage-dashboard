"""
coverage_app.py — Coverage Survey Dashboard Flask server
Serves the SARMAAN II Coverage Survey Dashboard with the AMR dashboard design.
"""
import os
import sys
from datetime import datetime
from flask import Flask, jsonify, render_template, request
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_processor import (
    load_all_data,
    COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_UUID,
    COL_SUBMISSION_TIME, COL_CHILD_SEX, COL_LAT, COL_LNG, COL_PRECISION,
    COL_OFFERED_AZM, COL_SWALLOWED_AZM, COL_CHILD_NAME,
    COL_CHILD_AGE, COL_IS_ELIGIBLE, COL_VACC_CARD, COL_HH_CODE,
    COL_CONSENT, COL_CDD_VISIT, COL_DATE, COL_CHILD_CODE,
    WEALTH_COLS, COL_SETTLEMENT_TYPE,
)

app = Flask(__name__)

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Coverage data.xlsx')
COMMUNITY_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dat.csv')

cov, child_info, child_eligible = None, None, None
loaded = False
community_map = {}  # code -> {name, sample_count, lga, ward}
data_loaded_at = None


def load_data():
    global cov, child_info, child_eligible, loaded, community_map, data_loaded_at
    if not loaded:
        cov, child_info, child_eligible = load_all_data()
        loaded = True
        data_loaded_at = datetime.now().strftime('%d %b %Y, %H:%M')
    if not community_map and os.path.exists(COMMUNITY_MAP_PATH):
        try:
            cmap = pd.read_csv(COMMUNITY_MAP_PATH, dtype=str)
            for _, row in cmap.iterrows():
                code = str(row.get('settlement_Name', '')).strip()
                if code:
                    community_map[code] = {
                        'name': str(row.get('settlement_Label', code)).strip(),
                        'sample_count': int(float(row.get('sample_count', 0) or 0)),
                        'lga': str(row.get('lga_Label', '')).strip(),
                        'ward': str(row.get('ward_Label', '')).strip(),
                    }
        except Exception:
            pass


load_data()


def filter_cov(lga=None, ward=None, community=None, ra=None):
    df = cov.copy()
    if lga and COL_LGA in df.columns:
        df = df[df[COL_LGA].astype(str).str.strip() == lga.strip()]
    if ward and COL_WARD in df.columns:
        df = df[df[COL_WARD].astype(str).str.strip() == ward.strip()]
    if community and COL_COMMUNITY in df.columns:
        df = df[df[COL_COMMUNITY].astype(str).str.strip() == community.strip()]
    if ra and COL_RA in df.columns:
        df = df[df[COL_RA].astype(str).str.strip() == ra.strip()]
    return df


def filter_child_eligible(lga=None, ward=None, community=None):
    if any([lga, ward, community]):
        filtered_cov = filter_cov(lga, ward, community)
        hh_codes = filtered_cov[COL_UUID].unique() if COL_UUID in filtered_cov.columns else []
        if len(hh_codes) > 0 and '_uuid' in child_eligible.columns:
            return child_eligible[child_eligible['_uuid'].isin(hh_codes)]
    return child_eligible


# ── API Endpoints ─────────────────────────────────────────────────────

@app.route('/api/kpis')
def api_kpis():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    ra = request.args.get('ra')
    df = filter_cov(lga, ward, community, ra)
    ce = filter_child_eligible(lga, ward, community)

    kpis = {}
    kpis['total_households'] = int(len(df))
    kpis['lgas_reached'] = int(df[COL_LGA].nunique()) if COL_LGA in df.columns else 0
    kpis['wards_reached'] = int(df[COL_WARD].nunique()) if COL_WARD in df.columns else 0
    kpis['communities_reached'] = int(df[COL_COMMUNITY].nunique()) if COL_COMMUNITY in df.columns else 0
    kpis['active_ras'] = int(df[COL_RA].nunique()) if COL_RA in df.columns else 0

    # Total planned counts from community_map
    if community_map:
        kpis['total_lgas'] = len(set(v.get('lga', '') for v in community_map.values()))
        kpis['total_wards'] = len(set(v.get('ward', '') for v in community_map.values()))
        kpis['total_communities'] = len(community_map)
    else:
        kpis['total_lgas'] = kpis['lgas_reached']
        kpis['total_wards'] = kpis['wards_reached']
        kpis['total_communities'] = kpis['communities_reached']

    if COL_OFFERED_AZM in ce.columns:
        kpis['offered_azm'] = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum())
    else:
        kpis['offered_azm'] = 0

    if COL_SWALLOWED_AZM in ce.columns:
        kpis['swallowed_azm'] = int((ce[COL_SWALLOWED_AZM].str.strip().str.lower() == 'yes').sum())
    else:
        kpis['swallowed_azm'] = 0

    if COL_IS_ELIGIBLE in child_info.columns:
        kpis['eligible_children'] = int((child_info[COL_IS_ELIGIBLE] == '1').sum())
    else:
        kpis['eligible_children'] = 0

    if COL_VACC_CARD in ce.columns:
        kpis['vacc_cards'] = int((ce[COL_VACC_CARD].str.strip().str.lower() == 'yes').sum())
    else:
        kpis['vacc_cards'] = 0

    if COL_IS_ELIGIBLE in child_info.columns:
        kpis['children_under_18'] = int(len(child_info))
    else:
        kpis['children_under_18'] = 0

    if COL_OFFERED_AZM in ce.columns:
        kpis['not_offered_azm'] = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == 'no').sum())
    else:
        kpis['not_offered_azm'] = 0

    total_screened = kpis['eligible_children']
    kpis['coverage_pct'] = round((kpis['offered_azm'] / total_screened * 100) if total_screened > 0 else 0, 1)
    kpis['swallow_rate'] = round((kpis['swallowed_azm'] / kpis['offered_azm'] * 100) if kpis['offered_azm'] > 0 else 0, 1)
    kpis['last_updated'] = data_loaded_at or 'Not loaded'

    return jsonify(kpis)


@app.route('/api/charts/daily')
def api_daily():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    ra = request.args.get('ra')
    df = filter_cov(lga, ward, community, ra)
    if COL_SUBMISSION_TIME in df.columns:
        daily = df.copy()
        daily['date'] = pd.to_datetime(daily[COL_SUBMISSION_TIME], errors='coerce').dt.date
        daily_counts = daily.groupby('date').size().reset_index(name='count').sort_values('date')
        data = [{'date': str(r['date']), 'count': int(r['count'])} for _, r in daily_counts.iterrows()]
    else:
        data = []
    return jsonify(data)


@app.route('/api/charts/gender')
def api_gender():
    ce = filter_child_eligible(
        request.args.get('lga'),
        request.args.get('ward'),
        request.args.get('community')
    )
    if COL_CHILD_SEX in ce.columns:
        gender_counts = ce[COL_CHILD_SEX].str.strip().str.lower().value_counts()
        result = {
            'male': int(gender_counts.get('male', 0) + gender_counts.get('m', 0)),
            'female': int(gender_counts.get('female', 0) + gender_counts.get('f', 0)),
        }
    else:
        result = {'male': 0, 'female': 0}
    return jsonify(result)


@app.route('/api/charts/funnel')
def api_funnel():
    ce = filter_child_eligible(
        request.args.get('lga'),
        request.args.get('ward'),
        request.args.get('community')
    )
    eligible_count = 0
    if COL_IS_ELIGIBLE in child_info.columns:
        eligible_count = int((child_info[COL_IS_ELIGIBLE] == '1').sum())

    if COL_OFFERED_AZM in ce.columns:
        offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum())
    else:
        offered = 0
    if COL_SWALLOWED_AZM in ce.columns:
        swallowed = int((ce[COL_SWALLOWED_AZM].str.strip().str.lower() == 'yes').sum())
    else:
        swallowed = 0
    total_children = int(len(child_info))
    return jsonify({
        'stages': ['Total Children', 'Eligible (1-59m)', 'Offered AZM', 'Swallowed AZM'],
        'counts': [total_children, eligible_count, offered, swallowed]
    })


@app.route('/api/charts/lga')
def api_lga_chart():
    df = cov.copy()
    if COL_LGA not in df.columns:
        return jsonify([])
    lga_data = df.groupby(COL_LGA).agg(households_reached=(COL_UUID, 'nunique')).reset_index()
    lga_data.columns = ['lga', 'reached']
    # Use CSV sample_count summed by LGA for planned values
    if community_map:
        lga_planned = {}
        for info in community_map.values():
            lga_name = info['lga']
            if lga_name:
                lga_planned[lga_name] = lga_planned.get(lga_name, 0) + info['sample_count']
        lga_data['planned'] = lga_data['lga'].map(lambda x: lga_planned.get(str(x), lga_data['reached'].max()))
    else:
        lga_data['planned'] = lga_data['reached'].max()
    lga_data['pct'] = (lga_data['reached'] / lga_data['planned'] * 100).round(1)
    lga_data = lga_data.sort_values('reached', ascending=False)
    return jsonify(lga_data.to_dict(orient='records'))


@app.route('/api/ra-submissions')
def api_ra_submissions():
    lga = request.args.get('lga')
    df = filter_cov(lga)
    if COL_RA not in df.columns:
        return jsonify([])
    ra_data = df.groupby(COL_RA).size().reset_index(name='count').sort_values('count', ascending=False)
    ra_data.columns = ['ra', 'count']
    return jsonify(ra_data.to_dict(orient='records'))


@app.route('/api/cdd-visitation')
def api_cdd_visitation():
    lga = request.args.get('lga')
    df = filter_cov(lga)
    if COL_CDD_VISIT in df.columns:
        vc = df[COL_CDD_VISIT].value_counts().reset_index()
        vc.columns = ['response', 'count']
    else:
        vc = pd.DataFrame({'response': [], 'count': []})
    return jsonify(vc.to_dict(orient='records'))


@app.route('/api/ra-performance')
def api_ra_performance():
    lga = request.args.get('lga')
    df = filter_cov(lga)
    if COL_RA not in df.columns or COL_LGA not in df.columns:
        return jsonify({'lga_groups': {}, 'summary': {'total_ras': 0, 'met_target': 0, 'met_pct': 0}})

    # RA submission counts per LGA (an RA can work across multiple LGAs)
    ra_lga = df.groupby([COL_RA, COL_LGA]).size().reset_index(name='count')

    # Overall RA totals across all LGAs
    ra_totals = ra_lga.groupby(COL_RA)['count'].sum().reset_index()

    MEET_PER_DAY = 7
    ABOVE_PER_DAY = 9

    def classify(c):
        if c < MEET_PER_DAY * 5:
            return 'Below Target'
        elif c >= ABOVE_PER_DAY * 5:
            return 'Above Target'
        return 'Meet Target'

    ra_totals['status'] = ra_totals['count'].apply(classify)
    status_map = dict(zip(ra_totals[COL_RA], ra_totals['status']))

    # Build LGA groups
    lga_groups = {}
    for lga_name in sorted(df[COL_LGA].unique()):
        lga_rows = ra_lga[ra_lga[COL_LGA] == lga_name]
        ras = []
        for _, r in lga_rows.iterrows():
            ra_name = r[COL_RA]
            ras.append({
                'ra': ra_name,
                'count': int(r['count']),
                'status': status_map.get(ra_name, 'Meet Target')
            })
        ras.sort(key=lambda x: x['count'], reverse=True)
        below = sum(1 for r in ras if r['status'] == 'Below Target')
        meet = sum(1 for r in ras if r['status'] == 'Meet Target')
        above = sum(1 for r in ras if r['status'] == 'Above Target')
        lga_groups[lga_name] = {'total': len(ras), 'below': below, 'meet': meet, 'above': above, 'ras': ras}

    met_count = int((ra_totals['status'] != 'Below Target').sum())
    total_ras = len(ra_totals)

    return jsonify({
        'lga_groups': lga_groups,
        'summary': {
            'total_ras': total_ras,
            'met_target': met_count,
            'met_pct': round(met_count / total_ras * 100, 1) if total_ras > 0 else 0
        },
        'lga_list': sorted(lga_groups.keys())
    })


@app.route('/api/dq-metrics')
def api_dq():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    df = filter_cov(lga, ward, community)
    ce = filter_child_eligible(lga, ward, community)
    from data_processor import compute_dq_metrics
    dq = compute_dq_metrics(df, child_info, ce)
    if COL_HH_CODE in df.columns:
        dup_hh = df[df.duplicated(subset=[COL_HH_CODE], keep=False)]
        dq['dup_household_count'] = int(dup_hh[COL_HH_CODE].nunique()) if len(dup_hh) > 0 else 0
    dq['active_ras'] = int(df[COL_RA].nunique()) if COL_RA in df.columns else 0
    return jsonify(dq)


@app.route('/api/errors-by-lga')
def api_errors_by_lga():
    df = cov.copy()
    if COL_LGA not in df.columns:
        return jsonify([])
    errors = []
    for lga_name in df[COL_LGA].unique():
        lga_df = df[df[COL_LGA] == lga_name]
        total = int(len(lga_df))
        dup_hh = 0
        if COL_HH_CODE in lga_df.columns:
            dup = lga_df[lga_df.duplicated(subset=[COL_HH_CODE], keep=False)]
            dup_hh = int(dup[COL_HH_CODE].nunique()) if len(dup) > 0 else 0
        mock_gps = 0
        if COL_PRECISION in lga_df.columns:
            prec = pd.to_numeric(lga_df[COL_PRECISION], errors='coerce')
            mock_gps = int((prec < 2).sum())
        stacked_gps = 0
        if COL_LAT in lga_df.columns and COL_LNG in lga_df.columns:
            gps = lga_df[[COL_LAT, COL_LNG]].dropna()
            stacked_gps = int(gps.duplicated(keep=False).sum())
        total_errors = dup_hh + mock_gps + stacked_gps
        errors.append({
            'lga': str(lga_name),
            'total': total,
            'dup_households': dup_hh,
            'mock_gps': mock_gps,
            'stacked_gps': stacked_gps,
            'total_errors': total_errors,
        })
    return jsonify(errors)


@app.route('/api/error-log')
def api_error_log():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    ra = request.args.get('ra')
    df = filter_cov(lga, ward, community, ra)
    ce = filter_child_eligible(lga, ward, community)
    from data_processor import compute_error_log, compute_dq_metrics
    dq = compute_dq_metrics(df, child_info, ce)
    errors_df = compute_error_log(df, ce, dq)
    error_cols = [c for c in errors_df.columns if c not in [COL_UUID, COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_HH_CODE, COL_SETTLEMENT_TYPE, COL_LAT, COL_LNG, COL_PRECISION]]
    errors_df['error_count'] = errors_df[error_cols].sum(axis=1) if len(error_cols) > 0 else 0
    errors_df = errors_df[errors_df['error_count'] > 0]
    if errors_df.empty:
        return jsonify([])
    records = []
    for _, r in errors_df.head(500).iterrows():
        records.append({
            'uuid': str(r.get(COL_UUID, '')),
            'lga': str(r.get(COL_LGA, '')),
            'ward': str(r.get(COL_WARD, '')),
            'community': str(r.get(COL_COMMUNITY, '')),
            'ra': str(r.get(COL_RA, '')),
            'household_code': str(r.get(COL_HH_CODE, '')),
            'error_count': int(r['error_count']),
        })
    return jsonify(records)


@app.route('/api/completion')
def api_completion():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    df = filter_cov(lga, ward, community)
    if COL_LGA not in df.columns:
        return jsonify([])
    completion_data = df.groupby([COL_LGA, COL_WARD, COL_COMMUNITY]).agg(
        households_reached=(COL_UUID, 'nunique'),
        ras=(COL_RA, 'nunique'),
    ).reset_index()
    result = []
    for _, r in completion_data.iterrows():
        code = str(r[COL_COMMUNITY]).strip()
        info = community_map.get(code, {})
        name = info.get('name', code)
        planned = info.get('sample_count', 0)
        reached = int(r['households_reached'])
        status = 'Complete' if planned > 0 and reached >= planned else 'Incomplete'
        result.append({
            'lga': str(r[COL_LGA]),
            'ward': str(r[COL_WARD]),
            'community': name,
            'community_code': code,
            'planned': planned,
            'reached': reached,
            'status': status,
            'ras': int(r['ras']),
        })
    return jsonify(result)


@app.route('/api/gps-data')
def api_gps_data():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    ra = request.args.get('ra')
    df = filter_cov(lga, ward, community, ra)
    if COL_LAT not in df.columns or COL_LNG not in df.columns:
        return jsonify([])
    gps = df[[COL_LAT, COL_LNG, COL_LGA, COL_WARD, COL_RA]].dropna(subset=[COL_LAT, COL_LNG]).copy()
    gps[COL_LAT] = pd.to_numeric(gps[COL_LAT], errors='coerce')
    gps[COL_LNG] = pd.to_numeric(gps[COL_LNG], errors='coerce')
    gps = gps.dropna(subset=[COL_LAT, COL_LNG])
    gps_precision = pd.to_numeric(df[COL_PRECISION], errors='coerce') if COL_PRECISION in df.columns else pd.Series([], dtype=float)
    result = []
    for _, r in gps.iterrows():
        result.append({
            'lat': float(r[COL_LAT]),
            'lng': float(r[COL_LNG]),
            'lga': str(r.get(COL_LGA, '')),
            'ward': str(r.get(COL_WARD, '')),
            'ra': str(r.get(COL_RA, '')),
        })
    return jsonify(result)


@app.route('/api/gps-summary')
def api_gps_summary():
    df = cov.copy()
    summary = {}
    if COL_LAT in df.columns and COL_LNG in df.columns:
        gps = df[[COL_LAT, COL_LNG]].dropna()
        total_gps = len(gps)
        stacked = int(gps.duplicated(keep=False).sum())
        unique_locations = int(gps.drop_duplicates().shape[0])
        summary['total_gps_points'] = total_gps
        summary['stacked_gps'] = stacked
        summary['unique_locations'] = unique_locations
        summary['stacked_pct'] = round((stacked / total_gps * 100) if total_gps > 0 else 0, 1)
    else:
        summary = {'total_gps_points': 0, 'stacked_gps': 0, 'unique_locations': 0, 'stacked_pct': 0}
    if COL_PRECISION in df.columns:
        prec = pd.to_numeric(df[COL_PRECISION], errors='coerce')
        summary['mock_gps'] = int((prec < 2).sum())
        summary['total_with_precision'] = int(prec.notna().sum())
    else:
        summary['mock_gps'] = 0
        summary['total_with_precision'] = 0
    return jsonify(summary)


@app.route('/api/validation')
def api_validation():
    df = cov.copy()
    ci = child_info.copy()
    ce = child_eligible.copy()
    validation = {}
    flags = []
    val_cols = []

    total_records = len(df)

    # VAL-05: Duplicate Household IDs
    dup_hh = 0
    if COL_HH_CODE in df.columns:
        dup_mask = df.duplicated(subset=[COL_HH_CODE], keep=False)
        dup_hh = int(dup_mask.sum())
        validation['dup_households'] = dup_hh
        if dup_hh > 0:
            val_cols.append('Duplicate Household IDs')
            for _, row in df[dup_mask].head(50).iterrows():
                lga = row.get(COL_LGA, '') if COL_LGA in row else ''
                ward = row.get(COL_WARD, '') if COL_WARD in row else ''
                ra = row.get(COL_RA, '') if COL_RA in row else ''
                flags.append({'type': 'Duplicate Household ID', 'lga': lga, 'ward': ward, 'ra': ra, 'detail': str(row.get(COL_HH_CODE, ''))})
    else:
        validation['dup_households'] = 0

    # VAL-06: Non-eligible children flagged
    non_eligible = 0
    if COL_IS_ELIGIBLE in ci.columns:
        ne_mask = ci[COL_IS_ELIGIBLE] == '0'
        non_eligible = int(ne_mask.sum())
        if non_eligible > 0:
            val_cols.append('Non-Eligible Children')
            for _, row in ci[ne_mask].head(50).iterrows():
                flags.append({'type': 'Non-Eligible Child', 'lga': '', 'ward': '', 'ra': '', 'detail': f'Child ID: {row.get("child_id", "")}'})
    validation['non_eligible_children'] = non_eligible

    # Duplicate children (child_info level)
    dup_children = 0
    child_name_col = None
    for c in ci.columns:
        if 'name of child' in str(c).lower():
            child_name_col = c
            break
    if child_name_col and COL_HH_CODE in df.columns:
        ci_with_hh = ci.copy()
        ci_with_hh['_parent_index'] = ci_with_hh['_parent_index'].astype(str)
        df_idx = df.copy()
        df_idx['_index'] = df_idx['_index'].astype(str)
        merged = ci_with_hh.merge(df_idx[['_index', COL_HH_CODE]], left_on='_parent_index', right_on='_index', how='left')
        dup_child_mask = merged.duplicated(subset=[child_name_col, COL_HH_CODE], keep=False)
        dup_children = int(dup_child_mask.sum())
        validation['dup_children'] = dup_children
        if dup_children > 0:
            val_cols.append('Duplicate Child Records')
    else:
        validation['dup_children'] = 0

    # VAL-01: Education vs Occupation consistency check
    edu_col = None
    occ_col = None
    for c in df.columns:
        if 'education' in str(c).lower():
            edu_col = c
        if 'occupation' in str(c).lower():
            occ_col = c
    edu_occ_flags = 0
    if edu_col and occ_col:
        edu_occ_mask = df[edu_col].notna() & df[occ_col].notna()
        edu_occ_flags = int(edu_occ_mask.sum())
        # Simple consistency: if education is "none" but occupation is "professional", flag
        LOW_EDU = ['none', 'no formal', 'primary', 'quranic']
        HIGH_OCC = ['professional', 'manager', 'teacher', 'doctor', 'nurse', 'engineer']
        for _, row in df[edu_occ_mask].head(50).iterrows():
            edu = str(row.get(edu_col, '')).lower().strip()
            occ = str(row.get(occ_col, '')).lower().strip()
            lga = row.get(COL_LGA, '') if COL_LGA in row else ''
            ward = row.get(COL_WARD, '') if COL_WARD in row else ''
            ra = row.get(COL_RA, '') if COL_RA in row else ''
            if any(e in edu for e in ['none', 'no formal']) and any(o in occ for o in HIGH_OCC):
                flags.append({'type': 'Education vs Occupation', 'lga': lga, 'ward': ward, 'ra': ra, 'detail': f'Edu: {edu}, Occ: {occ}'})
    validation['edu_occ_flags'] = edu_occ_flags

    # VAL-03: Gender vs Name consistency (basic - flag if gender is present)
    gender_col = None
    for c in df.columns:
        if 'gender' in str(c).lower() and 'head' in str(c).lower():
            gender_col = c
            break
    name_col = None
    for c in df.columns:
        if 'name' in str(c).lower() and 'head' in str(c).lower():
            name_col = c
            break
    gender_name_flags = 0
    if gender_col and name_col:
        gn_mask = df[gender_col].notna() & df[name_col].notna()
        gender_name_flags = int(gn_mask.sum())
    validation['gender_name_flags'] = gender_name_flags

    # Total households visited
    validation['total_records'] = total_records

    # Validator summary
    qc_cols = [c for c in df.columns if 'validation' in str(c).lower() or 'status' in str(c).lower() or '_status' in str(c).lower()]
    validated_count = 0
    approved_count = 0
    rejected_count = 0
    for c in qc_cols:
        vals = df[c].dropna().astype(str).str.lower()
        validated_count += int((vals != '').sum())
        approved_count += int(vals.isin(['approved', '1', 'yes']).sum())
        rejected_count += int(vals.isin(['rejected', 'not_approved', 'no', '0']).sum())
    validation['validated'] = min(validated_count, total_records)
    validation['approved'] = min(approved_count, total_records)
    validation['rejected'] = min(rejected_count, total_records)
    validation['outstanding'] = max(0, total_records - validation['validated'])
    validation['flagged_records'] = len(flags)

    # Per-LGA breakdown for the validator table
    lga_breakdown = []
    if COL_LGA in df.columns:
        for lga in df[COL_LGA].dropna().unique():
            lga_df = df[df[COL_LGA] == lga]
            lga_total = len(lga_df)
            ward_count = lga_df[COL_WARD].nunique() if COL_WARD in lga_df.columns else 0
            ra_count = lga_df[COL_RA].nunique() if COL_RA in lga_df.columns else 0
            lga_breakdown.append({'lga': lga, 'total': lga_total, 'wards': ward_count, 'ras': ra_count})
    validation['lga_breakdown'] = lga_breakdown

    # Per-RA error summary
    ra_errors = []
    if COL_RA in df.columns:
        for ra in df[COL_RA].dropna().unique():
            ra_df = df[df[COL_RA] == ra]
            ra_total = len(ra_df)
            ra_err = sum(1 for f in flags if f.get('ra') == ra)
            ra_errors.append({'ra': ra, 'records': ra_total, 'errors': ra_err, 'error_pct': round(ra_err / ra_total * 100, 1) if ra_total else 0})
    validation['ra_errors'] = sorted(ra_errors, key=lambda x: x['error_pct'], reverse=True)

    return jsonify({
        'summary': {
            'total_records': total_records,
            'validated': validation['validated'],
            'approved': validation['approved'],
            'rejected': validation['rejected'],
            'outstanding': validation['outstanding'],
            'flagged_records': validation['flagged_records'],
            'dup_households': validation['dup_households'],
            'non_eligible_children': validation['non_eligible_children'],
            'dup_children': dup_children,
            'edu_occ_flags': validation['edu_occ_flags'],
            'gender_name_flags': validation['gender_name_flags'],
            'total_ras': int(df[COL_RA].nunique()) if COL_RA in df.columns else 0,
        },
        'val_tasks': [
            {'id': 'VAL-01', 'name': 'Education vs Occupation', 'status': 'Active', 'flags': validation['edu_occ_flags']},
            {'id': 'VAL-02', 'name': 'Repetitive Child Selection', 'status': 'Not Started', 'flags': 0},
            {'id': 'VAL-03', 'name': 'Gender vs Name Consistency', 'status': 'Active', 'flags': validation['gender_name_flags']},
            {'id': 'VAL-04', 'name': 'Child Name vs Vaccination Card', 'status': 'Not Started', 'flags': 0},
            {'id': 'VAL-05', 'name': 'Duplicate Household ID', 'status': 'Active', 'flags': validation['dup_households']},
            {'id': 'VAL-06', 'name': 'Non-Eligible Children', 'status': 'Active', 'flags': validation['non_eligible_children']},
        ],
        'flags': sorted(flags, key=lambda x: x['type'])[:100],
        'lga_breakdown': lga_breakdown,
        'ra_errors': ra_errors[:50],
    })


@app.route('/api/filters')
def api_filters():
    from data_processor import get_lga_wards_communities, get_lga_hierarchy
    lga_list, ward_list, community_list, ra_list = get_lga_wards_communities(cov)
    # Build hierarchy for cascading dropdowns
    hierarchy = get_lga_hierarchy(cov) if COL_LGA in cov.columns else {}
    communities = [
        {'code': c, 'name': community_map.get(c, {}).get('name', c)}
        for c in community_list
    ]
    return jsonify({
        'lgas': lga_list,
        'wards': ward_list,
        'communities': communities,
        'ras': ra_list,
        'wards_by_lga': {lga: list(wards.keys()) for lga, wards in hierarchy.items()} if hierarchy else {},
        'communities_by_ward': hierarchy,
    })


@app.route('/api/supervision')
def api_supervision():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    settlement = request.args.get('settlement')
    df = cov.copy()
    ce = child_eligible.copy()
    from data_processor import compute_dq_metrics, compute_error_log
    dq = compute_dq_metrics(df, child_info, ce)
    errors_df = compute_error_log(df, ce, dq)
    error_cols = [c for c in errors_df.columns if c not in [COL_UUID, COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_HH_CODE, COL_SETTLEMENT_TYPE, COL_LAT, COL_LNG, COL_PRECISION]]
    errors_df['error_count'] = errors_df[error_cols].sum(axis=1) if len(error_cols) > 0 else 0
    errors_df = errors_df[errors_df['error_count'] > 0]

    level = 'lga'
    if settlement:
        level = 'settlement'
        group_cols = [COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA]
        if lga and ward and settlement:
            errs = errors_df[errors_df[COL_LGA] == lga]
            errs = errs[errs[COL_WARD] == ward]
            errs = errs[errs[COL_COMMUNITY] == settlement]
            total_records = len(df[(df[COL_LGA]==lga)&(df[COL_WARD]==ward)&(df[COL_COMMUNITY]==settlement)])
            ranking = []
            for ra_name, g in errs.groupby(COL_RA):
                total = len(g)
                dup = int(g['Duplicate Household'].sum()) if 'Duplicate Household' in g.columns else 0
                mock = int(g['Mock GPS'].sum()) if 'Mock GPS' in g.columns else 0
                stacked = int(g['Stacked GPS'].sum()) if 'Stacked GPS' in g.columns else 0
                score = round((total / max(total_records,1)) * 100, 1) if total > 0 else 0
                risk = 'High' if total > 5 else 'Medium' if total > 0 else 'Low'
                ranking.append({'name': str(ra_name), 'total_records': total_records, 'total_errors': total, 'dup_households': dup, 'mock_gps': mock, 'stacked_gps': stacked, 'score': score, 'risk': risk})
            ranking.sort(key=lambda x: x['score'], reverse=True)
    elif ward:
        level = 'ward'
        group_cols = [COL_LGA, COL_WARD, COL_COMMUNITY]
        if lga and ward:
            errs = errors_df[errors_df[COL_LGA] == lga]
            errs = errs[errs[COL_WARD] == ward]
            total_records = len(df[(df[COL_LGA]==lga)&(df[COL_WARD]==ward)])
            ranking = []
            for comm_name, g in errs.groupby(COL_COMMUNITY):
                total = int(len(g))
                total_records_for_unit = len(df[(df[COL_LGA]==lga)&(df[COL_WARD]==ward)&(df[COL_COMMUNITY]==comm_name)])
                dup = int(g['Duplicate Household'].sum()) if 'Duplicate Household' in g.columns else 0
                mock = int(g['Mock GPS'].sum()) if 'Mock GPS' in g.columns else 0
                stacked = int(g['Stacked GPS'].sum()) if 'Stacked GPS' in g.columns else 0
                score = round((total / max(total_records_for_unit,1)) * 100, 1)
                risk = 'High' if total > 5 else 'Medium' if total > 0 else 'Low'
                ranking.append({'name': str(comm_name), 'total_records': total_records_for_unit, 'total_errors': total, 'dup_households': dup, 'mock_gps': mock, 'stacked_gps': stacked, 'score': score, 'risk': risk})
            ranking.sort(key=lambda x: x['score'], reverse=True)
    elif lga:
        level = 'lga'
        group_cols = [COL_LGA, COL_WARD]
        errs = errors_df[errors_df[COL_LGA] == lga]
        total_records = len(df[df[COL_LGA]==lga])
        ranking = []
        for ward_name, g in errs.groupby(COL_WARD):
            total = int(len(g))
            total_records_for_unit = len(df[(df[COL_LGA]==lga)&(df[COL_WARD]==ward_name)])
            dup = int(g['Duplicate Household'].sum()) if 'Duplicate Household' in g.columns else 0
            mock = int(g['Mock GPS'].sum()) if 'Mock GPS' in g.columns else 0
            stacked = int(g['Stacked GPS'].sum()) if 'Stacked GPS' in g.columns else 0
            score = round((total / max(total_records_for_unit,1)) * 100, 1)
            risk = 'High' if total > 5 else 'Medium' if total > 0 else 'Low'
            ranking.append({'name': str(ward_name), 'total_records': total_records_for_unit, 'total_errors': total, 'dup_households': dup, 'mock_gps': mock, 'stacked_gps': stacked, 'score': score, 'risk': risk})
        ranking.sort(key=lambda x: x['score'], reverse=True)
    else:
        # Top-level: by LGA
        if COL_LGA not in df.columns:
            return jsonify({'ranking': [], 'totals': {}, 'level': 'lga', 'breadcrumb': []})
        ranking = []
        for lga_name, g in errors_df.groupby(COL_LGA):
            total = int(len(g))
            total_records_for_unit = int(len(df[df[COL_LGA]==lga_name]))
            dup = int(g['Duplicate Household'].sum()) if 'Duplicate Household' in g.columns else 0
            mock = int(g['Mock GPS'].sum()) if 'Mock GPS' in g.columns else 0
            stacked = int(g['Stacked GPS'].sum()) if 'Stacked GPS' in g.columns else 0
            score = round((total / max(total_records_for_unit,1)) * 100, 1)
            risk = 'High' if score > 10 else 'Medium' if score > 5 else 'Low'
            ranking.append({'name': str(lga_name), 'total_records': total_records_for_unit, 'total_errors': total, 'dup_households': dup, 'mock_gps': mock, 'stacked_gps': stacked, 'score': score, 'risk': risk})
        ranking.sort(key=lambda x: x['score'], reverse=True)

    breadcrumb = []
    if _sup_bc := locals().get('lga'):
        bc_lga = lga
        bc_ward = ward
        bc_settlement = settlement
        if bc_lga:
            breadcrumb.append({'label': str(bc_lga), 'lga': str(bc_lga), 'ward': None, 'settlement': None})
            if bc_ward:
                breadcrumb.append({'label': str(bc_ward), 'lga': str(bc_lga), 'ward': str(bc_ward), 'settlement': None})
                if bc_settlement:
                    breadcrumb.append({'label': str(bc_settlement), 'lga': str(bc_lga), 'ward': str(bc_ward), 'settlement': str(bc_settlement)})

    total_records = int(len(df))
    flagged_records = int(len(errors_df))
    totals = {'total_records': total_records, 'flagged_records': flagged_records}

    return jsonify({
        'ranking': ranking,
        'totals': totals,
        'level': level,
        'breadcrumb': breadcrumb,
    })


@app.route('/api/ai/insights')
def api_ai_insights():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    ra = request.args.get('ra')
    df = filter_cov(lga, ward, community, ra)
    ce = filter_child_eligible(lga, ward, community)
    insights = []
    # Coverage insight
    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_OFFERED_AZM in ce.columns else 0
    total_eligible = int(len(ce))
    cov_pct = round((offered / total_eligible * 100), 1) if total_eligible > 0 else 0
    if cov_pct >= 80:
        insights.append({'title': 'Good Coverage Rate', 'text': f'Coverage is at {cov_pct}%, meeting the 80% target.', 'type': 'success', 'icon': 'bi-check-circle-fill'})
    elif cov_pct >= 50:
        insights.append({'title': 'Moderate Coverage', 'text': f'Coverage is at {cov_pct}%. Efforts needed to reach 80% target.', 'type': 'warning', 'icon': 'bi-exclamation-triangle-fill'})
    else:
        insights.append({'title': 'Low Coverage Alert', 'text': f'Coverage is at {cov_pct}%. Immediate action required.', 'type': 'danger', 'icon': 'bi-bug-fill'})
    # Stacked GPS
    if COL_LAT in df.columns and COL_LNG in df.columns:
        gps = df[[COL_LAT, COL_LNG]].dropna()
        stacked = int(gps.duplicated(keep=False).sum())
        if stacked > 0:
            insights.append({'title': 'Stacked GPS Points Detected', 'text': f'{stacked} GPS points share identical coordinates, indicating possible falsification.', 'type': 'danger', 'icon': 'bi-pin-map-fill'})
    # Duplicate HH
    if COL_HH_CODE in df.columns:
        dup = int(df[df.duplicated(subset=[COL_HH_CODE], keep=False)][COL_HH_CODE].nunique())
        if dup > 0:
            insights.append({'title': 'Duplicate Household IDs', 'text': f'{dup} duplicate household IDs found. Review and resolve conflicts.', 'type': 'warning', 'icon': 'bi-house-x-fill'})
    return jsonify(insights)


@app.route('/api/ai/regression')
def api_ai_regression():
    lga = request.args.get('lga')
    ward = request.args.get('ward')
    community = request.args.get('community')
    ra = request.args.get('ra')
    df = filter_cov(lga, ward, community, ra)
    daily_data = []
    if COL_SUBMISSION_TIME in df.columns:
        daily = df.copy()
        daily['date'] = pd.to_datetime(daily[COL_SUBMISSION_TIME], errors='coerce').dt.date
        daily_counts = daily.groupby('date').size().reset_index(name='count').sort_values('date')
        dates = [str(r['date']) for _, r in daily_counts.iterrows()]
        counts = [int(r['count']) for _, r in daily_counts.iterrows()]
        # Simple forecast: use average of last 3 days
        avg = round(sum(counts[-3:]) / 3) if len(counts) >= 3 else (counts[-1] if counts else 0)
        from datetime import timedelta
        last_date = daily_counts['date'].iloc[-1] if len(daily_counts) > 0 else datetime.now().date()
        forecast_dates = []
        forecast_counts = []
        for i in range(1, 8):
            forecast_dates.append(str(last_date + timedelta(days=i)))
            forecast_counts.append(avg)
        # Pad actual with None for forecast period
        actual_padded = list(counts) + [None] * 7
        forecast_padded = [None] * len(counts) + forecast_counts
        all_labels = dates + forecast_dates
        daily_data = {'labels': all_labels, 'actual': actual_padded, 'forecast': forecast_padded}
    else:
        daily_data = {'labels': [], 'actual': [], 'forecast': []}

    # LGA trends
    lga_trends = {}
    if COL_LGA in df.columns and COL_SUBMISSION_TIME in df.columns:
        for lga_name in df[COL_LGA].unique():
            lga_df = df[df[COL_LGA] == lga_name]
            lga_df = lga_df.copy()
            lga_df['date'] = pd.to_datetime(lga_df[COL_SUBMISSION_TIME], errors='coerce').dt.date
            lga_daily = lga_df.groupby('date').size()
            if len(lga_daily) >= 2:
                current = int(lga_daily.iloc[-1])
                prev = int(lga_daily.iloc[-2])
                trend = round((current - prev) / max(prev, 1) * 100, 1)
            else:
                current = int(lga_daily.iloc[-1]) if len(lga_daily) > 0 else 0
                trend = 0
            lga_trends[str(lga_name)] = {'current': current, 'trend': trend}

    kpis = {}
    ce = filter_child_eligible(lga, ward, community)
    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_OFFERED_AZM in ce.columns else 0
    total_eligible = int(len(ce))
    kpis['Coverage'] = f'{round((offered / max(total_eligible,1))*100,1)}%'
    kpis['Total HH'] = str(int(len(df)))
    kpis['Active RAs'] = str(int(df[COL_RA].nunique())) if COL_RA in df.columns else '0'

    return jsonify({'chart': daily_data, 'kpis': kpis, 'lga_trends': lga_trends})


@app.route('/api/ai/anomaly')
def api_ai_anomaly():
    lga = request.args.get('lga')
    df = filter_cov(lga)
    anomalies = []
    # Check for unusually stacked GPS
    if COL_LAT in df.columns and COL_LNG in df.columns:
        gps = df[[COL_LAT, COL_LNG]].dropna()
        stacked = int(gps.duplicated(keep=False).sum())
        if stacked > 0:
            anomalies.append({'title': 'Stacked GPS Coordinates', 'description': f'{stacked} records share identical GPS coordinates.', 'severity': 'high', 'location': str(lga) if lga else 'All', 'date': ''})
    # Check for high error rate per RA
    if COL_RA in df.columns:
        ra_counts = df[COL_RA].value_counts()
        avg = ra_counts.mean()
        for ra, count in ra_counts.items():
            if count > avg * 2:
                anomalies.append({'title': f'High Submission Count: {ra}', 'description': f'{count} submissions vs average {avg:.0f}.', 'severity': 'medium', 'location': str(ra), 'date': ''})
    return jsonify(anomalies)


@app.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    import json
    data = request.get_json(silent=True) or {}
    msg = (data.get('message') or '').strip().lower()
    # Build summary for query answering
    total_hh = int(len(cov))
    total_lga = int(cov[COL_LGA].nunique()) if COL_LGA in cov.columns else 0
    total_ra = int(cov[COL_RA].nunique()) if COL_RA in cov.columns else 0
    total_wards = int(cov[COL_WARD].nunique()) if COL_WARD in cov.columns else 0
    total_communities = int(cov[COL_COMMUNITY].nunique()) if COL_COMMUNITY in cov.columns else 0
    ce = child_eligible
    offered = int((ce[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_OFFERED_AZM in ce.columns else 0
    swallowed = int((ce[COL_SWALLOWED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_SWALLOWED_AZM in ce.columns else 0
    eligible = int((child_info[COL_IS_ELIGIBLE] == '1').sum()) if COL_IS_ELIGIBLE in child_info.columns else 0
    cov_pct = round((offered / max(eligible,1)) * 100, 1)

    reply = ''
    if 'coverage' in msg or 'percentage' in msg:
        reply = f'The overall AZM coverage rate is {cov_pct}% ({offered} of {eligible} eligible children were offered AZM).'
    elif 'lga' in msg and ('top' in msg or 'most' in msg):
        if COL_LGA in cov.columns:
            top = cov[COL_LGA].value_counts().index[0]
            reply = f'The LGA with the most submissions is {top}.'
        else:
            reply = 'LGA data is not available.'
    elif 'quality' in msg or 'issue' in msg:
        from data_processor import compute_dq_metrics
        dq = compute_dq_metrics(cov, child_info, ce)
        issues = []
        if dq.get('dup_household_count', 0) > 0:
            issues.append(f"{dq['dup_household_count']} duplicate households")
        if dq.get('mock_gps', 0) > 0:
            issues.append(f"{dq['mock_gps']} mock GPS points")
        if dq.get('stacked_gps', 0) > 0:
            issues.append(f"{dq['stacked_gps']} stacked GPS points")
        if issues:
            reply = f'Data quality issues found: {", ".join(issues)}.'
        else:
            reply = 'No major data quality issues found.'
    elif 'eligible' in msg or 'child' in msg:
        reply = f'There are {eligible} eligible children (1-59 months) recorded in the survey.'
    elif 'household' in msg or 'hh' in msg:
        reply = f'A total of {total_hh} households were surveyed across {total_lga} LGAs, {total_wards} wards, and {total_communities} communities.'
    elif 'ra' in msg or 'assistant' in msg or 'enumerator' in msg:
        reply = f'There are {total_ra} active research assistants in the field.'
    elif 'swallow' in msg:
        rate = round((swallowed / max(offered,1)) * 100, 1)
        reply = f'{swallowed} of {offered} children who were offered AZM swallowed it ({rate}% swallow rate).'
    else:
        reply = f'I can tell you about coverage ({cov_pct}%), top LGAs, data quality issues, eligible children, households, RAs, or swallow rates. Try asking a specific question.'
    return jsonify({'reply': reply})


@app.route('/api/summary')
def api_summary():
    total_hh = int(len(cov))
    total_lga = int(cov[COL_LGA].nunique()) if COL_LGA in cov.columns else 0
    total_ra = int(cov[COL_RA].nunique()) if COL_RA in cov.columns else 0
    total_children = int(len(child_eligible))
    eligible = int((child_info[COL_IS_ELIGIBLE] == '1').sum()) if COL_IS_ELIGIBLE in child_info.columns else 0
    offered = int((child_eligible[COL_OFFERED_AZM].str.strip().str.lower() == 'yes').sum()) if COL_OFFERED_AZM in child_eligible.columns else 0
    return jsonify({
        'total_households': total_hh,
        'total_lgas': total_lga,
        'total_ras': total_ra,
        'total_children': total_children,
        'eligible_children': eligible,
        'offered_azm': offered,
    })


@app.route('/')
def index():
    return render_template('dashboard.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5051))
    print(f"Coverage Dashboard running at http://127.0.0.1:{port}")
    app.run(debug=True, host='127.0.0.1', port=port)
