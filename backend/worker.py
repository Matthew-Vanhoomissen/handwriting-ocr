"""Background thread that processes queued submissions one at a time.

Polling SQLite every couple of seconds is simpler than a real queue (Redis,
Celery) and plenty for a class of 50. One bad image sets that submission to
'error' and the loop moves on.
"""

import threading
import time
import traceback

from backend import db
from backend.pipeline import process_submission

POLL_SECONDS = 2


def process_next():
    """Process one queued submission. Returns False if the queue is empty."""
    claimed = db.claim_next_queued()
    if not claimed:
        return False
    submission_id = claimed["id"]
    try:
        process_submission(submission_id)
    except Exception as e:
        traceback.print_exc()
        db.update_submission(submission_id, status="error",
                             error_message=f"{type(e).__name__}: {e}")
    return True


def run_forever():
    db.requeue_stuck()
    while True:
        if not process_next():
            time.sleep(POLL_SECONDS)


def start():
    thread = threading.Thread(target=run_forever, name="grader-worker",
                              daemon=True)
    thread.start()
    return thread
