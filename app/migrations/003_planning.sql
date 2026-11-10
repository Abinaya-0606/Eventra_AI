-- Phase 4: venues, saved budget breakdowns, saved AI results and proposals.
CREATE TABLE venues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    cost_per_day REAL    NOT NULL DEFAULT 0 CHECK (cost_per_day >= 0),   -- INR
    facilities   TEXT    NOT NULL DEFAULT '',                            -- comma-separated keys, see services/insights.py
    notes        TEXT    NOT NULL DEFAULT '',
    is_active    INTEGER NOT NULL DEFAULT 1
);
-- The two venues the original budget calculator already knew. Admins add facilities and more venues in Admin -> Venues.
INSERT INTO venues (name, capacity, cost_per_day, notes) VALUES
    ('Seminar Hall', 100, 3000, 'Imported from the budget calculator. Facilities not listed yet.'),
    ('Auditorium',   300, 8000, 'Imported from the budget calculator. Facilities not listed yet.');

CREATE TABLE event_budget_items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    category TEXT    NOT NULL,
    amount   REAL    NOT NULL CHECK (amount >= 0),
    UNIQUE (event_id, category)
);

-- The latest AI result of each kind (venues / risks / improve) for an event.
CREATE TABLE ai_results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL CHECK (kind IN ('venues', 'risks', 'improve')),
    content    TEXT    NOT NULL,                                         -- JSON
    created_at TEXT    NOT NULL,
    UNIQUE (event_id, kind)
);

-- The AI-written text of the proposal. Schedule and budget are read live from the database when the PDF is built.
CREATE TABLE proposals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    content    TEXT    NOT NULL,                                         -- JSON
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
