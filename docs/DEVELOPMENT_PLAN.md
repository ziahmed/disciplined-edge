# Development Plan — "Disciplined Edge"

An intelligent stock-prediction and portfolio-management app for **STI (Singapore Exchange)** and **NASDAQ** stocks, fronted by the AI persona **Dr. Elena Marquez**.

> **Name choice.** Of the candidates in the brief, I recommend **Disciplined Edge**. It matches the core value ("Markets reward discipline, not prediction") and the non-hype, evidence-based tone. "Quantum Portfolio" sounds like a returns promise, which works against the trust positioning. The other names stay available as taglines.

> **Responsible-product note.** This is a decision-support tool, not advice. Every prediction surface shows probabilities and confidence intervals, never guarantees, and carries a "not financial advice" disclaimer. This constraint shapes the schema (we store confidence intervals and driving factors, not just a point price) and the UI copy.

---

## 1. Tech Stack Decision

The brief names a stack; below is the concrete version with the *why* and the tradeoff, so you can defend each choice.

### Recommended stack

| Layer | Choice | Why this over the alternative |
|---|---|---|
| **Monorepo tooling** | Turborepo + pnpm workspaces | Mobile, web, and backend share types and validation. One repo keeps a price-target shape from drifting between client and server. |
| **Mobile** | React Native via **Expo** (dev builds + EAS) | Expo dev builds support native modules (biometrics, secure storage) without ejecting. Faster than bare RN for an MVP. |
| **Web** | **Next.js** (App Router, TypeScript, React Server Components) | SSR for fast first paint on dashboards; API routes act as a thin BFF if needed. |
| **Core API** | **NestJS** (Node + TypeScript) | Opinionated structure (modules, DI, guards) fits a fintech domain with auth, portfolios, alerts. Fastify under the hood for speed. |
| **ML service** | **FastAPI** (Python) | Keeps Python ML (PyTorch, XGBoost, SHAP) in its native ecosystem. **Your existing NASDAQ notebook becomes this service's seed.** Separated from the Node API so model work and app work scale independently. |
| **Primary DB** | **PostgreSQL** | Relational core: users, portfolios, holdings, predictions. ACID matters when money is represented. |
| **Time-series** | **TimescaleDB** (Postgres extension) | OHLCV bars are append-heavy time-series. A hypertable handles millions of rows and time-bucketed queries far better than vanilla Postgres, while staying in the same database. |
| **Cache / queue** | **Redis** | Cache fresh predictions, dedupe data-provider calls, back the alert/digest job queue (BullMQ). |
| **ML models** | **PyTorch** (LSTM/Transformer), **XGBoost** (baseline, already in your notebook), **statsmodels** (factor models) | Ensemble per the brief. The model factory pattern (`make_model()`) you already have stays the swap point. |
| **Explainability** | **SHAP** | Required by the brief; turns model output into the plain-English "key driving factors." |
| **Auth + biometrics** | **Clerk** (or Supabase Auth) for identity; **expo-local-authentication** for device biometric gating | Managed identity gets you to MVP fast with MFA and session security handled. Biometrics live on-device and gate access to an already-authenticated session. |
| **Charts** | **Recharts** (web), **Victory Native / react-native-skia** (mobile) | Interactive confidence-band charts on both platforms. |
| **Data sources** | Polygon.io + Alpha Vantage (US/NASDAQ), **SGX** feed (STI), **FRED** (macro), a news API (sentiment) | yfinance is fine for prototyping/backfill; move price ingestion to a paid feed before launch for reliability and terms-of-use. |
| **Deployment** | Vercel (web), EAS (mobile builds), AWS ECS/Fargate or Render (API + ML), managed Postgres (RDS/Neon/Supabase) | Start managed; revisit only if cost or latency demands it. |
| **Observability** | Sentry (errors), OpenTelemetry → a managed backend (traces), structured logs | Needed early — a wrong prediction surfaced to a user is a trust event you must be able to trace. |

