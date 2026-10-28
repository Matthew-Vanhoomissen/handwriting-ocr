"""Transcription of a handwritten program with Muse Spark.

Handwriting ambiguity is resolved charitably; programming mistakes are kept.
Returns code, uncertain_lines, and static_flags.
"""

import ast
import builtins
import sys

from backend.llm import DEFAULT_MODEL, ask_with_image

TRANSCRIBE_PROMPT = """\
This photo shows a handwritten Python program written by a student.
Transcribe it into the program the student meant to write, reading the
handwriting the way a professor grading on paper would. The result will be
run against test cases, so the student is graded on their code, not on their
penmanship.

Resolve handwriting, not programming:
- Handwriting issues should be read charitably. Programming mistakes must be
  kept exactly as written, because those are what is being graded.
- Ask of each choice: "Is this about how the student formed a character, or
  about what code the student wrote?" Only the first may be resolved.

Allowed (handwriting):
- Ambiguous characters: pick the reading that fits the context. A character
  in a number is a digit, a character in a name is a letter (0 vs O, 1 vs l,
  6 vs b, 2 vs z). A slashed zero is 0.
- Letter case in names: if the same name appears with letters whose case is
  unclear (s vs S, total vs Total, myVar vs myvar), the student meant one
  name. Use the spelling from where it is first assigned, everywhere.
- Indentation: handwritten indentation drifts. Use 4 spaces per level and
  give each line the level its position and the surrounding structure
  indicate (for example, lines under an if belong to that block).
- Spacing inside a line, letter size, and messy strokes do not matter.
- Ignore crossed-out text.

Not allowed (programming):
- Do not add a missing colon, parenthesis, bracket, or quote.
- Do not fix a misspelled name when the letters are clearly different
  (count vs coutn), or a wrong function, operator, or number that is
  clearly written.
- Do not change logic, add imports, or add code that is not on the page.
- If a line is clearly placed at the wrong indentation level (not drift, but
  an obvious outdent or indent), keep it where the student put it.
- In string literals, keep the text as written. Use normal handwriting
  judgment for letter case, but do not correct spelling.

uncertain_lines: list only readings you could not settle with the rules
above, where the other reading would change what the program does. For each,
give the 1-based line number, the full line as you transcribed it (chosen),
the full line under the other reading (alternative), and a short reason.
Most programs should have none."""

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
