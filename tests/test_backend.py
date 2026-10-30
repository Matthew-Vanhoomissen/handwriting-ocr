"""End-to-end API tests with a fake transcription (no model calls)."""

import io
from pathlib import Path

import pytest

from backend import app as app_module
from backend import db, pipeline, worker

FAKE_CODE = {
    "good.jpg": "s = input()\nprint(s[::-1])",
    "misread.jpg": "S = input()\nprint(s[::-1])",
    "add.jpg": "a = int(input())\nb = int(input())\nprint(a + b)",
}

REVERSE_TESTS = [("abc\n", "cba"), ("racecar\n", "racecar")]


def fake_transcribe(image_path):
    for name, code in FAKE_CODE.items():
        if open(image_path, "rb").read() == name.encode():
            return {"code": code, "uncertain_lines": [],
                    "static_flags": pipeline.static_flags(code)}
    raise ValueError("unreadable image")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
    db.init_db()
    return app_module.app.test_client()


def make_assignment(client, title="HW1"):
    return client.post("/api/assignments", json={"title": title}).get_json()


def make_question(client, assignment_id, max_points=10, tests=(), **fields):
    q = client.post(f"/api/assignments/{assignment_id}/questions",
                    json={"max_points": max_points, **fields}).get_json()
    for inp, out in tests:
        client.post(f"/api/questions/{q['id']}/tests",
                    json={"input": inp, "expected_output": out})
    return q


def upload(client, question_id, names):
    """Upload fake photos whose bytes are their own file names."""
    data = {"files": [(io.BytesIO(n.encode()), n) for n in names]}
    r = client.post(f"/api/questions/{question_id}/submissions",
                    data=data, content_type="multipart/form-data")
    return r


def process_queue():
    while worker.process_next():
        pass


def test_full_flow(client):
    a = make_assignment(client)
    q = make_question(client, a["id"], tests=REVERSE_TESTS)

    r = upload(client, q["id"], ["good.jpg", "misread.jpg", "bad.jpg"])
    assert r.status_code == 201
    good, misread, bad = r.get_json()["submission_ids"]
    process_queue()

    sub = client.get(f"/api/submissions/{good}").get_json()
    assert sub["status"] == "ready"
    assert sub["question_id"] == q["id"]
    assert sub["question"]["max_points"] == 10
    assert sub["assignment"]["id"] == a["id"]
    assert sub["suggested_score"] == 10
    assert sub["verdict"] == "pass"
    assert all(t["passed"] for t in sub["test_results"])

    sub = client.get(f"/api/submissions/{misread}").get_json()
    assert sub["suggested_score"] == 0
    assert sub["verdict"] is None
    assert "NameError" in sub["test_results"][0]["error"]
    assert sub["flags"]["static_flags"][0]["line"] == 2

    # One bad image errors without stopping the queue.
    sub = client.get(f"/api/submissions/{bad}").get_json()
    assert sub["status"] == "error"
    assert "unreadable image" in sub["error_message"]

    # Professor fixes the misread and re-runs.
    sub = client.post(f"/api/submissions/{misread}/rerun", json={
        "code": "s = input()\nprint(s[::-1])"}).get_json()
    assert sub["suggested_score"] == 10
    assert sub["flags"]["static_flags"] == []

    sub = client.post(f"/api/submissions/{misread}/grade", json={
        "final_score": 9.5, "notes": "misread S"}).get_json()
    assert sub["status"] == "graded"
    assert sub["final_score"] == 9.5

    listed = client.get(f"/api/questions/{q['id']}/submissions").get_json()
    assert [s["id"] for s in listed] == [good, misread, bad]


