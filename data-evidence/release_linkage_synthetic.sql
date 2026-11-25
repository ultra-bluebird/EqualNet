-- SPDX-License-Identifier: MIT OR Apache-2.0
-- Synthetic-record release differencing analysis (SQLite 3.25+, window functions).
-- Operates only on tables marked synthetic. It publishes nothing and reads no
-- rider, journey, device, or account data. Re-running the script is safe.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS policy (
    policy_id      TEXT PRIMARY KEY CHECK (length(policy_id) BETWEEN 1 AND 120),
    rounding       INTEGER NOT NULL CHECK (rounding BETWEEN 1 AND 1000),
    suppress_below INTEGER NOT NULL CHECK (suppress_below >= 0),
    window_steps   INTEGER NOT NULL CHECK (window_steps BETWEEN 1 AND 100)
);

CREATE TABLE IF NOT EXISTS synthetic_occupancy (
    run_id    TEXT    NOT NULL CHECK (length(run_id) BETWEEN 1 AND 120),
    step      INTEGER NOT NULL CHECK (step >= 0),
    occupancy INTEGER NOT NULL CHECK (occupancy >= 0),
    origin    TEXT    NOT NULL DEFAULT 'synthetic' CHECK (origin = 'synthetic'),
    PRIMARY KEY (run_id, step)
);

CREATE TABLE IF NOT EXISTS synthetic_target_event (
    run_id TEXT    NOT NULL,
    step   INTEGER NOT NULL,
    PRIMARY KEY (run_id, step),
    FOREIGN KEY (run_id, step) REFERENCES synthetic_occupancy (run_id, step)
);

DROP VIEW IF EXISTS policy_summary;
DROP VIEW IF EXISTS transformation_error;
DROP VIEW IF EXISTS attack_outcome;
DROP VIEW IF EXISTS published_delta;
DROP VIEW IF EXISTS published;

-- One release per policy window: rounding is half-up on the grid, and a value
-- below the suppression threshold is published as NULL (suppressed).
CREATE VIEW published AS
SELECT p.policy_id,
       o.run_id,
       o.step,
       CASE WHEN o.occupancy < p.suppress_below THEN NULL
            ELSE ((2 * o.occupancy + p.rounding) / (2 * p.rounding)) * p.rounding
       END AS value
FROM policy AS p
JOIN synthetic_occupancy AS o ON o.step % p.window_steps = 0;

CREATE VIEW published_delta AS
SELECT policy_id,
       run_id,
       step,
       value,
       LAG(value) OVER (PARTITION BY policy_id, run_id ORDER BY step) AS prev_value,
       LAG(step)  OVER (PARTITION BY policy_id, run_id ORDER BY step) AS prev_step
FROM published;

-- Naive differencing attacker: guesses a single-entry event in an interval when
-- two consecutive non-suppressed releases differ by exactly one grid step.
CREATE VIEW attack_outcome AS
SELECT d.policy_id,
       d.run_id,
       d.step,
       CASE WHEN d.value IS NOT NULL
             AND d.prev_value IS NOT NULL
             AND d.value - d.prev_value = (SELECT rounding FROM policy WHERE policy_id = d.policy_id)
            THEN 1 ELSE 0 END AS guessed,
       EXISTS (SELECT 1
               FROM synthetic_target_event AS e
               WHERE e.run_id = d.run_id
                 AND e.step > d.prev_step
                 AND e.step <= d.step) AS actual
FROM published_delta AS d
WHERE d.prev_step IS NOT NULL;

CREATE VIEW policy_summary AS
SELECT policy_id,
       SUM(guessed AND actual)         AS true_positive,
       SUM(guessed AND NOT actual)     AS false_positive,
       SUM(NOT guessed AND actual)     AS false_negative,
       SUM(NOT guessed AND NOT actual) AS true_negative,
       CASE WHEN SUM(guessed) = 0 THEN NULL
            ELSE 1.0 * SUM(guessed AND actual) / SUM(guessed) END AS attack_precision,
       CASE WHEN SUM(actual) = 0 THEN NULL
            ELSE 1.0 * SUM(guessed AND actual) / SUM(actual) END  AS attack_recall
FROM attack_outcome
GROUP BY policy_id;

-- Transformation effects stay separate from attack outcomes.
CREATE VIEW transformation_error AS
SELECT p.policy_id,
       COUNT(*)                          AS releases,
       SUM(p.value IS NULL)              AS suppressed,
       AVG(ABS(p.value - o.occupancy))   AS mean_abs_error
FROM published AS p
JOIN synthetic_occupancy AS o ON o.run_id = p.run_id AND o.step = p.step
GROUP BY p.policy_id;
