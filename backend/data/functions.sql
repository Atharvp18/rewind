-- Postgres functions called through supabase.rpc(...). Technical spec sections 3.2, 3.4, 3.6, 3.7.
-- The REST client sends one request per call, so anything multi-step and atomic lives here.
-- Run after schema.sql. Safe to re-run (CREATE OR REPLACE).

-- ---------------------------------------------------------------------------
-- Prompts: 15 s TTL, single use, scope must match (section 3.7).
-- The DB clock decides expiry, so the laptop's clock cannot cause drift.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION create_prompt(
  p_prompt_id   TEXT,
  p_scope       TEXT,
  p_scan_id     TEXT,
  p_payload     JSONB,
  p_ttl_seconds INT DEFAULT 15
) RETURNS TEXT
LANGUAGE sql AS $$
  INSERT INTO prompts (prompt_id, scope, scan_id, payload_json, expires_at)
  VALUES (p_prompt_id, p_scope, p_scan_id, p_payload, now() + make_interval(secs => p_ttl_seconds))
  RETURNING prompt_id;
$$;

-- Returns NULL when the prompt is unknown, expired, already used, or the wrong scope.
-- A wrong-scope attempt does not consume the prompt.
CREATE OR REPLACE FUNCTION consume_prompt(p_prompt_id TEXT, p_scope TEXT)
RETURNS JSONB
LANGUAGE plpgsql AS $$
DECLARE
  r prompts;
BEGIN
  UPDATE prompts
     SET consumed = TRUE
   WHERE prompt_id = p_prompt_id
     AND scope = p_scope
     AND consumed = FALSE
     AND expires_at > now()
  RETURNING * INTO r;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  RETURN jsonb_build_object(
    'prompt_id', r.prompt_id,
    'scope',     r.scope,
    'scan_id',   r.scan_id,
    'payload',   r.payload_json
  );
END;
$$;

-- ---------------------------------------------------------------------------
-- Cart: "remove last item" removes the highest seq, in one statement.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION remove_last_cart_item()
RETURNS JSONB
LANGUAGE plpgsql AS $$
DECLARE
  r cart_items;
BEGIN
  DELETE FROM cart_items
   WHERE id = (SELECT id FROM cart_items ORDER BY seq DESC LIMIT 1)
  RETURNING * INTO r;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  RETURN to_jsonb(r);
END;
$$;

-- ---------------------------------------------------------------------------
-- Checkout (section 3.6): simulated, all or nothing, idempotent.
--   p_splits = [{"card_id": "card_hsa_1", "amount_cents": 1848}, ...]
-- A repeated idempotency key returns the original payment unchanged and charges nothing.
-- Any failed debit raises, which rolls back the payment row and every earlier debit.
-- A successful checkout copies the cart into purchase_items (for the History agent), then empties
-- the cart, so the same items cannot be paid twice under a new key.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION confirm_checkout(p_idempotency_key TEXT, p_splits JSONB)
RETURNS JSONB
LANGUAGE plpgsql AS $$
DECLARE
  v_payment_id TEXT := gen_random_uuid()::TEXT;
  v_total      BIGINT;
  v_inserted   INT;
  v_existing   payments;
  s            JSONB;
  v_amount     BIGINT;
