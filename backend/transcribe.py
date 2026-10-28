"""Faithful transcription of a handwritten program with Muse Spark.

Returns code and uncertain_lines.
"""

import sys

from backend.llm import DEFAULT_MODEL, ask_with_image

TRANSCRIBE_PROMPT = """This photo shows a handwritten Python program written by a student.
Transcribe it exactly as written, character for character.

Rules:
- Do NOT fix any mistakes. Keep typos, wrong variable names, missing colons, missing
  parentheses, and logic bugs exactly as they appear. The student's mistakes are being graded.
- Preserve indentation using 4 spaces per level, based on how far each line is indented
  relative to the lines around it.
- Do not add code, comments, or imports that are not on the page.
- Ignore crossed-out text.
- List the 1-based line numbers of any lines where you are unsure of a character or of the
  indentation in uncertain_lines. Use an empty list if you are confident in every line."""

TRANSCRIPTION_SCHEMA = {
    "name": "transcription",
    "schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "uncertain_lines": {"type": "array",
                                "items": {"type": "integer"}},
        },
        "required": ["code", "uncertain_lines"],
        "additionalProperties": False,
    },
}


def transcribe(image_path, model=DEFAULT_MODEL, use_cache=True):
    """Return {"code": str, "uncertain_lines": [int]} for one photo."""
    return ask_with_image(TRANSCRIBE_PROMPT, image_path,
                          schema=TRANSCRIPTION_SCHEMA, model=model,
                          use_cache=use_cache)


if __name__ == "__main__":
    # Usage: python -m backend.transcribe samples/simple_python1.jpg [...]
    for path in sys.argv[1:]:
        result = transcribe(path)
        print(f"=== {path}  uncertain_lines={result['uncertain_lines']}")
        print(result["code"], flush=True)
