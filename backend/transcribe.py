"""Faithful transcription of a handwritten program with Muse Spark.

Returns code and uncertain_lines.
"""

import ast
import builtins
import sys

from backend.llm import DEFAULT_MODEL, ask_with_image

TRANSCRIBE_PROMPT = """\
This photo shows a handwritten Python program written by a student.
Transcribe it exactly as written, character for character. The transcription
will be run against test cases to grade the student, so a misread character
can cost the student points they earned.

Faithfulness:
- Do NOT fix mistakes. Keep typos, misspelled or inconsistent variable names,
  missing colons or parentheses, and logic bugs exactly as written.
- Do not add code, comments, or imports that are not on the page.
- Ignore crossed-out text.

Python is case-sensitive, and handwriting makes some characters ambiguous.
Look closely at these pairs: s/S, c/C, o/O/0, x/X, z/Z/2, l/1/I/|, b/6, g/9,
u/v, colon/semicolon, single/double quotes, comma/period. A slashed zero means
0. Compare a letter's size to the same letter elsewhere on the page.

Indentation:
- Use 4 spaces per level. Handwritten indentation drifts, so decide each
  line's level from its horizontal position relative to the lines above it.

Uncertainty:
- For every line where a character's identity or case is ambiguous, or the
  indentation level is not clear from the page, add an entry to
  uncertain_lines with the 1-based line number, what you chose, the
  alternative reading, and why. Do not resolve ambiguity silently; flagging
  a line costs nothing, while a silent wrong guess can mis-grade a student.
- Use an empty list only if every line is unambiguous."""

TRANSCRIPTION_SCHEMA = {
    "name": "transcription",
    "schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "uncertain_lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line": {"type": "integer"},
                        "chosen": {"type": "string"},
                        "alternative": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["line", "chosen", "alternative", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["code", "uncertain_lines"],
        "additionalProperties": False,
    },
}


def transcribe(image_path, model=DEFAULT_MODEL, use_cache=True):
    """Return {"code", "uncertain_lines", "static_flags"} for one photo."""
    result = ask_with_image(TRANSCRIBE_PROMPT, image_path,
                            schema=TRANSCRIPTION_SCHEMA, model=model,
                            use_cache=use_cache)
    result["static_flags"] = static_flags(result["code"])
    return result


def static_flags(code):
    """Flag lines a human should check, without calling the model.

    Catches syntax errors and names that are used but never assigned. A name
    that matches an assigned one except for case (s vs S) is almost always an
    ambiguous glyph or a student typo; either way the grader should look.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"line": e.lineno, "reason": f"syntax error: {e.msg}"}]

    bound = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])

    flags = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                and node.id not in bound):
            twins = [b for b in bound if b.lower() == node.id.lower()]
            if twins:
                reason = (f"'{node.id}' is never assigned but '{twins[0]}' "
                          "is; check letter case")
            else:
                reason = f"'{node.id}' is used but never assigned"
            flags.append({"line": node.lineno, "reason": reason})
    return sorted(flags, key=lambda f: f["line"])


if __name__ == "__main__":
    # Usage: python -m backend.transcribe samples/simple_python1.jpg [...]
    for path in sys.argv[1:]:
        result = transcribe(path)
        print(f"=== {path}")
        print(result["code"])
        for u in result["uncertain_lines"]:
            print(f"  model unsure, line {u['line']}: chose {u['chosen']!r}"
                  f" over {u['alternative']!r} ({u['reason']})")
        for f in result["static_flags"]:
            print(f"  static check, line {f['line']}: {f['reason']}")
        print(flush=True)
