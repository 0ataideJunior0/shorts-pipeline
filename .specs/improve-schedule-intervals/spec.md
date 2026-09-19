# Specification: Improve Schedule Intervals (Issue #3)

## Problem
Currently, the publishing cadence in `shorts/publish.py` and the Web UI only supports scheduling videos at fixed hourly intervals (`start` datetime + `k * interval_hours`). When a user wants to publish multiple videos per day (e.g. 2 or 3 videos/day), fixed intervals (such as every 8 or 12 hours) inevitably push scheduled publish times into non-viable off-hours (e.g., 22:00 to 08:00). 

Users need the ability to specify the number of videos per day and configure specific, desirable publishing hours (e.g., 10:00, 14:00, 19:00) while retaining the ability to restrict publishing to certain weekdays.

## Goals / Non-goals
### Goals
- Allow users in the Web UI to define daily publishing time slots (e.g., 2 videos/day at 10:00 and 18:00) instead of only a uniform hour interval.
- Extend `resolve_schedule` in `shorts/publish.py` to support daily time slots (`times`) alongside existing weekday filtering and manual overrides.
- Maintain full backward compatibility for existing manifests and projects configured with `interval_hours`.
- Update the Web UI cadence section in `shorts/web/static/index.html` to let users view, add, remove, and edit daily time slots, and save the updated schedule.
- Update `PUT /api/projects/<name>/publish/cadence` in `shorts/web/app.py` to validate and store daily time slots.
- Ensure slot allocation skips times that are in the past relative to `not_before` or already taken by other videos.

### Non-goals
- Varying hours per weekday (e.g., different slot hours for Saturday vs. Monday); all active weekdays share the configured daily slot times.
- Automated algorithmic audience peak-time prediction.
- Modifying the underlying YouTube upload or authentication mechanism.

## Requirements

### R1 (Manifest Schema & Cadence Representation)
- `cadence` supports an optional `times` field containing a list of `HH:MM` 24-hour time strings (e.g. `["10:00", "14:00", "19:00"]`).
- `start` remains the anchor datetime for scheduling (ISO format).
- If `times` is present and non-empty, `resolve_schedule` uses daily time slot scheduling. If `times` is omitted or empty, `resolve_schedule` falls back to `interval_hours`.
- `cadence_from_manifest` in `shorts/publish.py` parses `times` (cleaned and sorted chronologically) alongside `start`, `interval_hours`, and `weekdays`.

### R2 (Schedule Resolution Algorithm with Daily Slots)
- In `shorts/publish.py:resolve_schedule`:
  - When `cadence["times"]` is provided:
    - Candidate slots are generated day by day starting from `start.date()`.
    - If a day's weekday (`slot_date.isoweekday()`) is not in `weekdays` (when `weekdays` is specified), the entire day is skipped.
    - On each active day, candidate datetime slots are constructed for each time in `times` (using the timezone of `start`).
    - Any slot with `slot <= not_before` (or `slot < start`) is skipped.
    - Any slot already in `taken` or previously assigned in the current run is skipped.
    - Eligible candidates are assigned sequentially to pending slugs.
    - Explicit per-idea overrides in `overrides` continue to take precedence.
    - A safety cap (similar to `_K_CAP`) prevents infinite loops if no valid slots are available.

### R3 (Web API Validation & Cadence Update)
- `PUT /api/projects/<name>/publish/cadence`:
  - Accepts `times`: a list of strings matching format `^([01]\d|2[0-3]):[0-5]\d$`.
  - Rejects invalid formats or non-list values with HTTP 422 (`"times must be a list of HH:MM strings"`).
  - Accepts `start` (ISO datetime) and optional `weekdays` (list of integers 1..7).
  - Continues to accept `interval_hours` (integer > 0) when `times` is not provided.
  - Updates `manifest.publish` via `manifest.set_publish(...)` and persists to `manifest.json`.
  - Returns the updated `publish_queue(project, config)` JSON response.

### R4 (Web UI Schedule Interval Configuration)
- In `shorts/web/static/index.html`:
  - The cadence editor displays the start date/time, active weekday checkboxes, and the daily time slots.
  - Users can see their configured daily times as editable time inputs (`<input type="time">`).
  - Users can dynamically add a new time slot (e.g., "+ Add time") or remove existing slots.
  - Saving the schedule sends `{ start, times, weekdays }` to the cadence PUT API.
  - On page load / refresh, existing `times` from the project's cadence are loaded into the slot editor. If the project only has legacy `interval_hours`, the UI gracefully reflects it or defaults to sensible daily hours.

### R5 (Automated Test Coverage)
- Unit tests in `tests/test_publish.py`:
  - `test_resolve_schedule_with_daily_times_basic`: verifies sequential assignment across multiple slots in a single day and across days.
  - `test_resolve_schedule_with_daily_times_weekdays`: verifies skipping inactive weekdays.
  - `test_resolve_schedule_with_daily_times_not_before`: verifies past slots on the current day are skipped and next valid slot is picked.
  - `test_resolve_schedule_with_daily_times_taken_and_overrides`: verifies taken slots and manual overrides are respected.
  - Existing tests for legacy `interval_hours` continue to pass without regressions.
- Integration/API tests in `tests/test_web_app.py`:
  - `test_put_cadence_with_daily_times`: verifies saving `times` via API and retrieving in `publish_queue`.
  - `test_put_cadence_invalid_times`: verifies 422 status on invalid time formats.

## Acceptance Criteria
- **AC1**: `resolve_schedule` with `cadence = {"start": dt, "times": ["10:00", "18:00"], "weekdays": [1, 2, 3, 4, 5]}` schedules 3 items across the first eligible slots (e.g. Day 1 10:00, Day 1 18:00, Day 2 10:00), verified by pytest in `tests/test_publish.py`.
- **AC2**: `resolve_schedule` with `not_before` set to 12:00 on Day 1 skips the 10:00 slot and assigns the 18:00 slot as the first slot, verified by pytest in `tests/test_publish.py`.
- **AC3**: Legacy cadence configs with `interval_hours` without `times` produce identical results as before, verified by existing tests in `tests/test_publish.py`.
- **AC4**: `PUT /api/projects/<name>/publish/cadence` with payload `{"start": "2026-09-20T10:00:00Z", "times": ["10:00", "14:00", "19:00"], "weekdays": [1, 2, 3]}` returns HTTP 200 with the new cadence present in the response, verified in `tests/test_web_app.py`.
- **AC5**: `PUT /api/projects/<name>/publish/cadence` with payload `{"start": "2026-09-20T10:00:00Z", "times": ["99:99"]}` returns HTTP 422, verified in `tests/test_web_app.py`.
- **AC6**: The Web UI in `index.html` renders interactive time controls allowing addition, editing, and deletion of daily time slots and successfully saves them.
- **AC7**: All tests pass: `python -m pytest tests/`.

## Constraints
- Stack: Python 3.10+, Click, Flask, HTML/Vanilla JS.
- Backward compatibility: Manifests with legacy `interval_hours` must remain valid and operational without migration scripts.
- Timezone integrity: Dates and times must maintain timezone awareness (UTC / ISO 8601).
- Zero external dependency additions: No new libraries required.

## Open Questions
*(None)*

