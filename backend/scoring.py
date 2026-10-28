"""Suggested score: max_points * (tests_passed / total_tests).

Comes with plain-text reasoning. The professor always makes the final call.
"""


def suggest_score(max_points, passed, total):
    """Return (score, reasoning). Score is None when there are no tests."""
    if total == 0:
        return None, "No test cases, so no score is suggested."
    score = round(max_points * passed / total, 2)
    reasoning = (f"Passed {passed} of {total} tests: "
                 f"{max_points:g} x {passed}/{total} = {score:g}.")
    return score, reasoning
