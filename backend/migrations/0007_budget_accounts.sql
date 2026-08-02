-- 0007_budget_accounts: give the budget domain the entity it was missing.
--
-- The problem
-- -----------
-- Until now a "bank account" was two free-text strings on every transaction row -
-- source_bank and account_type - partly inferred from the *filename* of the upload.
-- Three consequences, all of which make the headline numbers wrong:
--
--   * Two accounts at the same bank are indistinguishable. A salary account and a
--     joint account at HDFC merge into one.
--
--   * Moving 50,000 from HDFC to ICICI is counted as 50,000 of income *and* 50,000 of
--     expense. Savings rate, burn rate and the 50/30/20 split are all inflated by
--     however much the user shuffles between their own accounts.
--
--   * A credit card is treated as a spending account. The card purchase is an expense
--     and the bill payment from savings is *another* expense, so card spend is counted
--     twice and the card is never shown as the liability it is.
--
-- The model
-- ---------
-- Accounts are not created by hand. An upload names its bank and kind, and that
-- derives a stable `account_key`; the row here holds only what a statement cannot
-- tell us - credit limit, statement and due day, opening balance, a display label.
-- Uploading is therefore still the only thing a user has to do, and an account they
-- never customise needs no row at all.
--
-- account_key is text rather than a surrogate id precisely so it can be recomputed
-- from a transaction without a lookup: "HDFC:savings:1234".

CREATE TABLE IF NOT EXISTS budget_account_meta (
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_key     text NOT NULL,
    label           text NOT NULL DEFAULT '',
    -- 'savings' | 'current' | 'salary' | 'credit_card'. Not a CHECK constraint: the
    -- kind is derived from a user-selected account_type string, and a new kind should
    -- not require a migration to start appearing.
    kind            text NOT NULL DEFAULT 'savings',
    last4           text,
    -- Credit cards only. Utilisation above ~30% is the single largest negative input
    -- to an Indian credit score, which is why the limit is worth asking for.
    credit_limit    double precision,
    statement_day   smallint,
    due_day         smallint,
    -- Lets reconciliation verify opening + sum(transactions) == closing even when the
    -- export carries no running balance column.
    opening_balance double precision,
    archived        boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, account_key)
);

ALTER TABLE budget_account_meta ENABLE ROW LEVEL SECURITY;

-- ── Envelope budgets ─────────────────────────────────────────────────────────
--
-- A monthly cap per category. Kept separate from the category itself because a
-- category is derived from rules and may appear or vanish between uploads, whereas a
-- budget the user set should survive that.

CREATE TABLE IF NOT EXISTS budget_envelopes (
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category     text NOT NULL,
    monthly_cap  double precision NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, category)
);

ALTER TABLE budget_envelopes ENABLE ROW LEVEL SECURITY;

-- ── Merchant aliases ─────────────────────────────────────────────────────────
--
-- UPI narrations are unreadable ("UPI/DR/402938/SWIGGY BANGALORE/paytm@ybl"). The
-- parser normalises them heuristically; this is where a correction the user makes by
-- hand is remembered, so they only rename a merchant once.

CREATE TABLE IF NOT EXISTS budget_merchant_aliases (
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    normalised    text NOT NULL,
    display_name  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, normalised)
);

ALTER TABLE budget_merchant_aliases ENABLE ROW LEVEL SECURITY;

-- ── Per-transaction overrides ────────────────────────────────────────────────
--
-- Transfer detection is a heuristic: it pairs a debit in one account with a credit in
-- another at the same amount within a few days. It will occasionally be wrong in both
-- directions - a genuine payment to a friend who banks with you looks like a transfer,
-- and a transfer split across two days at different amounts does not.
--
-- Rather than persist the detection (which would have to be recomputed and reconciled
-- on every upload), only the user's *disagreements* are stored. Detection stays a pure
-- function of the transactions, and this table is the small correction layer on top.

CREATE TABLE IF NOT EXISTS budget_txn_flags (
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    txn_id      text NOT NULL,
    -- 'transfer' forces a row to be treated as internal movement, 'not_transfer'
    -- forces it back to real income/expense. NULL-free by design: absence of a row
    -- means "trust the heuristic".
    flag        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, txn_id)
);

ALTER TABLE budget_txn_flags ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_budget_txn_flags_user ON budget_txn_flags(user_id);
