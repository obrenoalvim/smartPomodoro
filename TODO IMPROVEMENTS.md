# TODO Improvements

### Add pomodoro_windows.py to CI lint job
- **Category:** Refactor
- **What:** `.github/workflows/ci.yml` only runs `flake8` against `pomodoro_linux.py`. `pomodoro_windows.py` (the file most users on the primary platform actually run) has no automated check at all — the recent `int | None` Python 3.8/3.9 incompatibility bug would not have been caught even with lint running, but a basic `py_compile`/flake8 step would catch syntax-level regressions.
- **Where:** `.github/workflows/ci.yml`
- **Why:** Left out of this pass — editing CI counts as restructuring, which was out of scope for this change.
- **Risk:** Low — additive CI step.
- **Effort:** Low

### No automated tests for TimerEngine / SessionStore logic
- **Category:** Test
- **What:** The state-machine logic in `TimerEngine` (focus → extension → rest transitions, pause/resume) and the pure calculation logic in `SessionStore.get_stats()` (streak counting, 7-day bucketing, calibration suggestion) are the most bug-prone parts of the app and have zero test coverage. They're logic-only (no real mouse/keyboard/tray I/O) and could be unit tested with stdlib `unittest` + an in-memory SQLite DB without adding a dependency.
- **Where:** `pomodoro_windows.py` / `pomodoro_linux.py` — `SessionStore`, `TimerEngine`
- **Why:** Queued rather than added directly — both files import `tkinter` unconditionally at module scope, so a test importing either module needs a working Tk install; that isn't guaranteed on the current CI runner (`ubuntu-latest` without `python3-tk`) or this headless environment, and there's no existing test job to verify the tests would actually run anywhere. Wiring that up safely means either refactoring the pure logic out of the Tk-coupled modules or extending CI — both are structural changes.
- **Risk:** N/A (not applied)
- **Effort:** Medium

### Streak/stats math assumes 5-minute-granularity habits
- **Category:** UI-UX
- **What:** `SessionStore.get_stats()` suggests rounding focus time to the nearest 5 minutes (`round(avg_real / 5) * 5`). This is a product/UX call (not a bug) — worth a deliberate look if user feedback ever suggests the suggested value feels too coarse or too aggressive.
- **Where:** `pomodoro_windows.py:206-210`, `pomodoro_linux.py:204-208` (`get_stats`)
- **Why:** Noted while reading the stats/suggestion feature; not a defect, just a design decision worth revisiting later.
- **Risk:** N/A
- **Effort:** Low