BEGIN
  IF p_splits IS NULL OR jsonb_array_length(p_splits) = 0 THEN
    RAISE EXCEPTION 'E_EMPTY_CART';
  END IF;

  SELECT COALESCE(SUM((e->>'amount_cents')::BIGINT), 0)
    INTO v_total
    FROM jsonb_array_elements(p_splits) e;

  INSERT INTO payments (payment_id, idempotency_key, total_cents, splits_json, status)
  VALUES (v_payment_id, p_idempotency_key, v_total, p_splits, 'simulated_complete')
  ON CONFLICT (idempotency_key) DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;

  IF v_inserted = 0 THEN
    SELECT * INTO v_existing FROM payments WHERE idempotency_key = p_idempotency_key;
    RETURN jsonb_build_object(
      'payment_id',   v_existing.payment_id,
      'total_cents',  v_existing.total_cents,
      'splits',       v_existing.splits_json,
      'new_balances', (SELECT jsonb_agg(jsonb_build_object(
                          'id', id, 'nickname', nickname, 'balance_cents', balance_cents)
                          ORDER BY id) FROM cards),
      'replayed',     TRUE
    );
  END IF;

  FOR s IN SELECT * FROM jsonb_array_elements(p_splits) LOOP
    v_amount := (s->>'amount_cents')::BIGINT;
    IF v_amount <= 0 THEN
      RAISE EXCEPTION 'E_BAD_AMOUNT: %', s->>'card_id';
    END IF;

    UPDATE cards
       SET balance_cents = balance_cents - v_amount
     WHERE id = s->>'card_id'
       AND status = 'active'
       AND balance_cents >= v_amount;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'E_CARD_CANNOT_PAY: %', s->>'card_id';
    END IF;
  END LOOP;

  -- Keep what was bought: the History agent reads purchase_items; the cart is about to be emptied.
  -- Over-the-counter only: a prescription copay is not kept. Category and is_medication come from
  -- the saved scan.
  INSERT INTO purchase_items (id, payment_id, product_key, display_name, amount_cents, amount_basis,
                              card_id, card_type, eligibility_label, user_overrode_card,
                              category, is_medication)
  SELECT ci.id, v_payment_id, ci.product_key, ci.display_name, ci.amount_cents, ci.amount_basis,
         ci.assigned_card_id, c.type, ci.eligibility_label, ci.user_overrode_card,
         s.product_json->>'category',
         COALESCE((s.product_json->>'is_medication')::BOOLEAN, FALSE)
    FROM cart_items ci
    JOIN cards c ON c.id = ci.assigned_card_id
    LEFT JOIN scans s ON s.scan_id = ci.scan_id
   WHERE ci.product_key <> 'prescription';

  DELETE FROM cart_items WHERE TRUE;   -- WHERE TRUE: see reset_demo (pg-safeupdate)

  RETURN jsonb_build_object(
    'payment_id',   v_payment_id,
    'total_cents',  v_total,
    'splits',       p_splits,
    'new_balances', (SELECT jsonb_agg(jsonb_build_object(
                        'id', id, 'nickname', nickname, 'balance_cents', balance_cents)
                        ORDER BY id) FROM cards),
    'replayed',     FALSE
  );
END;
$$;

