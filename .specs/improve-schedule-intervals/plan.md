# Implementation Plan: Improve Schedule Intervals

### T1: Update Manifest Schema & Cadence Representation
- Covers: R1
- Files: `shorts/publish.py`
- Depends on: none
- Parallel-safe: yes
- Steps: 
  - Modify `cadence_from_manifest` in `shorts/publish.py` to support the new optional `times` field.
  - Parse `times` as a list of `HH:MM` strings, clean and sort them chronologically.
  - Ensure it still parses `interval_hours` if `times` is absent.
- Done when: `python -m pytest tests/test_publish.py` passes without breaking existing tests.

### T2: Implement Daily Slots Schedule Resolution
- Covers: R2, R5, AC1, AC2, AC3
- Files: `shorts/publish.py`, `tests/test_publish.py`
- Depends on: T1
- Parallel-safe: no
- Steps:
  - In `shorts/publish.py`, update `resolve_schedule` to use daily time slots when `cadence["times"]` is provided.
  - Generate candidate slots day by day starting from `start.date()`. Skip skipped weekdays.
  - For each active day, create datetime slots for each time in `times` (applying `start`'s timezone).
  - Skip slots that are `<= not_before`, `< start`, or already taken.
  - Assign valid slots sequentially and respect overrides. Add safety loop cap.
  - Add test functions to `tests/test_publish.py` (`test_resolve_schedule_with_daily_times_basic`, `test_resolve_schedule_with_daily_times_weekdays`, `test_resolve_schedule_with_daily_times_not_before`, `test_resolve_schedule_with_daily_times_taken_and_overrides`).
- Done when: `python -m pytest tests/test_publish.py` passes with all new daily times and legacy interval tests successful.

### T3: Update Web API Validation & Route
- Covers: R3, R5, AC4, AC5
- Files: `shorts/web/app.py`, `tests/test_web_app.py`
- Depends on: none
- Parallel-safe: yes
- Steps:
  - In `shorts/web/app.py`'s `PUT /api/projects/<name>/publish/cadence`, accept `times` parameter.
  - Validate `times` using regex `^([01]\d|2[0-3]):[0-5]\d$`.
  - Return HTTP 422 with message `"times must be a list of HH:MM strings"` if format is invalid.
  - Save valid `times` (and `start`/`weekdays`) via `manifest.set_publish(...)` and update `manifest.json`. Maintain `interval_hours` logic for legacy setups.
  - Write integration tests in `tests/test_web_app.py`: `test_put_cadence_with_daily_times`, `test_put_cadence_invalid_times`.
- Done when: `python -m pytest tests/test_web_app.py` passes successfully.

### T4: Update Web UI for Schedule Interval Configuration
- Covers: R4, AC6
- Files: `shorts/web/static/index.html`
- Depends on: T3
- Parallel-safe: no
- Steps:
  - Update the cadence editor section to display daily time slots alongside start time and active weekday checkboxes.
  - Render an array of `<input type="time">` fields based on `times` from the fetched configuration.
  - Implement dynamic UI controls to add ("+ Add time") or remove daily time slots.
  - Ensure the save action builds the `{ start, times, weekdays }` payload and posts it to the cadence API.
  - Gracefully handle the display and fallback for legacy configs relying on `interval_hours` (e.g., convert or show fallback).
- Done when: Opening the web UI displays the time slots list, adding/removing them updates the UI, and saving successfully invokes the API.
