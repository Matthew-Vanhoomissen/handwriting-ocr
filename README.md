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
