-- Phase 2: accounts and password-reset tokens.
-- Plain SQL (no SQLite-only tricks beyond COLLATE NOCASE) so it can move to PostgreSQL later.
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'organizer', 'admin')),
    language        TEXT    NOT NULL DEFAULT 'en'      CHECK (language IN ('en', 'ta')),
    department      TEXT    NOT NULL DEFAULT '',
    session_version INTEGER NOT NULL DEFAULT 1,   -- bumped on password change: signs out every other device
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL
);

CREATE TABLE password_reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,           -- only the SHA-256 of the token is stored
    expires_at TEXT    NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE INDEX idx_reset_tokens_user ON password_reset_tokens(user_id);
