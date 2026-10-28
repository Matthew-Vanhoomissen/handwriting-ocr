"""Run student code with stdin and a timeout.

Docker isn't available on the dev machine, so this uses a restricted
subprocess. What it does give you: a timeout that kills the process, a fresh
temp working directory, an isolated interpreter (python -I ignores env vars
and user site-packages), and a cap on captured output. What it does NOT give
you on Windows: no network block and no memory limit. Fine for your own
samples, not for untrusted code from real students.
"""

import os
import subprocess
import sys
import tempfile

DEFAULT_TIMEOUT = 5
MAX_OUTPUT_BYTES = 64 * 1024


def run_code(code, stdin="", timeout=DEFAULT_TIMEOUT):
    """Run code as a script. Returns stdout, stderr, exit_code, timed_out."""
    with tempfile.TemporaryDirectory(prefix="grader_") as workdir:
        script = os.path.join(workdir, "main.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(code)

        # Write output to files instead of pipes so an infinite print loop
        # fills a file we only read the start of, not this process's memory.
        out_path = os.path.join(workdir, "stdout.txt")
        err_path = os.path.join(workdir, "stderr.txt")
        timed_out = False
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            try:
                proc = subprocess.run(
                    # -X utf8 because -I ignores PYTHONIOENCODING.
                    [sys.executable, "-I", "-X", "utf8", script],
                    input=stdin.encode("utf-8"), stdout=out, stderr=err,
                    cwd=workdir, timeout=timeout,
                    env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
                )
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = None

        return {
            "stdout": _read_capped(out_path),
            "stderr": _read_capped(err_path),
            "exit_code": exit_code,
            "timed_out": timed_out,
        }


def _read_capped(path):
    with open(path, "rb") as f:
        data = f.read(MAX_OUTPUT_BYTES + 1)
    text = data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    # Windows writes \r\n to redirected stdout; normalize so exact-match
    # comparisons don't depend on the host OS.
    text = text.replace("\r\n", "\n")
    if len(data) > MAX_OUTPUT_BYTES:
        text += "\n[output truncated]"
    return text


def outputs_match(actual, expected, exact=False):
    """Compare program output to the expected output.

    By default, trailing whitespace on each line and trailing blank lines are
    ignored, since students and professors rarely agree on those.
    """
    if exact:
        return actual == expected
    return _normalize(actual) == _normalize(expected)


def _normalize(text):
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")
