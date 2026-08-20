"""
Disciplined Edge — ML service entrypoint.

    cd services/ml
    uvicorn app.main:app --reload --port 8000

GET  /          -> preview page: prediction card + market-movers board
GET  /health
GET  /docs
GET  /movers    -> top 5 gainers/losers (today & weekly), NASDAQ & SGX, cached
POST /predict
"""

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.routers import predict

app = FastAPI(title="Disciplined Edge ML", version="0.1.0")
app.include_router(predict.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ════════════════════════════════════════════════════════════════════
#  MARKET MOVERS — top 5 gainers / losers among a tracked universe.
#  HONEST SCOPE: this ranks movers WITHIN these tracked names, NOT the
#  entire exchange. Pure price movement — nothing to do with the model.
#  Dead/unknown tickers are skipped, not crashed on.
# ════════════════════════════════════════════════════════════════════
NASDAQ_UNIVERSE = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "GOOGL": "Alphabet", "META": "Meta", "AVGO": "Broadcom", "TSLA": "Tesla",
    "AMD": "AMD", "INTC": "Intel", "QCOM": "Qualcomm", "MU": "Micron",
    "AMAT": "Applied Materials", "ASML": "ASML", "ADBE": "Adobe", "CRM": "Salesforce",
    "NFLX": "Netflix", "CSCO": "Cisco", "INTU": "Intuit", "PYPL": "PayPal",
    "PEP": "PepsiCo", "COST": "Costco", "TMUS": "T-Mobile", "AMGN": "Amgen",
    "GILD": "Gilead", "SBUX": "Starbucks", "MDLZ": "Mondelez", "ABNB": "Airbnb",
    "PLTR": "Palantir", "IONQ": "IonQ",
}
SGX_UNIVERSE = {
    "D05.SI": "DBS", "O39.SI": "OCBC", "U11.SI": "UOB", "Z74.SI": "Singtel",
    "C6L.SI": "SIA", "C38U.SI": "CapitaLand Int. Comm.", "A17U.SI": "Ascendas REIT",
    "J69U.SI": "Frasers Cpt Trust", "BN4.SI": "Keppel", "F34.SI": "Wilmar",
    "C07.SI": "Jardine C&C", "U96.SI": "Sembcorp", "S58.SI": "SATS",
    "G13.SI": "Genting Sing", "Y92.SI": "Thai Beverage", "BS6.SI": "Yangzijiang",
    "S63.SI": "ST Engineering", "C09.SI": "City Developments", "S68.SI": "SGX",
    "M44U.SI": "Mapletree Log", "H78.SI": "Hongkong Land", "BUOU.SI": "Frasers L&C",
}

_MOVERS_CACHE: dict = {}


def _compute_movers(universe: dict) -> dict:
    import yfinance as yf
    import pandas as pd

    syms = list(universe.keys())
    raw = yf.download(syms, period="1mo", auto_adjust=True, progress=False)
    if raw is None or raw.empty:
        raise HTTPException(503, detail={"error": "data_unavailable",
                            "detail": "Could not fetch market data. Try refresh."})
    closes = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw

    rows, skipped = [], []
    for sym in syms:
        try:
            s = closes[sym].dropna()
        except Exception:
            skipped.append(sym); continue
        if len(s) < 2:
            skipped.append(sym); continue
        last = float(s.iloc[-1])
        today = (s.iloc[-1] / s.iloc[-2] - 1) * 100
        weekly = (s.iloc[-1] / s.iloc[-6] - 1) * 100 if len(s) >= 6 else None
        rows.append({
            "symbol": sym, "name": universe[sym], "last": round(last, 2),
            "today": round(float(today), 2),
            "weekly": round(float(weekly), 2) if weekly is not None else None,
        })

    def top(key, reverse):
        valid = [r for r in rows if r[key] is not None]
        return sorted(valid, key=lambda r: r[key], reverse=reverse)[:5]

    return {
        "today":  {"gainers": top("today", True),  "losers": top("today", False)},
        "weekly": {"gainers": top("weekly", True), "losers": top("weekly", False)},
        "skipped": skipped,
        "tracked": len(rows),
    }


