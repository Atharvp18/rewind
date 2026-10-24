-- Rewind Supabase (Postgres) schema. Technical spec section 3.1.
-- Run once in the Supabase SQL editor, then run functions.sql.
-- Integer cents everywhere (bigint). IDs are application-generated text.

CREATE TABLE IF NOT EXISTS cards (
  id                TEXT PRIMARY KEY,         -- 'card_hsa_1', 'card_visa_1'
  type              TEXT NOT NULL CHECK (type IN ('hsa','fsa','general')),
  nickname          TEXT NOT NULL,            -- 'HSA card', 'Visa credit'
  balance_cents     BIGINT NOT NULL,
  nessie_account_id TEXT,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','frozen','closed','expired')),
  is_default        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS product_cache (
  product_key            TEXT PRIMARY KEY,
  upc                    TEXT,
  normalized_name        TEXT NOT NULL,
  brand                  TEXT,
  size                   TEXT,
  category               TEXT NOT NULL,
  shelf_price_cents      BIGINT,
  eligibility_label      TEXT CHECK (eligibility_label IN
                           ('eligible','not_eligible','could_not_confirm')),
  eligibility_confidence REAL,
  eligibility_basis      TEXT,
  source                 TEXT NOT NULL,
  last_updated           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cache_upc ON product_cache(upc);

CREATE TABLE IF NOT EXISTS eligibility_items (   -- Tiea populates; Atharv owns the table
  product_key   TEXT PRIMARY KEY,
  upc           TEXT,
  name          TEXT NOT NULL,
  brand         TEXT,
  size          TEXT,
  category_path TEXT,
  eligible      BOOLEAN NOT NULL,                -- both values must be present in the data
  source_url    TEXT NOT NULL,
  collected_at  TIMESTAMPTZ NOT NULL,
  basis         TEXT NOT NULL CHECK (basis IN ('retailer_badge','irs_category_rule','hand_entered'))
);
CREATE INDEX IF NOT EXISTS idx_elig_upc ON eligibility_items(upc);

CREATE TABLE IF NOT EXISTS scans (
  scan_id          TEXT PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  state            TEXT NOT NULL,
  product_json     JSONB NOT NULL,
  eligibility_json JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS cart_items (
  id                 TEXT PRIMARY KEY,
  seq                BIGINT GENERATED ALWAYS AS IDENTITY,   -- 'remove last item' uses MAX(seq)
  scan_id            TEXT NOT NULL REFERENCES scans(scan_id),
  product_key        TEXT NOT NULL,
  display_name       TEXT NOT NULL,
  amount_cents       BIGINT NOT NULL,
  amount_basis       TEXT NOT NULL CHECK (amount_basis IN ('shelf_price','remaining_after_copay')),
  assigned_card_id   TEXT NOT NULL REFERENCES cards(id),
  eligibility_label  TEXT NOT NULL,
  user_overrode_card BOOLEAN NOT NULL DEFAULT FALSE,        -- for 'possible reimbursement'
  added_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS insurers (
  id               TEXT PRIMARY KEY,
  display_name     TEXT NOT NULL,          -- must be visibly marked mock in the UI
  has_rx_benefit   BOOLEAN NOT NULL,
  copay_rules_json JSONB NOT NULL          -- {"drug_key": {"copay_cents": 1000}}
);

CREATE TABLE IF NOT EXISTS prompts (
  prompt_id    TEXT PRIMARY KEY,
  scope        TEXT NOT NULL,
  scan_id      TEXT,
  payload_json JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  consumed     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS payments (
  payment_id      TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  total_cents     BIGINT NOT NULL,
  splits_json     JSONB NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('simulated_complete','failed'))
);

-- Row-level security off for the demo (section 3.2): a blocked insert at judging time
-- looks identical to a bug. The service key lives on the backend only.
ALTER TABLE cards             DISABLE ROW LEVEL SECURITY;
ALTER TABLE product_cache     DISABLE ROW LEVEL SECURITY;
ALTER TABLE eligibility_items DISABLE ROW LEVEL SECURITY;
ALTER TABLE scans             DISABLE ROW LEVEL SECURITY;
ALTER TABLE cart_items        DISABLE ROW LEVEL SECURITY;
ALTER TABLE insurers          DISABLE ROW LEVEL SECURITY;
ALTER TABLE prompts           DISABLE ROW LEVEL SECURITY;
ALTER TABLE payments          DISABLE ROW LEVEL SECURITY;
