-- ════════════════════════════════════════════════════════════════════
-- 0001_init.sql — Phase 1 schema for Disciplined Edge
--
-- Run against PostgreSQL with the TimescaleDB extension available.
-- Money is numeric, never float. Predictions store intervals + scenarios,
-- not a bare number — the schema enforces "always show uncertainty".
-- ════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "timescaledb";

-- ── Identity & profile ───────────────────────────────────────────────
CREATE TABLE users (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_provider_id  text UNIQUE NOT NULL,
    email             citext UNIQUE NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    biometric_enabled boolean NOT NULL DEFAULT false
);

CREATE TABLE profiles (
    user_id             uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    display_name        text,
    base_currency       text NOT NULL DEFAULT 'SGD',
    risk_tolerance      text CHECK (risk_tolerance IN
                          ('conservative','balanced','growth','aggressive')),
    active_persona      text NOT NULL DEFAULT 'elena'
                          CHECK (active_persona IN ('elena','kai','ava')),
    onboarding_complete boolean NOT NULL DEFAULT false
);

CREATE TABLE goals (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label         text NOT NULL,
    horizon       text NOT NULL,
    target_amount numeric(18,2),
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── Instruments & market data ────────────────────────────────────────
CREATE TABLE securities (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol     text NOT NULL,
    exchange   text NOT NULL CHECK (exchange IN ('NASDAQ','SGX')),
    name       text,
    sector     text,
    industry   text,
    asset_type text NOT NULL DEFAULT 'equity' CHECK (asset_type IN ('equity','etf')),
    currency   text NOT NULL,
    UNIQUE (symbol, exchange)
);

CREATE TABLE security_fundamentals (
    security_id  uuid NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    as_of        date NOT NULL,
    market_cap   numeric(20,2),
    eps          numeric(12,4),
    pe           numeric(12,4),
    pb           numeric(12,4),
    peg          numeric(12,4),
    debt_equity  numeric(12,4),
    roe          numeric(12,4),
    rev_growth   numeric(12,4),
    ebitda       numeric(20,2),
    div_yield    numeric(8,4),
    beta         numeric(8,4),
    float_shares numeric(20,0),
    PRIMARY KEY (security_id, as_of)
);

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
SELECT create_hypertable('price_bars', 'ts', if_not_exists => TRUE);

-- ── Portfolio ────────────────────────────────────────────────────────
CREATE TABLE portfolios (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE holdings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id uuid NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    security_id  uuid NOT NULL REFERENCES securities(id),
    quantity     numeric(18,6) NOT NULL,
    avg_cost     numeric(18,6) NOT NULL,
    UNIQUE (portfolio_id, security_id)
);

CREATE TABLE transactions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id uuid NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    security_id  uuid NOT NULL REFERENCES securities(id),
    side         text NOT NULL CHECK (side IN ('buy','sell')),
    quantity     numeric(18,6) NOT NULL,
    price        numeric(18,6) NOT NULL,
    executed_at  timestamptz NOT NULL,
    fees         numeric(18,6) NOT NULL DEFAULT 0
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

-- ── Predictions (trust-critical) ─────────────────────────────────────
CREATE TABLE predictions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id   uuid NOT NULL REFERENCES securities(id),
    horizon       text NOT NULL,
    generated_at  timestamptz NOT NULL DEFAULT now(),
    model_version text NOT NULL,
    point_target  numeric(18,6) NOT NULL,
    ci68_low      numeric(18,6) NOT NULL,
    ci68_high     numeric(18,6) NOT NULL,
    ci95_low      numeric(18,6) NOT NULL,
    ci95_high     numeric(18,6) NOT NULL,
    prob_up       numeric(5,4) NOT NULL CHECK (prob_up BETWEEN 0 AND 1),
    bull_case     numeric(18,6) NOT NULL,
    base_case     numeric(18,6) NOT NULL,
    bear_case     numeric(18,6) NOT NULL,
    var_95        numeric(18,6) NOT NULL,
    vol_forecast  numeric(8,4)  NOT NULL CHECK (vol_forecast >= 0),
    UNIQUE (security_id, horizon, generated_at),
    -- DB-level mirror of the contract invariants.
    CHECK (ci68_low <= point_target AND point_target <= ci68_high),
    CHECK (ci95_low <= ci68_low AND ci95_high >= ci68_high),
    CHECK (bear_case <= base_case AND base_case <= bull_case)
);

CREATE TABLE prediction_factors (
    prediction_id uuid NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    rank          int NOT NULL,
    factor        text NOT NULL,
    contribution  numeric(8,4),
    explanation   text,
    PRIMARY KEY (prediction_id, rank)
);

-- ── Alerts, macro, digests, audit ────────────────────────────────────
CREATE TABLE alerts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    security_id uuid REFERENCES securities(id),
    kind        text NOT NULL CHECK (kind IN
                  ('price_target','risk_threshold','macro_shift')),
    condition   jsonb NOT NULL,
    active      boolean NOT NULL DEFAULT true,
    last_fired  timestamptz
);

CREATE TABLE macro_signals (
    id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name   text NOT NULL,
    as_of  date NOT NULL,
    value  numeric(18,6),
    trend  text CHECK (trend IN ('up','down','flat')),
    UNIQUE (name, as_of)
);

CREATE TABLE digests (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period       text NOT NULL CHECK (period IN ('weekly','monthly')),
    generated_at timestamptz NOT NULL DEFAULT now(),
    content      jsonb NOT NULL
);

CREATE TABLE audit_log (
    id         bigserial PRIMARY KEY,
    user_id    uuid REFERENCES users(id),
    action     text NOT NULL,
    detail     jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ── Helpful indexes ──────────────────────────────────────────────────
CREATE INDEX idx_predictions_lookup ON predictions (security_id, horizon, generated_at DESC);
CREATE INDEX idx_holdings_portfolio ON holdings (portfolio_id);
CREATE INDEX idx_watchlist_items_wl ON watchlist_items (watchlist_id);
