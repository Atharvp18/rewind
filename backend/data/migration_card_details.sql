-- Rewind: card details for POST /v1/cards (linking a card at onboarding). Paste into the Supabase
-- SQL Editor and Run. Safe to run twice. Only the last 4 digits are ever stored, never a full number.
ALTER TABLE cards ADD COLUMN IF NOT EXISTS last4 TEXT CHECK (last4 IS NULL OR last4 ~ '^[0-9]{4}$');
ALTER TABLE cards ADD COLUMN IF NOT EXISTS network TEXT
  CHECK (network IS NULL OR network IN ('visa','mastercard','amex','discover','other'));
