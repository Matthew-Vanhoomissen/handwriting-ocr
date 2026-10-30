# Handwritten Code Grading Assistant

Helps TAs and professors grade handwritten Python programs. Photos are transcribed with
Muse Spark (Meta Model API), run in a sandbox against professor-supplied test cases, and
failed tests are re-checked to separate transcription misreads from genuine student bugs.
The professor reviews every submission and makes the final call.

## Layout

```
backend/     Flask app, worker, and the grading pipeline
frontend/    React review UI
samples/     handwritten test photos + typed ground-truth .py files (no real student work)
eval/        evaluation script and results
tests/       pytest tests
```

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then set MODEL_API_KEY
```

## Running

```
python -m backend.app          # API on http://127.0.0.1:5000 plus the worker
python -m pytest tests         # sandbox and API tests (no model calls)
python -m backend.transcribe samples/simple_python1.jpg   # one transcription
python -m backend.pipeline <image> <question_id>          # one submission, CLI
```

Runtime data (SQLite db, uploaded photos, API response cache) lives in
`backend/data/`, which is gitignored.

## Data model

An assignment has questions. Each question has its own points, test cases,
and submissions (one photo per student per question). SQLite, five tables:

| Table | Columns |
|---|---|
| `assignments` | id, title, language |
| `questions` | id, assignment_id, position, title, prompt, max_points, exact_match |
| `test_cases` | id, question_id, input, expected_output |
| `submissions` | id, question_id, student_label, image_path, status, transcription, corrected_code, verdict, suggested_score, final_score, notes, flags, error_message |
| `test_results` | id, submission_id, test_case_id, version, passed, actual_output, error |

- An assignment's `total_points` is the sum of its questions' `max_points`,
  computed on read rather than stored.
- `status` is `queued`, `processing`, `ready`, `graded`, or `error`.
- `version` is `original` or `corrected` (the syntax-fix toggle).
- `flags` is JSON: the model's `uncertain_lines` plus the `ast` static checks.

## API

| Method | Route | Body |
|---|---|---|
| POST | `/api/assignments` | `{title, language?}` |
| GET | `/api/assignments`, `/api/assignments/<id>` | |
| DELETE | `/api/assignments/<id>` | |
| POST | `/api/assignments/<id>/questions` | `{max_points, title?, prompt?, exact_match?, position?}` |
| GET, DELETE | `/api/questions/<id>` | |
| PATCH | `/api/questions/<id>` | any of `{title, prompt, max_points, exact_match}` |
| POST | `/api/questions/<id>/tests` | `{input, expected_output}` |
| DELETE | `/api/tests/<id>` | |
| POST | `/api/questions/<id>/submissions` | multipart `files`, optional `labels` |
| GET | `/api/questions/<id>/submissions` | |
| GET, DELETE | `/api/submissions/<id>` | |
| GET | `/api/submissions/<id>/image` | |
| POST | `/api/submissions/<id>/rerun` | `{code}` |
| POST | `/api/submissions/<id>/requeue` | |
| POST | `/api/submissions/<id>/grade` | `{final_score, notes?}` |

Deleting an assignment or question also deletes everything under it,
including uploaded photos. Changing a question's `max_points` or
`exact_match` re-scores its submissions from the stored outputs (no code is
re-run); final scores already given are kept. CSV export is not implemented
yet.

## Sandbox

Student code runs in a fresh Docker container per test case
(`python:3.12-slim`): no network, 256 MB memory, 1 CPU, 64 processes,
read-only filesystem, no capabilities, unprivileged user, 5 s time limit.
Docker Desktop must be running; if it isn't, submissions go to `error`
instead of running on the host.

`SANDBOX=subprocess` switches to a host subprocess runner for quick local
checks. It has a timeout but no network or memory isolation, so use it only
with your own samples.