def test_assignment_totals_and_question_order(client):
    a = make_assignment(client)
    assert a["questions"] == []
    assert a["total_points"] == 0
    q1 = make_question(client, a["id"], 10, tests=REVERSE_TESTS, title="Rev")
    q2 = make_question(client, a["id"], 5, exact_match=True)
    q3 = make_question(client, a["id"], 2.5, prompt="Add two numbers")
    assert [q1["position"], q2["position"], q3["position"]] == [1, 2, 3]

    detail = client.get(f"/api/assignments/{a['id']}").get_json()
    assert detail["question_count"] == 3
    assert detail["total_points"] == 17.5
    assert [q["id"] for q in detail["questions"]] == [q1["id"], q2["id"],
                                                     q3["id"]]
    assert len(detail["questions"][0]["test_cases"]) == 2
    assert detail["questions"][1]["exact_match"] == 1

    listed = client.get("/api/assignments").get_json()
    assert listed[0]["total_points"] == 17.5

    q = client.get(f"/api/questions/{q1['id']}").get_json()
    assert q["title"] == "Rev"
    assert len(q["test_cases"]) == 2


def test_each_question_uses_its_own_tests_and_points(client):
    a = make_assignment(client)
    reverse = make_question(client, a["id"], 10, tests=REVERSE_TESTS)
    add = make_question(client, a["id"], 4,
                        tests=[("1\n2\n", "3"), ("5\n5\n", "10")])
    upload(client, reverse["id"], ["good.jpg"])
    upload(client, add["id"], ["add.jpg"])
    process_queue()

    def only_submission(question_id):
        listed = client.get(f"/api/questions/{question_id}/submissions")
        sub_id = listed.get_json()[0]["id"]
        return client.get(f"/api/submissions/{sub_id}").get_json()

    rev_sub = only_submission(reverse["id"])
    add_sub = only_submission(add["id"])
    assert rev_sub["suggested_score"] == 10
    assert add_sub["suggested_score"] == 4
    assert {t["input"] for t in add_sub["test_results"]} == {"1\n2\n",
                                                            "5\n5\n"}
    assert add_sub["score_reasoning"] == "Passed 2 of 2 tests: 4 x 2/2 = 4."


def test_validation(client):
    assert client.post("/api/assignments", json={}).status_code == 400
    a = make_assignment(client)
    r = client.post(f"/api/assignments/{a['id']}/questions", json={})
    assert r.status_code == 400
    r = client.post(f"/api/assignments/{a['id']}/questions",
                    json={"max_points": 1, "position": "first"})
    assert r.status_code == 400
    assert client.post("/api/assignments/999/questions",
                       json={"max_points": 1}).status_code == 404
    assert client.get("/api/questions/999").status_code == 404
    assert client.post("/api/questions/999/tests",
                       json={"expected_output": "x"}).status_code == 404
    assert upload(client, 999, ["good.jpg"]).status_code == 404


def test_rejects_unsupported_upload(client):
    q = make_question(client, make_assignment(client)["id"])
    assert upload(client, q["id"], ["photo.heic"]).status_code == 400


def test_partial_credit(client):
    q = make_question(client, make_assignment(client)["id"], 10, tests=[
        ("1\n2\n", "3"), ("2\n2\n", "4"), ("0\n0\n", "0")])
    sub_id = db.create_submission(q["id"], "s1", "unused")
    pipeline.rerun_submission(sub_id, "a = int(input())\nprint(a * 2)")
    sub = client.get(f"/api/submissions/{sub_id}").get_json()
    assert sub["suggested_score"] == pytest.approx(6.67)
    assert sub["score_reasoning"] == "Passed 2 of 3 tests: 10 x 2/3 = 6.67."


def test_update_question_rescores(client):
    q = make_question(client, make_assignment(client)["id"], 10,
                      tests=[("1\n", "1  ")], title="Old")
    sub_id = db.create_submission(q["id"], "s1", "unused")
    pipeline.rerun_submission(sub_id, "print(input())")
    db.update_submission(sub_id, final_score=7)
    assert db.get_submission(sub_id)["suggested_score"] == 10

    # Whole object sent back: extra keys are ignored.
    r = client.patch(f"/api/questions/{q['id']}",
                     json={**q, "title": "New", "max_points": 4})
    assert r.status_code == 200
    assert r.get_json()["title"] == "New"
    assert r.get_json()["position"] == 1
    sub = client.get(f"/api/submissions/{sub_id}").get_json()
    assert sub["suggested_score"] == 4
    assert sub["final_score"] == 7

    # Exact match fails on the trailing spaces, without re-running code.
    client.patch(f"/api/questions/{q['id']}", json={"exact_match": True})
    sub = client.get(f"/api/submissions/{sub_id}").get_json()
    assert sub["suggested_score"] == 0
    assert sub["verdict"] is None
    assert not sub["test_results"][0]["passed"]

    assert client.patch(f"/api/questions/{q['id']}",
                        json={"position": 3}).status_code == 400
    assert client.patch(f"/api/questions/{q['id']}",
                        json={"max_points": "ten"}).status_code == 400
    assert client.patch("/api/questions/999",
                        json={"title": "x"}).status_code == 404


