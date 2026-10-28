"""End-to-end API tests with a fake transcription (no model calls)."""

import io

import pytest

from backend import app as app_module
from backend import db, pipeline, worker

FAKE_CODE = {
    "good.jpg": "s = input()\nprint(s[::-1])",
    "misread.jpg": "S = input()\nprint(s[::-1])",
}


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


def upload(client, assignment_id, names, contents):
    data = {"files": [(io.BytesIO(c), n) for n, c in zip(names, contents)]}
    return client.post(f"/api/assignments/{assignment_id}/submissions",
                       data=data, content_type="multipart/form-data")


def test_full_flow(client):
    a = client.post("/api/assignments", json={
        "title": "Reverse", "max_points": 10}).get_json()
    for inp, out in [("abc\n", "cba"), ("racecar\n", "racecar")]:
        client.post(f"/api/assignments/{a['id']}/tests",
                    json={"input": inp, "expected_output": out})

    r = upload(client, a["id"], ["good.jpg", "misread.jpg", "bad.jpg"],
               [b"good.jpg", b"misread.jpg", b"garbage"])
    assert r.status_code == 201
    good, misread, bad = r.get_json()["submission_ids"]

    while worker.process_next():
        pass

    sub = client.get(f"/api/submissions/{good}").get_json()
    assert sub["status"] == "ready"
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

    csv_text = client.get(
        f"/api/assignments/{a['id']}/export.csv").get_data(as_text=True)
    assert "misread,graded,10.0,9.5,10.0,pass,misread S" in csv_text


def test_rejects_unsupported_upload(client):
    a = client.post("/api/assignments", json={
        "title": "X", "max_points": 1}).get_json()
    r = upload(client, a["id"], ["photo.heic"], [b"x"])
    assert r.status_code == 400


def test_partial_credit(client):
    a = client.post("/api/assignments", json={
        "title": "Add", "max_points": 10}).get_json()
    for inp, out in [("1\n2\n", "3"), ("2\n2\n", "4"), ("0\n0\n", "0")]:
        client.post(f"/api/assignments/{a['id']}/tests",
                    json={"input": inp, "expected_output": out})
    sub_id = db.create_submission(a["id"], "s1", "unused")
    pipeline.rerun_submission(sub_id, "a = int(input())\nprint(a * 2)")
    sub = client.get(f"/api/submissions/{sub_id}").get_json()
    assert sub["suggested_score"] == pytest.approx(6.67)
    assert sub["score_reasoning"] == "Passed 2 of 3 tests: 10 x 2/3 = 6.67."
