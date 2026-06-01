'use strict';

/* ══════════════════════════════════════════════════════════════
   Chart.js glow plugin
══════════════════════════════════════════════════════════════ */
Chart.register({
  id: 'glowLine',
  beforeDatasetsDraw(chart) {
    const ctx = chart.ctx;
    ctx.save();
    ctx.shadowBlur    = 22;
    ctx.shadowColor   = 'rgba(124,58,237,0.35)';
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
  },
  afterDatasetsDraw(chart) { chart.ctx.restore(); },
});

/* ══════════════════════════════════════════════════════════════
   State
══════════════════════════════════════════════════════════════ */
let skuList = [];
let allSkus = [];
let mapData = { warehouses: [], demand_by_region: [] };
let leafMap = null, layerWH = null, layerDem = null;
let activeCharts = {};
let currentLayer = 'warehouses';
let heroChartRange = '12w';
let heroRawSales   = [];

/* ══════════════════════════════════════════════════════════════
   Russian region → [lat, lng]
══════════════════════════════════════════════════════════════ */
const RU_REGIONS = {
  'Москва':[55.75,37.62],'Московская область':[55.73,37.56],
  'Санкт-Петербург':[59.95,30.32],'Ленинградская область':[59.95,30.32],
  'Краснодарский край':[45.04,38.97],'Ростовская область':[47.22,39.72],
  'Свердловская область':[56.83,60.60],'Республика Татарстан':[55.79,49.12],
  'Новосибирская область':[54.99,82.90],'Красноярский край':[56.01,92.85],
  'Самарская область':[53.20,50.15],'Республика Башкортостан':[54.74,55.97],
  'Башкортостан':[54.74,55.97],'Челябинская область':[55.15,61.40],
  'Пермский край':[58.01,56.24],'Нижегородская область':[56.33,44.00],
  'Воронежская область':[51.67,39.18],'Волгоградская область':[48.71,44.51],
  'Саратовская область':[51.53,46.03],'Тюменская область':[57.15,68.97],
  'Омская область':[54.99,73.37],'Иркутская область':[52.29,104.30],
  'Хабаровский край':[48.48,135.08],'Приморский край':[43.12,131.90],
  'Оренбургская область':[51.77,55.10],'Ставропольский край':[45.04,41.97],
  'Кемеровская область':[55.35,86.09],'Алтайский край':[53.35,83.74],
  'Тульская область':[54.19,37.62],'Ярославская область':[57.63,39.87],
  'Рязанская область':[54.63,39.73],'Тверская область':[56.86,35.91],
  'Белгородская область':[50.60,36.59],'Липецкая область':[52.61,39.59],
  'Брянская область':[53.25,34.37],'Курская область':[51.74,36.19],
  'Владимирская область':[56.13,40.40],'Калужская область':[54.51,36.26],
  'Смоленская область':[54.78,32.04],'Костромская область':[57.77,40.93],
  'Ивановская область':[57.00,40.97],'Тамбовская область':[52.72,41.45],
  'Орловская область':[52.97,36.06],'Пензенская область':[53.20,45.00],
  'Ульяновская область':[54.32,48.39],'Кировская область':[58.60,49.67],
  'Удмуртская Республика':[56.85,53.20],'Чувашская Республика':[56.13,47.25],
  'Республика Марий Эл':[56.63,47.88],'Республика Мордовия':[54.17,44.88],
  'Астраханская область':[46.35,48.03],'Республика Крым':[44.95,34.10],
  'Мурманская область':[68.97,33.08],'Архангельская область':[64.54,40.54],
  'Вологодская область':[59.22,39.89],'Псковская область':[57.82,28.33],
  'Новгородская область':[58.52,31.27],'Калининградская область':[54.71,20.50],
  'Республика Карелия':[61.79,34.36],'Республика Коми':[63.84,53.68],
  'Томская область':[56.50,84.97],'Забайкальский край':[52.05,113.46],
  'Амурская область':[53.74,127.51],'Республика Саха (Якутия)':[62.03,129.73],
  'Республика Бурятия':[51.83,107.61],'Сахалинская область':[50.68,142.76],
  'Камчатский край':[53.04,158.65],'Магаданская область':[59.56,150.79],
  'Курганская область':[55.45,65.34],'Республика Дагестан':[42.97,47.50],
  'Чеченская Республика':[43.31,45.69],
  'Ханты-Мансийский автономный округ':[61.00,69.00],
  'Ямало-Ненецкий автономный округ':[66.53,66.61],
};

/* ══════════════════════════════════════════════════════════════
   Helpers
══════════════════════════════════════════════════════════════ */
const fmt    = n => (n == null) ? '—' : Number(n).toLocaleString('ru-RU');
const fmtRub = n => (n == null) ? '—' : Number(n).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽';
const badge  = s => `<span class="badge ${s}">${{ critical: 'Критично', warning: 'Внимание', ok: 'ОК' }[s] || s}</span>`;
const coefPill = c => {
  if (c == null) return '<span style="color:var(--text-muted)">—</span>';
  const cls = c > 1.5 ? 'high' : c > 1.0 ? 'medium' : 'low';
  return `<span class="coef ${cls}">×${c.toFixed(2)}</span>`;
};

