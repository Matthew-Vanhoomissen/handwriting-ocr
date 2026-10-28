"""Flask routes for assignments, tests, uploads, submissions, and grades.

Also serves CSV export.

Run with: python -m backend.app  (starts the API and the worker thread)
"""

import csv
import io
import uuid
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file

from backend import db, worker
from backend.pipeline import rerun_submission
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


def _submission_or_404(submission_id):
    sub = db.get_submission(submission_id)
    if not sub:
        abort(404)
    return sub


# Assignments and test cases

@app.post("/api/assignments")
def create_assignment():
    body = request.get_json(silent=True) or {}
    if not body.get("title") or body.get("max_points") is None:
        return _bad_request("title and max_points are required")
    try:
        max_points = float(body["max_points"])
    except (TypeError, ValueError):
        return _bad_request("max_points must be a number")
    assignment_id = db.create_assignment(
        body["title"], body.get("prompt", ""), max_points,
        bool(body.get("exact_match", False)))
    return jsonify(db.get_assignment(assignment_id)), 201


@app.get("/api/assignments")
def list_assignments():
    return jsonify(db.list_assignments())


@app.get("/api/assignments/<int:assignment_id>")
def get_assignment(assignment_id):
    assignment = _assignment_or_404(assignment_id)
    assignment["test_cases"] = db.list_test_cases(assignment_id)
    return jsonify(assignment)


@app.post("/api/assignments/<int:assignment_id>/tests")
def add_test_case(assignment_id):
    _assignment_or_404(assignment_id)
    body = request.get_json(silent=True) or {}
    if "expected_output" not in body:
        return _bad_request("expected_output is required")
    test_id = db.add_test_case(assignment_id, body.get("input", ""),
                               body["expected_output"])
    return jsonify({"id": test_id}), 201


@app.delete("/api/tests/<int:test_case_id>")
def delete_test_case(test_case_id):
    db.delete_test_case(test_case_id)
    return "", 204


# Uploads and submissions

@app.post("/api/assignments/<int:assignment_id>/submissions")
def upload_submissions(assignment_id):
    """Multipart upload: one or more 'files', optional matching 'labels'.

    Labels default to the file name. Use anonymized labels, not real names.
    """
    _assignment_or_404(assignment_id)
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
        created.append(db.create_submission(assignment_id, label, str(path)))
    return jsonify({"submission_ids": created}), 201


@app.get("/api/assignments/<int:assignment_id>/submissions")
def list_submissions(assignment_id):
    _assignment_or_404(assignment_id)
    return jsonify(db.list_submissions(assignment_id))


@app.get("/api/submissions/<int:submission_id>")
def get_submission(submission_id):
    sub = _submission_or_404(submission_id)
    assignment = db.get_assignment(sub["assignment_id"])
    results = db.list_test_results(submission_id)
    original = [r for r in results if r["version"] == "original"]
    _, reasoning = suggest_score(assignment["max_points"],
                                 sum(r["passed"] for r in original),
                                 len(original))
    sub.pop("image_path")
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


@app.get("/api/assignments/<int:assignment_id>/export.csv")
def export_csv(assignment_id):
    assignment = _assignment_or_404(assignment_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_label", "status", "suggested_score",
                     "final_score", "max_points", "verdict", "notes"])
    for s in db.list_submissions(assignment_id):
        notes = db.get_submission(s["id"])["notes"]
        writer.writerow([s["student_label"], s["status"],
                         s["suggested_score"], s["final_score"],
                         assignment["max_points"], s["verdict"], notes])
    filename = f"assignment_{assignment_id}_grades.csv"
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f"attachment; filename={filename}"})


def main():
    db.init_db()
    worker.start()
    # The reloader would start a second worker thread, so keep it off.
    app.run(port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
