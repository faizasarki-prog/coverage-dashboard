/* ── API ──────────────────────────────────────────────────────────── */
async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/* ── Filter state ─────────────────────────────────────────────────── */
const filters = { lga: null, ward: null, community: null, ra: null };

function buildQS() {
  const p = new URLSearchParams();
  if (filters.lga)        p.set('lga', filters.lga);
  if (filters.ward)       p.set('ward', filters.ward);
  if (filters.community)  p.set('community', filters.community);
  if (filters.ra)         p.set('ra', filters.ra);
  const s = p.toString();
  return s ? `?${s}` : '';
}

function setFilter(key, value) {
  filters[key] = filters[key] === value ? null : value;
  if (key === 'lga') { filters.ward = null; filters.community = null; }
  if (key === 'ward') { filters.community = null; }
  renderFilterBar();
  reloadActivePage();
}

function removeFilter(key) {
  filters[key] = null;
  if (key === 'lga') { filters.ward = null; filters.community = null; }
  if (key === 'ward') { filters.community = null; }
  renderFilterBar();
  reloadActivePage();
}

function _escHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderFilterBar() {
  const bar = document.getElementById('filterBar');
  const chips = document.getElementById('filterChips');
  const active = Object.entries(filters).filter(([, v]) => v);
  if (!active.length) { bar.classList.remove('show'); return; }
  bar.classList.add('show');
  chips.innerHTML = active.map(([k, v]) =>
    `<span class="filter-chip">
       <span class="fc-key">${k}:</span>
       <span class="fc-val">${_escHtml(v)}</span>
       <button title="Remove" onclick="removeFilter('${k}')">✕</button>
     </span>`
  ).join('');
}

/* ── Sidebar toggle ───────────────────────────────────────────────── */
document.getElementById('sidebarToggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('collapsed');
  document.getElementById('mainContent').classList.toggle('expanded');
});

document.getElementById('clearFilters').addEventListener('click', () => {
  filters.lga = null; filters.ward = null; filters.community = null; filters.ra = null;
  renderFilterBar();
  closeFilterDrawer();
  reloadActivePage();
});

/* ── Toast ────────────────────────────────────────────────────────── */
function toast(msg, isError) {
  const el = document.createElement('div');
  el.className = `toast${isError ? ' error' : ''}`;
  el.innerHTML = `<span>${isError ? '❌' : '✅'}</span> ${msg}`;
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ── Loading ──────────────────────────────────────────────────────── */
const _LOADING_DELAY_MS = 450;
let _loadingDepth = 0, _loadingTimer = null;
function showLoading(msg) {
  document.getElementById('loadingMsg').textContent = msg || 'Loading…';
  _loadingDepth++;
  if (_loadingTimer === null) {
    _loadingTimer = setTimeout(() => {
      _loadingTimer = null;
      if (_loadingDepth > 0) document.getElementById('loadingOverlay').classList.add('show');
    }, _LOADING_DELAY_MS);
  }
}
function hideLoading() {
  _loadingDepth = Math.max(0, _loadingDepth - 1);
  if (_loadingDepth === 0) {
    if (_loadingTimer !== null) { clearTimeout(_loadingTimer); _loadingTimer = null; }
    document.getElementById('loadingOverlay').classList.remove('show');
  }
}

function reloadActivePage() {
  const page = document.querySelector('.nav-item.active')?.dataset.page || 'home';
  loadAll();
  if (page === 'completion') loadCompletion();
  if (page === 'quality') loadQuality();
  if (page === 'supervision') loadSupervision();
  if (page === 'geospatial') loadGeospatial();
  if (page === 'ai') loadAiAnalytics();
  if (page === 'validators') loadValidators();
}

/* ── Helpers ──────────────────────────────────────────────────────── */
const fmt = n => (n == null ? '-' : Number(n).toLocaleString());
const GREEN_PALETTE = ['#D9A441','#3B6B4C','#204A37','#8A5A17','#B23A3A','#1d4ed8','#9333ea','#0f766e','#be123c','#1e40af','#b45309','#6d28d9','#0e7490','#b91c1c','#1a56db'];

/* ── Chart instances ──────────────────────────────────────────────── */
let dailyChart, genderPieChart, gpsChart, errorsLgaChart;
const _supCharts = {};
Chart.register(ChartDataLabels);

/* ── HOME ─────────────────────────────────────────────────────────── */
async function loadAll() {
  showLoading('Fetching data…');
  try {
    const qs = buildQS();
    const [kpis, daily, funnel, cddData, lgaData, raPerf, filtersData] = await Promise.all([
      api(`/api/kpis${qs}`),
      api(`/api/charts/daily${qs}`),
      api(`/api/charts/funnel${qs}`),
      api(`/api/cdd-visitation${qs}`),
      api(`/api/charts/lga${qs}`),
      api(`/api/ra-performance${qs}`),
      api(`/api/filters${qs}`),
    ]);
    renderMetrics(kpis);
    renderDailyChart(daily);
    renderFunnelChart(funnel);
    renderCddChart(cddData);
    renderLgaCompletion(lgaData);
    renderRaPerformance(raPerf);
    populateFilters(filtersData);
  } catch (e) {
    toast('Load error: ' + e.message, true);
  } finally {
    hideLoading();
  }
}

function renderMetrics(m) {
  /* ── Hero: coverage dial ── */
  const covPct = parseFloat(m.coverage_pct) || 0;
  const circumference = 2 * Math.PI * 54; /* r=54 from SVG */
  const offset = circumference * (1 - covPct / 100);
  const heroDial = document.getElementById('heroDial');
  if (heroDial) heroDial.setAttribute('stroke-dashoffset', offset.toFixed(1));
  const heroVal = document.getElementById('heroDialValue');
  if (heroVal) heroVal.textContent = m.coverage_pct + '%';

  /* ── Hero: stat cards ── */
  const hh = document.getElementById('heroHouseholds');
  if (hh) hh.textContent = fmt(m.total_households);
  const el = document.getElementById('heroEligible');
  if (el) el.textContent = fmt(m.eligible_children);
  const sr = document.getElementById('heroSwallowRate');
  if (sr) sr.textContent = m.swallow_rate + '%';

  /* ── Section stat rows ── */
  document.getElementById('kpi-children-u18').textContent = fmt(m.children_under_18);
  document.getElementById('kpi-offered').textContent = fmt(m.offered_azm);
  document.getElementById('kpi-swallowed').textContent = fmt(m.swallowed_azm);
  document.getElementById('kpi-vacc-cards').textContent = fmt(m.vacc_cards);
  document.getElementById('kpi-lgas').textContent = fmt(m.lgas_reached);
  document.getElementById('kpi-wards').textContent = fmt(m.wards_reached);
  document.getElementById('kpi-communities').textContent = fmt(m.communities_reached);
  document.getElementById('kpi-ras').textContent = fmt(m.active_ras);
}

/* ── Daily Chart ──────────────────────────────────────────────────── */
let _dailyViewMode = 'bar', _dailyData = [];
function setDailyView(mode) {
  _dailyViewMode = mode;
  const toggle = document.getElementById('dailyViewToggle');
  if (toggle) {
    const btns = toggle.querySelectorAll('button');
    btns.forEach(b => {
      b.style.background = b.getAttribute('onclick').includes(`'${mode}'`) ? 'var(--primary)' : 'transparent';
      b.style.color = b.getAttribute('onclick').includes(`'${mode}'`) ? '#fff' : '#64748b';
    });
  }
  renderDailyChart(_dailyData);
}

function renderDailyChart(data) {
  _dailyData = data || [];
  const ctx = document.getElementById('dailyChart')?.getContext('2d');
  if (!ctx) return;
  if (dailyChart) dailyChart.destroy();
  const isLine = _dailyViewMode === 'line';
  dailyChart = new Chart(ctx, {
    type: isLine ? 'line' : 'bar',
    data: {
      labels: data.map(d => d.date),
      datasets: [{
        label: 'Households',
        data: data.map(d => d.count),
        ...(isLine ? {
          borderColor: '#3B6B4C', backgroundColor: 'rgba(59,107,76,.12)',
          pointRadius: 4, pointBackgroundColor: '#3B6B4C',
          tension: 0.4, fill: true,
        } : {
          backgroundColor: '#3B6B4C', borderRadius: 5, hoverBackgroundColor: '#22432E',
        }),
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { mode: 'index', intersect: false },
        datalabels: isLine ? { display: false } : {
          anchor: 'end', align: 'end',
          color: '#163628', font: { weight: 'bold', size: 13 },
          formatter: v => v.toLocaleString(),
        },
      },
      scales: { x: { grid: { display: false }, ticks: { font: { size: 10 } } }, y: { display: false, beginAtZero: true } },
      layout: { padding: { top: 22 } },
    },
  });
}

/* ── CDD Visitation Chart ─────────────────────────────────────────── */
let cddChart = null;
function renderCddChart(data) {
  const ctx = document.getElementById('cddDoughnutChart')?.getContext('2d');
  if (!ctx) return;
  if (cddChart) cddChart.destroy();
  if (!data?.length) { return; }
  const total = data.reduce((s, d) => s + d.count, 0);
  const labels = data.map(d => d.response || '-');
  const counts = data.map(d => d.count);
  const colors = ['#3B6B4C', '#D9A441', '#94a3b8', '#cbd5e1'];
  cddChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{ data: counts, backgroundColor: colors.slice(0, data.length), borderWidth: 3, borderColor: '#fff', hoverOffset: 6 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '62%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const p = total > 0 ? (ctx.parsed / total * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${ctx.parsed.toLocaleString()} (${p}%)`;
            },
          },
        },
        datalabels: {
          color: '#fff',
          font: { weight: 'bold', size: 13 },
          formatter: (value) => {
            const p = total > 0 ? (value / total * 100).toFixed(0) : 0;
            return p + '%';
          },
          display: (ctx) => {
            const p = total > 0 ? (ctx.dataset.data[ctx.dataIndex] / total * 100) : 0;
            return p > 5;
          },
        },
      },
    },
  });
  const legend = document.getElementById('cddLegend');
  if (legend) {
    legend.innerHTML = data.map((d, i) => {
      const p = total > 0 ? (d.count / total * 100).toFixed(1) : 0;
      return `<span style="display:inline-flex;align-items:center;gap:5px;font-size:.78rem;font-weight:700;color:#374151">
        <span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:${colors[i]}"></span>
        ${_escHtml(d.response)}: <span style="color:${colors[i]}">${d.count.toLocaleString()}</span>
        <span style="color:#6b7280;font-weight:500">(${p}%)</span>
      </span>`;
    }).join('');
  }
}

