"""Token check, ping, upload limit, and startup config for phone access."""

import io

import pytest

from backend import app as app_module
from backend import db

TOKEN = "a-test-token-that-is-long-enough"
PHONE = {"REMOTE_ADDR": "192.168.1.50"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setitem(app_module.app.config, "API_TOKEN", TOKEN)
    db.init_db()
    return app_module.app.test_client()


def phone_get(client, path, token=None):
    headers = {"X-API-Token": token} if token is not None else {}
    return client.get(path, headers=headers, environ_overrides=PHONE)


def test_loopback_needs_no_token(client):
    assert client.get("/api/ping").get_json() == {"ok": True,
                                                  "server": "grader"}
    for addr in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        r = client.get("/api/assignments",
                       environ_overrides={"REMOTE_ADDR": addr})
        assert r.status_code == 200, addr


def test_phone_needs_the_token(client):
    assert phone_get(client, "/api/ping").status_code == 401
    assert phone_get(client, "/api/ping", "wrong").status_code == 401
    assert phone_get(client, "/api/assignments", "").status_code == 401
    r = phone_get(client, "/api/ping", TOKEN)
    assert r.status_code == 200
    assert r.get_json()["server"] == "grader"
    assert phone_get(client, "/api/assignments", TOKEN).status_code == 200


def test_every_api_route_is_checked(client):
    a = client.post("/api/assignments", json={"title": "HW1"}).get_json()
    r = client.delete(f"/api/assignments/{a['id']}",
                      environ_overrides=PHONE)
    assert r.status_code == 401
    assert db.get_assignment(a["id"])
    r = client.post("/api/assignments", json={"title": "x"},
                    environ_overrides=PHONE)
    assert r.status_code == 401
    assert r.get_json()["error"]


def test_unset_token_fails_closed(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "API_TOKEN", "")
    assert phone_get(client, "/api/ping").status_code == 401
    assert phone_get(client, "/api/ping", "").status_code == 401


def test_forwarded_headers_are_ignored(client):
    r = client.get("/api/ping", environ_overrides=PHONE, headers={
        "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"})
    assert r.status_code == 401


def test_oversized_upload_returns_json_413(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 1024)
    q = client.post("/api/assignments", json={"title": "HW1"}).get_json()
    q = client.post(f"/api/assignments/{q['id']}/questions",
                    json={"max_points": 1}).get_json()
    data = {"files": [(io.BytesIO(b"x" * 4096), "big.jpg")]}
    r = client.post(f"/api/questions/{q['id']}/submissions", data=data,
                    content_type="multipart/form-data")
    assert r.status_code == 413
    assert "MB" in r.get_json()["error"]


def test_startup_config():
    assert app_module.config_error("127.0.0.1", "") is None
    assert app_module.config_error("localhost", "") is None
    assert app_module.config_error("0.0.0.0", "") is not None
    assert app_module.config_error("0.0.0.0", "short") is not None
    assert app_module.config_error("192.168.1.10", TOKEN) is None
