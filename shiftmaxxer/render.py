from __future__ import annotations
import json
from .models import Schedule, Resident, Shift
from .optimizer import CycleResult


def _fmt_time(dt) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.strftime('%M')} {'AM' if dt.hour < 12 else 'PM'}"


def _shift_dict(s: Shift) -> dict:
    return {
        "uid": s.uid,
        "summary": s.summary,
        "startFmt": _fmt_time(s.t_start),
        "endFmt": _fmt_time(s.t_end),
        "loc": s.loc,
        "type": s.type,
        "workDate": s.work_date.isoformat(),
        "isJeopardy": s.is_jeopardy,
    }


def _resident_dict(r: Resident) -> dict:
    return {
        "name": r.name,
        "locPref": r.loc_pref,
        "locWeight": round(r.loc_weight * 100),
        "typePref": r.type_pref,
        "typeWeight": round(r.type_weight * 100),
        "daysPref": r.days_pref,
        "daysWeight": round(r.days_weight * 100),
        "daysOff": [d.isoformat() for d in sorted(r.days_off)],
    }


def build_payload(sched: Schedule, log: list[CycleResult],
                  original_assignment: dict) -> dict:
    swaps: dict = {n: [] for n in sched.residents}
    for res in log:
        # Build recv_uid -> giver map for partner lookup
        recv_to_giver = {v: giver for giver, u, v in res.moves}
        for giver, u, v in res.moves:
            su, sv = sched.shifts[u], sched.shifts[v]
            # The partner is whoever gives away the shift we receive
            partner = recv_to_giver.get(u, "")
            swaps[giver].append({
                "giveUid": u,
                "giveSummary": su.summary,
                "giveDate": su.work_date.isoformat(),
                "giveLoc": su.loc,
                "giveType": su.type,
                "giveStart": _fmt_time(su.t_start),
                "giveEnd": _fmt_time(su.t_end),
                "recvUid": v,
                "recvSummary": sv.summary,
                "recvDate": sv.work_date.isoformat(),
                "recvLoc": sv.loc,
                "recvType": sv.type,
                "recvStart": _fmt_time(sv.t_start),
                "recvEnd": _fmt_time(sv.t_end),
                "delta": round(res.deltas.get(giver, 0), 4),
                "swapWith": partner,
            })

    return {
        "residents": {n: _resident_dict(r) for n, r in sched.residents.items()},
        "shifts": {uid: _shift_dict(s) for uid, s in sched.shifts.items()},
        "originalAssignment": {n: list(uids) for n, uids in original_assignment.items()},
        "finalAssignment": {n: list(uids) for n, uids in sched.assignment.items()},
        "swaps": swaps,
    }


def render_html(sched: Schedule, log: list[CycleResult],
                original_assignment: dict) -> str:
    payload = build_payload(sched, log, original_assignment)
    data_js = "const DATA = " + json.dumps(payload, indent=2) + ";"
    return _TEMPLATE.replace("/*__INJECT_DATA__*/", data_js)


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShiftMaxxer &mdash; Swap Report</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0A0F1E;
  --surface:#111827;
  --surface2:#1A2236;
  --border:#1E2D45;
  --border2:#253550;
  --text:#F0F6FF;
  --muted:#6B82A8;
  --muted2:#4A5E7A;
  --mgh:#3B82F6;--mgh-l:rgba(59,130,246,.15);--mgh-b:rgba(59,130,246,.35);
  --bwh:#10B981;--bwh-l:rgba(16,185,129,.15);--bwh-b:rgba(16,185,129,.35);
  --give:#F43F5E;--give-l:rgba(244,63,94,.12);--give-b:rgba(244,63,94,.35);
  --recv:#10B981;--recv-l:rgba(16,185,129,.12);--recv-b:rgba(16,185,129,.35);
  --jeop:#6B7280;--jeop-l:rgba(107,114,128,.15);
  --accent:#8B5CF6;--accent2:#A78BFA;--accent-l:rgba(139,92,246,.15);
  --gold:#F59E0B;--gold-l:rgba(245,158,11,.15);
  --r:14px;--r-sm:8px;
  --sh:0 1px 3px rgba(0,0,0,.4),0 1px 2px rgba(0,0,0,.3);
  --sh-lg:0 20px 40px rgba(0,0,0,.5),0 8px 16px rgba(0,0,0,.3);
  --sh-glow:0 0 20px rgba(139,92,246,.25);
}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px;min-height:100vh}