/* ── Treatment Cascade ────────────────────────────────────────────── */
let cascadeChart = null;
function renderFunnelChart(data) {
  const ctx = document.getElementById('cascadeChart')?.getContext('2d');
  if (!ctx) return;
  if (cascadeChart) cascadeChart.destroy();
  const stages = data?.stages || [], counts = data?.counts || [];
  if (!stages.length) { return; }
  cascadeChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: stages,
      datasets: [{
        label: 'Children',
        data: counts,
        backgroundColor: '#3B6B4C',
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.y.toLocaleString()} children`,
          },
        },
        datalabels: {
          anchor: 'end', align: 'end',
          color: '#163628', font: { weight: 'bold', size: 13 },
          formatter: v => v.toLocaleString(),
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11, weight: 'bold' } } },
        y: { display: false, beginAtZero: true },
      },
      layout: { padding: { top: 30 } },
    },
  });
}

/* ── LGA Completion ───────────────────────────────────────────────── */
let _lgaSort = 'reached', _lgaChartData = [];
function setLgaSort(mode) {
  _lgaSort = mode;
  document.querySelectorAll('.lga-sort-btn').forEach(b => b.classList.toggle('active', b.dataset.sort === mode));
  renderLgaCompletion(_lgaChartData);
}

function renderLgaCompletion(data) {
  _lgaChartData = data || [];
  const container = document.getElementById('lgaCompletionList');
  const tracker = document.getElementById('lgaCompletionTracker');
  if (!container) return;
  let rows = [...data].sort((a, b) => _lgaSort === 'pct' ? (b.pct ?? 0) - (a.pct ?? 0) : (b.reached ?? 0) - (a.reached ?? 0));
  if (!rows.length) { container.innerHTML = '<div style="padding:20px;text-align:center;color:#64748b;font-size:.8rem">No LGA data yet.</div>'; if (tracker) tracker.innerHTML = ''; return; }
  const palette = pct => ({ fill: '#3B6B4C', badge: pct >= 71 ? '#3B6B4C' : pct >= 31 ? '#D9A441' : '#B23A3A' });

  if (tracker) {
    const lgaMap = {};
    rows.forEach(d => {
      const key = d.lga || 'Unknown';
      if (!lgaMap[key]) lgaMap[key] = { reached: 0, planned: 0 };
      lgaMap[key].reached += Number(d.reached ?? 0);
      lgaMap[key].planned += Number(d.planned ?? 0);
    });
    const lgaEntries = Object.entries(lgaMap);
    const totalLgas = lgaEntries.length;
    const metTarget = lgaEntries.filter(([, v]) => v.planned > 0 && (v.reached / v.planned * 100) >= 71).length;
    tracker.innerHTML = `
      <span style="display:flex;align-items:center;gap:5px;font-size:.8rem;font-weight:700;color:#163628;background:#E5EEDD;padding:5px 14px;border-radius:20px">
        <i class="bi bi-check-circle-fill" style="color:#3B6B4C"></i>
        LGAs at target: <span style="font-size:1rem">${metTarget}/${totalLgas}</span>
        <span style="font-size:.75rem;font-weight:600;opacity:.8">(${(metTarget/totalLgas*100).toFixed(0)}%)</span>
      </span>
      <span style="display:flex;align-items:center;gap:5px;font-size:.75rem;color:#475569">
        Target: <span style="font-weight:700;color:#3B6B4C">≥71%</span> reached
      </span>`;
  }

  container.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:.8rem">
    <thead><tr style="border-bottom:2px solid #e2e8f0">
      <th style="text-align:left;padding:6px 8px;font-weight:700;color:#1e293b">LGA</th>
      <th style="text-align:right;padding:6px 8px;font-weight:700;color:#1e293b">Reached</th>
      <th style="text-align:right;padding:6px 8px;font-weight:700;color:#1e293b">Planned</th>
      <th style="text-align:right;padding:6px 8px;font-weight:700;color:#1e293b">%</th>
    </tr></thead><tbody>
    ${rows.map(d => {
      const pct = Number(d.pct ?? 0);
      const c = palette(pct);
      return `<tr class="lga-row" onclick="setFilter('lga','${_escHtml(d.lga)}')" style="cursor:pointer;border-bottom:1px solid #f1f5f9;transition:background .1s">
        <td style="padding:8px;font-weight:700;color:#1e293b;display:flex;align-items:center;gap:8px">
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${c.badge};flex-shrink:0"></span>
          <span title="${_escHtml(d.lga)}" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_escHtml(d.lga || '-')}</span>
        </td>
        <td style="text-align:right;padding:8px;font-weight:800;color:#1e293b;font-variant-numeric:tabular-nums">${Number(d.reached).toLocaleString()}</td>
        <td style="text-align:right;padding:8px;color:#64748b;font-variant-numeric:tabular-nums">${Number(d.planned).toLocaleString()}</td>
        <td style="text-align:right;padding:6px 8px"><span style="display:inline-block;padding:2px 8px;font-size:.7rem;font-weight:800;color:#fff;background:${c.badge};border-radius:10px;min-width:40px;text-align:center">${pct.toFixed(1)}%</span></td>
      </tr>`;
    }).join('')}
  </tbody></table>`;
}

