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
python -m backend.pipeline <image> <assignment_id>        # one submission, CLI
```

Runtime data (SQLite db, uploaded photos, API response cache) lives in
`backend/data/`, which is gitignored.

## API

| Method | Route | Body |
|---|---|---|
| POST | `/api/assignments` | `{title, max_points, prompt?, exact_match?}` |
| GET | `/api/assignments`, `/api/assignments/<id>` | |
| POST | `/api/assignments/<id>/tests` | `{input, expected_output}` |
| DELETE | `/api/tests/<id>` | |
| POST | `/api/assignments/<id>/submissions` | multipart `files`, optional `labels` |
| GET | `/api/assignments/<id>/submissions` | |
| GET | `/api/submissions/<id>`, `/api/submissions/<id>/image` | |
| POST | `/api/submissions/<id>/rerun` | `{code}` |
| POST | `/api/submissions/<id>/requeue` | |
| POST | `/api/submissions/<id>/grade` | `{final_score, notes?}` |
| GET | `/api/assignments/<id>/export.csv` | |

## Sandbox

Student code runs in a fresh Docker container per test case
(`python:3.12-slim`): no network, 256 MB memory, 1 CPU, 64 processes,
read-only filesystem, no capabilities, unprivileged user, 5 s time limit.
Docker Desktop must be running; if it isn't, submissions go to `error`
instead of running on the host.

`SANDBOX=subprocess` switches to a host subprocess runner for quick local
checks. It has a timeout but no network or memory isolation, so use it only
with your own samples.
