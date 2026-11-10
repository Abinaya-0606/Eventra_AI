-- Indexes for the approval queue, student browsing, admin activity log and notification inbox.
-- Additive only: no table, user or event is changed.
CREATE INDEX IF NOT EXISTS idx_events_status_date ON events(status, event_date);
CREATE INDEX IF NOT EXISTS idx_activities_id      ON activities(id DESC);
CREATE INDEX IF NOT EXISTS idx_activities_user    ON activities(user_id);