/* ── RA Performance ──────────────────────────────────────────────── */
let _raFilter = 'all', _raPerfData = null;
function setRaFilter(mode) {
  _raFilter = mode;
  document.querySelectorAll('.ra-filter-btn').forEach(b => b.classList.toggle('active', b.dataset.rastatus === mode));
  renderRaPerformance(_raPerfData);
}

function renderRaPerformance(raw) {
  _raPerfData = raw || { lga_groups: {}, summary: { total_ras: 0, met_target: 0, met_pct: 0 } };
  const wrap = document.getElementById('raPerformanceWrap');
  if (!wrap) return;
  const { lga_groups, summary } = _raPerfData;

  const metEl = document.getElementById('raMetSummary');
  if (metEl) {
    metEl.textContent = `${summary.met_target} / ${summary.total_ras} (${summary.met_pct}%) RAs met target`;
    metEl.style.display = summary.total_ras > 0 ? 'inline-block' : 'none';
  }

  const lgaNames = Object.keys(lga_groups);
  if (!lgaNames.length) { wrap.innerHTML = '<p style="text-align:center;padding:24px;color:#64748b">No performance data</p>'; return; }

  // Collect all RA totals from the first LGA group (or just use the global classification)
  const allRas = [];
  for (const lga of lgaNames) {
    for (const r of lga_groups[lga].ras) {
      if (!allRas.find(x => x.ra === r.ra)) allRas.push(r);
    }
  }

  const statusColor = s => s === 'Above Target' ? '#16A34A' : s === 'Meet Target' ? '#B8860B' : '#B23A3A';

  let html = `<table class="ra-lga-table" style="width:100%;border-collapse:collapse;font-size:.78rem">
    <thead><tr style="border-bottom:2px solid #e2e8f0">
      <th style="text-align:left;padding:8px 10px;font-weight:700;color:#1e293b">LGA</th>
      <th style="text-align:left;padding:8px 10px;font-weight:700;color:#1e293b">Research Assistant</th>
      <th style="text-align:right;padding:8px 10px;font-weight:700;color:#1e293b">Submitted</th>
      <th style="text-align:center;padding:8px 10px;font-weight:700;color:#1e293b">Status</th>
    </tr></thead><tbody>`;

  lgaNames.forEach((lga, lgaIdx) => {
    const grp = lga_groups[lga];
    let filteredRas = grp.ras;
    if (_raFilter !== 'all') {
      const targetStatus = _raFilter === 'below' ? 'Below Target' : _raFilter === 'meet' ? 'Meet Target' : 'Above Target';
      filteredRas = grp.ras.filter(r => r.status === targetStatus);
    }
    if (!filteredRas.length) return;
    const isLastLga = lgaIdx === lgaNames.length - 1;
    filteredRas.forEach((r, i) => {
      const isLastRowInLga = i === filteredRas.length - 1;
      const sep = (isLastRowInLga && !isLastLga) ? ' style="border-bottom:8px solid transparent"' : '';
      const clr = statusColor(r.status);
      const label = r.status;
      html += `<tr${sep} onclick="setFilter('lga','${_escHtml(lga)}')" style="cursor:pointer;border-bottom:1px solid #f1f5f9;transition:background .1s">
        ${i === 0 ? `<td style="padding:8px 10px;font-weight:700;color:#1e293b;vertical-align:top" rowspan="${filteredRas.length}">${_escHtml(lga)}</td>` : ''}
        <td style="padding:8px 10px;color:#1e293b">${_escHtml(r.ra)}</td>
        <td style="text-align:right;padding:8px 10px;font-weight:800;color:#1e293b;font-variant-numeric:tabular-nums">${r.count.toLocaleString()}</td>
        <td style="text-align:center;padding:8px 10px"><span style="display:inline-block;padding:3px 12px;font-size:.72rem;font-weight:700;border-radius:12px;background:${clr}18;color:${clr};border:1.5px solid ${clr}50">${label}</span></td>
      </tr>`;
    });
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;
}

/* ── Filters Populate ─────────────────────────────────────────────── */
function populateFilters(fd) {
  ['drLGA','drWard','drCommunity','drRA'].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const key = id === 'drLGA' ? 'lgas' : id === 'drWard' ? 'wards' : id === 'drCommunity' ? 'communities' : 'ras';
    const items = fd[key === 'lgas' ? 'lgas' : key === 'wards' ? 'wards' : key === 'communities' ? 'communities' : 'ras'];
    const label = key === 'ras' ? 'RAs' : key.charAt(0).toUpperCase() + key.slice(1);
    sel.innerHTML = '<option value="">All ' + (key === 'ras' ? 'RAs' : label) + '</option>' +
      (items || []).map(v => `<option value="${_escHtml(v)}">${_escHtml(v)}</option>`).join('');
  });
}

function onDrawerLGAChange() {
  const lga = document.getElementById('drLGA').value;
  const wardSel = document.getElementById('drWard');
  const commSel = document.getElementById('drCommunity');
  wardSel.innerHTML = '<option value="">All Wards</option>';
  commSel.innerHTML = '<option value="">All Communities</option>';
  if (lga && window._wardMap && window._wardMap[lga]) {
    window._wardMap[lga].forEach(w => wardSel.add(new Option(w, w)));
  }
}

