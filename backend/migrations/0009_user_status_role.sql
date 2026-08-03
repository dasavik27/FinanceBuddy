-- 0009_user_status_role: account status and role on users.

ALTER TABLE users ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user';

CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