### Decisions worth flagging early
- **Two backends, on purpose.** Node API owns the app domain; Python owns ML. They talk over an internal REST/gRPC contract. Don't merge them — mixing request-serving and model-serving creates deploy coupling you'll regret.
- **TimescaleDB vs. a separate TSDB (InfluxDB).** Staying inside Postgres means one backup story, one connection pool, JOINs between fundamentals and price history. Choose a separate TSDB only if ingestion volume outgrows a single Postgres node — unlikely at MVP.
- **Managed auth vs. roll-your-own.** For a finance app, roll-your-own auth is a liability surface you don't want during MVP. Use a provider; own the *authorization* (who can see which portfolio) in your API.

---

## 2. Folder Structure

A Turborepo monorepo. The ML service is a first-class member, and your notebook lives inside it.

```
disciplined-edge/
├── apps/
│   ├── mobile/                 # React Native (Expo)
│   │   ├── app/                # expo-router screens
│   │   ├── components/
│   │   ├── features/           # onboarding, dashboard, prediction, alerts
│   │   ├── lib/                # api client, secure storage, biometrics
│   │   └── app.config.ts
│   ├── web/                    # Next.js (App Router)
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   └── lib/
│   └── api/                    # NestJS core backend
│       ├── src/
│       │   ├── modules/
│       │   │   ├── auth/
│       │   │   ├── users/
│       │   │   ├── portfolios/
│       │   │   ├── watchlists/
│       │   │   ├── predictions/    # proxies + caches the ML service
│       │   │   ├── alerts/
│       │   │   ├── macro/
│       │   │   └── digests/
│       │   ├── common/             # guards, interceptors, pipes
│       │   └── main.ts
│       └── test/
│
├── services/
│   └── ml/                     # FastAPI ML service  ← your notebook grows up here
│       ├── app/
│       │   ├── main.py
│       │   ├── routers/        # /predict, /forecast, /explain, /backtest
│       │   ├── features/       # engineer_features() from the notebook
│       │   ├── data/           # providers (polygon, sgx, fred, yfinance), ingestion
│       │   ├── models/         # make_model(): xgb | lstm | tft factory
│       │   ├── validation/     # walk_forward(), sharpe(), IC, cost_aware_pnl()
│       │   └── explain/        # SHAP wrappers
│       ├── notebooks/
│       │   └── US_MultiStock_Advanced_NASDAQ.ipynb   # your research artifact
│       ├── artifacts/          # trained model files (git-ignored; stored in S3)
│       └── tests/
│
├── packages/
│   ├── types/                  # shared TS types + zod schemas (Prediction, Holding…)
│   ├── ui/                     # shared design tokens, primitives
│   ├── api-client/             # generated typed client for web + mobile
│   └── config/                 # eslint, tsconfig, prettier
│
├── infra/
│   ├── docker/                 # Dockerfiles per service
│   ├── migrations/             # SQL migrations (or Prisma)
│   └── ci/                     # GitHub Actions
│
├── docs/
│   ├── DEVELOPMENT_PLAN.md
│   ├── api-contract.md         # Node ↔ Python contract
│   └── compliance.md           # disclaimers, data-use, retention
│
├── turbo.json
├── pnpm-workspace.yaml
└── package.json
```

**Key idea:** the prediction *shape* (price target, 68%/95% bands, scenario cases, driving factors) is defined once in `packages/types` and reused by mobile, web, and the Node API. The Python service validates against the same contract (`docs/api-contract.md`). This is what keeps Dr. Elena saying the same thing everywhere.

---

## 3. Database Schema

PostgreSQL with the TimescaleDB extension. Below is MVP-shaped DDL — concrete enough to migrate, lean enough to evolve. Money is stored as `numeric`, never `float`.

