"""Tests for sandbox.run_code and output comparison."""

from backend.sandbox import outputs_match, run_code


def test_stdout_and_stdin():
    result = run_code("s = input()\nprint(s[::-1])", stdin="hello\n")
    assert result["stdout"] == "olleh\n"
    assert result["exit_code"] == 0
    assert not result["timed_out"]


def test_runtime_error_reports_stderr():
    result = run_code("print(undefined_name)")
    assert result["exit_code"] != 0
    assert "NameError" in result["stderr"]


def test_syntax_error():
    result = run_code("for i in range(3)\n    print(i)")
    assert result["exit_code"] != 0
    assert "SyntaxError" in result["stderr"]


def test_timeout_kills_infinite_loop():
    result = run_code("while True:\n    pass", timeout=1)
    assert result["timed_out"]
    assert result["exit_code"] is None


def test_output_is_capped():
    result = run_code("while True:\n    print('x' * 1000)", timeout=1)
    assert result["stdout"].endswith("[output truncated]")


def test_missing_stdin_raises_eof():
    result = run_code("input()")
    assert "EOFError" in result["stderr"]


def test_runs_in_temp_dir_not_repo():
    result = run_code("import os\nprint(os.listdir('.'))")
    assert "backend" not in result["stdout"]


def test_outputs_match_ignores_trailing_whitespace():
    assert outputs_match("1\n2  \n\n", "1\n2")
    assert outputs_match("1\r\n2\r\n", "1\n2\n")
    assert not outputs_match("1\n2", "1\n3")


def test_outputs_match_exact():
    assert not outputs_match("1\n2\n", "1\n2", exact=True)
    assert outputs_match("1\n2", "1\n2", exact=True)