@app.get("/movers")
def movers(refresh: bool = False) -> dict:
    if refresh or "data" not in _MOVERS_CACHE:
        nasdaq = _compute_movers(NASDAQ_UNIVERSE)
        sgx = _compute_movers(SGX_UNIVERSE)
        _MOVERS_CACHE["data"] = {
            "nasdaq": nasdaq, "sgx": sgx,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
    return _MOVERS_CACHE["data"]



# ════════════════════════════════════════════════════════════════════
#  HONEST AI ANALYST — explains the data's verdict; never advises trades.
#  The MATH decides the verdict (from IC); the LLM only narrates it.
#  Needs ANTHROPIC_API_KEY in the environment; without it, falls back to
#  a rule-based honest explanation so the app still works.
# ════════════════════════════════════════════════════════════════════
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    symbol: str
    ic: float
    dir_acc: float
    pred_ret: float
    prob_up: float
    ctrl_ok: bool = True


def _analyst_verdict(ic, dir_acc, ctrl_ok):
    if not ctrl_ok:
        return ("unreliable", "The validation control failed — the IC may be "
                "contaminated, so no conclusion can be trusted.")
    if abs(ic) <= NOISE_BAND_A:
        return ("no_edge", "No demonstrated edge: the information coefficient is "
                "in the noise zone, consistent with random chance.")
    if ic < 0:
        return ("negative", "Negative edge in testing — the model did worse than a "
                "coin flip out-of-sample.")
    return ("weak_positive", "A weak positive signal that is unproven against costs "
            "and across more tickers — not actionable.")


def _analyst_rule_based(req, code, summary):
    # Plain-English: define the two numbers, say what they mean, then the
    # honest "what should I do" — which, for near-zero signal, is "nothing".
    ic_txt = (f"The 'information coefficient' (IC) is {req.ic:+.3f}. Think of it as "
              "a grade from -1 to +1 for how well the model's guesses line up with "
              "what the stock actually did next. 0 means no skill at all - pure luck. "
              "Anything close to 0 (roughly -0.02 to +0.02) is basically a coin toss.")
    da_txt = (f"'Direction accuracy' is {req.dir_acc*100:.0f}% - how often the model "
              "got the up-or-down call right. 50% is a coin flip.")
    if code in ("no_edge", "negative", "unreliable"):
        meaning = ("So for this stock, the model has shown no real ability to predict "
                   "tomorrow. The number it gives you is a guess with no proven skill "
                   "behind it.")
        action = ("What this means for action: there is nothing here to act on. The "
                  "honest 'financial action' is no action - this tool gives you no "
                  "reason to buy or sell. That sounds disappointing, but it is the "
                  "normal, expected answer: predicting tomorrow's price from public "
                  "data is something even professionals rarely manage.")
    else:
        meaning = ("So for this stock there is a faint hint of skill - but 'faint hint' "
                   "is not the same as 'reliable'. A single stock looking slightly "
                   "predictable is far more often luck than a real pattern.")
        action = ("What this means for action: still nothing to act on yet. Before this "
                  "hint could justify anything, it would have to keep working across "
                  "many stocks and survive trading fees. Treat it as something to "
                  "investigate, not a green light.")
    return f"For {req.symbol}: {ic_txt} {da_txt} {meaning} {action}"


NOISE_BAND_A = 0.02
_ANALYST_SYSTEM = (
    "You are Dr. Elena Marquez, a quantitative finance analyst with a calm, "
    "evidence-based, mentor-like voice, explaining a model's output to a user.\n"
    "ABSOLUTE RULES (never break):\n"
    "- No buy, sell, hold, or position advice. You are not a financial advisor.\n"
    "- Add no confidence the numbers don't support. The verdict you are given was "
    "computed from the data; only explain it, never revise it.\n"
    "- If the verdict is no-edge or negative, make clear the data gives no reliable "
    "reason to act; do not soften it into a trade suggestion.\n"
    "- 3-4 short plain-language sentences. End by noting what would be needed to "
    "trust any signal (walk-forward across tickers, surviving costs), not an action."
)


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    code, summary = _analyst_verdict(req.ic, req.dir_acc, req.ctrl_ok)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"verdict": code, "source": "rule-based",
                "analysis": _analyst_rule_based(req, code, summary)}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user_msg = (
            f"Stock: {req.symbol}\n"
            f"Information coefficient (out-of-sample): {req.ic:+.4f}\n"
            f"Direction accuracy: {req.dir_acc*100:.1f}%\n"
            f"Predicted next-day return: {req.pred_ret*100:+.2f}%\n"
            f"COMPUTED VERDICT (do not change): {code} - {summary}\n\n"
            "Explain this verdict in your voice, following all rules."
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=400,
            system=_ANALYST_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {"verdict": code, "source": "anthropic", "analysis": text.strip()}
    except Exception as e:
        return {"verdict": code, "source": f"fallback ({type(e).__name__})",
                "analysis": _analyst_rule_based(req, code, summary)}



# ════════════════════════════════════════════════════════════════════
#  CONFIDENCE SCAN ("fact check") — on-demand, cached.
#  Scans the tracked universe with WALK-FORWARD and classifies each stock
#  against a STRICT bar. Reuses predict.py's verified walk-forward so the
#  scan and the prediction card measure the same way.
#
#  Bar to PASS (all three): walk-forward IC > 0.05  AND  dir-acc > 52%
#  AND control IC near zero. Strict on purpose — easy-to-pass would lie.
#  Expect almost everything to land in "no edge". An empty pass-list is
#  the honest headline, not a failure.
# ════════════════════════════════════════════════════════════════════
SCAN_MIN_ROWS = 200
PASS_IC = 0.05
PASS_DACC = 0.52

_SCAN_CACHE: dict = {}


def _scan_one(symbol, name, exchange):
    import numpy as np, pandas as pd, yfinance as yf
    try:
        raw = yf.download(symbol, period="6y", auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return {"symbol": symbol, "name": name, "exchange": exchange,
                    "class": "unreliable", "reason": "no data"}
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        feats = predict._build_features(raw)
        target = raw["Close"].shift(-1) / raw["Close"] - 1.0
        data = feats.join(target.rename("y")).dropna().sort_index()
        if len(data) < SCAN_MIN_ROWS:
            return {"symbol": symbol, "name": name, "exchange": exchange,
                    "class": "unreliable", "reason": "too little history"}
        X = data[predict.FEATURES].to_numpy(); y = data["y"].to_numpy()
        ic, dacc, _ = predict._walk_forward(X, y)
        y_shuf = y.copy(); np.random.default_rng(0).shuffle(y_shuf)
        ctrl_ic, _, _ = predict._walk_forward(X, y_shuf)
        ctrl_ok = abs(ctrl_ic) <= predict.NOISE_BAND
        rec = {"symbol": symbol, "name": name, "exchange": exchange,
               "ic": round(ic, 4), "dir_acc": round(dacc, 4), "ctrl_ic": round(ctrl_ic, 4)}
        if not ctrl_ok:
            rec["class"] = "unreliable"; rec["reason"] = "control failed"
        elif ic > PASS_IC and dacc > PASS_DACC:
            rec["class"] = "passed"
        else:
            rec["class"] = "no_edge"
        return rec
    except Exception as e:
        return {"symbol": symbol, "name": name, "exchange": exchange,
                "class": "unreliable", "reason": type(e).__name__}


@app.get("/scan")
def scan(refresh: bool = False) -> dict:
    if refresh or "data" not in _SCAN_CACHE:
        results = []
        for sym, nm in NASDAQ_UNIVERSE.items():
            results.append(_scan_one(sym, nm, "NASDAQ"))
        for sym, nm in SGX_UNIVERSE.items():
            results.append(_scan_one(sym, nm, "SGX"))
        passed = [r for r in results if r["class"] == "passed"]
        unreliable = [r for r in results if r["class"] == "unreliable"]
        no_edge = [r for r in results if r["class"] == "no_edge"]
        _SCAN_CACHE["data"] = {
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "bar": f"IC > {PASS_IC} AND dir-acc > {int(PASS_DACC*100)}% AND control clean",
            "summary": {"passed": len(passed), "no_edge": len(no_edge),
                        "unreliable": len(unreliable), "total": len(results)},
            "passed": sorted(passed, key=lambda r: r["ic"], reverse=True),
            "unreliable": unreliable,
        }
    return _SCAN_CACHE["data"]


_PREVIEW_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Disciplined Edge</title>
<style>
  :root { --bg:#0f1420; --card:#1a2235; --ink:#e8edf7; --muted:#8b97ad;
          --accent:#5b8def; --band:#5b8def33; --band2:#5b8def66; --warn:#f0a85c;
          --up:#4cc38a; --down:#e5707e; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  .wrap { max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 17px; margin: 36px 0 4px; }
  .sub { color: var(--muted); font-size: 14px; margin: 0 0 20px; }
  .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; margin-bottom:20px; }
  label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
  input, select, button { font-size:14px; padding:9px 12px; border-radius:8px;
                   border:1px solid #2c3854; background:var(--card); color:var(--ink); }
  input { text-transform:uppercase; width:130px; }
  button { background:var(--accent); border:none; cursor:pointer; font-weight:600; }
  button:hover { filter:brightness(1.08); }
  button.ghost { background:transparent; border:1px solid #2c3854; font-weight:500; }
  button.ghost.on { background:#2c3854; }
  .card { background:var(--card); border:1px solid #2c3854; border-radius:14px; padding:22px; }
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
  /* movers */
  .mv-controls { display:flex; gap:8px; align-items:center; margin:10px 0 16px; }
  .panels { display:flex; gap:16px; flex-wrap:wrap; }
  .panel { background:var(--card); border:1px solid #2c3854; border-radius:14px;
           padding:16px 18px; flex:1; min-width:300px; }
  .panel h3 { margin:0 0 10px; font-size:15px; }
  .mv-sub { font-size:12px; color:var(--muted); margin:12px 0 6px; text-transform:uppercase; letter-spacing:.04em; }
  .mv-row { display:flex; justify-content:space-between; align-items:baseline;
            padding:6px 0; border-top:1px solid #232d44; font-size:14px; }
  .mv-row .nm { color:var(--ink); }
  .mv-row .tk { color:var(--muted); font-size:12px; margin-left:6px; }
  .mv-row .pc { font-weight:600; }
  .up { color:var(--up); } .down { color:var(--down); }
</style>
</head>
<body>
<div class="wrap">
  <h1>Disciplined Edge</h1>
  <p class="sub">Type any NASDAQ or SGX ticker (SGX uses codes like D05.SI).</p>

  <div class="controls">
    <div><label for="symbol">Ticker</label>
      <input id="symbol" value="ASML" maxlength="10" autocomplete="off" spellcheck="false" /></div>
    <div><label for="horizon">Horizon</label>
      <select id="horizon">
        <option value="1w" selected>Next-day</option>
        <option value="1m">1 month</option>
        <option value="3m">3 months</option>
        <option value="6m">6 months</option>
        <option value="1y">1 year</option>
      </select></div>
    <button id="go">Get prediction</button>
  </div>
  <div id="out" class="card" style="display:none"></div>
  <div id="loading" class="sub" style="display:none">Training model (walk-forward) &mdash; first view can take 1.5-3 min&hellip;</div>
  <button id="ask" style="margin-top:14px;display:none">Ask the analyst</button>
  <div id="analysis" class="card" style="display:none;margin-top:12px;border-color:#3a4a6e"></div>

  <h2>Market movers</h2>
  <p class="sub" style="margin-bottom:0">Top 5 up / down among tracked names &mdash; price movement only, not predictions. Not the whole exchange.</p>
  <div class="mv-controls">
    <button class="ghost on" id="tog-today">Today</button>
    <button class="ghost" id="tog-weekly">Weekly</button>
    <button id="refresh" style="margin-left:auto">Refresh</button>
  </div>
  <div class="panels">
    <div class="panel" id="panel-nasdaq"><h3>NASDAQ</h3><div class="mv-body sub">Loading&hellip;</div></div>
    <div class="panel" id="panel-sgx"><h3>SGX (Singapore)</h3><div class="mv-body sub">Loading&hellip;</div></div>
  </div>
  <p class="hint" id="mv-note"></p>

  <h2>Confidence check (fact-check)</h2>
  <p class="sub" style="margin-bottom:0">Which stocks clear a STRICT bar: walk-forward IC &gt; 0.05, direction accuracy &gt; 52%, and a clean control. Almost nothing should pass &mdash; that empty list is the honest answer.</p>
  <div class="mv-controls"><button id="scan-btn">Run confidence scan</button><span id="scan-status" class="sub" style="margin-left:12px"></span></div>
  <div id="scan-out" class="card" style="display:none"></div>
</div>

<script>
function money(n){ return Number(n).toLocaleString(undefined,{maximumFractionDigits:2}); }
function pct(v, lo, hi){ return ((v - lo) / (hi - lo)) * 100; }

/* ---- prediction card (unchanged behaviour) ---- */
async function getPrediction(){
  const symbol=(document.getElementById('symbol').value||'').trim().toUpperCase();
  const horizon=document.getElementById('horizon').value;
  const out=document.getElementById('out'), loading=document.getElementById('loading');
  if(!symbol){ out.innerHTML='<p class="err">Enter a ticker symbol.</p>'; out.style.display='block'; return; }
  out.style.display='none'; loading.style.display='block';
  try{
    const res=await fetch('/predict',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol,exchange:'NASDAQ',horizon})});
    loading.style.display='none';
    if(!res.ok){ const e=await res.json().catch(()=>({}));
      out.innerHTML='<p class="err">'+((e.detail&&e.detail.detail)||('Error '+res.status))+'</p>';
      out.style.display='block'; return; }
    const p=await res.json();
    const lo=p.intervals.ci95[0],hi=p.intervals.ci95[1];
    const i68lo=pct(p.intervals.ci68[0],lo,hi), i68w=pct(p.intervals.ci68[1],lo,hi)-i68lo, mk=pct(p.point_target,lo,hi);
    out.innerHTML=
      '<div class="stat"><div class="k">Base case ('+p.symbol+', '+p.horizon+')</div><div class="big">'+money(p.point_target)+'</div></div>'+
      '<div class="row"><div class="stat"><div class="k">Chance higher</div><div class="v">'+Math.round(p.prob_up*100)+'%</div></div>'+
      '<div class="stat"><div class="k">Forecast volatility</div><div class="v">'+(p.risk.vol_forecast*100).toFixed(1)+'%</div></div>'+
      '<div class="stat"><div class="k">Value at risk (95%)</div><div class="v">'+(p.risk.var_95*100).toFixed(1)+'%</div></div></div>'+
      '<div class="bandwrap"><div class="k" style="font-size:12px;color:var(--muted);margin-bottom:6px">Likely range &mdash; darker band = more likely (68%), full bar = 95%</div>'+
      '<div class="track"><div class="inner" style="left:'+i68lo+'%;width:'+i68w+'%"></div><div class="marker" style="left:'+mk+'%"></div></div>'+
      '<div class="ends"><span>'+money(lo)+'</span><span>'+money(hi)+'</span></div></div>'+
      '<div class="factors">'+p.factors.map(function(f){return '<div class="factor"><div class="name">'+f.factor+'</div><div class="exp">'+f.explanation+'</div></div>';}).join('')+'</div>';
    out.style.display='block';
    window._lastPred=p; document.getElementById('ask').style.display='inline-block';
    document.getElementById('analysis').style.display='none';
  }catch(err){ loading.style.display='none';
    out.innerHTML='<p class="err">Could not reach the server. Is uvicorn still running?</p>'; out.style.display='block'; }
}
document.getElementById('go').addEventListener('click',getPrediction);
document.getElementById('symbol').addEventListener('keydown',function(e){ if(e.key==='Enter') getPrediction(); });
async function askAnalyst(){
  const p=window._lastPred; if(!p) return;
  const a=document.getElementById('analysis');
  a.style.display='block'; a.innerHTML='<span class="sub">The analyst is reviewing the data&hellip;</span>';
  // ic = factor[0].contribution, pred_ret = factor[1].contribution, dir_acc = prob_up
  const ic=(p.factors[0]&&p.factors[0].contribution)||0;
  const pr=(p.factors[1]&&p.factors[1].contribution)||0;
  try{
    const res=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:p.symbol,ic:ic,dir_acc:p.prob_up,pred_ret:pr,prob_up:p.prob_up,ctrl_ok:true})});
    const d=await res.json();
    a.innerHTML='<div class="factor" style="border:none;padding:0"><div class="name">Dr. Elena Marquez &mdash; analysis</div>'+
      '<div class="exp" style="font-size:14px;margin-top:8px">'+d.analysis+'</div>'+
      '<div class="sub" style="margin-top:10px;font-size:11px">Source: '+d.source+'. Not financial advice.</div></div>';
  }catch(e){ a.innerHTML='<span class="err">Analyst unavailable. Is the server running?</span>'; }
}
document.getElementById('ask').addEventListener('click',askAnalyst);

