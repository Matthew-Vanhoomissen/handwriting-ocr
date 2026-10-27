"""Meta Model API client (OpenAI SDK pointed at https://api.meta.ai/v1) with an on-disk cache keyed by image hash."""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"

_client = None


def get_client():
    """Return a shared client. The OpenAI SDK doesn't read MODEL_API_KEY, so pass it explicitly."""
    global _client
    if _client is None:
        api_key = os.environ.get("MODEL_API_KEY")
        if not api_key:
            raise RuntimeError("MODEL_API_KEY is not set. Add it to .env at the repo root.")
        _client = OpenAI(base_url=BASE_URL, api_key=api_key)
    return _client


def ask_text(prompt, model=DEFAULT_MODEL):
    """Plain text request through the Responses API. Returns the model's text output."""
    response = get_client().responses.create(model=model, input=prompt)
    return response.output_text


if __name__ == "__main__":
    # Smoke test: python -m backend.llm
    print(ask_text("Reply with exactly: pong"))