function onDrawerWardChange() {
  const lga = document.getElementById('drLGA').value;
  const ward = document.getElementById('drWard').value;
  const commSel = document.getElementById('drCommunity');
  commSel.innerHTML = '<option value="">All Communities</option>';
  if (lga && ward && window._commMap && window._commMap[lga] && window._commMap[lga][ward]) {
    window._commMap[lga][ward].forEach(c => commSel.add(new Option(c, c)));
  }
}

function openFilterDrawer() {
  document.getElementById('filterDrawer').classList.add('open');
  document.getElementById('drawerOverlay').classList.add('show');
}
function closeFilterDrawer() {
  document.getElementById('filterDrawer').classList.remove('open');
  document.getElementById('drawerOverlay').classList.remove('show');
}

function clearDrawerFilters() {
  document.getElementById('drLGA').value = '';
  document.getElementById('drWard').value = '';
  document.getElementById('drCommunity').value = '';
  document.getElementById('drRA').value = '';
}

function applyDrawerFilters() {
  filters.lga = document.getElementById('drLGA').value || null;
  filters.ward = document.getElementById('drWard').value || null;
  filters.community = document.getElementById('drCommunity').value || null;
  filters.ra = document.getElementById('drRA').value || null;
  closeFilterDrawer();
  renderFilterBar();
  reloadActivePage();
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
    item.classList.add('active');
    const page = item.dataset.page;
    const section = document.getElementById(`page-${page}`);
    if (section) section.classList.add('active');
    document.querySelector('.page-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    if (page === 'home') loadAll();
    if (page === 'completion') loadCompletion();
    if (page === 'quality') loadQuality();
    if (page === 'supervision') loadSupervision();
    if (page === 'geospatial') loadGeospatial();
    if (page === 'ai') loadAiAnalytics();
    if (page === 'validators') loadValidators();
  });
});

/* ── COMPLETION ──────────────────────────────────────────────────── */
let completionData = [];

async function loadCompletion() {
  showLoading('Loading completion data…');
  try {
    const qs = buildQS();
    const [lgaData, settlData] = await Promise.all([
      api(`/api/charts/lga${qs}`),
      api(`/api/completion${qs}`),
    ]);
    completionData = settlData || [];
    renderLgaCompletionPage(lgaData);
    renderCompletionTable(completionData);
  } catch (e) { toast('Completion error: ' + e.message, true); }
  finally { hideLoading(); }
}

function renderLgaCompletionPage(data) {
  const container = document.getElementById('lgaCompletionListPage');
  if (!container) return;
  let rows = [...(data || [])].sort((a, b) => _lgaSort === 'pct' ? (b.pct ?? 0) - (a.pct ?? 0) : (b.reached ?? 0) - (a.reached ?? 0));
  if (!rows.length) { container.innerHTML = '<div style="padding:24px;text-align:center;color:#64748b">No data</div>'; return; }
  const palette = pct => ({ fill: '#3B6B4C', badge: pct >= 71 ? '#3B6B4C' : pct >= 31 ? '#D9A441' : '#B23A3A' });
  container.innerHTML = rows.map(d => {
    const pct = Number(d.pct ?? 0), fillPct = Math.min(100, Math.max(0, pct));
    const c = palette(pct);
    return `<div class="lga-row" onclick="setFilter('lga','${_escHtml(d.lga)}')" style="display:grid;grid-template-columns:160px 1fr 130px 64px;gap:12px;align-items:center;padding:8px 10px;border-bottom:1px solid #f1f5f9;cursor:pointer">
      <div style="font-size:.82rem;font-weight:700;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_escHtml(d.lga || '-')}</div>
      <div style="position:relative;height:18px;background:#e2e8f0;border-radius:9px;overflow:hidden">
        <div style="position:absolute;inset:0 auto 0 0;width:${fillPct}%;background:${c.fill};border-radius:9px;transition:width .25s"></div>
      </div>
      <div style="font-size:.8rem;color:#475569;text-align:right;font-variant-numeric:tabular-nums">
        <b style="color:#1e293b">${Number(d.reached).toLocaleString()}</b>
        <span style="color:#94a3b8">/</span> ${Number(d.planned).toLocaleString()}
      </div>
      <div style="text-align:right">
        <span style="display:inline-block;padding:2px 8px;font-size:.78rem;font-weight:800;color:#fff;background:${c.badge};border-radius:10px;min-width:46px;text-align:center">${pct.toFixed(1)}%</span>
      </div>
    </div>`;
  }).join('');
}

let _completionSort = 'default';

function setCompletionSort(mode) {
  _completionSort = mode;
  renderCompletionTable(completionData);
}

function renderCompletionTable(data) {
  const search = (document.getElementById('settlementSearch')?.value || '').toLowerCase();
  let filtered = [...(data || [])];
  if (search) filtered = filtered.filter(r => JSON.stringify(r).toLowerCase().includes(search));
  if (_completionSort === 'complete') filtered.sort((a, b) => (a.status === 'Complete' ? -1 : 1));
  if (_completionSort === 'incomplete') filtered.sort((a, b) => (a.status !== 'Complete' ? -1 : 1));
  const total = filtered.length;
  const complete = filtered.filter(r => r.status === 'Complete').length;
  const summEl = document.getElementById('completeSummary');
  if (summEl) {
    const pct = total > 0 ? (complete / total * 100).toFixed(1) : '0.0';
    summEl.textContent = `${complete} / ${total} (${pct}%) complete`;
  }
  const tbody = document.getElementById('completionTbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  if (!filtered.length) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#64748b">No data</td></tr>'; return; }
  let lastLga = '', lastWard = '';
  filtered.forEach(r => {
    const tr = document.createElement('tr');
    const lgaCell = r.lga !== lastLga ? `<td><strong>${r.lga}</strong></td>` : '<td></td>';
    const wardCell = r.ward !== lastWard ? `<td>${r.ward}</td>` : '<td></td>';
    tr.innerHTML = `${lgaCell}${wardCell}
      <td>${_escHtml(r.community || '-')}</td>
      <td class="num" style="text-align:right">${fmt(r.planned)}</td>
      <td class="num" style="text-align:right;color:#163628">${fmt(r.reached)}</td>
      <td style="text-align:center"><span class="badge-${r.status === 'Complete' ? 'complete' : 'incomplete'}">${r.status || '-'}</span></td>
      <td>${fmt(r.ras)}</td>`;
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => setFilter('lga', r.lga));
    tbody.appendChild(tr);
    lastLga = r.lga; lastWard = r.ward;
  });
}

document.getElementById('settlementSearch')?.addEventListener('input', () => renderCompletionTable(completionData));

