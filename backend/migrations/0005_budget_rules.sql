-- 0005_budget_rules: schema for user-defined categorization rules.

CREATE TABLE IF NOT EXISTS budget_rules (
    rule_id      text PRIMARY KEY,
    user_id      uuid NOT NULL,
    pattern      text NOT NULL,
    category     text NOT NULL,
    match_type   text NOT NULL DEFAULT 'contains', -- 'contains', 'exact', 'regex'
    created_at   timestamptz NOT NULL DEFAULT now(),
    match_count  integer NOT NULL DEFAULT 0
);

CREATE INDEX idx_budget_rules_user ON budget_rules(user_id);