/* ── Header ── */
.hdr{
  background:linear-gradient(180deg,rgba(17,24,39,.98) 0%,rgba(17,24,39,.95) 100%);
  border-bottom:1px solid var(--border);
  padding:.875rem 2rem;
  display:flex;align-items:center;gap:1.25rem;
  position:sticky;top:0;z-index:50;
  backdrop-filter:blur(12px);
  box-shadow:0 1px 0 var(--border),0 4px 24px rgba(0,0,0,.4);
}
.logo-mark{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--accent),#6D28D9);
  display:flex;align-items:center;justify-content:center;
  font-size:1.1rem;font-weight:900;color:#fff;
  box-shadow:0 0 12px rgba(139,92,246,.5);
  flex-shrink:0;
}
.logo{font-size:1.05rem;font-weight:800;color:var(--text);letter-spacing:-.3px}
.logo-sub{color:var(--muted);font-size:.75rem;font-weight:400;margin-top:1px}

/* Happiness orb */
.happiness-orb{
  margin-left:auto;
  display:flex;align-items:center;gap:.875rem;
  background:var(--gold-l);
  border:1px solid rgba(245,158,11,.3);
  border-radius:999px;
  padding:.45rem 1rem .45rem .6rem;
}
.orb-pulse{
  width:28px;height:28px;border-radius:50%;
  background:radial-gradient(circle,#FBBF24,#F59E0B);
  box-shadow:0 0 10px rgba(245,158,11,.6),0 0 20px rgba(245,158,11,.3);
  display:flex;align-items:center;justify-content:center;
  font-size:.85rem;
  animation:pulse 2.4s ease-in-out infinite;
  flex-shrink:0;
}
@keyframes pulse{0%,100%{box-shadow:0 0 8px rgba(245,158,11,.5),0 0 16px rgba(245,158,11,.25)}50%{box-shadow:0 0 16px rgba(245,158,11,.8),0 0 32px rgba(245,158,11,.4)}}
.orb-text{line-height:1.2}
.orb-label{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;color:var(--gold);font-weight:700}
.orb-value{font-size:.95rem;font-weight:800;color:#FDE68A}

/* Resident selector */
.sel-wrap{display:flex;align-items:center;gap:.6rem;margin-left:1.5rem}
.sel-wrap label{font-size:.75rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
select{
  padding:.45rem .9rem .45rem .75rem;
  border:1px solid var(--border2);border-radius:9px;
  font-size:.85rem;background:var(--surface2);color:var(--text);
  cursor:pointer;outline:none;font-family:inherit;font-weight:600;
  appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236B82A8' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right .65rem center;
  padding-right:2rem;
  transition:border-color .15s,box-shadow .15s;
}
select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-l)}

/* ── Layout ── */
.main{max-width:1440px;margin:0 auto;padding:1.75rem 2rem 4rem}

/* ── Section labels ── */
.sec-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:.875rem}
.sec-label{font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);display:flex;align-items:center;gap:.4rem}
.sec-label::before{content:'';display:block;width:3px;height:12px;background:var(--accent);border-radius:2px}

/* ── Week Navigation ── */
.week-nav{display:flex;align-items:center;gap:.75rem}
.nav-btn{
  width:34px;height:34px;border-radius:9px;border:1px solid var(--border2);
  background:var(--surface2);color:var(--muted);cursor:pointer;
  display:flex;align-items:center;justify-content:center;font-size:.9rem;
  transition:all .15s;flex-shrink:0;
}
.nav-btn:hover{background:var(--surface);border-color:var(--accent);color:var(--accent);box-shadow:var(--sh-glow)}
.week-label{font-size:.82rem;font-weight:700;color:var(--text);min-width:180px;text-align:center}