async function api(path, opts = {}) {
  const r = await fetch('/api' + path, opts);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

function destroyChart(id) {
  if (activeCharts[id]) { activeCharts[id].destroy(); delete activeCharts[id]; }
}

/* ══════════════════════════════════════════════════════════════
   Counter animation (eased, from → to)
══════════════════════════════════════════════════════════════ */
function animateCount(el, target, duration = 1400) {
  if (typeof target !== 'number' || isNaN(target)) return;
  const fromStr = el.textContent.replace(/[^0-9-]/g, '');
  const from = parseInt(fromStr) || 0;
  const start = performance.now();
  const tick = now => {
    const t    = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(from + (target - from) * ease).toLocaleString('ru-RU');
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ══════════════════════════════════════════════════════════════
   Scroll progress bar + topbar hide on scroll down
══════════════════════════════════════════════════════════════ */
const progressBar = document.getElementById('scroll-progress');
const topbarEl    = document.querySelector('.topbar');
let lastScrollY   = 0;

window.addEventListener('scroll', () => {
  const h   = document.documentElement;
  const max = h.scrollHeight - h.clientHeight;
  progressBar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + '%';

  const y = window.scrollY;
  if (y > lastScrollY + 6 && y > 80) {
    topbarEl.classList.add('is-hidden');
  } else if (y < lastScrollY - 6) {
    topbarEl.classList.remove('is-hidden');
  }
  lastScrollY = y;
}, { passive: true });

/* ══════════════════════════════════════════════════════════════
   Cursor-follow glow (dashboard section only)
══════════════════════════════════════════════════════════════ */
const cursorGlow = document.getElementById('cursor-glow');
const heroSection = document.getElementById('hero');
let cursorActive = false;
window.addEventListener('mousemove', e => {
  if (cursorGlow) {
    cursorGlow.style.left = e.clientX + 'px';
    cursorGlow.style.top  = e.clientY + 'px';
    const rect   = heroSection.getBoundingClientRect();
    const inHero = e.clientY >= rect.top && e.clientY <= rect.bottom;
    if (inHero !== cursorActive) {
      cursorActive = inHero;
      cursorGlow.classList.toggle('active', inHero);
    }
  }
}, { passive: true });

/* ══════════════════════════════════════════════════════════════
   Card tilt on hover
══════════════════════════════════════════════════════════════ */
function bindTilts() {
  document.querySelectorAll('.tilt').forEach(el => {
    if (el.__tilted) return;
    el.__tilted = true;
    el.addEventListener('mousemove', e => {
      const r  = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width  - 0.5;
      const py = (e.clientY - r.top)  / r.height - 0.5;
      el.style.transform = `perspective(900px) rotateX(${-py * 4}deg) rotateY(${px * 5}deg) translateY(-2px)`;
    });
    el.addEventListener('mouseleave', () => { el.style.transform = ''; });
  });
}

/* ══════════════════════════════════════════════════════════════
   Magnetic button
══════════════════════════════════════════════════════════════ */
function bindMagnetic() {
  document.querySelectorAll('.magnetic').forEach(btn => {
    if (btn.__mag) return; btn.__mag = true;
    btn.addEventListener('mousemove', e => {
      const r = btn.getBoundingClientRect();
      btn.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.18}px, ${(e.clientY - r.top - r.height / 2) * 0.22}px)`;
    });
    btn.addEventListener('mouseleave', () => { btn.style.transform = ''; });
  });
}

/* ══════════════════════════════════════════════════════════════
   Scroll-enter animation (rAF-driven for precision)
══════════════════════════════════════════════════════════════ */
const io = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    revealEl(entry.target);
    io.unobserve(entry.target);
  });
}, { threshold: 0.08 });

function revealEl(el) {
  if (el.classList.contains('visible') || el.__revealing) return;
  el.__revealing = true;
  const delay    = parseInt(el.dataset.delay || 0);
  const isLeft   = el.classList.contains('fade-left');
  const isRight  = el.classList.contains('fade-right');
  const isZoom   = el.classList.contains('zoom-in');
  const start    = isLeft  ? { x: -32, y: 0, s: 1 }
                 : isRight ? { x:  32, y: 0, s: 1 }
                 : isZoom  ? { x: 0, y: 0, s: .93 }
                 :           { x: 0, y: 28, s: 1 };
  const beginAt  = performance.now() + delay;
  const duration = 700;
  const ease     = t => 1 - Math.pow(1 - t, 3);

  function frame(now) {
    if (now < beginAt) { requestAnimationFrame(frame); return; }
    const t = Math.min((now - beginAt) / duration, 1);
    const e = ease(t);
    el.style.opacity   = e;
    el.style.transform = `translate(${start.x * (1 - e)}px, ${start.y * (1 - e)}px) scale(${start.s + (1 - start.s) * e})`;
    if (t < 1) { requestAnimationFrame(frame); return; }
    el.style.opacity   = '';
    el.style.transform = '';
    el.classList.add('visible');
    el.querySelectorAll('[data-target]').forEach(c => animateCount(c, parseInt(c.dataset.target)));
    el.querySelectorAll('[data-spark]').forEach(c => drawSpark(c));
  }
  requestAnimationFrame(frame);
}

function registerAnims() {
  document.querySelectorAll('.anim:not(.visible)').forEach(el => io.observe(el));
  requestAnimationFrame(() => {
    document.querySelectorAll('.anim:not(.visible)').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.top < window.innerHeight && r.bottom > 0) revealEl(el);
    });
  });
}

window.addEventListener('scroll', () => {
  document.querySelectorAll('.anim:not(.visible)').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight - 40 && r.bottom > 0) revealEl(el);
  });
}, { passive: true });

/* ══════════════════════════════════════════════════════════════
   Sparkline mini-charts on metric cards
══════════════════════════════════════════════════════════════ */
function drawSpark(host) {
  const kind = host.dataset.spark;
  const w = 70, h = 28;
  const PTS = {
    rising: [18,15,17,13,14,11,12,9,10,7,8,5],
    wave:   [14,11,17,13,9,15,12,18,11,14,10,16],
    alert:  [9,11,8,14,10,16,12,19,15,21,17,23],
    warn:   [12,14,11,15,13,16,14,17,15,18,16,17],
  };
  const pts  = PTS[kind] || PTS.wave;
  const maxY = Math.max(...pts), minY = Math.min(...pts);
  const dx   = w / (pts.length - 1);
  let d = '';
  pts.forEach((y, i) => {
    const nx = i * dx;
    const ny = h - ((y - minY) / Math.max(maxY - minY, 1)) * (h - 4) - 2;
    d += (i === 0 ? 'M' : 'L') + nx.toFixed(1) + ',' + ny.toFixed(1) + ' ';
  });
  const color = kind === 'alert' ? '#dc2626' : kind === 'warn' ? '#d97706' : '#7c3aed';
  host.innerHTML = `
    <svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="g-${kind}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="${color}" stop-opacity=".35"/>
          <stop offset="1" stop-color="${color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="${d} L ${w},${h} L 0,${h} Z" fill="url(#g-${kind})"/>
      <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"
        stroke-linecap="round" stroke-linejoin="round"
        style="filter:drop-shadow(0 0 4px ${color}88);stroke-dasharray:200;stroke-dashoffset:200;animation:draw 1.2s ease forwards"/>
    </svg>`;
}
(() => {
  const s = document.createElement('style');
  s.textContent = '@keyframes draw { to { stroke-dashoffset: 0; } }';
  document.head.appendChild(s);
})();

/* ══════════════════════════════════════════════════════════════
   Topbar snapshot label (current date)
══════════════════════════════════════════════════════════════ */
function setSnapshot() {
  const d = new Date('2024-12-31').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
  const el  = document.getElementById('topbar-snap');
  const el2 = document.getElementById('dh-snapshot');
  if (el)  el.textContent  = d;
  if (el2) el2.textContent = d;
}

/* ══════════════════════════════════════════════════════════════
   Sidebar nav + scroll sync
══════════════════════════════════════════════════════════════ */
document.querySelectorAll('.sb-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.getElementById(b.dataset.sec)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

const NAV_SECTIONS = ['hero', 'portfolio', 'map-sec', 'analyzer', 'optimizer'];
window.addEventListener('scroll', () => {
  let cur = NAV_SECTIONS[0];
  NAV_SECTIONS.forEach(id => {
    const el = document.getElementById(id);
    if (el && el.getBoundingClientRect().top <= 120) cur = id;
  });
  document.querySelectorAll('.sb-btn').forEach(b => b.classList.toggle('active', b.dataset.sec === cur));
}, { passive: true });

/* ══════════════════════════════════════════════════════════════
   Chart factory
══════════════════════════════════════════════════════════════ */
const BASE_OPTS = {
  responsive: true, maintainAspectRatio: false,
  animation: { duration: 1000, easing: 'easeOutQuart' },
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(255,255,255,.97)',
      borderColor: 'rgba(124,58,237,.25)',
      borderWidth: 1, padding: 10, cornerRadius: 10,
      titleColor: '#7b7b9a', titleFont: { size: 11, weight: '500' },
      bodyColor: '#0f0f1a', bodyFont: { family: 'Avenir Next', size: 13, weight: '600' },
      displayColors: false,
      callbacks: { label: ctx => fmt(ctx.parsed.y) + ' шт.' },
    },
  },
  scales: {
    x: {
      grid: { color: 'rgba(0,0,0,.06)' },
      ticks: { color: '#7b7b9a', font: { size: 10 } },
      border: { color: 'rgba(0,0,0,.08)' },
    },
    y: {
      grid: { color: 'rgba(0,0,0,.06)' },
      ticks: { color: '#7b7b9a', font: { size: 10 }, callback: v => fmt(v) },
      border: { color: 'rgba(0,0,0,.08)' },
    },
  },
};

function makeGradient(ctx, top, bot) {
  const g = ctx.createLinearGradient(0, 0, 0, 220);
  g.addColorStop(0, top);
  g.addColorStop(1, bot);
  return g;
}

/* ══════════════════════════════════════════════════════════════
   HERO — loads /api/overview
══════════════════════════════════════════════════════════════ */
async function loadHero() {
  const d = await api('/overview');

  animateCount(document.getElementById('hm-units'),    d.total_units);
  animateCount(document.getElementById('hm-critical'), d.critical_count);
  animateCount(document.getElementById('hm-warning'),  d.warning_count);

  // Critical SKU chips
  const miniEl = document.getElementById('critical-mini');
  if (miniEl && d.critical_skus?.length) {
    miniEl.innerHTML = d.critical_skus.map(s =>
      `<div class="feat-mini-chip" title="${s.name}">${s.name}</div>`).join('');
  }

  heroRawSales = d.sales_chart;
  const RANGE_N = { '4w': 4, '8w': 8, '12w': 12, '26w': 26 };
  const n     = RANGE_N[heroChartRange] || 12;
  const slice = heroRawSales.slice(-n);
  drawHeroChart(slice);
  updateHeroChartSummary(slice);

  renderActivityFeed(d.activity_feed || []);
  renderCatBars(d.categories || []);
}

/* ══════════════════════════════════════════════════════════════
   TOP-DEMAND chart — top-5 SKUs weekly sales
══════════════════════════════════════════════════════════════ */
const DEMAND_COLORS = [
  { border: '#7c3aed', bg: 'rgba(124,58,237,.50)' },
  { border: '#0891b2', bg: 'rgba(8,145,178,.45)'  },
  { border: '#d97706', bg: 'rgba(217,119,6,.42)'  },
  { border: '#059669', bg: 'rgba(5,150,105,.42)'  },
  { border: '#dc2626', bg: 'rgba(220,38,38,.40)'  },
];

async function loadTopDemand() {
  const skus = await api('/top-demand');
  if (!skus?.length) return;

  // Collect all unique weeks (union of all SKUs)
  const weekSet = new Set();
  skus.forEach(s => s.data.forEach(pt => weekSet.add(pt.week)));
  const weeks = [...weekSet].sort();
  const labels = weeks.map(w => w.slice(5)); // "MM-DD"

  destroyChart('demand-chart');
  const ctx = document.getElementById('demand-chart')?.getContext('2d');
  if (!ctx) return;

  const datasets = skus.map((s, i) => {
    const c = DEMAND_COLORS[i % DEMAND_COLORS.length];
    const map = Object.fromEntries(s.data.map(pt => [pt.week, pt.units]));
    return {
      label: s.name,
      data: weeks.map(w => map[w] ?? 0),
      backgroundColor: c.bg,
      borderColor: c.border,
      borderWidth: 0,
      borderRadius: 5,
      borderSkipped: false,
    };
  });

  activeCharts['demand-chart'] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      ...BASE_OPTS,
      plugins: {
        ...BASE_OPTS.plugins,
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: '#7b7b9a', font: { size: 10, family: 'Avenir Next' },
            boxWidth: 10, boxHeight: 10, borderRadius: 3, useBorderRadius: true,
            padding: 12,
          },
        },
      },
    },
  });
}

function updateHeroChartSummary(points) {
  if (!points.length) return;
  const total = points.reduce((s, x) => s + x.units, 0);
  const n     = points.length;
  const prev  = heroRawSales.slice(-(n * 2), -n);
  const sub   = document.getElementById('hero-chart-sub');
  if (!sub) return;

  // Only show delta if previous period has enough data (≥ half the window)
  if (prev.length >= Math.ceil(n / 2)) {
    const prevTotal = prev.reduce((s, x) => s + x.units, 0);
    const delta  = prevTotal > 0 ? Math.round((total - prevTotal) / prevTotal * 1000) / 10 : 0;
    const sign   = delta >= 0 ? '+' : '';
    const color  = delta >= 0 ? 'var(--accent-neon)' : 'var(--danger)';
    sub.innerHTML = `${fmt(total)} <span style="color:${color};font-family:var(--font-mono);font-size:13px;margin-left:8px;font-weight:500">${sign}${delta}%</span>`;
  } else {
    sub.innerHTML = `${fmt(total)}`;
  }
}

function drawHeroChart(points) {
  const labels = points.map(x => x.week.slice(5));
  const data   = points.map(x => x.units);

  // Update existing chart in-place (avoids canvas reuse issues on tab switches)
  if (activeCharts['hero-chart']) {
    const chart = activeCharts['hero-chart'];
    chart.data.labels = labels;
    chart.data.datasets[0].data = data;
    chart.update('active');
    return;
  }

  // First render
  const ctx = document.getElementById('hero-chart')?.getContext('2d');
  if (!ctx) return;
  const grad = makeGradient(ctx, 'rgba(124,58,237,.18)', 'rgba(124,58,237,.0)');
  activeCharts['hero-chart'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Единиц', data,
        borderColor: '#7c3aed', backgroundColor: grad,
        fill: true, tension: .45,
        pointRadius: 0, pointHoverRadius: 6,
        pointBackgroundColor: '#7c3aed', pointBorderColor: '#fff', pointBorderWidth: 2,
        borderWidth: 2.5,
      }],
    },
    options: { ...BASE_OPTS, plugins: { ...BASE_OPTS.plugins, glowLine: {} } },
  });
}

document.getElementById('hero-tabs').addEventListener('click', e => {
  const tab = e.target.closest('.cc-tab');
  if (!tab) return;
  document.querySelectorAll('#hero-tabs .cc-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  heroChartRange = tab.dataset.range;
  const n     = ({ '4w': 4, '8w': 8, '12w': 12, '26w': 26 })[heroChartRange] || 12;
  const slice = heroRawSales.slice(-n);
  drawHeroChart(slice);
  updateHeroChartSummary(slice);
});

/* ══════════════════════════════════════════════════════════════
   PORTFOLIO — loads /api/skus
══════════════════════════════════════════════════════════════ */
async function loadPortfolio() {
  allSkus  = await api('/skus');
  skuList  = allSkus;
  populateSkuSelects();
  renderSkuTable('all', '');
  renderRiskDonut();
  document.getElementById('fb-all').textContent      = allSkus.length;
  document.getElementById('fb-critical').textContent = allSkus.filter(s => s.status === 'critical').length;
  document.getElementById('fb-warning').textContent  = allSkus.filter(s => s.status === 'warning').length;
  document.getElementById('fb-ok').textContent       = allSkus.filter(s => s.status === 'ok').length;
  document.getElementById('donut-total').textContent = allSkus.length;
}

function renderSkuTable(filter, query) {
  let rows = filter === 'all' ? allSkus : allSkus.filter(r => r.status === filter);
  if (query) {
    const q = query.toLowerCase();
    rows = rows.filter(r => r.sa_name.toLowerCase().includes(q) || String(r.nm_id).includes(q));
  }
  const tbody = document.getElementById('skus-tbody');
  tbody.innerHTML = rows.length
    ? rows.map(r => `
        <tr data-nm="${r.nm_id}">
          <td><b>${r.sa_name}</b><br><span style="color:var(--text-muted);font-size:11px;font-family:var(--font-mono)">${r.nm_id}</span></td>
          <td style="color:var(--text-dim)">${r.subject_name}</td>
          <td style="font-variant-numeric:tabular-nums">${fmt(r.total_stock)}</td>
          <td>${r.n_warehouses}</td>
          <td style="font-variant-numeric:tabular-nums">${r.days_of_cover ?? '—'}</td>
          <td>${badge(r.status)}</td>
        </tr>`).join('')
    : '<tr><td colspan="6" class="loading-cell">Нет данных</td></tr>';
  tbody.querySelectorAll('tr[data-nm]').forEach(tr =>
    tr.addEventListener('click', () => jumpToSku(parseInt(tr.dataset.nm))));
}

function renderRiskDonut() {
  const critical = allSkus.filter(r => r.status === 'critical').length;
  const warning  = allSkus.filter(r => r.status === 'warning').length;
  const ok       = allSkus.filter(r => r.status === 'ok').length;
  destroyChart('risk-donut');
  const ctx = document.getElementById('risk-donut')?.getContext('2d');
  if (!ctx) return;
  activeCharts['risk-donut'] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Критично', 'Внимание', 'ОК'],
      datasets: [{
        data: [critical, warning, ok],
        backgroundColor: ['#dc2626', '#d97706', '#0891b2'],
        borderColor: 'transparent', borderWidth: 0, hoverOffset: 10,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '72%',
      animation: { duration: 1100, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true, backgroundColor: 'rgba(255,255,255,.97)',
          borderColor: 'rgba(124,58,237,.25)', borderWidth: 1, cornerRadius: 10,
          titleColor: '#7b7b9a', bodyColor: '#0f0f1a', displayColors: false,
        },
      },
    },
  });
  document.getElementById('risk-legend').innerHTML = [
    { label: 'Критично (< 14 дн.)',  color: '#dc2626', n: critical },
    { label: 'Внимание (14–30 дн.)', color: '#d97706', n: warning },
    { label: 'ОК (> 30 дн.)',         color: '#0891b2', n: ok },
  ].map(x => `
    <div class="donut-legend-item">
      <div class="donut-dot" style="background:${x.color};color:${x.color}"></div>
      <span>${x.label} — <b style="color:var(--text)">${x.n}</b></span>
    </div>`).join('');
}

document.getElementById('portfolio-filters').addEventListener('click', e => {
  const btn = e.target.closest('.filter-btn');
  if (!btn) return;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderSkuTable(btn.dataset.status, document.getElementById('sku-search').value);
});

document.getElementById('sku-search').addEventListener('input', e => {
  const active = document.querySelector('.filter-btn.active')?.dataset.status || 'all';
  renderSkuTable(active, e.target.value);
});

function jumpToSku(nmId) {
  const sel = document.getElementById('sku-select');
  if (sel) { sel.value = nmId; loadSkuDetail(); }
  document.getElementById('analyzer')?.scrollIntoView({ behavior: 'smooth' });
}

/* ══════════════════════════════════════════════════════════════
   MAP — loads /api/warehouses
══════════════════════════════════════════════════════════════ */
async function loadMap() {
  mapData = await api('/warehouses');

  if (!leafMap) {
    leafMap  = L.map('map', { zoomControl: true, preferCanvas: true, attributionControl: false }).setView([60, 80], 3);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 16, subdomains: 'abcd',
    }).addTo(leafMap);
    layerWH  = L.layerGroup().addTo(leafMap);
    layerDem = L.layerGroup();
  }

  buildWarehouseMarkers();
  buildDemandMarkers();
  setLayer('warehouses');
  renderWhTable();

  document.getElementById('map-leg').innerHTML = `
    <span><div class="leg-dot" style="background:#0891b2;color:#0891b2"></div> Коэф. ≤ 1.0</span>
    <span><div class="leg-dot" style="background:#d97706;color:#d97706"></div> 1.0 – 1.5</span>
    <span><div class="leg-dot" style="background:#dc2626;color:#dc2626"></div> &gt; 1.5</span>
    <span style="opacity:.4">|</span>
    <span><div class="leg-dot" style="background:#8b5cf6;color:#8b5cf6"></div> Спрос по регионам</span>`;
}

function pulsingMarker(lat, lng, color, radius) {
  const size = radius * 2;
  const html = `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};box-shadow:0 0 0 0 ${color}88,0 0 12px ${color};animation:marker-pulse 2.2s ease-out infinite"></div>`;
  return L.marker([lat, lng], {
    icon: L.divIcon({ className: 'pm', html, iconSize: [size, size], iconAnchor: [radius, radius] }),
  });
}

function buildWarehouseMarkers() {
  layerWH.clearLayers();
  const maxU = Math.max(...mapData.warehouses.map(w => w.total_units), 1);
  mapData.warehouses.filter(w => w.lat && w.lng).forEach(w => {
    const c     = w.delivery_coef || 1;
    const color = c > 1.5 ? '#dc2626' : c > 1.0 ? '#d97706' : '#0891b2';
    const r     = 7 + (w.total_units / maxU) * 18;
    const m     = pulsingMarker(w.lat, w.lng, color, r);
    m.bindPopup(`
      <div style="min-width:230px">
        <b style="font-size:14px;color:#0f0f1a">${w.name}</b>
        ${w.geo ? `<div style="color:#7b7b9a;font-size:11px;margin:4px 0 10px;font-family:'JetBrains Mono'">${w.geo}</div>` : ''}
        <div style="display:grid;grid-template-columns:1fr auto;gap:5px 14px;font-size:12px">
          <span style="color:#7b7b9a">Единиц:</span><b style="color:#0f0f1a;font-variant-numeric:tabular-nums">${fmt(w.total_units)}</b>
          <span style="color:#7b7b9a">Артикулов:</span><span style="color:#3d3d5c">${w.sku_count}</span>
          <span style="color:#7b7b9a">Коэф. доставки:</span><b style="color:${color}">×${(w.delivery_coef || 0).toFixed(2)}</b>
          <span style="color:#7b7b9a">Коэф. хранения:</span><span style="color:#3d3d5c">×${(w.storage_coef || 0).toFixed(2)}</span>
          <span style="color:#7b7b9a">Мин. запас:</span><span style="color:#3d3d5c">${w.min_days_of_cover ? Math.round(w.min_days_of_cover) + ' дн.' : '—'}</span>
          <span style="color:#7b7b9a">Критичных SKU:</span><b style="color:${w.critical_skus > 0 ? '#dc2626' : '#0891b2'}">${w.critical_skus}</b>
        </div>
      </div>`);
    layerWH.addLayer(m);
  });
}

function buildDemandMarkers() {
  layerDem.clearLayers();
  const maxQ = Math.max(...mapData.demand_by_region.map(r => r.qty), 1);
  mapData.demand_by_region.forEach(r => {
    const coords = RU_REGIONS[r.region];
    if (!coords) return;
    L.circleMarker(coords, {
      radius: 5 + (r.qty / maxQ) * 22,
      color: '#8b5cf6', fillColor: '#a78bfa', fillOpacity: .35, weight: 1.5,
    }).addTo(layerDem)
      .bindPopup(`<b style="color:#0f0f1a">${r.region}</b><br><span style="color:#7b7b9a">Продаж:</span> <b style="color:#7c3aed">${fmt(r.qty)}</b> шт.`);
  });
}

function setLayer(mode) {
  currentLayer = mode;
  document.querySelectorAll('.layer-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + mode).classList.add('active');
  if (mode === 'warehouses') { layerWH.addTo(leafMap); leafMap.removeLayer(layerDem); }
  else if (mode === 'demand') { leafMap.removeLayer(layerWH); layerDem.addTo(leafMap); }
  else { layerWH.addTo(leafMap); layerDem.addTo(leafMap); }
  leafMap.invalidateSize();
}

document.getElementById('btn-warehouses').addEventListener('click', () => setLayer('warehouses'));
document.getElementById('btn-demand').addEventListener('click', () => setLayer('demand'));
document.getElementById('btn-both').addEventListener('click', () => setLayer('both'));

function renderWhTable() {
  const tbody = document.getElementById('wh-tbody');
  tbody.innerHTML = mapData.warehouses.map(w => {
    const d = w.min_days_of_cover ? Math.round(w.min_days_of_cover) : null;
    const s = d == null ? 'ok' : d < 14 ? 'critical' : d < 30 ? 'warning' : 'ok';
    return `<tr>
      <td><b>${w.name}</b></td>
      <td style="color:var(--text-muted);font-size:12px">${w.geo || '—'}</td>
      <td style="font-variant-numeric:tabular-nums">${fmt(w.total_units)}</td>
      <td>${w.sku_count}</td>
      <td>${coefPill(w.delivery_coef)}</td>
      <td>${coefPill(w.storage_coef)}</td>
      <td>${w.critical_skus > 0 ? `<b style="color:var(--danger)">${w.critical_skus}</b>` : `<span style="color:var(--success)">0</span>`}</td>
      <td style="font-variant-numeric:tabular-nums">${d ?? '—'}</td>
      <td>${badge(s)}</td>
    </tr>`;
  }).join('');
}

/* ══════════════════════════════════════════════════════════════
   SIDE RAIL — uses already-loaded allSkus + mapData
══════════════════════════════════════════════════════════════ */
function renderSideRail() {
  const topWh      = mapData.warehouses.slice().sort((a, b) => b.total_units - a.total_units).slice(0, 6);
  const totalUnits = topWh.reduce((s, w) => s + w.total_units, 0);

  const wlist = document.getElementById('top-wh-list');
  if (wlist) wlist.innerHTML = topWh.map((w, i) => {
    const pct = Math.round(w.total_units / Math.max(totalUnits, 1) * 100);
    return `
      <div class="mini-row">
        <div class="mini-idx">${String(i + 1).padStart(2, '0')}</div>
        <div class="mini-main">
          <div class="mini-name">${w.name}</div>
          <div class="mini-sub">${w.geo || '—'} · ${w.sku_count} SKU</div>
        </div>
        <div class="mini-val">${fmt(w.total_units)}<div class="mini-sub" style="text-align:right">${pct}%</div></div>
      </div>`;
  }).join('');

  const risky = allSkus
    .filter(s => s.days_of_cover != null)
    .sort((a, b) => a.days_of_cover - b.days_of_cover)
    .slice(0, 6);

  const rlist = document.getElementById('top-risk-list');
  if (rlist) {
    rlist.innerHTML = risky.map((s, i) => `
      <div class="mini-row" data-nm="${s.nm_id}" style="cursor:pointer">
        <div class="mini-idx">${String(i + 1).padStart(2, '0')}</div>
        <div class="mini-main">
          <div class="mini-name">${s.sa_name}</div>
          <div class="mini-sub">${s.subject_name} · ${s.brand_name}</div>
        </div>
        <div class="mini-val ${s.status}">${s.days_of_cover}<div class="mini-sub" style="text-align:right">дн.</div></div>
      </div>`).join('');
    rlist.querySelectorAll('[data-nm]').forEach(el =>
      el.addEventListener('click', () => jumpToSku(parseInt(el.dataset.nm))));
  }
}

/* ══════════════════════════════════════════════════════════════
   SKU ANALYZER
══════════════════════════════════════════════════════════════ */
function populateSkuSelects() {
  const html = skuList.map(r => `<option value="${r.nm_id}">${r.sa_name} (${r.nm_id})</option>`).join('');
  document.getElementById('sku-select').innerHTML = '<option value="">— выберите SKU —</option>' + html;
  document.getElementById('opt-sku').innerHTML = html;
}

function buildTimeline(rows, max = 90) {
  if (!rows?.length) return '<p style="color:var(--text-muted);padding:12px 0">Нет данных</p>';
  const html = rows.map(r => {
    const d   = r.days_until_stockout;
    const pct = d == null ? 100 : Math.min(100, (d / max) * 100);
    const cls = d == null ? 'safe' : r.status;
    const lbl = d == null ? `> ${max} дн.` : `${d} дн.`;
    return `
      <div class="timeline-row">
        <div class="tl-label" title="${r.warehouse}">${r.warehouse}</div>
        <div class="tl-bg"><div class="tl-bar ${cls}" data-target="${Math.max(pct, 7)}" style="width:0">${lbl}</div></div>
        <div class="tl-units">${fmt(r.initial_stock)} шт.</div>
      </div>`;
  }).join('');
  setTimeout(() => {
    document.querySelectorAll('.tl-bar[data-target]').forEach((b, i) => {
      setTimeout(() => { b.style.width = b.dataset.target + '%'; b.removeAttribute('data-target'); }, i * 60);
    });
  }, 30);
  return html;
}

document.getElementById('sku-select').addEventListener('change', loadSkuDetail);

async function loadSkuDetail() {
  const nmId = parseInt(document.getElementById('sku-select').value);
  if (!nmId) return;
  const d = await api('/sku/' + nmId);
  if (!d) return;

  const total   = d.stock.reduce((s, r) => s + r.quantity, 0);
  const nearest = d.simulation.reduce((m, r) =>
    r.days_until_stockout != null && (m == null || r.days_until_stockout < m) ? r.days_until_stockout : m, null);
  const nearCls = nearest == null ? '' : nearest < 14 ? 'danger' : nearest < 30 ? 'warning' : 'success';

  document.getElementById('sku-kpis').innerHTML = `
    <div class="metric-card tilt"><div class="mc-label">Всего единиц</div><div class="mc-val">${fmt(total)}</div></div>
    <div class="metric-card tilt"><div class="mc-label">Активных складов</div><div class="mc-val purple">${d.stock.length}</div></div>
    <div class="metric-card tilt"><div class="mc-label">Ближайший стокаут</div><div class="mc-val ${nearCls}">${nearest != null ? nearest + ' дн.' : '—'}</div></div>
    <div class="metric-card tilt"><div class="mc-label">Категория</div><div class="mc-val" style="font-size:18px">${d.info.subject_name}</div></div>`;
  document.getElementById('sku-kpis').style.display = '';
  bindTilts();

  document.getElementById('sku-charts').style.display = '';
  document.getElementById('sku-timeline').innerHTML = buildTimeline(d.simulation);

  const weeks = d.demand_history.map(x => x.week.slice(5));
  const units = d.demand_history.map(x => x.units);
  destroyChart('sku-demand-chart');
  const ctx = document.getElementById('sku-demand-chart')?.getContext('2d');
  if (ctx) {
    const grad = makeGradient(ctx, 'rgba(124,58,237,.45)', 'rgba(124,58,237,.12)');
    activeCharts['sku-demand-chart'] = new Chart(ctx, {
      type: 'bar',
      data: { labels: weeks, datasets: [{ label: 'Продано', data: units, backgroundColor: grad, borderRadius: 6, borderSkipped: false }] },
      options: { ...BASE_OPTS, plugins: { ...BASE_OPTS.plugins, legend: { display: false } } },
    });
  }

  document.getElementById('sku-table-wrap').style.display = '';
  document.getElementById('sku-detail-tbody').innerHTML = d.simulation.map(r => `
    <tr>
      <td>${r.warehouse}</td>
      <td style="font-variant-numeric:tabular-nums">${fmt(r.initial_stock)}</td>
      <td style="font-family:var(--font-mono);font-size:12px">${r.stockout_date || '—'}</td>
      <td style="font-variant-numeric:tabular-nums">${r.days_until_stockout ?? '—'}</td>
      <td>${badge(r.status)}</td>
    </tr>`).join('');
}

/* ══════════════════════════════════════════════════════════════
   OPTIMIZER CHARTS
══════════════════════════════════════════════════════════════ */

/** Grouped horizontal bar: дни запаса до/после по каждому складу */
function drawOptCompareChart(current, proposed, horizonDays) {
  destroyChart('opt-compare-chart');
  const ctx = document.getElementById('opt-compare-chart')?.getContext('2d');
  if (!ctx) return;

  // Объединяем склады из обоих симуляций
  const whSet = new Set([
    ...current.map(r => r.warehouse),
    ...proposed.map(r => r.warehouse),
  ]);
  const warehouses = [...whSet];

  // Динамически подбираем высоту контейнера под количество складов
  const wrap = document.getElementById('opt-compare-wrap');
  if (wrap) wrap.style.height = Math.max(180, warehouses.length * 52) + 'px';

  const cap = horizonDays;
  const curMap  = Object.fromEntries(current.map(r  => [r.warehouse, r.days_until_stockout]));
  const propMap = Object.fromEntries(proposed.map(r => [r.warehouse, r.days_until_stockout]));

  const curData  = warehouses.map(w => Math.min(curMap[w] ?? cap, cap));
  // Если склад не получил поставку — его запас не изменился (берём текущий)
  const propData = warehouses.map(w =>
    Math.min(propMap[w] !== undefined ? (propMap[w] ?? cap) : (curMap[w] ?? cap), cap)
  );

  activeCharts['opt-compare-chart'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: warehouses,
      datasets: [
        {
          label: 'Сейчас',
          data: curData,
          backgroundColor: 'rgba(229,130,145,.55)',
          borderColor: 'rgba(229,85,106,.70)',
          borderWidth: 1,
          borderRadius: 5,
          borderSkipped: false,
        },
        {
          label: 'После отправки',
          data: propData,
          backgroundColor: 'rgba(155,145,255,.50)',
          borderColor: 'rgba(109,94,246,.75)',
          borderWidth: 1,
          borderRadius: 5,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 900, easing: 'easeOutQuart' },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true, position: 'bottom',
          labels: {
            color: '#8d8ba6', font: { size: 11, family: 'Manrope' },
            boxWidth: 10, boxHeight: 10, borderRadius: 4, useBorderRadius: true,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: 'rgba(255,255,255,.97)',
          borderColor: 'rgba(109,94,246,.25)',
          borderWidth: 1, cornerRadius: 10, padding: 10,
          titleColor: '#8d8ba6', bodyColor: '#0f0f1a',
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.x;
              return `${ctx.dataset.label}: ${v >= cap ? `> ${cap}` : v} дн.`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(0,0,0,.05)' },
          border: { color: 'rgba(0,0,0,.08)' },
          ticks: {
            color: '#8d8ba6', font: { size: 10 },
            callback: v => v >= cap ? `>${cap}` : v,
          },
          max: cap + Math.ceil(cap * 0.06),
        },
        y: {
          grid: { display: false },
          border: { display: false },
          ticks: { color: '#4f4d68', font: { size: 11, family: 'Manrope' } },
        },
      },
    },
  });
}

/** Doughnut: доля затрат по складам */
function drawOptCostDonut(allocation) {
  destroyChart('opt-cost-donut');
  const ctx = document.getElementById('opt-cost-donut')?.getContext('2d');
  if (!ctx) return;

  const items = allocation.filter(r => r.total_cost > 0);
  if (!items.length) return;

  const PALETTE = [
    '#6d5ef6','#0891b2','#d97706','#059669',
    '#dc2626','#8b5cf6','#f59e0b','#10b981','#ec4899',
  ];

  activeCharts['opt-cost-donut'] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: items.map(r => r.warehouse),
      datasets: [{
        data: items.map(r => r.total_cost),
        backgroundColor: PALETTE.slice(0, items.length),
        borderColor: 'transparent',
        borderWidth: 0,
        hoverOffset: 10,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      animation: { duration: 1100, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(255,255,255,.97)',
          borderColor: 'rgba(109,94,246,.25)',
          borderWidth: 1, cornerRadius: 10, padding: 10,
          titleColor: '#8d8ba6', bodyColor: '#0f0f1a', displayColors: false,
          callbacks: {
            label: ctx => `${ctx.label}: ${fmtRub(ctx.parsed)}`,
          },
        },
      },
    },
  });

  // Центр — итого
  const total = items.reduce((s, r) => s + r.total_cost, 0);
  const totalEl = document.getElementById('opt-cost-total');
  if (totalEl) totalEl.textContent = Math.round(total).toLocaleString('ru-RU');

  // Легенда
  const legend = document.getElementById('opt-cost-legend');
  if (legend) {
    legend.innerHTML = items.map((r, i) => `
      <div class="donut-legend-item">
        <div class="donut-dot" style="background:${PALETTE[i]}"></div>
        <span>${r.warehouse} — <b style="color:var(--text)">${fmtRub(r.total_cost)}</b></span>
      </div>`).join('');
  }
}

/* ══════════════════════════════════════════════════════════════
   OPTIMIZER — POST /api/optimize
══════════════════════════════════════════════════════════════ */
document.getElementById('calc-btn').addEventListener('click', runOptimizer);

async function runOptimizer() {
  const nmId   = parseInt(document.getElementById('opt-sku').value);
  const units  = parseInt(document.getElementById('opt-units').value);
  const nWeeks = parseInt(document.getElementById('opt-weeks').value);
  if (!nmId || !units) return;

  const btn = document.getElementById('calc-btn');
  btn.disabled = true;
  const lbl = btn.querySelector('span');
  const old = lbl.textContent;
  lbl.textContent = 'Считаю…';

  try {
    const d = await api('/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nm_id: nmId, total_units: units, n_weeks: nWeeks }),
    });

    const totalSent = d.allocation.reduce((s, r) => s + r.allocated, 0);
    const cov = d.coverage_pct ?? 0;
    const covCls = cov >= 60 ? 'success' : cov >= 25 ? 'warning' : 'danger';

    document.getElementById('opt-kpis').innerHTML = [
      { label: 'К отправке',        val: fmt(totalSent) + ' шт.',         cls: 'purple' },
      { label: 'Покрытие спроса',   val: cov + '%',                       cls: covCls,
        sub: `из ${fmt(d.total_demand ?? 0)} шт. за горизонт` },
      { label: 'Упущенные продажи', val: fmtRub(d.total_stockout_cost),   cls: d.total_stockout_cost > 0 ? 'warning' : 'success' },
      { label: 'Хранение',          val: fmtRub(d.total_storage_cost),    cls: '' },
    ].map(m => `
      <div class="metric-card tilt">
        <div class="mc-label">${m.label}</div>
        <div class="mc-val ${m.cls}" style="font-size:22px">${m.val}</div>
        ${m.sub ? `<div class="mc-sub">${m.sub}</div>` : ''}
      </div>`).join('');

    // Предупреждение если покрытие < 30% или меньше мин. рекомендованного кол-ва
    const minRec = d.min_recommended ?? 0;
    const warnEl = document.getElementById('opt-coverage-warn') || (() => {
      const el = document.createElement('div'); el.id = 'opt-coverage-warn'; return el;
    })();
    warnEl.style.cssText = 'margin:-8px 0 18px;font-size:12.5px;padding:10px 16px;border-radius:10px;';
    if (cov < 30 && minRec > totalSent) {
      warnEl.style.background = 'rgba(229,85,106,.08)';
      warnEl.style.color = 'var(--danger)';
      warnEl.innerHTML = `⚠️ Поставка покрывает лишь ${cov}% прогнозируемого спроса. Для покрытия 2 недель топ-склада рекомендуется минимум <b>${fmt(minRec)} шт.</b>`;
    } else {
      warnEl.innerHTML = '';
    }
    const kpisEl = document.getElementById('opt-kpis');
    if (!document.getElementById('opt-coverage-warn')) kpisEl.after(warnEl);

    bindTilts();

    // Grouped bar: до и после
    drawOptCompareChart(d.current_simulation, d.proposed_simulation, nWeeks * 7);

    // Таблица распределения
    document.getElementById('opt-alloc-tbody').innerHTML = d.allocation.map(r => `
      <tr>
        <td>${r.warehouse}</td>
        <td><b style="font-variant-numeric:tabular-nums">${fmt(r.allocated)}</b></td>
        <td style="font-variant-numeric:tabular-nums">${fmt(Math.round(r.demand))}</td>
        <td style="font-family:var(--font-mono);font-size:12px">${fmtRub(r.storage_cost)}</td>
        <td style="font-family:var(--font-mono);font-size:12px">${fmtRub(r.stockout_cost)}</td>
        <td style="font-variant-numeric:tabular-nums">${r.new_days_until_stockout ?? '—'} дн.</td>
        <td>${badge(r.status)}</td>
      </tr>`).join('');

    // Donut: затраты по складам
    drawOptCostDonut(d.allocation);

    document.getElementById('opt-results').style.display = '';
    document.querySelectorAll('#opt-results .anim').forEach(el => el.classList.add('visible'));
  } finally {
    btn.disabled  = false;
    lbl.textContent = old;
  }
}

/* ══════════════════════════════════════════════════════════════
   Activity feed
══════════════════════════════════════════════════════════════ */
function renderActivityFeed(events) {
  const el = document.getElementById('activity-feed');
  if (!el) return;
  if (!events.length) {
    el.innerHTML = '<div style="color:var(--text-muted);padding:16px 0;font-size:12px;text-align:center">Нет событий</div>';
    return;
  }
  el.innerHTML = events.map((ev, i) => `
    <div class="feed-row" style="animation-delay:${i * 0.07}s">
      <div class="feed-time">${ev.time}</div>
      <div class="feed-kind">
        <div class="feed-dot ${ev.dot || 'ok'}"></div>
        <span class="feed-kind-text">${ev.kind}</span>
      </div>
      <div class="feed-meta"><b>${ev.meta}</b></div>
    </div>`).join('');
}

/* ══════════════════════════════════════════════════════════════
   Category bars
══════════════════════════════════════════════════════════════ */
function renderCatBars(cats) {
  const el = document.getElementById('cat-bars');
  if (!el || !cats.length) return;
  el.innerHTML = cats.map(c => `
    <div class="cat-row">
      <div class="cat-name" title="${c.name}">${c.name}</div>
      <div class="cat-bar-bg"><div class="cat-bar" data-w="${c.pct}"></div></div>
      <div class="cat-val">${c.pct}%</div>
    </div>`).join('');
  setTimeout(() => {
    el.querySelectorAll('.cat-bar[data-w]').forEach((b, i) => {
      setTimeout(() => { b.style.width = b.dataset.w + '%'; b.removeAttribute('data-w'); }, i * 90);
    });
  }, 120);
}

/* ══════════════════════════════════════════════════════════════
   Stock boxplot (SVG bar chart — top warehouses by stock)
══════════════════════════════════════════════════════════════ */
function renderBoxPlot() {
  const el = document.getElementById('stock-boxplot');
  if (!el || !mapData.warehouses.length) return;

  const top  = mapData.warehouses.slice(0, 7);
  const maxU = Math.max(...top.map(w => w.total_units), 1);

  const labelW = 126, barMaxW = 168, gap = 30, padTop = 8;
  const svgH = top.length * gap + padTop;
  const svgW = labelW + barMaxW + 52;

  const rows = top.map((w, i) => {
    const y   = padTop + i * gap;
    const bw  = Math.max(4, (w.total_units / maxU) * barMaxW);
    const c   = (w.delivery_coef || 1) > 1.5 ? '#e5556a'
               : (w.delivery_coef || 1) > 1.0 ? '#e09a3c' : '#6d5ef6';
    const lbl = w.name.length > 15 ? w.name.slice(0, 14) + '…' : w.name;
    const val = w.total_units >= 1000
      ? (w.total_units / 1000).toFixed(0) + 'k'
      : String(w.total_units);
    const dur = (0.5 + i * 0.07).toFixed(2);
    return `
      <text x="${labelW - 8}" y="${y + 13}" text-anchor="end"
            font-size="11" fill="#8d8ba6"
            font-family="Manrope,system-ui,sans-serif">${lbl}</text>
      <rect x="${labelW}" y="${y}" width="0" height="18" rx="5"
            fill="${c}" opacity=".82">
        <animate attributeName="width" from="0" to="${bw.toFixed(1)}"
                 dur="${dur}s" fill="freeze" calcMode="spline"
                 keySplines="0.4 0 0.2 1" keyTimes="0;1"/>
      </rect>
      <text x="${labelW + bw + 6}" y="${y + 13}"
            font-size="10.5" fill="#8d8ba6"
            font-family="JetBrains Mono,ui-monospace,monospace"
            font-variant-numeric="tabular-nums">${val}</text>`;
  }).join('');

  el.innerHTML = `<svg viewBox="0 0 ${svgW} ${svgH}" width="${svgW}" height="${svgH}">${rows}</svg>`;
}

/* ══════════════════════════════════════════════════════════════
   INIT
══════════════════════════════════════════════════════════════ */
(async () => {
  registerAnims();
  bindTilts();
  bindMagnetic();
  setSnapshot();
  await loadHero();
  await loadPortfolio();
  await loadMap();
  renderBoxPlot();
  renderSideRail();
  bindTilts();
  registerAnims();
})();