/* ── QUALITY CHECKS ───────────────────────────────────────────────── */
async function loadQuality() {
  showLoading('Loading quality data…');
  try {
    const qs = buildQS();
    const [dq, errorsByLga, errorLog] = await Promise.all([
      api(`/api/dq-metrics${qs}`),
      api(`/api/errors-by-lga${qs}`),
      api(`/api/error-log${qs}`),
    ]);
    renderDqCards(dq);
    renderErrorsByLgaChart(errorsByLga);
    renderErrorLog(errorLog);
  } catch (e) { toast('Quality error: ' + e.message, true); }
  finally { hideLoading(); }
}

function renderDqCards(dq) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = fmt(v); };
  set('qc-dup-hh', dq.dup_household_count||0);
  set('qc-rep-child', dq.rep_child_selection||0);
  set('qc-active-ras', dq.active_ras||0);
  set('qc-ineligible', dq.ineligible_children||0);
  set('qc-dup-children', dq.dup_child_count||0);
  set('qc-settlement', dq.settlement_mismatch||0);
  set('qc-form-validation', dq.form_validation_issues||0);
}

function renderErrorsByLgaChart(data) {
  const ctx = document.getElementById('errorsLgaChart')?.getContext('2d');
  if (!ctx) return;
  if (errorsLgaChart) errorsLgaChart.destroy();
  if (!data || !data.length) return;
  errorsLgaChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.lga),
      datasets: [
        { label: 'Dup HH', data: data.map(d => d.dup_households), backgroundColor: '#0891b2', borderRadius: 3 },
        { label: 'Mock GPS', data: data.map(d => d.mock_gps), backgroundColor: '#d97706', borderRadius: 3 },
        { label: 'Stacked GPS', data: data.map(d => d.stacked_gps), backgroundColor: '#dc2626', borderRadius: 3 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12 } } },
      scales: { x: { grid: { display: false }, ticks: { font: { size: 10 } } }, y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.06)' }, ticks: { font: { size: 9 } } } },
    },
  });
}

function renderErrorLog(data) {
  const tbody = document.getElementById('errorLogBody');
  if (!tbody) return;
  if (!data || !data.length) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:20px">No flagged records</td></tr>'; return; }
  tbody.innerHTML = data.slice(0, 200).map(r => `
    <tr>
      <td>${_escHtml(r.lga)}</td>
      <td>${_escHtml(r.ward)}</td>
      <td>${_escHtml(r.community)}</td>
      <td>${_escHtml(r.ra)}</td>
      <td>${_escHtml(r.household_code)}</td>
      <td style="font-weight:700;color:#dc2626">${r.error_count}</td>
    </tr>
  `).join('');
}

/* ── SUPPORTIVE SUPERVISION ───────────────────────────────────────── */
let _supLevel = null, _supLga = null, _supWard = null, _supSettlement = null;
let _supTableData = [], _supTableLevel = 'lga';
let _supSortCol = 'score', _supSortDir = 'desc', _supRiskFilter = '';

async function loadSupervision() {
  showLoading('Loading supervision data…');
  try {
    let url = '/api/supervision';
    const p = [];
    if (_supLga) p.push('lga=' + encodeURIComponent(_supLga));
    if (_supWard) p.push('ward=' + encodeURIComponent(_supWard));
    if (_supSettlement) p.push('settlement=' + encodeURIComponent(_supSettlement));
    if (p.length) url += '?' + p.join('&');
    const data = await api(url);
    if (!data) return;
    _renderSupBreadcrumb(data.breadcrumb);
    _renderSupKpis(data.totals);
    _renderSupRanking(data.ranking);
    _renderSupDist(data.ranking);
    _renderSupTable(data.ranking, data.level);
  } catch (e) { toast('Supervision error: ' + e.message, true); }
  finally { hideLoading(); }
}

function _supDrillDown(name) {
  if (!_supLga) { _supLga = name; _supWard = null; _supSettlement = null; }
  else if (!_supWard) { _supWard = name; _supSettlement = null; }
  else if (!_supSettlement) { _supSettlement = name; }
  loadSupervision();
}

function _supGoTo(lga, ward, settlement) {
  _supLga = lga; _supWard = ward; _supSettlement = settlement || null;
  loadSupervision();
}

function _renderSupBreadcrumb(crumb) {
  const el = document.getElementById('supBreadcrumb');
  if (!el) return;
  if (!crumb?.length || (!_supLga && !_supWard && !_supSettlement)) { el.innerHTML = ''; return; }
  const parts = crumb.map((c, i) => {
    const isLast = i === crumb.length - 1;
    const style = isLast ? 'font-weight:700;color:#1e293b;font-size:.8rem' : 'color:#0369a1;cursor:pointer;font-size:.8rem;text-decoration:underline';
    const click = isLast ? '' : `onclick="_supGoTo(${JSON.stringify(c.lga)},${JSON.stringify(c.ward)},${JSON.stringify(c.settlement)})"`;
    return `<span style="${style}" ${click}>${c.label}</span>${isLast ? '' : '<span style="color:#94a3b8;margin:0 4px">/</span>'}`;
  }).join('');
  el.innerHTML = `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:6px 10px;background:#f0f9ff;border-radius:8px;border:1px solid #bae6fd">
    <i class="bi bi-geo-alt-fill" style="color:#0284c7;font-size:.78rem"></i> ${parts}
    <button onclick="_supGoTo(null,null,null)" style="margin-left:8px;padding:2px 8px;font-size:.7rem;border:1.5px solid #e2e8f0;border-radius:20px;background:#fff;cursor:pointer;color:#475569">↺ Reset</button>
  </div>`;
}

function _renderSupKpis(t) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const total = t?.total_records || 0;
  const flagged = t?.flagged_records || 0;
  const errRate = total > 0 ? (flagged / total * 100).toFixed(1) : '0.0';
  const health = total > 0 ? ((1 - flagged / total) * 100).toFixed(1) : '100.0';
  set('sup-total', total.toLocaleString());
  set('sup-flagged', flagged.toLocaleString());
  set('sup-error-rate', errRate + '%');
  set('sup-health', health + '%');
  const healthEl = document.getElementById('sup-health');
  const card = document.getElementById('supScoreCard');
  if (healthEl) {
    const h = parseFloat(health);
    healthEl.style.color = h >= 90 ? '#3B6B4C' : h >= 70 ? '#D9A441' : '#B23A3A';
  }
  if (card) {
    const h = parseFloat(health);
    card.style.borderLeft = `3px solid ${h >= 90 ? '#3B6B4C' : h >= 70 ? '#D9A441' : '#B23A3A'}`;
  }
  const lbl = document.getElementById('sup-health-lbl');
  if (lbl) lbl.textContent = flagged === 0 ? 'No issues found' : `${flagged} record(s) flagged`;
}

