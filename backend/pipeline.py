"""Process one submission end to end: transcribe, run tests, score.

Shared by the worker and the command line. Failure investigation (agent.py)
plugs in here later.

Usage: python -m backend.pipeline <image> <question_id> [student_label]
"""

import sys
from pathlib import Path

from backend import db
from backend.sandbox import outputs_match, run_code
from backend.scoring import suggest_score
from backend.transcribe import static_flags, transcribe


def run_tests(code, test_cases, exact_match=False):
    """Run code against each test case. Returns a list of result dicts."""
    results = []
    for tc in test_cases:
        run = run_code(code, stdin=tc["input"])
        if run["timed_out"]:
            error = "Timed out"
        elif run["exit_code"] != 0:
            error = run["stderr"].strip() or f"Exit code {run['exit_code']}"
        else:
            error = None
        passed = error is None and outputs_match(
            run["stdout"], tc["expected_output"], exact=exact_match)
        results.append({"test_case_id": tc["id"], "passed": passed,
                        "actual_output": run["stdout"], "error": error})
    return results


def _score(question, results):
    """Suggested score and verdict from one version's test results."""
    passed = sum(r["passed"] for r in results)
    score, _ = suggest_score(question["max_points"], passed, len(results))
    # Until failure investigation exists, failed submissions get no verdict.
    verdict = "pass" if results and passed == len(results) else None
    return score, verdict


def _grade(submission_id, question, code):
    """Run tests on code, store results, and set the suggested score."""
    tests = db.list_test_cases(question["id"])
    results = run_tests(code, tests, bool(question["exact_match"]))
    db.replace_test_results(submission_id, "original", results)
    return _score(question, results)


def rescore_question(question_id):
    """Update stored results and scores after a question's points or
    exact_match setting changes.

    No code runs: pass/fail is re-checked against the saved actual_output
    and error. Final scores the professor already set are left alone.
    """
    question = db.get_question(question_id)
    exact = bool(question["exact_match"])
    for sub in db.list_submissions(question_id):
        results = db.list_test_results(sub["id"])
        if not results:
            continue
        for r in results:
            r["passed"] = r["error"] is None and outputs_match(
                r["actual_output"], r["expected_output"], exact=exact)
        for version in {r["version"] for r in results}:
            db.replace_test_results(
                sub["id"], version,
                [r for r in results if r["version"] == version])
        score, verdict = _score(
            question, [r for r in results if r["version"] == "original"])
        db.update_submission(sub["id"], suggested_score=score,
                             verdict=verdict)


def process_submission(submission_id):
    sub = db.get_submission(submission_id)
    question = db.get_question(sub["question_id"])

    result = transcribe(sub["image_path"])
    code = result["code"]
    flags = {"uncertain_lines": result["uncertain_lines"],
             "static_flags": result["static_flags"]}

    score, verdict = _grade(submission_id, question, code)
    db.update_submission(submission_id, transcription=code, flags=flags,
                         suggested_score=score, verdict=verdict,
                         status="ready", error_message=None)


def rerun_submission(submission_id, code):
    """Re-run tests after the professor edits the code on the review page.

    The edited code replaces the transcription. The model's uncertain_lines
    are kept for reference; static flags are recomputed for the new code.
    """
    sub = db.get_submission(submission_id)
    question = db.get_question(sub["question_id"])
    flags = dict(sub["flags"] or {})
    flags["static_flags"] = static_flags(code)

    score, verdict = _grade(submission_id, question, code)
    db.update_submission(submission_id, transcription=code, flags=flags,
                         suggested_score=score, verdict=verdict)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    image, question_id = sys.argv[1], int(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) > 3 else Path(image).stem

    db.init_db()
    if not db.get_question(question_id):
        sys.exit(f"No question with id {question_id}")
    submission_id = db.create_submission(question_id, label, image)
    db.update_submission(submission_id, status="processing")
    process_submission(submission_id)

    sub = db.get_submission(submission_id)
    print(f"Submission {submission_id}: suggested score"
          f" {sub['suggested_score']}, verdict {sub['verdict']}")
    print(sub["transcription"])
    for r in db.list_test_results(submission_id):
        status = "PASS" if r["passed"] else "FAIL"
        error = f" error={r['error'].splitlines()[-1]}" if r["error"] else ""
        print(f"  [{status}] input={r['input']!r}"
              f" expected={r['expected_output']!r}"
              f" got={r['actual_output']!r}{error}")


if __name__ == "__main__":
    main()
