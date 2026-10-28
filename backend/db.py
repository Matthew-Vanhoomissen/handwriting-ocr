"""SQLite helpers for the four tables.

Tables: assignments, test_cases, submissions, test_results.

Each helper opens its own connection, so the Flask request threads and the
worker thread never share one. WAL mode lets them read while the other
writes.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "grader.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS assignments (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    prompt      TEXT NOT NULL DEFAULT '',
    max_points  REAL NOT NULL,
    language    TEXT NOT NULL DEFAULT 'python',
    exact_match INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS test_cases (
    id              INTEGER PRIMARY KEY,
    assignment_id   INTEGER NOT NULL REFERENCES assignments(id),
    input           TEXT NOT NULL DEFAULT '',
    expected_output TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY,
    assignment_id   INTEGER NOT NULL REFERENCES assignments(id),
    student_label   TEXT NOT NULL,
    image_path      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    transcription   TEXT,
    corrected_code  TEXT,
    verdict         TEXT,
    suggested_score REAL,
    final_score     REAL,
    notes           TEXT,
    flags           TEXT,
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS test_results (
    id            INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES submissions(id),
    test_case_id  INTEGER NOT NULL REFERENCES test_cases(id),
    version       TEXT NOT NULL,
    passed        INTEGER NOT NULL,
    actual_output TEXT,
    error         TEXT
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


def _rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def _row(cursor):
    r = cursor.fetchone()
    return dict(r) if r else None


# Assignments and test cases

def create_assignment(title, prompt, max_points, exact_match=False):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO assignments (title, prompt, max_points, exact_match)"
            " VALUES (?, ?, ?, ?)",
            (title, prompt, max_points, int(exact_match)))
        return cur.lastrowid


def list_assignments():
    with connect() as conn:
        return _rows(conn.execute("SELECT * FROM assignments ORDER BY id"))


def get_assignment(assignment_id):
    with connect() as conn:
        return _row(conn.execute(
            "SELECT * FROM assignments WHERE id = ?", (assignment_id,)))


def add_test_case(assignment_id, input_text, expected_output):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO test_cases (assignment_id, input, expected_output)"
            " VALUES (?, ?, ?)", (assignment_id, input_text, expected_output))
        return cur.lastrowid


def delete_test_case(test_case_id):
    with connect() as conn:
        conn.execute("DELETE FROM test_results WHERE test_case_id = ?",
                     (test_case_id,))
        conn.execute("DELETE FROM test_cases WHERE id = ?", (test_case_id,))


def list_test_cases(assignment_id):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT * FROM test_cases WHERE assignment_id = ? ORDER BY id",
            (assignment_id,)))


# Submissions

def create_submission(assignment_id, student_label, image_path):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO submissions (assignment_id, student_label, image_path)"
            " VALUES (?, ?, ?)", (assignment_id, student_label, image_path))
        return cur.lastrowid


def list_submissions(assignment_id):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT id, assignment_id, student_label, status, verdict,"
            " suggested_score, final_score, error_message"
            " FROM submissions WHERE assignment_id = ? ORDER BY id",
            (assignment_id,)))


def get_submission(submission_id):
    with connect() as conn:
        sub = _row(conn.execute(
            "SELECT * FROM submissions WHERE id = ?", (submission_id,)))
    if sub:
        sub["flags"] = json.loads(sub["flags"]) if sub["flags"] else None
    return sub


def update_submission(submission_id, **fields):
    if "flags" in fields and fields["flags"] is not None:
        fields["flags"] = json.dumps(fields["flags"])
    columns = ", ".join(f"{name} = ?" for name in fields)
    with connect() as conn:
        conn.execute(f"UPDATE submissions SET {columns} WHERE id = ?",
                     (*fields.values(), submission_id))


def claim_next_queued():
    """Atomically move the oldest queued submission to processing."""
    with connect() as conn:
        return _row(conn.execute(
            "UPDATE submissions SET status = 'processing', error_message = NULL"
            " WHERE id = (SELECT id FROM submissions WHERE status = 'queued'"
            " ORDER BY id LIMIT 1) RETURNING id"))


def requeue_stuck():
    """Put back anything left 'processing' by a crash or restart."""
    with connect() as conn:
        conn.execute("UPDATE submissions SET status = 'queued'"
                     " WHERE status = 'processing'")


# Test results

def replace_test_results(submission_id, version, results):
    """Store results for one version, replacing any earlier run of it."""
    with connect() as conn:
        conn.execute("DELETE FROM test_results"
                     " WHERE submission_id = ? AND version = ?",
                     (submission_id, version))
        conn.executemany(
            "INSERT INTO test_results (submission_id, test_case_id, version,"
            " passed, actual_output, error) VALUES (?, ?, ?, ?, ?, ?)",
            [(submission_id, r["test_case_id"], version, int(r["passed"]),
              r["actual_output"], r["error"]) for r in results])


def list_test_results(submission_id):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT tr.*, tc.input, tc.expected_output FROM test_results tr"
            " JOIN test_cases tc ON tc.id = tr.test_case_id"
            " WHERE tr.submission_id = ? ORDER BY tr.version, tc.id",
            (submission_id,)))