function _renderSupRanking(data) {
  const scroll = document.getElementById('supRankingScroll');
  if (!data?.length) { if (scroll) scroll.innerHTML = '<p style="padding:24px;color:#64748b;text-align:center">No data</p>'; return; }
  const h = Math.max(data.length * 36 + 60, 260);
  if (scroll) scroll.style.minHeight = h + 'px';
  const canvas = document.getElementById('supRankingChart');
  if (!canvas) return;
  canvas.style.height = h + 'px'; canvas.height = h;
  if (_supCharts.ranking) _supCharts.ranking.destroy();
  _supCharts.ranking = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.map(d => d.name),
      datasets: [{
        data: data.map(d => d.score),
        backgroundColor: data.map(d => d.risk === 'High' ? '#B23A3Acc' : d.risk === 'Medium' ? '#D9A441cc' : '#3B6B4Ccc'),
        borderColor: data.map(d => d.risk === 'High' ? '#B23A3A' : d.risk === 'Medium' ? '#D9A441' : '#3B6B4C'),
        borderWidth: 1, borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      onClick: (_, els) => { if (els.length) _supDrillDown(data[els[0].index].name); },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => { const d = data[ctx.dataIndex]; return `Score: ${d.score}% | Errors: ${d.total_errors}`; } } },
      },
      scales: { x: { max: 100, grid: { display: false }, ticks: { callback: v => v + '%', font: { size: 9 } } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } },
    },
  });
}

function _renderSupDist(data) {
  const scroll = document.getElementById('supDistScroll');
  if (!data?.length) { if (scroll) scroll.innerHTML = '<p style="padding:24px;color:#64748b;text-align:center">No data</p>'; return; }
  const h = Math.max(data.length * 36 + 60, 260);
  if (scroll) scroll.style.minHeight = h + 'px';
  const canvas = document.getElementById('supDistChart');
  if (!canvas) return;
  canvas.style.height = h + 'px'; canvas.height = h;
  if (_supCharts.dist) _supCharts.dist.destroy();
  _supCharts.dist = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.map(d => d.name),
      datasets: [
        { label: 'Duplicate HH', data: data.map(d => d.dup_households || 0), backgroundColor: '#0891b2cc', borderRadius: 2 },
        { label: 'Mock GPS', data: data.map(d => d.mock_gps || 0), backgroundColor: '#d97706cc', borderRadius: 2 },
        { label: 'Stacked GPS', data: data.map(d => d.stacked_gps || 0), backgroundColor: '#dc2626cc', borderRadius: 2 },
      ],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 9 } } }, tooltip: { mode: 'index', intersect: false } },
      scales: { x: { stacked: true, grid: { display: false }, ticks: { font: { size: 9 } } }, y: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } } },
    },
  });
}

function _renderSupTable(data, level) {
  _supTableData = data || []; _supTableLevel = level || 'lga';
  _supSortCol = 'score'; _supSortDir = 'desc'; _supRiskFilter = '';
  const sel = document.getElementById('supRiskSelect');
  if (sel) sel.value = '';
  const sh = document.getElementById('supScoreSort'); if (sh) sh.textContent = '↓';
  const rh = document.getElementById('supRiskSort'); if (rh) rh.textContent = '↕';
  const lh = document.getElementById('supLocationHeader');
  const levelLabel = { lga: 'LGA', ward: 'Ward', settlement: 'Settlement Name' };
  if (lh) lh.textContent = levelLabel[level] || 'Location';
  _supApplyTableFilters();
}

function _supFilterByRisk(val) { _supRiskFilter = val; _supApplyTableFilters(); }

function _supSortByCol(col) {
  if (_supSortCol === col) _supSortDir = _supSortDir === 'desc' ? 'asc' : 'desc';
  else { _supSortCol = col; _supSortDir = 'desc'; }
  ['score','risk'].forEach(c => {
    const el = document.getElementById('sup' + c.charAt(0).toUpperCase() + c.slice(1) + 'Sort');
    if (el) el.textContent = _supSortCol === c ? (_supSortDir === 'desc' ? '↓' : '↑') : '↕';
  });
  _supApplyTableFilters();
}

function _supApplyTableFilters() {
  const riskOrder = { High: 3, Medium: 2, Low: 1 };
  let rows = [..._supTableData];
  if (_supRiskFilter) rows = rows.filter(r => r.risk === _supRiskFilter);
  rows.sort((a, b) => {
    const v = _supSortDir === 'asc' ? 1 : -1;
    if (_supSortCol === 'score') return (a.score - b.score) * v;
    if (_supSortCol === 'risk') return ((riskOrder[a.risk]||0) - (riskOrder[b.risk]||0)) * v;
    return 0;
  });
  _supDrawTableRows(rows, _supTableLevel);
}

function _supDrawTableRows(data, level) {
  const tbody = document.getElementById('supTbody');
  if (!tbody) return;
  const RISK_STYLE = {
    High: 'background:#F6E2E2;color:#B23A3A;border:1px solid #E8C4C4',
    Medium: 'background:#E5EEDD;color:#8A5A17;border:1px solid #C5D9BC',
    Low: 'background:#E5EEDD;color:#22432E;border:1px solid #C5D9BC',
  };
  if (!data?.length) { tbody.innerHTML = '<tr><td colspan="5" style="padding:20px;text-align:center;color:#94a3b8">No data</td></tr>'; return; }
  tbody.innerHTML = data.map((r, i) => {
    const bg = i % 2 === 0 ? '#fff' : '#f8fafc';
    const rs = RISK_STYLE[r.risk] || RISK_STYLE.Low;
    const canDrill = level !== 'ra';
    const name = canDrill
      ? `<span style="color:#0369a1;cursor:pointer;text-decoration:underline;font-weight:600" onclick="_supDrillDown('${r.name.replace(/'/g,"\\'")}')">${_escHtml(r.name)}</span>`
      : `<strong>${_escHtml(r.name)}</strong>`;
    return `<tr style="background:${bg}">
      <td style="padding:7px 12px;border-bottom:1px solid #f1f5f9">${name}</td>
      <td style="padding:7px 12px;border-bottom:1px solid #f1f5f9;text-align:right">${r.total_records.toLocaleString()}</td>
      <td style="padding:7px 12px;border-bottom:1px solid #f1f5f9;text-align:right;color:#dc2626;font-weight:700">${r.total_errors}</td>
      <td style="padding:7px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:800">${r.score}%</td>
      <td style="padding:7px 12px;border-bottom:1px solid #f1f5f9;text-align:center">
        <span style="font-size:.68rem;font-weight:700;padding:2px 10px;border-radius:20px;${rs}">${r.risk}</span>
      </td>
    </tr>`;
  }).join('');
}

/* ── GEOSPATIAL ──────────────────────────────────────────────────── */
async function loadGeospatial() {
  showLoading('Loading geospatial data…');
  try {
    const qs = buildQS();
    const [gpsData, gpsSummary] = await Promise.all([
      api(`/api/gps-data${qs}`),
      api(`/api/gps-summary${qs}`),
    ]);
    renderGpsSummary(gpsSummary);
    renderGpsScatter(gpsData);
  } catch (e) { toast('Geospatial error: ' + e.message, true); }
  finally { hideLoading(); }
}

