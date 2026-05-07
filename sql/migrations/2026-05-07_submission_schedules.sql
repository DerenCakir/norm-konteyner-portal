-- Admin-configurable submission window
-- Single-row table (id=1) holds the active day-of-week + open/close hours.
-- Default: Monday 09:00–12:00 (TR).

CREATE TABLE IF NOT EXISTS submission_schedules (
    id           INTEGER PRIMARY KEY,
    day_of_week  INTEGER NOT NULL DEFAULT 1,
    open_hour    INTEGER NOT NULL DEFAULT 9,
    close_hour   INTEGER NOT NULL DEFAULT 12,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by   INTEGER REFERENCES users(id),

    CONSTRAINT valid_day_of_week  CHECK (day_of_week BETWEEN 1 AND 7),
    CONSTRAINT valid_open_hour    CHECK (open_hour BETWEEN 0 AND 23),
    CONSTRAINT valid_close_hour   CHECK (close_hour BETWEEN 1 AND 24),
    CONSTRAINT close_after_open   CHECK (close_hour > open_hour)
);

INSERT INTO submission_schedules (id, day_of_week, open_hour, close_hour)
VALUES (1, 1, 9, 12)
ON CONFLICT (id) DO NOTHING;