```sql
-- ── Identity & profile ───────────────────────────────────────────────
CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_provider_id text UNIQUE NOT NULL,      -- Clerk/Supabase subject id
    email           citext UNIQUE NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    biometric_enabled boolean NOT NULL DEFAULT false
);

CREATE TABLE profiles (
    user_id         uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    display_name    text,
    base_currency   text NOT NULL DEFAULT 'SGD',     -- SGD or USD
    risk_tolerance  text CHECK (risk_tolerance IN ('conservative','balanced','growth','aggressive')),
    active_persona  text NOT NULL DEFAULT 'elena'    -- elena | kai | ava
        CHECK (active_persona IN ('elena','kai','ava')),
    onboarding_complete boolean NOT NULL DEFAULT false
);

CREATE TABLE goals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label       text NOT NULL,                  -- "Retirement target", "Short-term alpha"
    horizon     text NOT NULL,                  -- 1w | 1m | 3m | 6m | 1y | long
    target_amount numeric(18,2),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Instruments & market data ────────────────────────────────────────
CREATE TABLE securities (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      text NOT NULL,                  -- AAPL, D05.SI
    exchange    text NOT NULL,                  -- NASDAQ | SGX
    name        text,
    sector      text,
    industry    text,
    asset_type  text NOT NULL DEFAULT 'equity', -- equity | etf
    currency    text NOT NULL,
    UNIQUE (symbol, exchange)
);

-- Fundamentals snapshot (slow-moving; refreshed daily).
CREATE TABLE security_fundamentals (
    security_id uuid NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    as_of       date NOT NULL,
    market_cap  numeric(20,2),
    eps         numeric(12,4),
    pe          numeric(12,4),
    pb          numeric(12,4),
    peg         numeric(12,4),
    debt_equity numeric(12,4),
    roe         numeric(12,4),
    rev_growth  numeric(12,4),
    ebitda      numeric(20,2),
    div_yield   numeric(8,4),
    beta        numeric(8,4),
    float_shares numeric(20,0),
    PRIMARY KEY (security_id, as_of)
);

-- Time-series price bars → TimescaleDB hypertable.
CREATE TABLE price_bars (
    security_id uuid NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    ts          timestamptz NOT NULL,
    open        numeric(18,6),
    high        numeric(18,6),
    low         numeric(18,6),
    close       numeric(18,6),
    adj_close   numeric(18,6),
    volume      bigint,
    PRIMARY KEY (security_id, ts)
);
SELECT create_hypertable('price_bars', 'ts');

-- ── Portfolio ────────────────────────────────────────────────────────
CREATE TABLE portfolios (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE holdings (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id uuid NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    security_id uuid NOT NULL REFERENCES securities(id),
    quantity    numeric(18,6) NOT NULL,
    avg_cost    numeric(18,6) NOT NULL,
    UNIQUE (portfolio_id, security_id)
);

CREATE TABLE transactions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id uuid NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    security_id uuid NOT NULL REFERENCES securities(id),
    side        text NOT NULL CHECK (side IN ('buy','sell')),
    quantity    numeric(18,6) NOT NULL,
    price       numeric(18,6) NOT NULL,
    executed_at timestamptz NOT NULL,
    fees        numeric(18,6) NOT NULL DEFAULT 0
);

-- ── Watchlist ────────────────────────────────────────────────────────
CREATE TABLE watchlists (
    id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name    text NOT NULL DEFAULT 'My Watchlist'
);

CREATE TABLE watchlist_items (
    watchlist_id uuid NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    security_id  uuid NOT NULL REFERENCES securities(id),
    added_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, security_id)
);

-- ── Predictions (the trust-critical table) ───────────────────────────
CREATE TABLE predictions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id uuid NOT NULL REFERENCES securities(id),
    horizon     text NOT NULL,                  -- 1w | 1m | 3m | 6m | 1y
    generated_at timestamptz NOT NULL DEFAULT now(),
    model_version text NOT NULL,                -- e.g. "xgb-2026.06.01"
    point_target numeric(18,6),                 -- base-case price/return
    ci68_low    numeric(18,6),
    ci68_high   numeric(18,6),
    ci95_low    numeric(18,6),
    ci95_high   numeric(18,6),
    prob_up     numeric(5,4),                   -- e.g. 0.62
    bull_case   numeric(18,6),
    base_case   numeric(18,6),
    bear_case   numeric(18,6),
    var_95      numeric(18,6),                  -- value at risk
    vol_forecast numeric(8,4),
    UNIQUE (security_id, horizon, generated_at)
);

-- Plain-English driving factors from SHAP, one row per factor.
CREATE TABLE prediction_factors (
    prediction_id uuid NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    rank        int NOT NULL,
    factor      text NOT NULL,                  -- "RSI(14) overbought"
    contribution numeric(8,4),                  -- signed SHAP value
    explanation text,                           -- Elena's plain-English line
    PRIMARY KEY (prediction_id, rank)
);

-- ── Alerts, macro, digests ───────────────────────────────────────────
CREATE TABLE alerts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    security_id uuid REFERENCES securities(id),
    kind        text NOT NULL,                  -- price_target | risk_threshold | macro_shift
    condition   jsonb NOT NULL,                 -- {"op":">=","value":250}
    active      boolean NOT NULL DEFAULT true,
    last_fired  timestamptz
);

CREATE TABLE macro_signals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,                  -- fed_funds, sgd_usd, sg_cpi, vix
    as_of       date NOT NULL,
    value       numeric(18,6),
    trend       text,                           -- up | down | flat
    UNIQUE (name, as_of)
);

CREATE TABLE digests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period      text NOT NULL,                  -- weekly | monthly
    generated_at timestamptz NOT NULL DEFAULT now(),
    content     jsonb NOT NULL                  -- structured Elena summary
);

-- ── Audit (compliance) ───────────────────────────────────────────────
CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    user_id     uuid REFERENCES users(id),
    action      text NOT NULL,
    detail      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

Deferred to later phases (sketched, not built at MVP): `community_posts`, `community_reactions`, `learning_modules`, `module_progress`, `referrals`, `badges`.

**Schema reasoning to keep in mind:**
- `predictions` stores intervals and scenarios, not a single number — the schema *enforces* the "always show uncertainty" rule.
- `model_version` on every prediction lets you trace which model said what, and run A/B or shadow comparisons.
- Fundamentals are a daily snapshot keyed by `as_of`; this avoids look-ahead bias if you ever backtest against stored data.

---

## 4. MVP Feature Breakdown (Phases 1–3)

Phasing rule: each phase must be **shippable and trustworthy on its own**. We don't ship a half-built prediction surface.

### Phase 1 — MVP (prove the core loop)
*Goal: a user can sign up, watch a few stocks, and get one honest, explained forecast.*

- Auth + onboarding (account, goals, risk tolerance, base currency).
- Biometric gate on app open (mobile).
- Securities master + daily price ingestion for a starter universe (your NASDAQ names: ASML, TSLA, INTC, IONQ, SLV — plus a handful of STI names).
- **Single-security prediction**, served by the FastAPI ML service using your existing XGBoost baseline and walk-forward harness. Horizons: start with 1-week and 1-month.
- Prediction surface shows: base-case target, 68%/95% bands, probability up, and top 3 driving factors in Dr. Elena's voice.
- Basic dashboard: watchlist with the latest signal per stock.
- Disclaimers + "how to read this" copy everywhere a number appears.

*Out of scope in P1: portfolio P&L, ensemble models, community, simulations.*

### Phase 2 — v0.5 (depth and stickiness)
*Goal: it becomes a tool you check weekly.*

- Portfolio tracking (holdings, transactions, live valuation, simple P&L).
- AI portfolio **risk score** and per-holding risk exposure.
- **Scenario analysis**: explicit Bull / Base / Bear cases with VaR and volatility forecast.
- Longer horizons (3m, 6m, 1y) once backtests justify them.
- Alerts engine (price target, risk threshold, macro shift) on a Redis/BullMQ queue.
- Macro signal board (Fed funds, SGD/USD, SG CPI, VIX) from FRED + SGX.
- Weekly digest from Dr. Elena (generated job → `digests` table → push/email).

### Phase 3 — v1.0 (the full vision)
*Goal: the addictive-but-responsible product in the brief.*

- **Ensemble models**: LSTM/Transformer + factor model + macro overlay + sentiment, blended.
- **SHAP-driven explanations** wired into `prediction_factors` (replaces the simpler P1 factor logic).
- **Simulation / "what-if" stress engine** (portfolio-level shocks).
- Multiple personas (Kai, Ava) toggleable, each with its own prompt template and lens.
- Community feed (moderated, insights-only) + learning modules + progress tracking.
- Referral rewards and premium tier.
- Sentiment ingestion (news + social) feeding both predictions and the digest.

**Sequencing logic:** P1 proves the prediction is honest and the pipeline works end to end. P2 makes the predictions actionable against a real portfolio. P3 adds the heavier ML and the growth/engagement loop — none of which is worth building before the core forecast earns trust.

---

## 5. User Journey Implementation

Mapping the brief's journey table to concrete screens, endpoints, and data, in Dr. Elena's voice.

### Discovery → Onboarding
- **Screens:** intro carousel with Dr. Elena → sign-up → goal & risk setup.
- **Backend:** `POST /auth/register` (provider callback) → create `users` + `profiles`; `POST /goals`.
- **Elena copy (example):** "Before I show you any forecast, I want to understand your goals. Are we building for retirement, or hunting shorter-term opportunities? Both are valid — they just change how I read risk for you."
- **Emotional target:** curious → motivated. Achieved by asking, not lecturing.

### Prediction Experience (core loop)
- **Screens:** search a stock → prediction detail (chart with 68%/95% bands, bull/base/bear, driving factors, risk metrics).
- **Backend flow:**
  1. `GET /predictions/:symbol?horizon=1m` (Node API).
  2. Node checks Redis cache; on miss, calls ML service `POST /predict`.
  3. ML service runs the model (`make_model()`), returns the prediction contract (point + bands + prob + factors).
  4. Node persists to `predictions` / `prediction_factors`, caches, returns to client.
- **Elena copy (example):** "Our models suggest a **62% probability** that ASML trades higher over the next month, with a base case around $X. The 95% range is wide — $A to $B — so size any position for the downside, not the headline."
- **Emotional target:** empowered, analytical. The wide band is a feature, not a bug.

### Engagement
- **Screens:** dashboard, weekly digest, alerts inbox.
- **Backend:** scheduled jobs build `digests` and evaluate `alerts` against fresh prices/macro; push notifications via Expo / web push.
- **Elena copy (example):** "This week your portfolio's risk score rose from 4 to 6. The main driver was concentration in semiconductors. Here's one diversification idea to consider — not a recommendation, a prompt to think."
- **Emotional target:** informed, connected.

### Advocacy
- **Screens:** shareable (anonymized) insight cards, referral screen.
- **Backend (Phase 3):** `referrals` table, reward issuance, premium upgrade flow.
- **Guardrail:** users share *insights and process*, never guaranteed-return claims. Share cards are templated to stay compliant.
- **Emotional target:** proud, loyal.

### Cross-cutting implementation notes
- **Persona layer:** each persona (Elena/Kai/Ava) is a prompt template + tone config in the API, selected by `profiles.active_persona`. The same prediction data is narrated differently; the numbers never change between personas.
- **Uncertainty is mandatory in copy:** the API returns probability and intervals; the client is built so there is no code path that renders a bare price target without its band.
- **Compliance surface:** disclaimers, data-use, and retention live in `docs/compliance.md` and are rendered from a single source so legal copy stays consistent across mobile and web.

---

## Suggested first sprint (so this plan turns into code)

1. Scaffold the Turborepo (`apps/api`, `apps/web`, `apps/mobile`, `services/ml`, `packages/types`).
2. Stand up Postgres + TimescaleDB; run the Phase-1 migrations above.
3. Move your notebook's `fetch_nasdaq_listed`, `engineer_features`, `make_model`, and `walk_forward` into `services/ml/app/` behind a `POST /predict` endpoint.
4. Define the `Prediction` zod schema in `packages/types`; generate the typed client.
5. Build the prediction detail screen (web first) against real ML output for one stock.

That gives you a working vertical slice — one stock, one honest forecast, end to end — which is the right thing to validate before widening the universe or adding models.