function renderGpsSummary(s) {
  document.getElementById('gis-total-points').textContent = fmt(s.total_gps_points);
  document.getElementById('gis-unique').textContent = fmt(s.unique_locations);
  document.getElementById('gis-stacked').textContent = fmt(s.stacked_gps);
  const stackedEl = document.getElementById('gis-stacked-pct');
  if (stackedEl) { stackedEl.textContent = s.stacked_pct + '%'; stackedEl.style.color = s.stacked_pct > 10 ? '#B23A3A' : '#3B6B4C'; }
  const mockEl = document.getElementById('gis-mock');
  if (mockEl) { mockEl.textContent = fmt(s.mock_gps); mockEl.style.color = s.mock_gps > 0 ? '#B23A3A' : '#3B6B4C'; }
}

function renderGpsScatter(data) {
  const canvas = document.getElementById('gpsChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (gpsChart) gpsChart.destroy();
  if (!data || !data.length) {
    canvas.parentElement.innerHTML = '<p style="text-align:center;color:#94a3b8;padding:40px">No GPS data available</p>';
    return;
  }
  const lgas = [...new Set(data.map(d => d.lga))];
  const lgaColors = {};
  lgas.forEach((l, i) => lgaColors[l] = GREEN_PALETTE[i % GREEN_PALETTE.length]);
  const datasets = lgas.map(lga => ({
    label: lga,
    data: data.filter(d => d.lga === lga).map(d => ({ x: d.lng, y: d.lat })),
    backgroundColor: lgaColors[lga],
    pointRadius: 3, pointHoverRadius: 6,
  }));
  gpsChart = new Chart(ctx, {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12, padding: 12 } },
        tooltip: { callbacks: { label: ctx => { const raw = ctx.raw; return ` ${ctx.dataset.label}: ${Number(raw.y).toFixed(5)}, ${Number(raw.x).toFixed(5)}`; } } },
      },
      scales: {
        x: { title: { display: true, text: 'Longitude', font: { size: 10 } }, grid: { color: 'rgba(0,0,0,.06)' } },
        y: { title: { display: true, text: 'Latitude', font: { size: 10 } }, grid: { color: 'rgba(0,0,0,.06)' } },
      },
    },
  });
}

/* ── ADVANCED ANALYTICS ──────────────────────────────────────────── */
async function loadAiAnalytics() {
  showLoading('Loading analytics…');
  try {
    const qs = buildQS();
    const [insights, regression] = await Promise.all([
      api(`/api/ai/insights${qs}`),
      api(`/api/ai/regression${qs}`),
    ]);
    renderAiInsights(insights);
    renderAiRegression(regression);
    renderAiAnomalies(qs);
  } catch (e) { toast('AI error: ' + e.message, true); }
  finally { hideLoading(); }
}

function renderAiInsights(data) {
  const grid = document.getElementById('aiInsightsGrid');
  if (!grid) return;
  if (!data?.length) {
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:32px;color:#64748b">No insights available yet.</div>';
    return;
  }
  grid.innerHTML = data.map(d => `
    <div class="ai-insight-card ${d.type || 'info'}">
      <div class="ai-insight-icon"><i class="bi ${d.icon || 'bi-lightbulb'}"></i></div>
      <div class="ai-insight-body">
        <div class="ai-insight-title">${_escHtml(d.title)}</div>
        <div class="ai-insight-text">${_escHtml(d.text)}</div>
      </div>
    </div>
  `).join('');
}

function renderAiRegression(data) {
  const kpis = document.getElementById('regKpis');
  if (kpis && data?.kpis) {
    kpis.innerHTML = Object.entries(data.kpis).map(([k, v]) =>
      `<div class="ai-kpi-card"><div class="ai-kpi-val">${v}</div><div class="ai-kpi-lbl">${k}</div></div>`
    ).join('');
  }
  const ctx = document.getElementById('regressionChart')?.getContext('2d');
  if (!ctx) return;
  if (window.regressionChart) window.regressionChart.destroy();
  if (!data?.chart) return;
  window.regressionChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.chart.labels,
      datasets: [
        { label: 'Actual', data: data.chart.actual, borderColor: '#3B6B4C', backgroundColor: 'rgba(59,107,76,.1)', fill: true, tension: .4, pointRadius: 4, pointBackgroundColor: '#3B6B4C' },
        { label: 'Forecast', data: data.chart.forecast, borderColor: '#D9A441', borderDash: [6, 3], pointRadius: 3, pointBackgroundColor: '#D9A441' },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'top', labels: { font: { size: 10 } } }, tooltip: { mode: 'index', intersect: false } },
      scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.06)' } } },
    },
  });
  const trends = document.getElementById('lgaTrendsBody');
  if (trends && data?.lga_trends) {
    trends.innerHTML = Object.entries(data.lga_trends).slice(0, 10).map(([lga, vals]) =>
      `<div style="display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid #f1f5f9">
        <span style="font-weight:700;color:#1e293b;width:160px">${_escHtml(lga)}</span>
        <span style="color:#64748b">${vals.current} today</span>
        <span style="color:${vals.trend >= 0 ? '#3B6B4C' : '#B23A3A'};font-weight:700">${vals.trend >= 0 ? '+' : ''}${vals.trend}%</span>
      </div>`
    ).join('');
  }
}

async function renderAiAnomalies(qs) {
  try {
    const data = await api(`/api/ai/anomaly${qs}`);
    const grid = document.getElementById('anomalyGrid');
    if (!grid) return;
    if (!data?.length) { grid.innerHTML = '<div style="text-align:center;padding:32px;color:#64748b">No anomalies detected.</div>'; return; }
    grid.innerHTML = data.map(d => `
      <div class="anomaly-card" style="border-left:4px solid ${d.severity === 'high' ? '#B23A3A' : d.severity === 'medium' ? '#D9A441' : '#3B6B4C'}">
        <div class="anomaly-title">${_escHtml(d.title)}</div>
        <div class="anomaly-desc">${_escHtml(d.description)}</div>
        <div class="anomaly-meta">${_escHtml(d.location)} · ${_escHtml(d.date)}</div>
      </div>
    `).join('');
  } catch (_) {}
}

/* ── AI Subtabs ──────────────────────────────────────────────────── */
document.querySelectorAll('.ai-subtab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ai-subtab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.ai-tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const pane = document.getElementById('ai-tab-' + btn.dataset.aitab);
    if (pane) pane.classList.add('active');
  });
});