/* ── Week View ── */
.week-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:1.25rem}
.week-col-hdr{
  text-align:center;padding:.6rem .25rem .5rem;
  border-radius:var(--r-sm) var(--r-sm) 0 0;
}
.week-col-hdr.today{background:var(--accent-l);border:1px solid rgba(139,92,246,.3);border-bottom:none}
.wch-dow{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.wch-dow.today-txt{color:var(--accent2)}
.wch-date{font-size:1.1rem;font-weight:800;color:var(--text);line-height:1.1}
.wch-date.today-txt{color:var(--accent2)}
.week-col-body{
  background:var(--surface);border:1px solid var(--border);border-radius:0 0 var(--r-sm) var(--r-sm);
  padding:6px;min-height:140px;display:flex;flex-direction:column;gap:4px;
}
.week-col-body.today-col{border-color:rgba(139,92,246,.3);background:rgba(139,92,246,.04)}
.week-empty{flex:1;display:flex;align-items:center;justify-content:center}
.week-empty-dot{width:4px;height:4px;border-radius:50%;background:var(--border2)}
.shift-block{
  border-radius:6px;padding:.45rem .55rem;cursor:default;
  transition:transform .1s,box-shadow .1s;
  border-left:3px solid transparent;
}
.shift-block:hover{transform:translateY(-1px);box-shadow:var(--sh-lg)}
.sb-mgh{background:var(--mgh-l);border-left-color:var(--mgh)}
.sb-bwh{background:var(--bwh-l);border-left-color:var(--bwh)}
.sb-give{background:var(--give-l);border-left-color:var(--give);opacity:.75}
.sb-recv{background:var(--recv-l);border-left-color:var(--recv)}
.sb-jeop{background:var(--jeop-l);border-left-color:var(--jeop)}
.sb-loc{font-size:.6rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px}
.sb-mgh .sb-loc{color:var(--mgh)}
.sb-bwh .sb-loc{color:var(--bwh)}
.sb-give .sb-loc{color:var(--give)}
.sb-recv .sb-loc{color:var(--recv)}
.sb-jeop .sb-loc{color:var(--jeop)}
.sb-time{font-size:.62rem;color:var(--muted);line-height:1.3}
.sb-badge{display:inline-block;font-size:.52rem;font-weight:700;border-radius:3px;padding:1px 5px;margin-top:3px;text-transform:uppercase;letter-spacing:.04em}
.badge-give{background:var(--give-b);color:var(--give)}
.badge-recv{background:var(--recv-b);color:var(--recv)}
.badge-give-txt{text-decoration:line-through}

/* ── Legend ── */
.legend{display:flex;gap:1rem;flex-wrap:wrap;margin-top:.5rem}
.leg{display:flex;align-items:center;gap:.4rem;font-size:.68rem;color:var(--muted)}
.leg-dot{width:10px;height:10px;border-radius:3px;flex-shrink:0}

/* ── Two-col layout ── */
.top-grid{display:grid;grid-template-columns:1fr 290px;gap:1.5rem;align-items:start;margin-bottom:1.75rem}
@media(max-width:960px){.top-grid{grid-template-columns:1fr}}

/* ── Preferences ── */
.prefs-card{
  background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:1.25rem;box-shadow:var(--sh);position:sticky;top:72px;
}
.prefs-title{font-size:.8rem;font-weight:700;color:var(--text);margin-bottom:1rem;display:flex;align-items:center;gap:.4rem}
.pref-row{margin-bottom:.875rem}
.pref-row:last-child{margin-bottom:0}
.pref-lbl{font-size:.62rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted2);font-weight:700;margin-bottom:.25rem}
.pref-val{font-size:.88rem;font-weight:700;color:var(--text)}
.pref-val.any{color:var(--muted);font-style:italic;font-weight:400}
.wbar-wrap{display:flex;align-items:center;gap:.6rem;margin-top:.35rem}
.wbar{flex:1;height:5px;background:var(--border);border-radius:3px;overflow:hidden}
.wfill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:3px;transition:width .6s cubic-bezier(.34,1.56,.64,1)}
.wlbl{font-size:.65rem;color:var(--muted);min-width:30px;text-align:right;font-weight:600}
.doff-list{font-size:.75rem;color:var(--give);margin-top:.25rem;line-height:1.6}
.doff-none{font-size:.75rem;color:var(--muted);font-style:italic}
.divider{border:none;border-top:1px solid var(--border);margin:1rem 0}

