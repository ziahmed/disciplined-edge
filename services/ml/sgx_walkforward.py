# ════════════════════════════════════════════════════════════════════
#  SGX WALK-FORWARD TEST  — paste into a notebook cell and run.
#  Same verified harness as your NASDAQ four. Tests whether Singapore's
#  single-split ICs (0.04-0.10) survive honest 5-fold walk-forward, or
#  collapse toward zero like ASML's 0.083 did.
#
#  Needs: pip install yfinance xgboost scikit-learn pandas numpy
# ════════════════════════════════════════════════════════════════════
import numpy as np, pandas as pd, yfinance as yf
from xgboost import XGBRegressor

SGX = {
    "D05.SI": "DBS", "O39.SI": "OCBC", "U11.SI": "UOB",
    "Z74.SI": "Singtel", "C6L.SI": "SIA",
}
START, MIN_ROWS = "2020-01-01", 200
FEATURES = ["rsi_14","stoch_k","stoch_d","bb_pctb","macd_hist",
            "fib_dist_382","fib_dist_500","fib_dist_618",
            "hist_vol_20","hist_vol_60","dow","month","quarter"]

def _rsi(c,n=14):
    d=c.diff(); g=d.clip(lower=0).rolling(n).mean(); l=(-d.clip(upper=0)).rolling(n).mean()
    return 100-100/(1+g/l.replace(0,np.nan))
def _stoch(h,l,c,n=14):
    ll,hh=l.rolling(n).min(),h.rolling(n).max(); return 100*(c-ll)/(hh-ll).replace(0,np.nan)

def build_features(df):
    c,h,l=df["Close"],df["High"],df["Low"]; out=pd.DataFrame(index=df.index)
    out["rsi_14"]=_rsi(c); out["stoch_k"]=_stoch(h,l,c); out["stoch_d"]=out["stoch_k"].rolling(3).mean()
    mid,sd=c.rolling(20).mean(),c.rolling(20).std(); up,lo=mid+2*sd,mid-2*sd
    out["bb_pctb"]=(c-lo)/(up-lo).replace(0,np.nan)
    macd=c.ewm(span=12).mean()-c.ewm(span=26).mean(); out["macd_hist"]=macd-macd.ewm(span=9).mean()
    hi,low=h.rolling(60).max(),l.rolling(60).min(); rng=(hi-low).replace(0,np.nan)
    for lvl in (0.382,0.5,0.618): out[f"fib_dist_{int(lvl*1000)}"]=(c-(hi-lvl*rng))/c
    ret=c.pct_change(); out["hist_vol_20"]=ret.rolling(20).std()*np.sqrt(252)
    out["hist_vol_60"]=ret.rolling(60).std()*np.sqrt(252)
    out["dow"]=df.index.dayofweek; out["month"]=df.index.month; out["quarter"]=df.index.quarter
    return out

def make_model():
    return XGBRegressor(n_estimators=300,max_depth=4,learning_rate=0.05,
                        subsample=0.8,colsample_bytree=0.8,n_jobs=-1)

def ic_(p,a):
    p,a=pd.Series(p),pd.Series(a); m=p.notna()&a.notna()
    return float(p[m].corr(a[m],method="spearman")) if m.sum()>=3 else 0.0
def dacc_(p,a):
    p,a=np.sign(np.asarray(p)),np.sign(np.asarray(a)); m=~(np.isnan(p)|np.isnan(a))
    return float((p[m]==a[m]).mean()) if m.sum() else 0.0

def walk_forward(X,y,n_splits=5):
    n=len(X); fold=n//(n_splits+1)
    if n<n_splits+2: raise ValueError("not enough rows")
    preds,actuals=[],[]
    for k in range(1,n_splits+1):
        tr,te=fold*k,fold*(k+1)
        m=make_model(); m.fit(X[:tr],y[:tr])
        preds.extend(m.predict(X[tr:te]).tolist()); actuals.extend(y[tr:te].tolist())
    return ic_(np.array(preds),np.array(actuals)), dacc_(np.array(preds),np.array(actuals)), len(preds)

rng=np.random.default_rng(0)
print(f"{'stock':<9}{'rows':>6}{'ctrl_IC':>10}{'REAL_IC':>10}{'dir_acc':>9}")
print("-"*44)
real_ics=[]
for sym,name in SGX.items():
    raw=yf.download(sym,start=START,auto_adjust=False,progress=False)
    if raw is None or raw.empty:
        print(f"{name:<9}  -- no data"); continue
    if isinstance(raw.columns,pd.MultiIndex): raw.columns=raw.columns.get_level_values(0)
    feats=build_features(raw); tgt=raw["Close"].shift(-1)/raw["Close"]-1.0
    data=feats.join(tgt.rename("y")).dropna().sort_index()
    if len(data)<MIN_ROWS: print(f"{name:<9}  -- too few rows"); continue
    assert data.index.is_monotonic_increasing
    X,y=data[FEATURES].to_numpy(),data["y"].to_numpy()
    y_shuf=y.copy(); rng.shuffle(y_shuf)
    cic,_,_=walk_forward(X,y_shuf)              # control: must be ~0
    ric,rda,n=walk_forward(X,y)                 # real
    real_ics.append(ric)
    print(f"{name:<9}{len(data):>6}{cic:>10.4f}{ric:>10.4f}{rda:>9.4f}")
print("-"*44)
if real_ics:
    print(f"mean REAL IC: {np.mean(real_ics):+.4f}   spread: {min(real_ics):+.4f} .. {max(real_ics):+.4f}")
print("\nCompare to the single-split web numbers (0.04-0.10). If walk-forward")
print("collapses these toward zero, Singapore behaves like NASDAQ: no edge.")