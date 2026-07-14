import dash
from dash import dcc, html, dash_table, Input, Output, State, callback
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from data_processor import *

# ─── Load data ───
cov, child_info, child_eligible = load_all_data()
kpis = compute_kpis(cov, child_info, child_eligible)
charts_data = compute_chart_data(cov, child_eligible)
dq = compute_dq_metrics(cov, child_info, child_eligible)
lga_list, ward_list, community_list, ra_list = get_lga_wards_communities(cov)
lga_summary = compute_completion_data(cov)
error_log = compute_error_log(cov, child_eligible, dq)

# ─── Color palette (modern, accessible) ───
COLORS = {
    'primary': '#1B3A5C',
    'secondary': '#2E86C1',
    'accent': '#17A589',
    'danger': '#E74C3C',
    'warning': '#F39C12',
    'light': '#F8F9FA',
    'dark': '#212529',
    'sidebar': '#0D2137',
    'card_bg': '#FFFFFF',
    'card_shadow': '0 2px 8px rgba(0,0,0,0.08)',
    'text_muted': '#6C757D',
    'success': '#28B463',
    'gradient_start': '#1B3A5C',
    'gradient_end': '#2E86C1',
}

KPI_COLORS = {
    'total_households': '#2E86C1',
    'children_under_18': '#17A589',
    'eligible_children': '#F39C12',
    'offered_azm': '#28B463',
    'not_offered_azm': '#E74C3C',
    'swallowed_azm': '#1ABC9C',
    'vacc_cards': '#8E44AD',
    'lgas_reached': '#3498DB',
    'wards_reached': '#E67E22',
    'communities_reached': '#9B59B6',
}

KPI_LABELS = {
    'total_households': 'Total Households',
    'children_under_18': 'Children < 18 Yrs',
    'eligible_children': 'Eligible (1-59 Mo)',
    'offered_azm': 'Offered AZM',
    'not_offered_azm': 'Not Offered AZM',
    'swallowed_azm': 'Swallowed AZM',
    'vacc_cards': 'Vaccination Cards',
    'lgas_reached': 'LGAs Reached',
    'wards_reached': 'Wards Reached',
    'communities_reached': 'Communities Reached',
}

KPI_ICONS = {
    'total_households': '🏠',
    'children_under_18': '👶',
    'eligible_children': '🎯',
    'offered_azm': '💊',
    'not_offered_azm': '🚫',
    'swallowed_azm': '✅',
    'vacc_cards': '📋',
    'lgas_reached': '🗺️',
    'wards_reached': '📍',
    'communities_reached': '🏘️',
}