/* ── Swap Cards ── */
.swaps-section{margin-top:1.75rem}
.swaps-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem}
.no-swaps{
  background:var(--surface);border:1px dashed var(--border2);border-radius:var(--r);
  padding:3rem;text-align:center;color:var(--muted);
}
.no-swaps-emoji{font-size:2rem;margin-bottom:.5rem}
.no-swaps-msg{font-size:.875rem;font-weight:600}
.no-swaps-sub{font-size:.75rem;color:var(--muted2);margin-top:.25rem}

.swap-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);box-shadow:var(--sh);overflow:hidden;
  transition:transform .15s,box-shadow .15s,border-color .15s;
}
.swap-card:hover{transform:translateY(-2px);box-shadow:var(--sh-lg);border-color:var(--border2)}
.swap-card.pos-card{border-top:2px solid var(--recv)}
.swap-card.neg-card{border-top:2px solid var(--give)}
.swap-card.neu-card{border-top:2px solid var(--border2)}

.card-hdr{padding:.7rem 1rem;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)}
.card-hdr.pos{background:linear-gradient(135deg,rgba(16,185,129,.08),transparent)}
.card-hdr.neu{background:var(--surface2)}
.card-hdr.neg{background:linear-gradient(135deg,rgba(244,63,94,.08),transparent)}
.card-hdr-left{display:flex;flex-direction:column;gap:2px}
.card-hdr-title{font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.swap-with-badge{
  font-size:.72rem;font-weight:700;color:var(--text);
  display:flex;align-items:center;gap:.3rem;
}
.swap-with-badge .partner-name{
  background:var(--accent-l);color:var(--accent2);
  border-radius:5px;padding:1px 7px;font-size:.68rem;
}
.delta-pill{
  border-radius:999px;padding:3px 10px;font-size:.7rem;font-weight:800;
  white-space:nowrap;
}
.dp-pos{background:rgba(16,185,129,.15);color:#34D399;border:1px solid rgba(16,185,129,.3)}
.dp-neu{background:var(--surface2);color:var(--muted);border:1px solid var(--border2)}
.dp-neg{background:rgba(244,63,94,.12);color:#FB7185;border:1px solid rgba(244,63,94,.25)}

.card-body{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:.5rem;padding:.875rem 1rem}
.shift-blk{padding:.75rem;border-radius:10px;position:relative}
.shift-blk.give{background:var(--give-l);border:1px solid var(--give-b)}
.shift-blk.recv{background:var(--recv-l);border:1px solid var(--recv-b)}
.blk-lbl{font-size:.58rem;font-weight:800;text-transform:uppercase;letter-spacing:.09em;margin-bottom:.35rem}
.shift-blk.give .blk-lbl{color:var(--give)}
.shift-blk.recv .blk-lbl{color:var(--recv)}
.blk-summary{font-size:.78rem;font-weight:700;line-height:1.35;margin-bottom:.3rem;color:var(--text)}
.blk-meta{font-size:.66rem;color:var(--muted);line-height:1.8}
.loc-tag{display:inline-flex;align-items:center;gap:3px;border-radius:5px;padding:2px 7px;font-size:.62rem;font-weight:700;margin-top:.4rem}
.lt-mgh{background:var(--mgh-l);color:var(--mgh);border:1px solid var(--mgh-b)}
.lt-bwh{background:var(--bwh-l);color:var(--bwh);border:1px solid var(--bwh-b)}
.lt-none{background:var(--jeop-l);color:var(--jeop)}

.arrow-col{display:flex;flex-direction:column;align-items:center;gap:4px}
.arrow-icon{
  width:28px;height:28px;border-radius:50%;
  background:var(--surface2);border:1px solid var(--border2);
  display:flex;align-items:center;justify-content:center;
  font-size:.85rem;color:var(--muted);
}

/* ── Swaps count badge ── */
.count-badge{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:20px;height:20px;border-radius:999px;padding:0 6px;
  background:var(--accent-l);color:var(--accent2);
  font-size:.67rem;font-weight:700;border:1px solid rgba(139,92,246,.25);
}
</style>
</head>
<body>
<header class="hdr">
  <div class="logo-mark">S</div>
  <div>
    <div class="logo">ShiftMaxxer</div>
    <div class="logo-sub">Swap Optimizer Report</div>
  </div>
  <div class="happiness-orb" id="happiness-orb">
    <div class="orb-pulse">&#127881;</div>
    <div class="orb-text">
      <div class="orb-label">Total Happiness Conserved</div>
      <div class="orb-value" id="happiness-value">+0.0%</div>
    </div>
  </div>
  <div class="sel-wrap">
    <label for="rsel">Resident</label>
    <select id="rsel"></select>
  </div>
</header>

<main class="main">
  <div class="top-grid">
    <section>
      <div class="sec-header">
        <div class="sec-label">Week View</div>
        <div class="week-nav">
          <button class="nav-btn" id="prev-week" title="Previous week">&#8592;</button>
          <div class="week-label" id="week-label"></div>
          <button class="nav-btn" id="next-week" title="Next week">&#8594;</button>
        </div>
      </div>
      <div id="week-view"></div>
      <div class="legend">
        <div class="leg"><div class="leg-dot" style="background:var(--mgh-l);border:1px solid var(--mgh)"></div>MGH (kept)</div>
        <div class="leg"><div class="leg-dot" style="background:var(--bwh-l);border:1px solid var(--bwh)"></div>BWH (kept)</div>
        <div class="leg"><div class="leg-dot" style="background:var(--give-l);border:2px solid var(--give)"></div>Given away</div>
        <div class="leg"><div class="leg-dot" style="background:var(--recv-l);border:2px solid var(--recv)"></div>Received</div>
        <div class="leg"><div class="leg-dot" style="background:var(--jeop-l);border:1px solid var(--jeop)"></div>Jeopardy</div>
      </div>
    </section>
    <aside>
      <div class="sec-label" style="margin-bottom:.875rem">Preferences</div>
      <div class="prefs-card" id="prefs"></div>
    </aside>
  </div>

  <div class="swaps-section">
    <div class="sec-header">
      <div class="sec-label">Proposed Swaps <span class="count-badge" id="swap-count">0</span></div>
    </div>
    <div id="swaps-grid" class="swaps-grid"></div>
  </div>
</main>

<script>
/*__INJECT_DATA__*/

const MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];
const DOWS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const DOWS_SHORT = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

let cur = null;
let weekOffset = 0; // weeks from the "anchor" week (first week with any shift)
let anchorMonday = null; // Date object for Monday of anchor week

function isoToDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}
function dateToIso(dt) {
  return dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0') + '-' + String(dt.getDate()).padStart(2,'0');
}
function getMonday(dt) {
  const d = new Date(dt);
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d;
}
function addDays(dt, n) {
  const d = new Date(dt);
  d.setDate(d.getDate() + n);
  return d;
}
function fmtShort(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return MONTHS[m-1].slice(0,3) + ' ' + d;
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

function init() {
  const names = Object.keys(DATA.residents).sort();
  const sel = document.getElementById('rsel');
  names.forEach(n => {
    const o = document.createElement('option');
    o.value = n;
    o.textContent = cap(n);
    sel.appendChild(o);
  });
  cur = names[0];
  sel.value = cur;

  // Anchor week = Monday of first shift date across all residents
  const allDates = Object.values(DATA.shifts).map(s => s.workDate).sort();
  if (allDates.length) {
    anchorMonday = getMonday(isoToDate(allDates[0]));
  } else {
    anchorMonday = getMonday(new Date());
  }

  document.getElementById('prev-week').addEventListener('click', () => { weekOffset--; renderWeek(); });
  document.getElementById('next-week').addEventListener('click', () => { weekOffset++; renderWeek(); });
  sel.addEventListener('change', e => { cur = e.target.value; weekOffset = 0; render(); });

  render();
}

function render() {
  renderHappiness();
  renderPrefs();
  renderWeek();
  renderSwaps();
}

/* ── Happiness Orb ── */
function renderHappiness() {
  const swaps = DATA.swaps[cur] || [];
  const total = swaps.reduce((s, sw) => s + sw.delta, 0);
  const pct = (total * 100).toFixed(1);
  const el = document.getElementById('happiness-value');
  const orb = document.getElementById('happiness-orb');
  el.textContent = (total >= 0 ? '+' : '') + pct + '%';
  if (total > 0.001) {
    orb.style.background = 'rgba(245,158,11,.12)';
    orb.style.borderColor = 'rgba(245,158,11,.35)';
  } else if (total < -0.001) {
    orb.style.background = 'rgba(244,63,94,.1)';
    orb.style.borderColor = 'rgba(244,63,94,.25)';
    el.style.color = '#FB7185';
  }
}

/* ── Preferences ── */
function renderPrefs() {
  const r = DATA.residents[cur];
  const fmtDate = iso => {
    const [y, m, d] = iso.split('-').map(Number);
    return MONTHS[m-1].slice(0,3) + ' ' + d + ', ' + y;
  };
  const row = (icon, label, val, isAny, weight) => {
    const bar = weight != null
      ? '<div class="wbar-wrap"><div class="wbar"><div class="wfill" style="width:' + weight + '%"></div></div><div class="wlbl">' + weight + '%</div></div>'
      : '';
    return '<div class="pref-row">'
      + '<div class="pref-lbl">' + label + '</div>'
      + '<div class="pref-val' + (isAny ? ' any' : '') + '">' + icon + ' ' + (isAny ? 'No preference' : val) + '</div>'
      + bar + '</div>';
  };
  const doff = r.daysOff.length
    ? '<div class="doff-list">' + r.daysOff.map(fmtDate).join('<br>') + '</div>'
    : '<div class="doff-none">None declared</div>';
  document.getElementById('prefs').innerHTML =
    '<div class="prefs-title">&#9881;&#65039; Preferences for ' + cap(r.name) + '</div>'
    + row('&#127968;', 'Location', r.locPref, r.locPref === 'ANY', r.locWeight)
    + '<hr class="divider">'
    + row('&#9728;&#65039;', 'Time of Day', r.typePref, r.typePref === 'ANY', r.typeWeight)
    + '<hr class="divider">'
    + row('&#128197;', 'Preferred Streak', r.daysPref + ' days in a row', false, r.daysWeight)
    + '<hr class="divider">'
    + '<div class="pref-row"><div class="pref-lbl">&#128683; Days Off</div>' + doff + '</div>';
}

/* ── Week View ── */
function renderWeek() {
  const orig = new Set(DATA.originalAssignment[cur] || []);
  const final = new Set(DATA.finalAssignment[cur] || []);
  const gives = new Set((DATA.swaps[cur] || []).map(s => s.giveUid));
  const recvs = new Set((DATA.swaps[cur] || []).map(s => s.recvUid));
  const all = new Set([...orig, ...final]);

  const dm = {};
  all.forEach(uid => {
    const s = DATA.shifts[uid];
    if (!s) return;
    const k = s.workDate;
    if (!dm[k]) dm[k] = [];
    let st = 'keep';
    if (gives.has(uid)) st = 'give';
    else if (recvs.has(uid)) st = 'recv';
    dm[k].push({ s, st });
  });

  const monday = addDays(anchorMonday, weekOffset * 7);
  const sunday = addDays(monday, 6);
  const todayIso = new Date().toISOString().slice(0,10);

  // Update week label
  const moIso = dateToIso(monday);
  const suIso = dateToIso(sunday);
  const [my, mm, md] = moIso.split('-').map(Number);
  const [sy, sm, sd] = suIso.split('-').map(Number);
  const weekLbl = MONTHS[mm-1].slice(0,3) + ' ' + md
    + (mm !== sm ? ' – ' + MONTHS[sm-1].slice(0,3) + ' ' + sd : ' – ' + sd)
    + ', ' + my;
  document.getElementById('week-label').textContent = weekLbl;

  let hdrs = '';
  let cols = '';
  for (let i = 0; i < 7; i++) {
    const day = addDays(monday, i);
    const iso = dateToIso(day);
    const isToday = iso === todayIso;
    const dow = DOWS_SHORT[day.getDay()];
    const dateNum = day.getDate();

    hdrs += '<div class="week-col-hdr' + (isToday ? ' today' : '') + '">'
      + '<div class="wch-dow' + (isToday ? ' today-txt' : '') + '">' + dow + '</div>'
      + '<div class="wch-date' + (isToday ? ' today-txt' : '') + '">' + dateNum + '</div>'
      + '</div>';

    const entries = dm[iso] || [];
    let blocks = '';
    if (!entries.length) {
      blocks = '<div class="week-empty"><div class="week-empty-dot"></div></div>';
    } else {
      blocks = entries.map(({ s, st }) => {
        let cls = s.isJeopardy ? 'sb-jeop' : st === 'give' ? 'sb-give' : st === 'recv' ? 'sb-recv' : s.loc === 'MGH' ? 'sb-mgh' : 'sb-bwh';
        const locLabel = s.isJeopardy ? 'Jeopardy' : (s.loc || 'Unknown');
        const badge = st === 'give'
          ? '<span class="sb-badge badge-give">&#8593; Giving Away</span>'
          : st === 'recv'
          ? '<span class="sb-badge badge-recv">&#8595; Received</span>'
          : '';
        return '<div class="shift-block ' + cls + '" title="' + s.summary + '">'
          + '<div class="sb-loc">' + locLabel + (s.type ? ' · ' + s.type : '') + '</div>'
          + '<div class="sb-time">' + s.startFmt + '<br>' + s.endFmt + '</div>'
          + badge
          + '</div>';
      }).join('');
    }

    cols += '<div class="week-col-body' + (isToday ? ' today-col' : '') + '">' + blocks + '</div>';
  }

  document.getElementById('week-view').innerHTML =
    '<div class="week-grid">' + hdrs + cols + '</div>';
}

/* ── Swap Cards ── */
function renderSwaps() {
  const list = DATA.swaps[cur] || [];
  const grid = document.getElementById('swaps-grid');
  document.getElementById('swap-count').textContent = list.length;

  if (!list.length) {
    grid.innerHTML = '<div class="no-swaps">'
      + '<div class="no-swaps-emoji">&#127881;</div>'
      + '<div class="no-swaps-msg">Already optimized!</div>'
      + '<div class="no-swaps-sub">No swaps proposed for ' + cap(cur) + ' — schedule is already great.</div>'
      + '</div>';
    return;
  }

  grid.innerHTML = list.map((sw, i) => {
    const pct = (sw.delta * 100).toFixed(1);
    const isPos = sw.delta > 0.0001;
    const isNeg = sw.delta < -0.0001;
    const deltaLabel = isPos ? '+' + pct + '% &#127881;' : isNeg ? pct + '%' : 'Neutral';
    const dpClass = isPos ? 'dp-pos' : isNeg ? 'dp-neg' : 'dp-neu';
    const cardClass = isPos ? 'pos-card' : isNeg ? 'neg-card' : 'neu-card';
    const hdrClass = isPos ? 'pos' : isNeg ? 'neg' : 'neu';
    const partnerName = sw.swapWith ? cap(sw.swapWith) : 'Partner';

    return '<div class="swap-card ' + cardClass + '">'
      + '<div class="card-hdr ' + hdrClass + '">'
      + '<div class="card-hdr-left">'
      + '<div class="card-hdr-title">Swap ' + (i+1) + '</div>'
      + '<div class="swap-with-badge">&#8644; with <span class="partner-name">' + partnerName + '</span></div>'
      + '</div>'
      + '<span class="delta-pill ' + dpClass + '">' + deltaLabel + '</span>'
      + '</div>'
      + '<div class="card-body">'
      + blk(sw, 'give')
      + '<div class="arrow-col"><div class="arrow-icon">&#8594;</div></div>'
      + blk(sw, 'recv')
      + '</div></div>';
  }).join('');
}

function blk(sw, side) {
  const p = side === 'give' ? 'give' : 'recv';
  const label = side === 'give' ? '&#8593; Giving Away' : '&#8595; Receiving';
  const loc = sw[p + 'Loc'];
  const type = sw[p + 'Type'];
  const lcls = loc === 'MGH' ? 'lt-mgh' : loc === 'BWH' ? 'lt-bwh' : 'lt-none';
  const lbl = loc || 'Jeopardy';
  return '<div class="shift-blk ' + side + '">'
    + '<div class="blk-lbl">' + label + '</div>'
    + '<div class="blk-summary">' + sw[p + 'Summary'] + '</div>'
    + '<div class="blk-meta">'
    + fmtShort(sw[p + 'Date']) + '<br>'
    + sw[p + 'Start'] + ' &ndash; ' + sw[p + 'End']
    + '</div>'
    + '<span class="loc-tag ' + lcls + '">' + lbl + (type ? ' &middot; ' + type : '') + '</span>'
    + '</div>';
}

init();
</script>
</body>
</html>
"""
