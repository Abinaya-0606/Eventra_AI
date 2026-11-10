-- Phase 7: approval audit columns, student registrations and notifications.
-- Additive only: no existing table, user or event is dropped or rewritten.

ALTER TABLE events ADD COLUMN submitted_at TEXT;
ALTER TABLE events ADD COLUMN reviewed_by  INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN reviewed_at  TEXT;
-- Events that were already waiting for approval get a submission time.
UPDATE events SET submitted_at = updated_at WHERE status = 'pending';

-- A student's registration for an event. One row per (event, student): cancelling keeps the row
-- (status = 'cancelled') so history is preserved and re-registering simply flips it back.
CREATE TABLE registrations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    status       TEXT    NOT NULL DEFAULT 'registered' CHECK (status IN ('registered', 'cancelled')),
    created_at   TEXT    NOT NULL,
    cancelled_at TEXT,
    UNIQUE (event_id, user_id)
);
CREATE INDEX idx_registrations_event ON registrations(event_id, status);
CREATE INDEX idx_registrations_user  ON registrations(user_id, status);

CREATE TABLE notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL DEFAULT 'info',   -- approval_request, approved, rejected, registration, update, ...
    message    TEXT    NOT NULL,
    link       TEXT    NOT NULL DEFAULT '',        -- site-relative URL or empty
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE INDEX idx_notifications_user ON notifications(user_id, is_read, id);

-- Before this version every account could create events. Students who already own events are made
-- organizers so they keep control of the events they created (nothing is deleted or hidden).
UPDATE users SET role = 'organizer'
 WHERE role = 'student' AND id IN (SELECT DISTINCT owner_id FROM events);
