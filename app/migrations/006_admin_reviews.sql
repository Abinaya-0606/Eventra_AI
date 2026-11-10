-- Admin review history: one row per approve / reject decision, so earlier decisions stay visible after an
-- organizer corrects and resubmits. Additive only: no existing table, user or event is changed.
CREATE TABLE event_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    reviewer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decision    TEXT    NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason      TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);
CREATE INDEX idx_event_reviews_event ON event_reviews(event_id, id);
CREATE INDEX idx_event_reviews_decision ON event_reviews(decision, id);

-- Decisions made before this version: one row per event that currently carries a review.
INSERT INTO event_reviews (event_id, reviewer_id, decision, reason, created_at)
SELECT id, reviewed_by, CASE WHEN status = 'rejected' THEN 'rejected' ELSE 'approved' END,
       CASE WHEN status = 'rejected' THEN admin_note ELSE '' END, reviewed_at
  FROM events
 WHERE reviewed_at IS NOT NULL AND status IN ('approved', 'rejected', 'completed');