/* ---- market movers ---- */
let MOVERS=null, PERIOD='today';
function moverRows(list){
  if(!list||!list.length) return '<div class="sub" style="padding:6px 0">No data.</div>';
  return list.map(function(m){
    const v=m[PERIOD]; if(v===null||v===undefined) return '';
    const cls=v>=0?'up':'down', sign=v>=0?'+':'';
    return '<div class="mv-row"><span><span class="nm">'+m.name+'</span><span class="tk">'+m.symbol+'</span></span>'+
           '<span class="pc '+cls+'">'+sign+v.toFixed(2)+'%</span></div>';
  }).join('');
}
function renderPanel(id, data){
  const el=document.querySelector('#'+id+' .mv-body');
  const g=data[PERIOD].gainers, l=data[PERIOD].losers;
  el.innerHTML='<div class="mv-sub up">Top gainers</div>'+moverRows(g)+
               '<div class="mv-sub down">Top losers</div>'+moverRows(l);
}
function renderMovers(){
  if(!MOVERS) return;
  renderPanel('panel-nasdaq', MOVERS.nasdaq);
  renderPanel('panel-sgx', MOVERS.sgx);
  const sk=(MOVERS.nasdaq.skipped||[]).concat(MOVERS.sgx.skipped||[]);
  document.getElementById('mv-note').innerHTML=
    'As of '+MOVERS.as_of+'. Tracking '+(MOVERS.nasdaq.tracked+MOVERS.sgx.tracked)+' names.'+
    (sk.length? ' Skipped (no data): '+sk.join(', ')+'.' : '');
}
async function loadMovers(refresh){
  document.querySelectorAll('.mv-body').forEach(function(e){ e.innerHTML='<div class="sub" style="padding:6px 0">Loading market data (first load ~1 min)&hellip;</div>'; });
  try{
    const res=await fetch('/movers'+(refresh?'?refresh=true':''));
    if(!res.ok){ throw new Error('status '+res.status); }
    MOVERS=await res.json(); renderMovers();
  }catch(err){
    document.querySelectorAll('.mv-body').forEach(function(e){ e.innerHTML='<div class="err" style="padding:6px 0">Could not load movers. Try Refresh.</div>'; });
  }
}
function setPeriod(p){
  PERIOD=p;
  document.getElementById('tog-today').classList.toggle('on', p==='today');
  document.getElementById('tog-weekly').classList.toggle('on', p==='weekly');
  renderMovers();
}
document.getElementById('tog-today').addEventListener('click',function(){ setPeriod('today'); });
document.getElementById('tog-weekly').addEventListener('click',function(){ setPeriod('weekly'); });
document.getElementById('refresh').addEventListener('click',function(){ loadMovers(true); });

