"""
Disciplined Edge — ML service entrypoint.

Run locally:
    cd services/ml
    uvicorn app.main:app --reload --port 8000

Endpoints:
    GET  /          -> a small preview page that renders a prediction (dev convenience)
    GET  /health    -> {"status": "ok"}
    GET  /docs      -> interactive API docs (auto-generated)
    POST /predict   -> the prediction contract (see docs/api-contract.md)

NOTE: the page served at "/" is a lightweight DEV PREVIEW so you can see a
prediction in the browser without running the full Next.js frontend. The real
frontend lives in apps/web. This preview is fine to delete later.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.routers import predict

app = FastAPI(title="Disciplined Edge ML", version="0.1.0")
app.include_router(predict.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── Dev preview page ─────────────────────────────────────────────────
# Pure HTML/CSS/JS, no external libraries — served from the same origin as
# /predict, so there are no CORS issues and nothing extra to install.
_PREVIEW_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Disciplined Edge — Prediction Preview</title>
<style>
  :root { --bg:#0f1420; --card:#1a2235; --ink:#e8edf7; --muted:#8b97ad;
          --accent:#5b8def; --band:#5b8def33; --band2:#5b8def66; --warn:#f0a85c; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  .wrap { max-width: 680px; margin: 0 auto; padding: 32px 20px 64px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 14px; margin: 0 0 24px; }
  .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; margin-bottom:20px; }
  label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
  select, button { font-size:14px; padding:9px 12px; border-radius:8px; border:1px solid #2c3854;
                   background:var(--card); color:var(--ink); }
  button { background:var(--accent); border:none; cursor:pointer; font-weight:600; }
  button:hover { filter:brightness(1.08); }
  .card { background:var(--card); border:1px solid #2c3854; border-radius:14px; padding:22px; }
  .badge { display:inline-block; font-size:11px; color:#0f1420; background:var(--warn);
           padding:3px 8px; border-radius:999px; font-weight:700; margin-bottom:16px; }
  .big { font-size:34px; font-weight:700; margin:2px 0; }
  .row { display:flex; gap:24px; flex-wrap:wrap; margin-top:8px; }
  .stat .k { font-size:12px; color:var(--muted); }
  .stat .v { font-size:18px; font-weight:600; }
  .bandwrap { margin:26px 0 8px; }
  .track { position:relative; height:46px; border-radius:8px; background:var(--band); }
  .inner { position:absolute; top:0; bottom:0; background:var(--band2); border-radius:6px; }
  .marker { position:absolute; top:-6px; bottom:-6px; width:3px; background:var(--ink); }
  .ends { display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-top:6px; }
  .factors { margin-top:20px; }
  .factor { border-top:1px solid #2c3854; padding:12px 0; }
  .factor .name { font-weight:600; font-size:14px; }
  .factor .exp { color:var(--muted); font-size:13px; margin-top:3px; }
  .err { color:#f08c8c; }
  .hint { color:var(--muted); font-size:12px; margin-top:18px; line-height:1.5; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Disciplined Edge</h1>
  <p class="sub">Prediction preview &mdash; live from your local ML service.</p>

  <div class="controls">
    <div>
      <label for="symbol">Stock</label>
      <select id="symbol">
        <option value="ASML">ASML</option>
        <option value="TSLA">TSLA (Tesla)</option>
        <option value="INTC">INTC (Intel)</option>
        <option value="IONQ">IONQ</option>
        <option value="SLV">SLV (silver ETF)</option>
      </select>
    </div>
    <div>
      <label for="horizon">Horizon</label>
      <select id="horizon">
        <option value="1w">1 week</option>
        <option value="1m" selected>1 month</option>
        <option value="3m">3 months</option>
        <option value="6m">6 months</option>
        <option value="1y">1 year</option>
      </select>
    </div>
    <button id="go">Get prediction</button>
  </div>

  <div id="out" class="card" style="display:none"></div>
  <div id="loading" class="sub" style="display:none">Asking the model&hellip;</div>

  <p class="hint">
    The numbers are a <strong>placeholder model</strong> for now (note the
    "stub" badge). It proves the page, the server, and the data flow all work.
    Wiring in your real NASDAQ model is the next step &mdash; the page won't change,
    only the numbers will become real.
  </p>
</div>

<script>
function money(n){ return Number(n).toLocaleString(undefined,{maximumFractionDigits:2}); }
function pct(v, lo, hi){ return ((v - lo) / (hi - lo)) * 100; }

async function getPrediction(){
  const symbol = document.getElementById('symbol').value;
  const horizon = document.getElementById('horizon').value;
  const out = document.getElementById('out');
  const loading = document.getElementById('loading');
  out.style.display = 'none';
  loading.style.display = 'block';

  try {
    const res = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, exchange: 'NASDAQ', horizon })
    });
    loading.style.display = 'none';
    if (!res.ok) {
      const e = await res.json().catch(()=>({}));
      out.innerHTML = '<p class="err">Error: ' + (e.detail?.detail || res.status) + '</p>';
      out.style.display = 'block';
      return;
    }
    const p = await res.json();
    const lo = p.intervals.ci95[0], hi = p.intervals.ci95[1];
    const i68lo = pct(p.intervals.ci68[0], lo, hi);
    const i68w  = pct(p.intervals.ci68[1], lo, hi) - i68lo;
    const mk    = pct(p.point_target, lo, hi);
    const isStub = (p.model_version || '').includes('stub');

    out.innerHTML =
      (isStub ? '<span class="badge">PLACEHOLDER MODEL</span><br>' : '') +
      '<div class="stat"><div class="k">Base case ('+p.symbol+', '+p.horizon+')</div>' +
      '<div class="big">'+money(p.point_target)+'</div></div>' +
      '<div class="row">' +
        '<div class="stat"><div class="k">Chance higher</div><div class="v">'+Math.round(p.prob_up*100)+'%</div></div>' +
        '<div class="stat"><div class="k">Forecast volatility</div><div class="v">'+(p.risk.vol_forecast*100).toFixed(1)+'%</div></div>' +
        '<div class="stat"><div class="k">Value at risk (95%)</div><div class="v">'+(p.risk.var_95*100).toFixed(1)+'%</div></div>' +
      '</div>' +
      '<div class="bandwrap"><div class="k" style="font-size:12px;color:var(--muted);margin-bottom:6px">' +
        'Likely range &mdash; darker band = more likely (68%), full bar = 95%</div>' +
        '<div class="track"><div class="inner" style="left:'+i68lo+'%;width:'+i68w+'%"></div>' +
        '<div class="marker" style="left:'+mk+'%"></div></div>' +
        '<div class="ends"><span>'+money(lo)+'</span><span>'+money(hi)+'</span></div></div>' +
      '<div class="row">' +
        '<div class="stat"><div class="k">Bear</div><div class="v">'+money(p.scenarios.bear)+'</div></div>' +
        '<div class="stat"><div class="k">Base</div><div class="v">'+money(p.scenarios.base)+'</div></div>' +
        '<div class="stat"><div class="k">Bull</div><div class="v">'+money(p.scenarios.bull)+'</div></div>' +
      '</div>' +
      '<div class="factors">' + p.factors.map(function(f){
        return '<div class="factor"><div class="name">'+f.factor+'</div>' +
               '<div class="exp">'+f.explanation+'</div></div>';
      }).join('') + '</div>';
    out.style.display = 'block';
  } catch (err) {
    loading.style.display = 'none';
    out.innerHTML = '<p class="err">Could not reach the server. Is uvicorn still running?</p>';
    out.style.display = 'block';
  }
}

document.getElementById('go').addEventListener('click', getPrediction);
getPrediction(); // load one on first paint
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def preview() -> str:
    return _PREVIEW_PAGE
