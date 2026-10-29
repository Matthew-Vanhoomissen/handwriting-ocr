# Frontend

Vite + React (JavaScript). One page: create or pick an assignment, manage its test cases, upload a photo to it, watch its status, and compare the photo with the transcription and the corrected code.

## Run

```
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173.

## Mock vs real backend

One flag in `frontend/.env.development` controls this:

```
VITE_USE_MOCK=true    # in-browser mock, no backend needed (current default)
VITE_USE_MOCK=false   # real Flask API
```

Restart `npm run dev` after changing it. Vite only reads `.env` files at startup.

**Mock mode** (`src/mockApi.js`): nothing leaves the browser. Assignments and test cases are kept in memory, seeded with one sample assignment, and reset on reload. Each upload moves through `queued` (about 2.5s), then `processing` (about 5s), then a final state. You pick the final state from the "Mock scenario" dropdown:
- ready, no corrected code
- ready, syntax error + corrected code
- error

Mock images are placeholders in `public/mock/`. The photo you upload is ignored, but its file type is checked like the backend does (jpg, png, webp). The mock fakes test results against the assignment's current test cases: "ready, no corrected code" always prints `5` (so it passes some tests and fails others), and "syntax error" fails every test with a traceback. Scores follow the backend's formula.

**Real mode**: start Flask on port 5000 first. The Vite dev proxy forwards `/api/*` to `http://localhost:5000` (see `vite.config.js`), so the browser makes same-origin requests and Flask needs no CORS setup. The frontend never talks to the Meta API and never sees `MODEL_API_KEY`.

## Files

- `src/api.js`: the mock/real switch and the fetch calls for assignments, test cases, and submissions
- `src/mockApi.js`: mock responses, shaped exactly like the contract in CLAUDE.md section 12 (which mirrors `backend/app.py`)
- `src/App.jsx`: owns the assignment list, upload form, polling (every 1.5s, stops at `ready`, `graded`, or `error`), the review layout, and deleting the open submission
- `src/components/AssignmentTabs.jsx`: tab bar across the top for switching assignments; "+ New assignment" opens the create form
- `src/components/AssignmentSetup.jsx`: the selected assignment's details, create form, and delete; plus the test case list with add and delete
- `src/components/SubmissionList.jsx`: right-hand sidebar listing the assignment's submissions; click one to open it, "Hide" collapses it to a tab. Refreshes every 3s while any submission is queued or processing.
- `src/components/TestResults.jsx`: per-test table under the photo and code (input, expected, actual, score, pass/fail) with the total. Each test is worth `max_points / number of tests`; the total is the backend's `suggested_score`.
- `src/components/CodeBlock.jsx`: code with line numbers; highlights the lines in `flags.uncertain_lines` (1-indexed)
- `src/components/ConfirmDialog.jsx`: modal confirmation (native `<dialog>`) shown before deleting an assignment or submission

New components go in `src/components/`.

## Debugging

The "Raw JSON" section at the bottom shows the last response body and which request produced it. If the page looks wrong but the JSON looks right, the bug is in the frontend. If the JSON is wrong, the bug is in the backend. If a request fails (for example a non-2xx status or Flask not running), the page shows a red banner and stops polling.
