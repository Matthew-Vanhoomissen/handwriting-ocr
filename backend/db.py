"""SQLite helpers for the five tables.

Tables: assignments, questions, test_cases, submissions, test_results.
An assignment has questions; each question has its own test cases, points,
and submissions (one photo per student per question).

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
    id       INTEGER PRIMARY KEY,
    title    TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'python'
);

CREATE TABLE IF NOT EXISTS questions (
    id            INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id),
    position      INTEGER NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    prompt        TEXT NOT NULL DEFAULT '',
    max_points    REAL NOT NULL,
    exact_match   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS test_cases (
    id              INTEGER PRIMARY KEY,
    question_id     INTEGER NOT NULL REFERENCES questions(id),
    input           TEXT NOT NULL DEFAULT '',
    expected_output TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY,
    question_id     INTEGER NOT NULL REFERENCES questions(id),
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

# Assignment fields plus totals computed from its questions, so the total
# points can never drift from the sum of the question points.
ASSIGNMENT_SELECT = """
SELECT a.*,
       COUNT(q.id) AS question_count,
       COALESCE(SUM(q.max_points), 0) AS total_points
FROM assignments a LEFT JOIN questions q ON q.assignment_id = a.id
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
        # CREATE TABLE IF NOT EXISTS won't change existing tables, so a db
        # from before questions existed would fail later in confusing ways.
        columns = {r["name"] for r in conn.execute(
            "PRAGMA table_info(submissions)")}
        if "assignment_id" in columns:
            raise RuntimeError(
                f"{DB_PATH} uses the old schema (no questions table). Move"
                " or delete it and its uploads/ folder, then restart.")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


def _rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def _row(cursor):
    r = cursor.fetchone()
    return dict(r) if r else None


def _delete_submissions_where(conn, condition, params):
    """Delete matching submissions and their results. Returns image paths.

    Children go first: foreign_keys is on, so parents can't be deleted while
    rows still point at them.
    """
    images = [r["image_path"] for r in _rows(conn.execute(
        f"SELECT image_path FROM submissions WHERE {condition}", params))]
    conn.execute("DELETE FROM test_results WHERE submission_id IN"
                 f" (SELECT id FROM submissions WHERE {condition})", params)
    conn.execute(f"DELETE FROM submissions WHERE {condition}", params)
    return images


# Assignments

def create_assignment(title, language="python"):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO assignments (title, language) VALUES (?, ?)",
            (title, language))
        return cur.lastrowid


def list_assignments():
    with connect() as conn:
        return _rows(conn.execute(
            ASSIGNMENT_SELECT + " GROUP BY a.id ORDER BY a.id"))


def get_assignment(assignment_id):
    with connect() as conn:
        return _row(conn.execute(
            ASSIGNMENT_SELECT + " WHERE a.id = ? GROUP BY a.id",
            (assignment_id,)))


def delete_assignment(assignment_id):
    """Delete an assignment and everything under it.

    Returns the image paths of the deleted submissions so the caller can
    remove the files.
    """
    question_ids = ("question_id IN"
                    " (SELECT id FROM questions WHERE assignment_id = ?)")
    with connect() as conn:
        images = _delete_submissions_where(conn, question_ids,
                                           (assignment_id,))
        conn.execute(f"DELETE FROM test_cases WHERE {question_ids}",
                     (assignment_id,))
        conn.execute("DELETE FROM questions WHERE assignment_id = ?",
                     (assignment_id,))
        conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    return images


# Questions

def create_question(assignment_id, max_points, title="", prompt="",
                    exact_match=False, position=None):
    """Add a question. Without a position, it goes after the last one."""
    with connect() as conn:
        if position is None:
            position = conn.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM questions"
                " WHERE assignment_id = ?", (assignment_id,)).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO questions (assignment_id, position, title, prompt,"
            " max_points, exact_match) VALUES (?, ?, ?, ?, ?, ?)",
            (assignment_id, position, title, prompt, max_points,
             int(exact_match)))
        return cur.lastrowid


def list_questions(assignment_id):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT * FROM questions WHERE assignment_id = ?"
            " ORDER BY position, id", (assignment_id,)))


def get_question(question_id):
    with connect() as conn:
        return _row(conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)))


def update_question(question_id, **fields):
    columns = ", ".join(f"{name} = ?" for name in fields)
    with connect() as conn:
        conn.execute(f"UPDATE questions SET {columns} WHERE id = ?",
                     (*fields.values(), question_id))


def delete_question(question_id):
    """Delete a question with its tests, submissions, and results.

    Later questions move up one position so numbering stays 1..n. Returns
    the image paths of the deleted submissions.
    """
    with connect() as conn:
        question = _row(conn.execute(
            "SELECT assignment_id, position FROM questions WHERE id = ?",
            (question_id,)))
        if not question:
            return []
        images = _delete_submissions_where(conn, "question_id = ?",
                                           (question_id,))
        conn.execute("DELETE FROM test_cases WHERE question_id = ?",
                     (question_id,))
        conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        conn.execute(
            "UPDATE questions SET position = position - 1"
            " WHERE assignment_id = ? AND position > ?",
            (question["assignment_id"], question["position"]))
    return images


# Test cases

def add_test_case(question_id, input_text, expected_output):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO test_cases (question_id, input, expected_output)"
            " VALUES (?, ?, ?)", (question_id, input_text, expected_output))
        return cur.lastrowid


def delete_test_case(test_case_id):
    with connect() as conn:
        conn.execute("DELETE FROM test_results WHERE test_case_id = ?",
                     (test_case_id,))
        conn.execute("DELETE FROM test_cases WHERE id = ?", (test_case_id,))


def list_test_cases(question_id):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT * FROM test_cases WHERE question_id = ? ORDER BY id",
            (question_id,)))


# Submissions

def create_submission(question_id, student_label, image_path):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO submissions"
            " (question_id, student_label, image_path) VALUES (?, ?, ?)",
            (question_id, student_label, image_path))
        return cur.lastrowid


def list_submissions(question_id):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT id, question_id, student_label, status, verdict,"
            " suggested_score, final_score, error_message"
            " FROM submissions WHERE question_id = ? ORDER BY id",
            (question_id,)))


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


def delete_submission(submission_id):
    """Delete a submission and its results. Returns its image path."""
    with connect() as conn:
        images = _delete_submissions_where(conn, "id = ?", (submission_id,))
    return images[0] if images else None


def claim_next_queued():
    """Atomically move the oldest queued submission to processing."""
    with connect() as conn:
        return _row(conn.execute(
            "UPDATE submissions"
            " SET status = 'processing', error_message = NULL"
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