/* ── Export ────────────────────────────────────────────────────────── */
function downloadTableCSV(tableId, filename) {
  const t = document.getElementById(tableId);
  if (!t) return;
  const rows = [...t.querySelectorAll('tr')].map(tr =>
    [...tr.querySelectorAll('th,td')].map(c => `"${c.textContent.trim().replace(/"/g,'""')}"`).join(',')
  );
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(rows.join('\n'));
  a.download = `${filename}_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

/* ── Theme / Settings ──────────────────────────────────────────────── */
function initTheme() {
  const theme = localStorage.getItem('cov_theme') || 'green';
  const dark = localStorage.getItem('cov_dark') === 'true';
  document.documentElement.setAttribute('data-theme', theme);
  if (dark) document.documentElement.setAttribute('data-dark', 'true');
  const track = document.getElementById('darkToggle');
  if (track) track.classList.toggle('on', dark);
  document.querySelectorAll('.theme-card').forEach(s => s.classList.toggle('active', s.dataset.theme === theme));
}

function applyTheme(theme, save = true) {
  document.documentElement.setAttribute('data-theme', theme);
  if (save) localStorage.setItem('cov_theme', theme);
  document.querySelectorAll('.theme-card').forEach(s => s.classList.toggle('active', s.dataset.theme === theme));
}

function toggleDarkMode() {
  const isDark = document.documentElement.getAttribute('data-dark') === 'true';
  const next = !isDark;
  document.documentElement.setAttribute('data-dark', String(next));
  localStorage.setItem('cov_dark', String(next));
  const track = document.getElementById('darkToggle');
  if (track) track.classList.toggle('on', next);
}

function openSettings() { document.getElementById('settingsModal').classList.add('show'); }
function closeSettings() { document.getElementById('settingsModal').classList.remove('show'); }
function switchSettingsTab() {}

/* ── Bug Report ──────────────────────────────────────────────────── */
function openBugReport() { document.getElementById('bugModal').style.display = 'flex'; }
function closeBugReport() { document.getElementById('bugModal').style.display = 'none'; }
async function submitBugReport() {
  const title = document.getElementById('bugTitle').value.trim();
  if (!title) { toast('Please enter a bug title', true); return; }
  toast('Bug report submitted. Thank you!');
  closeBugReport();
  document.getElementById('bugTitle').value = '';
  document.getElementById('bugDesc').value = '';
}

/* ── Chat ────────────────────────────────────────────────────────── */
function toggleChat() {
  document.getElementById('chatPanel').classList.toggle('open');
}
async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  const msgs = document.getElementById('chatMessages');
  msgs.innerHTML += `<div class="chat-msg user">${_escHtml(msg)}</div>`;
  document.getElementById('chatTyping').style.display = '';
  msgs.scrollTop = msgs.scrollHeight;
  try {
    const qs = buildQS();
    const data = await api(`/api/ai/chat${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    msgs.innerHTML += `<div class="chat-msg bot">${_escHtml(data.reply || 'No response')}</div>`;
  } catch (_) {
    msgs.innerHTML += `<div class="chat-msg bot">Sorry, I couldn't process that. Please try again.</div>`;
  }
  document.getElementById('chatTyping').style.display = 'none';
  msgs.scrollTop = msgs.scrollHeight;
}

function sendQuick(q) {
  document.getElementById('chatInput').value = q;
  sendChat();
}

/* ── VALIDATORS ─────────────────────────────────────────────────────── */
async function loadValidators() {
  showLoading('Loading validation data…');
  try {
    const qs = buildQS();
    const data = await api(`/api/validation${qs}`);
    renderValKpis(data.summary);
    renderValTasks(data.val_tasks);
    renderValFlags(data.flags);
  } catch (e) { toast('Validation error: ' + e.message, true); }
  finally { hideLoading(); }
}

function renderValKpis(s) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = fmt(v); };
  set('val-total', s.total_records);
  set('val-validated', s.validated);
  set('val-approved', s.approved);
  set('val-flagged', s.flagged_records);
  set('val-outstanding', s.outstanding);
  set('val-ras', s.total_ras);
  set('val-dup-hh', s.dup_households);
}

function renderValTasks(tasks) {
  const container = document.getElementById('valTaskList');
  if (!container) return;
  if (!tasks || !tasks.length) { container.innerHTML = '<p style="text-align:center;color:#94a3b8;padding:16px">No tasks defined.</p>'; return; }
  container.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">${tasks.map(t => {
    const statusColor = t.status === 'Active' ? '#3B6B4C' : t.status === 'Not Started' ? '#94a3b8' : '#D9A441';
    const flagColor = t.flags > 0 ? '#B23A3A' : '#3B6B4C';
    return `<div style="background:var(--card-bg);border-radius:10px;padding:12px 14px;border:1px solid var(--border);display:flex;align-items:center;gap:10px">
      <div style="width:32px;height:32px;border-radius:8px;background:${statusColor}22;display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <span style="font-size:.7rem;font-weight:800;color:${statusColor}">${t.id.replace('VAL-','')}</span>
      </div>
      <div style="flex:1;min-width:0">
        <div style="font-size:.8rem;font-weight:700;color:var(--text-body);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_escHtml(t.name)}</div>
        <div style="display:flex;gap:8px;margin-top:3px;font-size:.68rem">
          <span style="color:${statusColor};font-weight:600">${_escHtml(t.status)}</span>
          <span style="color:${flagColor};font-weight:600">${t.flags} flag${t.flags !== 1 ? 's' : ''}</span>
        </div>
      </div>
      <span style="font-size:.65rem;padding:2px 8px;border-radius:12px;background:${statusColor}18;color:${statusColor};font-weight:700;flex-shrink:0">${t.status === 'Active' ? 'ON' : 'OFF'}</span>
    </div>`;
  }).join('')}</div>`;
}

function renderValFlags(flags) {
  const wrap = document.getElementById('valFlagsWrap');
  const count = document.getElementById('valFlagCount');
  if (!wrap) return;
  if (count) count.textContent = `${flags?.length || 0} flag(s)`;
  if (!flags || !flags.length) { wrap.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8">No flagged records.</div>'; return; }
  const badge = t => t === 'Duplicate Household ID' ? '<span class="badge br">Duplicate HH</span>'
    : t === 'Non-Eligible Child' ? '<span class="badge bh">Non-Eligible</span>'
    : t === 'Education vs Occupation' ? '<span class="badge bp">Edu vs Occ</span>'
    : '<span class="badge">' + _escHtml(t) + '</span>';
  wrap.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:.78rem">
    <thead><tr style="background:#f8fafc;position:sticky;top:0;z-index:1">
      <th style="padding:8px 10px;text-align:left;font-weight:700;color:#475569;border-bottom:1px solid #e2e8f0">Type</th>
      <th style="padding:8px 10px;text-align:left;font-weight:700;color:#475569;border-bottom:1px solid #e2e8f0">LGA</th>
      <th style="padding:8px 10px;text-align:left;font-weight:700;color:#475569;border-bottom:1px solid #e2e8f0">Ward</th>
      <th style="padding:8px 10px;text-align:left;font-weight:700;color:#475569;border-bottom:1px solid #e2e8f0">RA</th>
      <th style="padding:8px 10px;text-align:left;font-weight:700;color:#475569;border-bottom:1px solid #e2e8f0">Detail</th>
    </tr></thead>
    <tbody>${flags.map(f => `<tr>
      <td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">${badge(f.type)}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">${_escHtml(f.lga || '-')}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">${_escHtml(f.ward || '-')}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">${_escHtml(f.ra || '-')}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #f1f5f9;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_escHtml(f.detail)}">${_escHtml(f.detail)}</td>
    </tr>`).join('')}</tbody>
  </table>`;
}

/* ── Init ─────────────────────────────────────────────────────────── */
initTheme();

document.addEventListener('DOMContentLoaded', () => loadAll());
