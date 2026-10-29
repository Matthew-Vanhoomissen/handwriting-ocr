# Frontend

Vite + React (JavaScript). One page: create or pick an assignment, add its questions (each with its own points and test cases), upload a photo to a question, watch its status, and compare the photo with the transcription, the corrected code, and the test results.

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

**Mock mode** (`src/mockApi.js`): nothing leaves the browser. Assignments, questions, and test cases are kept in memory and reset on reload. It starts with one assignment holding three questions (the third is untitled, to show the "Question N" fallback) and a few finished submissions. Each upload moves through `queued` (about 2.5s), then `processing` (about 5s), then a final state. You pick the final state from the "Mock scenario" dropdown:
- ready, no corrected code
- ready, syntax error + corrected code
- error

Mock images are placeholders in `public/mock/`. The photo you upload is ignored, but its file type is checked like the backend does (jpg, png, webp). The mock fakes test results against the question's current test cases: "ready, no corrected code" always prints `5` (so it passes some tests and fails others), and "syntax error" fails every test with a traceback. Scores follow the backend's formula.

**Real mode**: start Flask on port 5000 first. The Vite dev proxy forwards `/api/*` to `http://localhost:5000` (see `vite.config.js`), so the browser makes same-origin requests and Flask needs no CORS setup. The frontend never talks to the Meta API and never sees `MODEL_API_KEY`.

## Files

- `src/api.js`: the mock/real switch and the fetch calls for assignments, questions, test cases, and submissions
- `src/mockApi.js`: mock responses, shaped exactly like the contract in CLAUDE.md section 12 (which mirrors `backend/app.py`)
- `src/format.js`: `questionLabel` ("Q2. Title", or "Question 2" when the title is empty) and points formatting
- `src/callApi.js`: shared call-and-report helper for the setup panels (feeds Raw JSON, sets the panel's error)
- `src/App.jsx`: owns the assignment list, the selected assignment's detail and selected question, the upload form, polling (every 1.5s, stops at `ready`, `graded`, or `error`), the review layout, and deleting the open submission
- `src/components/AssignmentTabs.jsx`: tab bar across the top for switching assignments; "+ New assignment" opens the create form
- `src/components/AssignmentPanel.jsx`: left setup panel; the assignment's question count and total points, its question list (click to select, "+ Add question"), delete, and the create-assignment form
- `src/components/QuestionPanel.jsx`: right setup panel; the selected question's points, match mode, prompt, delete, and test cases (add/delete), or the add-question form
- `src/components/SubmissionList.jsx`: right-hand sidebar listing the selected question's submissions; click one to open it, "Hide" collapses it to a tab. Refreshes every 3s while any submission is queued or processing.
- `src/components/TestResults.jsx`: per-test table under the photo and code (input, expected, actual, score, pass/fail) with the total. Each test is worth the question's `max_points / number of tests`; the total is the backend's `suggested_score`.
- `src/components/CodeBlock.jsx`: code with line numbers; highlights the lines in `flags.uncertain_lines` (1-indexed)
- `src/components/ConfirmDialog.jsx`: modal confirmation (native `<dialog>`) shown before deleting an assignment, question, or submission

New components go in `src/components/`.

## Debugging

The "Raw JSON" section at the bottom shows the last response body and which request produced it. If the page looks wrong but the JSON looks right, the bug is in the frontend. If the JSON is wrong, the bug is in the backend. If a request fails (for example a non-2xx status or Flask not running), the page shows a red banner and stops polling.
