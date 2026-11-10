-- Phase 3: events, their saved schedules, tasks and the activity feed.
CREATE TABLE events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,
    event_type     TEXT    NOT NULL,
    description    TEXT    NOT NULL DEFAULT '',
    participants   INTEGER NOT NULL CHECK (participants > 0),
    budget         REAL    NOT NULL DEFAULT 0 CHECK (budget >= 0),   -- estimated budget in INR
    duration_hours INTEGER NOT NULL CHECK (duration_hours > 0),
    venue          TEXT    NOT NULL DEFAULT '',
    event_date     TEXT    NOT NULL,                                 -- YYYY-MM-DD
    start_time     TEXT    NOT NULL DEFAULT '09:00',                 -- HH:MM (24-hour)
    status         TEXT    NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft', 'pending', 'approved', 'rejected', 'completed')),
    admin_note     TEXT    NOT NULL DEFAULT '',                      -- reason shown after a rejection
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE INDEX idx_events_owner ON events(owner_id);
CREATE INDEX idx_events_date  ON events(event_date);

CREATE TABLE event_schedule_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    start_time  TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX idx_schedule_event ON event_schedule_items(event_id);

CREATE TABLE tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    assignee_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    deadline     TEXT,                                               -- YYYY-MM-DD or NULL
    status       TEXT    NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    phase        TEXT    CHECK (phase IN ('before', 'during', 'after')),
    created_at   TEXT    NOT NULL,
    completed_at TEXT
);
CREATE INDEX idx_tasks_event    ON tasks(event_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);

-- History survives deleting an event, so event_id has no foreign key.
CREATE TABLE activities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,      -- who did it
    owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- whose feed it appears in
    event_id   INTEGER,
    message    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);
CREATE INDEX idx_activities_owner ON activities(owner_id, id);
