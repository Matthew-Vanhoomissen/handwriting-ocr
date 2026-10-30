"""Flask routes for assignments, questions, tests, uploads, and submissions.

An assignment holds questions; each question holds its own test cases and
submissions. Submission routes are keyed by submission id alone.

Run with: python -m backend.app  (starts the API and the worker thread)
"""

import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

from backend import db, worker
from backend.pipeline import rerun_submission, rescore_question
from backend.scoring import suggest_score

UPLOAD_DIR = db.DATA_DIR / "uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


def _bad_request(message):
    return jsonify({"error": message}), 400


def _assignment_or_404(assignment_id):
    assignment = db.get_assignment(assignment_id)
    if not assignment:
        abort(404)
    return assignment


def _question_or_404(question_id):
    question = db.get_question(question_id)
    if not question:
        abort(404)
    return question


def _submission_or_404(submission_id):
    sub = db.get_submission(submission_id)
    if not sub:
        abort(404)
    return sub


def _question_with_tests(question):
    question["test_cases"] = db.list_test_cases(question["id"])
    return question


def _delete_upload(image_path):
    """Remove an uploaded photo. Files outside UPLOAD_DIR are left alone.

    Submissions created from the CLI point at photos in samples/, which must
    survive deleting the submission.
    """
    if not image_path:
        return
    path = Path(image_path).resolve()
    if path.is_relative_to(UPLOAD_DIR.resolve()):
        path.unlink(missing_ok=True)


# Assignments

@app.post("/api/assignments")
def create_assignment():
    body = request.get_json(silent=True) or {}
    if not body.get("title"):
        return _bad_request("title is required")
    assignment_id = db.create_assignment(body["title"],
                                         body.get("language", "python"))
    return jsonify(_assignment_detail(assignment_id)), 201


@app.get("/api/assignments")
def list_assignments():
    return jsonify(db.list_assignments())


@app.get("/api/assignments/<int:assignment_id>")
def get_assignment(assignment_id):
    return jsonify(_assignment_detail(assignment_id))


def _assignment_detail(assignment_id):
    """Assignment with its questions in order, each with its test cases."""
    assignment = _assignment_or_404(assignment_id)
    assignment["questions"] = [_question_with_tests(q) for q in
                               db.list_questions(assignment_id)]
    return assignment


@app.delete("/api/assignments/<int:assignment_id>")
def delete_assignment(assignment_id):
    for image_path in db.delete_assignment(assignment_id):
        _delete_upload(image_path)
    return "", 204


# Questions

@app.post("/api/assignments/<int:assignment_id>/questions")
def create_question(assignment_id):
    _assignment_or_404(assignment_id)
    body = request.get_json(silent=True) or {}
    try:
        max_points = float(body["max_points"])
    except (KeyError, TypeError, ValueError):
        return _bad_request("max_points must be a number")
    position = body.get("position")
    if position is not None and not isinstance(position, int):
        return _bad_request("position must be an integer")
    question_id = db.create_question(
        assignment_id, max_points, title=body.get("title", ""),
        prompt=body.get("prompt", ""),
        exact_match=bool(body.get("exact_match", False)), position=position)
    return jsonify(_question_with_tests(db.get_question(question_id))), 201


@app.get("/api/questions/<int:question_id>")
def get_question(question_id):
    return jsonify(_question_with_tests(_question_or_404(question_id)))


@app.patch("/api/questions/<int:question_id>")
def update_question(question_id):
    """Edit any of title, prompt, max_points, exact_match.

    Other keys (id, position, test_cases, ...) are ignored, so the frontend
    can send back the whole question object.
    """
    question = _question_or_404(question_id)
    body = request.get_json(silent=True) or {}
    fields = {}
    for name in ("title", "prompt"):
        if name in body:
            if not isinstance(body[name], str):
                return _bad_request(f"{name} must be a string")
            fields[name] = body[name]
    if "max_points" in body:
        try:
            fields["max_points"] = float(body["max_points"])
        except (TypeError, ValueError):
            return _bad_request("max_points must be a number")
    if "exact_match" in body:
        fields["exact_match"] = int(bool(body["exact_match"]))
    if not fields:
        return _bad_request(
            "nothing to update (title, prompt, max_points, exact_match)")

    db.update_question(question_id, **fields)
    if any(fields.get(k, question[k]) != question[k]
           for k in ("max_points", "exact_match")):
        rescore_question(question_id)
    return jsonify(_question_with_tests(db.get_question(question_id)))