-- ---------------------------------------------------------------------------
-- reset_demo (section 3.4): one transaction, same result every time.
-- The seed values come from data/seed.py as parameters, so the numbers live in one place.
--   p_run         1 or 2 (validated here; the run's HSA balance is already in p_cards)
--   p_cards       [{id,type,nickname,balance_cents,nessie_account_id,status,is_default}]
--   p_products    [{product_key,upc,normalized_name,brand,size,category,shelf_price_cents,
--                   eligibility_label,eligibility_basis,source}]
--   p_insurers    [{id,display_name,has_rx_benefit,copay_rules_json}]
--   p_eligibility [{product_key,upc,name,brand,size,category_path,eligible,source_url,
--                   collected_at,basis}]
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION reset_demo(
  p_run         INT,
  p_cards       JSONB,
  p_products    JSONB,
  p_insurers    JSONB,
  p_eligibility JSONB
) RETURNS JSONB
LANGUAGE plpgsql AS $$
BEGIN
  IF p_run NOT IN (1, 2) THEN
    RAISE EXCEPTION 'E_BAD_RUN: %', p_run;
  END IF;

  -- children before parents (cart_items references scans and cards).
  -- WHERE TRUE: Supabase rejects a DELETE with no WHERE clause (pg-safeupdate).
  DELETE FROM cart_items WHERE TRUE;
  DELETE FROM scans      WHERE TRUE;
  DELETE FROM prompts    WHERE TRUE;
  DELETE FROM purchase_items WHERE TRUE;   -- references payments, so it goes first
  DELETE FROM payments   WHERE TRUE;
  -- prices saved from earlier scans go too, so every rehearsal starts the same;
  -- the seeded demo products are re-inserted below
  DELETE FROM product_cache WHERE source <> 'seeded';

  INSERT INTO cards (id, type, nickname, balance_cents, nessie_account_id, status, is_default)
  SELECT c->>'id', c->>'type', c->>'nickname', (c->>'balance_cents')::BIGINT,
         c->>'nessie_account_id', COALESCE(c->>'status', 'active'),
         COALESCE((c->>'is_default')::BOOLEAN, FALSE)
    FROM jsonb_array_elements(p_cards) c
  ON CONFLICT (id) DO UPDATE SET
    type              = EXCLUDED.type,
    nickname          = EXCLUDED.nickname,
    balance_cents     = EXCLUDED.balance_cents,
    nessie_account_id = EXCLUDED.nessie_account_id,
    status            = EXCLUDED.status,
    is_default        = EXCLUDED.is_default;

  -- any card that is not in the seed goes, so two resets always leave the same cards
  DELETE FROM cards
   WHERE id NOT IN (SELECT c->>'id' FROM jsonb_array_elements(p_cards) c);

  INSERT INTO product_cache (product_key, upc, normalized_name, brand, size, category,
                             shelf_price_cents, eligibility_label, eligibility_basis,
                             source, last_updated)
  SELECT p->>'product_key', p->>'upc', p->>'normalized_name', p->>'brand', p->>'size',
         p->>'category', (p->>'shelf_price_cents')::BIGINT, p->>'eligibility_label',
         p->>'eligibility_basis', p->>'source', now()
    FROM jsonb_array_elements(p_products) p
  ON CONFLICT (product_key) DO UPDATE SET
    upc               = EXCLUDED.upc,
    normalized_name   = EXCLUDED.normalized_name,
    brand             = EXCLUDED.brand,
    size              = EXCLUDED.size,
    category          = EXCLUDED.category,
    shelf_price_cents = EXCLUDED.shelf_price_cents,
    eligibility_label = EXCLUDED.eligibility_label,
    eligibility_basis = EXCLUDED.eligibility_basis,
    source            = EXCLUDED.source,
    last_updated      = now();

  INSERT INTO insurers (id, display_name, has_rx_benefit, copay_rules_json)
  SELECT i->>'id', i->>'display_name', (i->>'has_rx_benefit')::BOOLEAN, i->'copay_rules_json'
    FROM jsonb_array_elements(p_insurers) i
  ON CONFLICT (id) DO UPDATE SET
    display_name     = EXCLUDED.display_name,
    has_rx_benefit   = EXCLUDED.has_rx_benefit,
    copay_rules_json = EXCLUDED.copay_rules_json;

  INSERT INTO eligibility_items (product_key, upc, name, brand, size, category_path,
                                 eligible, source_url, collected_at, basis)
  SELECT e->>'product_key', e->>'upc', e->>'name', e->>'brand', e->>'size',
         e->>'category_path', (e->>'eligible')::BOOLEAN, e->>'source_url',
         (e->>'collected_at')::TIMESTAMPTZ, e->>'basis'
    FROM jsonb_array_elements(p_eligibility) e
  ON CONFLICT (product_key) DO UPDATE SET
    upc           = EXCLUDED.upc,
    name          = EXCLUDED.name,
    brand         = EXCLUDED.brand,
    size          = EXCLUDED.size,
    category_path = EXCLUDED.category_path,
    eligible      = EXCLUDED.eligible,
    source_url    = EXCLUDED.source_url,
    collected_at  = EXCLUDED.collected_at,
    basis         = EXCLUDED.basis;

  RETURN jsonb_build_object(
    'cards', (SELECT COALESCE(jsonb_agg(to_jsonb(c) ORDER BY c.id), '[]'::JSONB) FROM cards c)
  );
END;
$$;