# ─── Initialize app ───
app = dash.Dash(
    __name__,
    title='SARMAAN II Coverage Dashboard',
    suppress_callback_exceptions=True,
    assets_folder='assets',
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

server = app.server

# ─── App Layout ───
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div([
        # ─── Sidebar ───
        html.Div([
            html.Div([
                html.Div('📊', style={'fontSize': '28px', 'textAlign': 'center'}),
                html.H3('SARMAAN II', style={'color': 'white', 'margin': '8px 0 2px', 'fontSize': '16px', 'fontWeight': '600'}),
                html.P('Coverage Dashboard', style={'color': 'rgba(255,255,255,0.7)', 'fontSize': '12px', 'margin': '0'}),
                html.P('Sokoto, Nigeria', style={'color': 'rgba(255,255,255,0.5)', 'fontSize': '11px', 'margin': '2px 0 0'}),
            ], style={'padding': '20px 16px', 'borderBottom': '1px solid rgba(255,255,255,0.1)'}),

            # Navigation
            html.Nav([
                html.Div([
                    html.A('📊  Overview', href='/', className='nav-link', id='nav-overview',
                           style={'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.8)',
                                  'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
                                  'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s',
                                  'background': 'rgba(255,255,255,0.1)'}),
                    html.A('📈  Demography', href='/demography', className='nav-link', id='nav-demography',
                           style={'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.6)',
                                  'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
                                  'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s'}),
                    html.A('✓  Completion', href='/completion', className='nav-link', id='nav-completion',
                           style={'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.6)',
                                  'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
                                  'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s'}),
                    html.A('📍  GIS Analysis', href='/gis', className='nav-link', id='nav-gis',
                           style={'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.6)',
                                  'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
                                  'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s'}),
                    html.A('🔍  Data Quality', href='/quality', className='nav-link', id='nav-quality',
                           style={'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.6)',
                                  'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
                                  'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s'}),
                    html.A('✅  Validation', href='/validation', className='nav-link', id='nav-validation',
                           style={'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.6)',
                                  'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
                                  'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s'}),
                ], style={'padding': '12px 0'})
            ]),

            # Filters section
            html.Div([
                html.H4('Filters', style={'color': 'rgba(255,255,255,0.7)', 'fontSize': '13px',
                                          'textTransform': 'uppercase', 'letterSpacing': '1px',
                                          'margin': '0 0 12px', 'padding': '0 16px'}),
                html.Label('LGA', style={'color': 'rgba(255,255,255,0.6)', 'fontSize': '12px', 'padding': '0 16px'}),
                dcc.Dropdown(
                    id='filter-lga',
                    options=[{'label': l, 'value': l} for l in lga_list],
                    multi=True,
                    placeholder='All LGAs',
                    style={'margin': '4px 16px 12px', 'fontSize': '13px'}
                ),
                html.Label('Ward', style={'color': 'rgba(255,255,255,0.6)', 'fontSize': '12px', 'padding': '0 16px'}),
                dcc.Dropdown(
                    id='filter-ward',
                    options=[{'label': w, 'value': w} for w in ward_list],
                    multi=True,
                    placeholder='All Wards',
                    style={'margin': '4px 16px 12px', 'fontSize': '13px'}
                ),
                html.Label('Research Assistant', style={'color': 'rgba(255,255,255,0.6)', 'fontSize': '12px', 'padding': '0 16px'}),
                dcc.Dropdown(
                    id='filter-ra',
                    options=[{'label': r, 'value': r} for r in ra_list],
                    multi=True,
                    placeholder='All RAs',
                    style={'margin': '4px 16px 16px', 'fontSize': '13px'}
                ),
                html.Button('Reset Filters', id='btn-reset', n_clicks=0,
                           style={'margin': '0 16px', 'padding': '8px', 'width': 'calc(100% - 32px)',
                                  'background': 'rgba(255,255,255,0.1)', 'border': '1px solid rgba(255,255,255,0.2)',
                                  'color': 'white', 'borderRadius': '6px', 'cursor': 'pointer', 'fontSize': '13px'}),
            ], style={'padding': '16px 0', 'borderTop': '1px solid rgba(255,255,255,0.1)'}),

            # Footer
            html.Div([
                html.P('v1.0 | SARMAAN II', style={'color': 'rgba(255,255,255,0.3)', 'fontSize': '11px', 'textAlign': 'center'})
            ], style={'padding': '16px', 'borderTop': '1px solid rgba(255,255,255,0.1)', 'marginTop': 'auto'}),
        ], style={
            'width': '260px', 'height': '100vh', 'background': COLORS['sidebar'],
            'position': 'fixed', 'top': '0', 'left': '0',
            'display': 'flex', 'flexDirection': 'column', 'zIndex': '1000',
            'overflowY': 'auto'
        }),

        # ─── Main Content ───
        html.Div([
            html.Div(id='page-content')
        ], style={
            'marginLeft': '260px', 'padding': '24px 32px',
            'background': '#F0F2F5', 'minHeight': '100vh'
        }),
    ])
], style={'fontFamily': "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"})