@app.delete("/api/questions/<int:question_id>")
def delete_question(question_id):
    for image_path in db.delete_question(question_id):
        _delete_upload(image_path)
    return "", 204


# Test cases

@app.post("/api/questions/<int:question_id>/tests")
def add_test_case(question_id):
    _question_or_404(question_id)
    body = request.get_json(silent=True) or {}
    if "expected_output" not in body:
        return _bad_request("expected_output is required")
    test_id = db.add_test_case(question_id, body.get("input", ""),
                               body["expected_output"])
    return jsonify({"id": test_id}), 201


@app.delete("/api/tests/<int:test_case_id>")
def delete_test_case(test_case_id):
    db.delete_test_case(test_case_id)
    return "", 204


# Uploads and submissions

@app.post("/api/questions/<int:question_id>/submissions")
def upload_submissions(question_id):
    """Multipart upload: one or more 'files', optional matching 'labels'.

    One photo per student for this question. Labels default to the file
    name. Use anonymized labels, not real names.
    """
    _question_or_404(question_id)
    files = request.files.getlist("files")
    labels = request.form.getlist("labels")
    if not files:
        return _bad_request("no files uploaded (field name: files)")
    for f in files:
        if Path(f.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
            return _bad_request(f"{f.filename}: use jpg, png, or webp")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    created = []
    for i, f in enumerate(files):
        suffix = Path(f.filename).suffix.lower()
        path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        f.save(path)
        label = labels[i] if i < len(labels) and labels[i] else \
            Path(f.filename).stem
        created.append(db.create_submission(question_id, label, str(path)))
    return jsonify({"submission_ids": created}), 201


@app.get("/api/questions/<int:question_id>/submissions")
def list_submissions(question_id):
    _question_or_404(question_id)
    return jsonify(db.list_submissions(question_id))


@app.get("/api/submissions/<int:submission_id>")
def get_submission(submission_id):
    sub = _submission_or_404(submission_id)
    question = db.get_question(sub["question_id"])
    assignment = db.get_assignment(question["assignment_id"])
    results = db.list_test_results(submission_id)
    original = [r for r in results if r["version"] == "original"]
    _, reasoning = suggest_score(question["max_points"],
                                 sum(r["passed"] for r in original),
                                 len(original))
    sub.pop("image_path")
    sub["question"] = question
    sub["assignment"] = assignment
    sub["test_results"] = results
    sub["score_reasoning"] = reasoning if original else None
    return jsonify(sub)


@app.get("/api/submissions/<int:submission_id>/image")
def submission_image(submission_id):
    return send_file(_submission_or_404(submission_id)["image_path"])


@app.post("/api/submissions/<int:submission_id>/rerun")
def rerun(submission_id):
    """Re-run tests on code the professor edited (e.g. a fixed misread)."""
    _submission_or_404(submission_id)
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("code"), str):
        return _bad_request("code is required")
    rerun_submission(submission_id, body["code"])
    return get_submission(submission_id)


@app.post("/api/submissions/<int:submission_id>/requeue")
def requeue(submission_id):
    """Send a submission back through the worker, e.g. after an error."""
    _submission_or_404(submission_id)
    db.update_submission(submission_id, status="queued", error_message=None)
    return "", 204


@app.post("/api/submissions/<int:submission_id>/grade")
def grade(submission_id):
    _submission_or_404(submission_id)
    body = request.get_json(silent=True) or {}
    try:
        final_score = float(body["final_score"])
    except (KeyError, TypeError, ValueError):
        return _bad_request("final_score must be a number")
    db.update_submission(submission_id, final_score=final_score,
                         notes=body.get("notes"), status="graded")
    return get_submission(submission_id)


@app.delete("/api/submissions/<int:submission_id>")
def delete_submission(submission_id):
    _delete_upload(db.delete_submission(submission_id))
    return "", 204


def main():
    db.init_db()
    worker.start()
    # The reloader would start a second worker thread, so keep it off.
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