def make_processed_question(client, assignment_id):
    """A question with tests and two processed, uploaded submissions."""
    q = make_question(client, assignment_id, tests=REVERSE_TESTS)
    ids = upload(client, q["id"], ["good.jpg", "misread.jpg"]
                 ).get_json()["submission_ids"]
    process_queue()
    return q["id"], ids


def test_delete_submission_removes_results_and_photo(client):
    _, (sub_id, other_id) = make_processed_question(
        client, make_assignment(client)["id"])
    photo = db.get_submission(sub_id)["image_path"]
    assert db.list_test_results(sub_id)

    assert client.delete(f"/api/submissions/{sub_id}").status_code == 204
    assert client.get(f"/api/submissions/{sub_id}").status_code == 404
    assert db.list_test_results(sub_id) == []
    assert not Path(photo).exists()
    # The other submission is untouched.
    assert Path(db.get_submission(other_id)["image_path"]).exists()
    assert db.list_test_results(other_id)


def test_delete_question_removes_its_data_and_renumbers(client):
    a = make_assignment(client)
    q1_id, q1_subs = make_processed_question(client, a["id"])
    q2_id, q2_subs = make_processed_question(client, a["id"])
    q3 = make_question(client, a["id"], 5)
    q2_photos = [db.get_submission(s)["image_path"] for s in q2_subs]

    assert client.delete(f"/api/questions/{q2_id}").status_code == 204
    assert client.get(f"/api/questions/{q2_id}").status_code == 404
    assert db.list_test_cases(q2_id) == []
    for s in q2_subs:
        assert db.get_submission(s) is None
        assert db.list_test_results(s) == []
    assert not any(Path(p).exists() for p in q2_photos)

    detail = client.get(f"/api/assignments/{a['id']}").get_json()
    assert [(q["id"], q["position"]) for q in detail["questions"]] == [
        (q1_id, 1), (q3["id"], 2)]
    assert detail["total_points"] == 15
    # Question 1 is untouched.
    assert all(db.get_submission(s) for s in q1_subs)
    assert all(db.list_test_results(s) for s in q1_subs)


def test_delete_assignment_removes_everything(client):
    a = make_assignment(client)
    q_ids, sub_ids = [], []
    for _ in range(2):
        q_id, subs = make_processed_question(client, a["id"])
        q_ids.append(q_id)
        sub_ids += subs
    photos = [db.get_submission(s)["image_path"] for s in sub_ids]
    other = make_assignment(client, "Other")
    other_q = make_question(client, other["id"], tests=REVERSE_TESTS)

    assert client.delete(f"/api/assignments/{a['id']}").status_code == 204
    assert client.get(f"/api/assignments/{a['id']}").status_code == 404
    for q_id in q_ids:
        assert db.get_question(q_id) is None
        assert db.list_test_cases(q_id) == []
    for s in sub_ids:
        assert db.get_submission(s) is None
        assert db.list_test_results(s) == []
    assert not any(Path(p).exists() for p in photos)
    # Other assignments are untouched.
    assert len(db.list_test_cases(other_q["id"])) == 2


def test_delete_empty_assignment(client):
    a = make_assignment(client)
    assert client.delete(f"/api/assignments/{a['id']}").status_code == 204


def test_delete_keeps_photos_outside_uploads(client, tmp_path):
    # CLI submissions point at samples/; deleting them must not touch those.
    sample = tmp_path / "sample.jpg"
    sample.write_bytes(b"good.jpg")
    q = make_question(client, make_assignment(client)["id"])
    sub_id = db.create_submission(q["id"], "cli", str(sample))
    client.delete(f"/api/submissions/{sub_id}")
    assert sample.exists()