# ─── KPI Card Component ───
def kpi_card(label, value, color, icon, subtitle=None, delta=None):
    return html.Div([
        html.Div([
            html.Span(icon, style={'fontSize': '22px', 'opacity': '0.8'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
        html.Div(value, style={
            'fontSize': '28px', 'fontWeight': '700', 'color': COLORS['dark'],
            'lineHeight': '1.1', 'marginBottom': '4px'
        }),
        html.Div(label, style={
            'fontSize': '12px', 'color': COLORS['text_muted'],
            'fontWeight': '500', 'textTransform': 'uppercase', 'letterSpacing': '0.5px'
        }),
        html.Div(subtitle, style={'fontSize': '11px', 'color': COLORS['text_muted'], 'marginTop': '4px'}) if subtitle else None,
    ], style={
        'background': COLORS['card_bg'], 'borderRadius': '12px', 'padding': '16px 18px',
        'boxShadow': COLORS['card_shadow'], 'borderTop': f'3px solid {color}',
        'transition': 'transform 0.15s', 'cursor': 'default',
        ':hover': {'transform': 'translateY(-2px)'}
    })


# ─── Overview Page ───
def overview_page():
    demography_kpis = ['total_households', 'lgas_reached', 'wards_reached', 'communities_reached',
                       'eligible_children', 'offered_azm', 'swallowed_azm', 'vacc_cards']
    top_kpis = [k for k in demography_kpis if k in kpis]

    kpi_row = html.Div([
        html.Div([
            kpi_card(KPI_LABELS[k], f'{kpis[k]:,}', KPI_COLORS.get(k, COLORS['primary']), KPI_ICONS.get(k, '📊'))
            for k in top_kpis
        ], style={
            'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fill, minmax(200px, 1fr))',
            'gap': '16px', 'marginBottom': '24px'
        })
    ])

    # Charts row
    daily_df = charts_data['daily_hh']
    if not daily_df.empty:
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        fig_daily = px.bar(daily_df, x='date', y='count', title='Households per Implementation Day',
                           color_discrete_sequence=[COLORS['secondary']],
                           labels={'date': 'Date', 'count': 'Households'})
        fig_daily.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=40, r=20, t=50, b=40),
            hovermode='x', title_font=dict(size=14, color=COLORS['dark']),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#F0F2F5')
        )
    else:
        fig_daily = go.Figure()
        fig_daily.add_annotation(text='No data available', showarrow=False)

    ra_df = charts_data['submissions_per_ra']
    if not ra_df.empty:
        ra_top = ra_df.head(20)
        fig_ra = px.bar(ra_top, x='count', y=COL_RA, title='Submissions per Research Assistant',
                        color='count', color_continuous_scale='Blues', orientation='h',
                        labels={'count': 'Submissions', COL_RA: 'Research Assistant'})
        fig_ra.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=20, r=20, t=50, b=20),
            title_font=dict(size=14, color=COLORS['dark']),
            xaxis=dict(showgrid=True, gridcolor='#F0F2F5'),
            yaxis=dict(showgrid=False, autorange='reversed'),
            coloraxis_showscale=False
        )
    else:
        fig_ra = go.Figure()
        fig_ra.add_annotation(text='No data available', showarrow=False)

    # AZM Funnel
    funnel = charts_data['azm_funnel']
    fig_funnel = go.Figure()
    if funnel['count'][0] > 0:
        fig_funnel.add_trace(go.Funnel(
            name='AZM Coverage',
            y=funnel['stage'],
            x=funnel['count'],
            textinfo='value+percent initial',
            marker=dict(colors=[COLORS['warning'], COLORS['secondary'], COLORS['accent']])
        ))
    fig_funnel.update_layout(
        title='AZM Coverage Funnel', margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor='white', paper_bgcolor='white',
        title_font=dict(size=14, color=COLORS['dark'])
    )

    # CDD Visitation
    cdd_df = charts_data['cdd_visitation']
    if not cdd_df.empty:
        fig_cdd = px.pie(cdd_df, values='count', names='response', title='CDD Home Visitation',
                         color_discrete_sequence=[COLORS['accent'], COLORS['danger']],
                         hole=0.4)
        fig_cdd.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=20, r=20, t=50, b=20),
            title_font=dict(size=14, color=COLORS['dark'])
        )
    else:
        fig_cdd = go.Figure()
        fig_cdd.add_annotation(text='No data', showarrow=False)

    # DQ Summary Cards
    dq_kpis = html.Div([
        kpi_card('Duplicate HHs', f'{dq["dup_household_count"]}', COLORS['danger'], '⚠️'),
        kpi_card('Active RAs', f'{dq["active_ras"]}', COLORS['accent'], '👤'),
        kpi_card('Settlement Mismatch', f'{dq["settlement_mismatch"]}', COLORS['warning'], '🏠'),
        kpi_card('Mock GPS', f'{dq["mock_gps"]}', COLORS['danger'], '📡'),
        kpi_card('Stacked GPS', f'{dq["stacked_gps"]}', COLORS['warning'], '📍'),
        kpi_card('Ineligible Children', f'{dq["ineligible_children"]}', COLORS['danger'], '🔞'),
    ], style={
        'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fill, minmax(180px, 1fr))',
        'gap': '14px', 'marginBottom': '24px'
    })

    # LGA Completion Table
    lga_table = dash_table.DataTable(
        id='lga-table',
        columns=[{'name': c, 'id': c} for c in lga_summary.columns],
        data=lga_summary.to_dict('records'),
        style_header={
            'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': '600',
            'fontSize': '13px', 'textAlign': 'left', 'padding': '10px 14px'
        },
        style_cell={
            'padding': '8px 14px', 'fontSize': '13px', 'textAlign': 'left',
            'borderBottom': '1px solid #F0F2F5', 'fontFamily': 'inherit'
        },
        style_data_conditional=[
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#F8F9FA'},
        ],
        style_table={'borderRadius': '8px', 'overflow': 'hidden', 'boxShadow': COLORS['card_shadow']},
    )

    return html.Div([
        html.Div([
            html.H2('Coverage Dashboard Overview', style={'margin': '0', 'fontSize': '24px', 'fontWeight': '600', 'color': COLORS['dark']}),
            html.P('Real-time monitoring of SARMAAN II MDA Coverage Survey — Sokoto State',
                   style={'margin': '4px 0 0', 'color': COLORS['text_muted'], 'fontSize': '14px'}),
        ], style={'marginBottom': '24px'}),

        html.H3('📊 Demography KPIs', style={'fontSize': '16px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '12px'}),
        kpi_row,

        html.Div([
            html.Div([
                html.Div([dcc.Graph(figure=fig_daily)], style={
                    'background': 'white', 'borderRadius': '12px', 'padding': '16px',
                    'boxShadow': COLORS['card_shadow'], 'flex': '1'
                }),
                html.Div([dcc.Graph(figure=fig_cdd)], style={
                    'background': 'white', 'borderRadius': '12px', 'padding': '16px',
                    'boxShadow': COLORS['card_shadow'], 'flex': '1'
                }),
            ], style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}),
            html.Div([
                html.Div([dcc.Graph(figure=fig_ra)], style={
                    'background': 'white', 'borderRadius': '12px', 'padding': '16px',
                    'boxShadow': COLORS['card_shadow'], 'flex': '1'
                }),
                html.Div([dcc.Graph(figure=fig_funnel)], style={
                    'background': 'white', 'borderRadius': '12px', 'padding': '16px',
                    'boxShadow': COLORS['card_shadow'], 'flex': '1'
                }),
            ], style={'display': 'flex', 'gap': '20px', 'marginBottom': '24px'}),
        ]),

        html.H3('🔍 Data Quality Summary', style={'fontSize': '16px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '12px'}),
        dq_kpis,

        html.H3('🗺️ LGA Completion Summary', style={'fontSize': '16px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '12px'}),
        lga_table,
    ])


# ─── Demography Page ───
def demography_page():
    all_demo_kpis = ['total_households', 'children_under_18', 'eligible_children',
                     'offered_azm', 'not_offered_azm', 'swallowed_azm', 'vacc_cards',
                     'lgas_reached', 'wards_reached', 'communities_reached']
    kpi_row = html.Div([
        html.Div([
            kpi_card(KPI_LABELS[k], f'{kpis[k]:,}', KPI_COLORS.get(k, COLORS['primary']), KPI_ICONS.get(k, '📊'))
            for k in all_demo_kpis
        ], style={
            'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fill, minmax(180px, 1fr))',
            'gap': '14px', 'marginBottom': '24px'
        })
    ])

    daily_df = charts_data['daily_hh']
    if not daily_df.empty:
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        fig_daily = px.bar(daily_df, x='date', y='count', title='Households per Implementation Day',
                           color_discrete_sequence=[COLORS['secondary']],
                           labels={'date': 'Date', 'count': 'Households'})
        fig_daily.update_layout(plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=40, r=20, t=50, b=40))
    else:
        fig_daily = go.Figure()

    ra_df = charts_data['submissions_per_ra']
    if not ra_df.empty:
        ra_top = ra_df.head(20)
        fig_ra = px.bar(ra_top, x='count', y=COL_RA, title='Submissions per Research Assistant',
                        color='count', color_continuous_scale='Blues', orientation='h',
                        labels={'count': 'Submissions', COL_RA: 'Research Assistant'})
        fig_ra.update_layout(plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=20, r=20, t=50, b=20),
                            yaxis=dict(autorange='reversed'), coloraxis_showscale=False)
    else:
        fig_ra = go.Figure()

    # AZM Offer vs Not Offer pie
    azm_data = {'Offered': kpis['offered_azm'], 'Not Offered': kpis['not_offered_azm']}
    if sum(azm_data.values()) > 0:
        fig_azm_pie = px.pie(names=list(azm_data.keys()), values=list(azm_data.values()),
                            title='AZM Offer Rate', color_discrete_sequence=[COLORS['accent'], COLORS['danger']], hole=0.4)
        fig_azm_pie.update_layout(plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=20, r=20, t=50, b=20))
    else:
        fig_azm_pie = go.Figure()

    # GPS Distribution Map
    if COL_LAT in cov.columns and COL_LNG in cov.columns:
        gps = cov[[COL_LAT, COL_LNG]].dropna().copy()
        gps[COL_LAT] = pd.to_numeric(gps[COL_LAT], errors='coerce')
        gps[COL_LNG] = pd.to_numeric(gps[COL_LNG], errors='coerce')
        gps = gps.dropna()
        if not gps.empty:
            fig_gps = px.scatter_map(
                gps.sample(min(500, len(gps))), lat=COL_LAT, lon=COL_LNG,
                title='Household GPS Distribution', zoom=8, height=400,
                color_discrete_sequence=[COLORS['secondary']], opacity=0.6
            )
            fig_gps.update_layout(margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor='white')
        else:
            fig_gps = go.Figure()
    else:
        fig_gps = go.Figure()

    return html.Div([
        html.H2('Demography', style={'fontSize': '24px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '20px'}),
        kpi_row,
        html.Div([
            html.Div([dcc.Graph(figure=fig_daily)], style={'background': 'white', 'borderRadius': '12px', 'padding': '16px', 'boxShadow': COLORS['card_shadow'], 'flex': '1'}),
            html.Div([dcc.Graph(figure=fig_azm_pie)], style={'background': 'white', 'borderRadius': '12px', 'padding': '16px', 'boxShadow': COLORS['card_shadow'], 'flex': '0.6'}),
        ], style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}),
        html.Div([
            html.Div([dcc.Graph(figure=fig_ra)], style={'background': 'white', 'borderRadius': '12px', 'padding': '16px', 'boxShadow': COLORS['card_shadow'], 'flex': '1'}),
            html.Div([dcc.Graph(figure=fig_gps)], style={'background': 'white', 'borderRadius': '12px', 'padding': '16px', 'boxShadow': COLORS['card_shadow'], 'flex': '1.5'}),
        ], style={'display': 'flex', 'gap': '20px'}),
    ])


# ─── Completion Page ───
def completion_page():
    lga_table = dash_table.DataTable(
        columns=[{'name': c, 'id': c} for c in lga_summary.columns],
        data=lga_summary.to_dict('records'),
        style_header={'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': '600', 'fontSize': '13px', 'textAlign': 'left', 'padding': '10px 14px'},
        style_cell={'padding': '8px 14px', 'fontSize': '13px', 'textAlign': 'left', 'borderBottom': '1px solid #F0F2F5', 'fontFamily': 'inherit'},
        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#F8F9FA'}],
        style_table={'borderRadius': '8px', 'overflow': 'hidden', 'boxShadow': COLORS['card_shadow']},
        sort_action='native', filter_action='native',
    )

    fig_lga = px.bar(lga_summary, x='LGA', y='Households Reached',
                     title='Households Reached by LGA',
                     color='Households Reached', color_continuous_scale='Blues',
                     text='Households Reached')
    fig_lga.update_traces(textposition='outside')
    fig_lga.update_layout(plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=40, r=20, t=50, b=40),
                         xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#F0F2F5'))

    return html.Div([
        html.H2('Completion Tracking', style={'fontSize': '24px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '20px'}),
        html.Div([
            html.Div([
                html.H4('COMP-01: LGA Planned vs Reached', style={'fontSize': '15px', 'fontWeight': '600', 'margin': '0 0 16px'}),
                dcc.Graph(figure=fig_lga),
            ], style={'background': 'white', 'borderRadius': '12px', 'padding': '20px', 'boxShadow': COLORS['card_shadow'], 'marginBottom': '20px'}),
            html.Div([
                html.H4('COMP-02: LGA Completion Summary Table', style={'fontSize': '15px', 'fontWeight': '600', 'margin': '0 0 16px'}),
                lga_table,
            ], style={'background': 'white', 'borderRadius': '12px', 'padding': '20px', 'boxShadow': COLORS['card_shadow']}),
        ]),
    ])


# ─── GIS Page ───
def gis_page():
    gps = pd.DataFrame()
    if COL_LAT in cov.columns and COL_LNG in cov.columns:
        gps = cov[[COL_LAT, COL_LNG, COL_PRECISION, COL_UUID, COL_LGA, COL_WARD, COL_COMMUNITY]].dropna(subset=[COL_LAT, COL_LNG]).copy()
        gps[COL_LAT] = pd.to_numeric(gps[COL_LAT], errors='coerce')
        gps[COL_LNG] = pd.to_numeric(gps[COL_LNG], errors='coerce')
        gps[COL_PRECISION] = pd.to_numeric(gps[COL_PRECISION], errors='coerce')
        gps = gps.dropna(subset=[COL_LAT, COL_LNG])

    # Map all GPS points
    if not gps.empty:
        gps['is_stacked'] = gps.duplicated(subset=[COL_LAT, COL_LNG], keep=False)
        gps['is_mock'] = gps[COL_PRECISION] < 2

        fig_gps_map = px.scatter_map(
            gps.sample(min(800, len(gps))),
            lat=COL_LAT, lon=COL_LNG,
            color='is_mock' if gps['is_mock'].any() else None,
            hover_name=COL_UUID,
            hover_data={COL_LAT: ':.4f', COL_LNG: ':.4f', COL_PRECISION: True, 'is_stacked': True},
            title='GPS Distribution (Red = Mock GPS)',
            zoom=8, height=500,
            color_discrete_map={True: COLORS['danger'], False: COLORS['secondary']}
        )
        fig_gps_map.update_layout(margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor='white')
    else:
        fig_gps_map = go.Figure()

    # DQ GPS metrics
    gis_kpis = html.Div([
        kpi_card('Stacked GPS Points', f'{dq["stacked_gps"]}', COLORS['warning'], '📍',
                 subtitle=f'{(dq["stacked_gps"]/len(cov)*100) if len(cov) > 0 else 0:.1f}% of records'),
        kpi_card('Mock GPS Detected', f'{dq["mock_gps"]}', COLORS['danger'], '📡',
                 subtitle=f'{(dq["mock_gps"]/len(cov)*100) if len(cov) > 0 else 0:.1f}% of records'),
        kpi_card('Total GPS Records', f'{len(gps)}', COLORS['accent'], '🗺️',
                 subtitle=f'of {len(cov)} total households'),
        kpi_card('Avg GPS Precision', f'{gps[COL_PRECISION].mean():.1f}' if not gps.empty else 'N/A', COLORS['secondary'], '🎯'),
    ], style={
        'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fill, minmax(200px, 1fr))',
        'gap': '16px', 'marginBottom': '20px'
    })

    # Stacked GPS table
    stacked_records = gps[gps['is_stacked']].drop_duplicates(subset=[COL_LAT, COL_LNG]) if not gps.empty else pd.DataFrame()
    stacked_table_data = stacked_records.head(50).to_dict('records') if not stacked_records.empty else []

    stacked_table = dash_table.DataTable(
        columns=[{'name': c, 'id': c} for c in ['_uuid', COL_LGA, COL_WARD, COL_COMMUNITY, COL_LAT, COL_LNG]],
        data=stacked_table_data,
        style_header={'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': '600', 'fontSize': '13px'},
        style_cell={'padding': '8px 12px', 'fontSize': '12px', 'borderBottom': '1px solid #F0F2F5'},
        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#F8F9FA'}],
        style_table={'borderRadius': '8px', 'overflow': 'hidden', 'boxShadow': COLORS['card_shadow'], 'maxHeight': '400px', 'overflowY': 'auto'},
    )

    return html.Div([
        html.H2('GIS Analysis', style={'fontSize': '24px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '20px'}),
        gis_kpis,
        html.Div([
            html.Div([dcc.Graph(figure=fig_gps_map)], style={'background': 'white', 'borderRadius': '12px', 'padding': '16px', 'boxShadow': COLORS['card_shadow'], 'marginBottom': '20px'}),
            html.Div([
                html.H4('Stacked GPS Records', style={'fontSize': '15px', 'fontWeight': '600', 'margin': '0 0 12px'}),
                stacked_table,
            ], style={'background': 'white', 'borderRadius': '12px', 'padding': '20px', 'boxShadow': COLORS['card_shadow']}),
        ]),
    ])


# ─── Data Quality Page ───
def quality_page():
    dq_kpis = html.Div([
        kpi_card('Duplicate Households', f'{dq["dup_household_count"]}', COLORS['danger'], '🏠',
                 subtitle=f'{dq["dup_households"]} total records affected'),
        kpi_card('Duplicate Children', f'{dq["dup_child_count"]}', COLORS['danger'], '👶',
                 subtitle=f'{dq["dup_children"]} total records affected'),
        kpi_card('Settlement Mismatch', f'{dq["settlement_mismatch"]}', COLORS['warning'], '🏠'),
        kpi_card('Mock GPS', f'{dq["mock_gps"]}', COLORS['danger'], '📡'),
        kpi_card('Stacked GPS', f'{dq["stacked_gps"]}', COLORS['warning'], '📍'),
        kpi_card('Ineligible Children', f'{dq["ineligible_children"]}', COLORS['danger'], '🔞'),
        kpi_card('Active RAs', f'{dq["active_ras"]}', COLORS['accent'], '👤'),
        kpi_card('Total Flagged', f'{dq["total_flagged"]}', COLORS['danger'], '🚩'),
    ], style={
        'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fill, minmax(200px, 1fr))',
        'gap': '16px', 'marginBottom': '24px'
    })

    # Error Log Table
    error_table_data = error_log.head(100).to_dict('records') if not error_log.empty else []
    error_cols = [COL_LGA, COL_WARD, COL_COMMUNITY, COL_RA, COL_HH_CODE,
                  'Settlement Type Mismatch', 'Duplicate Household', 'Mock GPS', 'Stacked GPS']
    error_cols = [c for c in error_cols if c in error_log.columns]

    error_table = dash_table.DataTable(
        id='error-log-table',
        columns=[{'name': c, 'id': c} for c in error_cols],
        data=error_table_data,
        style_header={'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': '600', 'fontSize': '12px'},
        style_cell={'padding': '6px 10px', 'fontSize': '12px', 'borderBottom': '1px solid #F0F2F5', 'fontFamily': 'inherit'},
        style_data_conditional=[
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#F8F9FA'},
            {'if': {'column_id': 'Settlement Type Mismatch', 'filter_query': '{Settlement Type Mismatch} > 0'},
             'backgroundColor': '#FDEDEC', 'color': COLORS['danger']},
            {'if': {'column_id': 'Duplicate Household', 'filter_query': '{Duplicate Household} > 0'},
             'backgroundColor': '#FDEDEC', 'color': COLORS['danger']},
            {'if': {'column_id': 'Mock GPS', 'filter_query': '{Mock GPS} > 0'},
             'backgroundColor': '#FEF9E7', 'color': COLORS['warning']},
            {'if': {'column_id': 'Stacked GPS', 'filter_query': '{Stacked GPS} > 0'},
             'backgroundColor': '#FEF9E7', 'color': COLORS['warning']},
        ],
        style_table={'borderRadius': '8px', 'overflow': 'hidden', 'boxShadow': COLORS['card_shadow']},
        sort_action='native', filter_action='native', page_size=25,
        tooltip_data=[{c: str(row[c]) for c in error_cols} for row in error_table_data],
    )

    return html.Div([
        html.H2('Data Quality Dashboard', style={'fontSize': '24px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '20px'}),
        dq_kpis,
        html.Div([
            html.H4('DQ-09: Error Log by Research Assistant', style={'fontSize': '15px', 'fontWeight': '600', 'margin': '0 0 12px'}),
            html.P('Records with data quality flags. Red = errors, Yellow = warnings.',
                   style={'fontSize': '12px', 'color': COLORS['text_muted'], 'margin': '0 0 12px'}),
            error_table,
        ], style={'background': 'white', 'borderRadius': '12px', 'padding': '20px', 'boxShadow': COLORS['card_shadow']}),
    ])


# ─── Validation Page ───
def validation_page():
    return html.Div([
        html.H2('Validation Checks', style={'fontSize': '24px', 'fontWeight': '600', 'color': COLORS['dark'], 'marginBottom': '20px'}),
        html.Div([
            html.Div([
                html.H4('Validation Rules', style={'fontSize': '15px', 'fontWeight': '600', 'marginBottom': '16px'}),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th('ID', style={'padding': '10px 14px', 'background': COLORS['primary'], 'color': 'white', 'fontSize': '13px'}),
                        html.Th('Check', style={'padding': '10px 14px', 'background': COLORS['primary'], 'color': 'white', 'fontSize': '13px'}),
                        html.Th('Status', style={'padding': '10px 14px', 'background': COLORS['primary'], 'color': 'white', 'fontSize': '13px'}),
                    ])),
                    html.Tbody([
                        html.Tr([
                            html.Td('VAL-01', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td('Education vs Occupation Consistency', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td(html.Span('Pending', style={'background': '#FEF9E7', 'color': COLORS['warning'], 'padding': '2px 10px', 'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '500'})),
                        ]),
                        html.Tr([
                            html.Td('VAL-02', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td('Repetitive Child Selection per Household', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td(html.Span('Pending', style={'background': '#FEF9E7', 'color': COLORS['warning'], 'padding': '2px 10px', 'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '500'})),
                        ]),
                        html.Tr([
                            html.Td('VAL-03', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td('Gender vs Name Consistency', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td(html.Span('Pending', style={'background': '#FEF9E7', 'color': COLORS['warning'], 'padding': '2px 10px', 'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '500'})),
                        ]),
                        html.Tr([
                            html.Td('VAL-04', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td('Child Name vs Vaccination Card Check', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td(html.Span('Pending', style={'background': '#FEF9E7', 'color': COLORS['warning'], 'padding': '2px 10px', 'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '500'})),
                        ]),
                        html.Tr([
                            html.Td('VAL-05', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td('Household ID Duplicate Flag', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td(html.Span('Active', style={'background': '#E8F8F5', 'color': COLORS['accent'], 'padding': '2px 10px', 'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '500'})),
                        ]),
                        html.Tr([
                            html.Td('VAL-06', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td('Non-Eligible Children Flag', style={'padding': '8px 14px', 'borderBottom': '1px solid #F0F2F5'}),
                            html.Td(html.Span('Active', style={'background': '#E8F8F5', 'color': COLORS['accent'], 'padding': '2px 10px', 'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '500'})),
                        ]),
                    ])
                ], style={'width': '100%', 'borderCollapse': 'collapse', 'fontSize': '13px'}),
            ], style={'background': 'white', 'borderRadius': '12px', 'padding': '20px', 'boxShadow': COLORS['card_shadow'], 'marginBottom': '20px'}),

            html.Div([
                html.H4('Validation Summary', style={'fontSize': '15px', 'fontWeight': '600', 'margin': '0 0 16px'}),
                html.P('Validation rules that require name-gender reference lists and cross-field consistency checks are marked as Pending. These checks require additional reference data (name-gender mappings, vaccination card images) to be fully implemented.',
                       style={'fontSize': '13px', 'color': COLORS['text_muted'], 'lineHeight': '1.5'}),
            ], style={'background': 'white', 'borderRadius': '12px', 'padding': '20px', 'boxShadow': COLORS['card_shadow']}),
        ]),
    ])


# ─── Routing ───
@callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    if pathname == '/demography':
        return demography_page()
    elif pathname == '/completion':
        return completion_page()
    elif pathname == '/gis':
        return gis_page()
    elif pathname == '/quality':
        return quality_page()
    elif pathname == '/validation':
        return validation_page()
    else:
        return overview_page()


# ─── Nav highlight ───
@callback(
    [Output('nav-overview', 'style'), Output('nav-demography', 'style'),
     Output('nav-completion', 'style'), Output('nav-gis', 'style'),
     Output('nav-quality', 'style'), Output('nav-validation', 'style')],
    Input('url', 'pathname')
)
def highlight_nav(pathname):
    base = {'display': 'block', 'padding': '10px 16px', 'color': 'rgba(255,255,255,0.6)',
            'textDecoration': 'none', 'borderRadius': '6px', 'margin': '2px 8px',
            'fontSize': '14px', 'cursor': 'pointer', 'transition': 'all 0.2s'}
    active = {**base, 'background': 'rgba(255,255,255,0.1)', 'color': 'rgba(255,255,255,0.9)', 'fontWeight': '600'}
    return (
        active if pathname == '/' or pathname == '' else base,
        active if pathname == '/demography' else base,
        active if pathname == '/completion' else base,
        active if pathname == '/gis' else base,
        active if pathname == '/quality' else base,
        active if pathname == '/validation' else base,
    )


# ─── Run ───
if __name__ == '__main__':
    app.run(debug=True, port=8050)