async function runScan(){
  const status=document.getElementById('scan-status'), out=document.getElementById('scan-out');
  status.textContent='Scanning the whole universe with walk-forward — this takes a few minutes…';
  out.style.display='none';
  try{
    const res=await fetch('/scan');
    const d=await res.json();
    status.textContent='Done. As of '+d.as_of+'.';
    const s=d.summary;
    let html='<div class="big">'+s.passed+' of '+s.total+'</div>'+
      '<div class="sub">stocks cleared the bar ('+d.bar+')</div>'+
      '<div class="row" style="margin-top:10px">'+
      '<div class="stat"><div class="k">Passed</div><div class="v up">'+s.passed+'</div></div>'+
      '<div class="stat"><div class="k">No edge</div><div class="v">'+s.no_edge+'</div></div>'+
      '<div class="stat"><div class="k">Unreliable</div><div class="v down">'+s.unreliable+'</div></div></div>';
    if(s.passed===0){
      html+='<div class="factor"><div class="name">No stock cleared the bar.</div>'+
        '<div class="exp">This is the honest, expected result: by a rigorous standard, none of the tracked names is reliably predictable next-day right now. That is what an efficient market looks like.</div></div>';
    } else {
      html+='<div class="mv-sub up">Cleared the bar — worth investigating (not a buy signal)</div>';
      d.passed.forEach(function(r){
        html+='<div class="mv-row"><span><span class="nm">'+r.name+'</span><span class="tk">'+r.symbol+' · '+r.exchange+'</span></span>'+
          '<span class="pc up">IC '+r.ic.toFixed(3)+' · '+(r.dir_acc*100).toFixed(0)+'%</span></div>';
      });
      html+='<div class="exp" style="margin-top:10px;color:var(--muted)">Passing the bar means "investigate with proper backtesting and costs" — never "buy". A single pass is still more likely luck than edge.</div>';
    }
    if(d.unreliable.length){
      html+='<div class="mv-sub down">Unreliable / no data</div>';
      html+='<div class="exp" style="color:var(--muted)">'+d.unreliable.map(function(r){return r.symbol;}).join(', ')+'</div>';
    }
    out.innerHTML=html; out.style.display='block';
  }catch(e){ status.textContent='Scan failed — is the server running?'; }
}
document.getElementById('scan-btn').addEventListener('click',runScan);


/* initial load */
getPrediction();
loadMovers(false);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def preview() -> str:
    return _PREVIEW_PAGE