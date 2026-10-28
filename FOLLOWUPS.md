# Follow-ups

Known issues to look into later. Nothing here blocks the current slice.

## Flags (`backend/transcribe.py`, `backend/pipeline.py`)

- **Stale `uncertain_lines` after Re-run.** `rerun_submission` recomputes `static_flags` for the edited code but keeps the model's `uncertain_lines` from the original transcription. If the professor adds or removes a line, those line numbers point at the wrong rows and the review page would highlight the wrong lines. Options: drop them on rerun, mark them as "from original transcription", or match them by the `chosen` text instead of the line number.
- **False positive on `except ... as e`.** `static_flags` never registers the name bound by an except clause (it is stored on `ast.ExceptHandler.name` as a string, not as an `ast.Name`), so any later use of `e` is flagged "used but never assigned". Fix: add `ExceptHandler` names to the bound set. Same gap for names bound by `match` patterns (`MatchAs`, `MatchStar`, `MatchMapping` rest), which matters less for CS221.
- **Duplicate flags.** An unassigned name used three times produces three flags. Consider one flag per name, listing all its lines.
- **No scoping.** A name assigned anywhere counts as defined everywhere, so use-before-assignment and use outside the defining function are not caught. Acceptable for now, since the sandbox run surfaces those as errors.
- **Only the first syntax error is reported.** `ast.parse` stops at the first error, and then the name check does not run at all. Fine for now, but a transcription with two misread colons will only show one.
- **Flags only reflect what the model wrote.** `uncertain_lines` is the model's self-assessment, so a confident misread produces no entry. Verdict accuracy in the evaluation step should measure how often this happens.

## API

- **404s return HTML.** `abort(404)` returns Flask's HTML error page, while 400s return `{"error": ...}`. A JSON 404 handler would make frontend error messages consistent.
