"""Meta Model API client with an on-disk cache keyed by image hash.

Uses the OpenAI SDK pointed at https://api.meta.ai/v1.
"""

import base64
import hashlib
import io
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

load_dotenv()

BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"
CACHE_DIR = Path(__file__).parent / "data" / "cache"

# Phone photos are 4032x3024. Image token cost grows with resolution,
# so cap the long side.
MAX_IMAGE_SIDE = 2048

_client = None


def get_client():
    """Return a shared client.

    The OpenAI SDK doesn't read MODEL_API_KEY, so pass it explicitly.
    """
    global _client
    if _client is None:
        api_key = os.environ.get("MODEL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MODEL_API_KEY is not set. Add it to .env at the repo root.")
        # max_retries caps the SDK's automatic retries on 429s and 5xx errors.
        _client = OpenAI(base_url=BASE_URL, api_key=api_key, max_retries=2)
    return _client


def ask_text(prompt, model=DEFAULT_MODEL):
    """Plain text request through the Responses API. Returns the text."""
    response = get_client().responses.create(model=model, input=prompt)
    return response.output_text


def image_to_data_url(image_path, max_side=MAX_IMAGE_SIDE):
    """Load an image upright, downscale it, return a base64 JPEG data URL.

    Phone cameras store pixels sideways plus an EXIF "rotate me" tag. The
    API receives raw bytes, so apply the rotation here instead of trusting
    the server to read the tag.
    """
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    if max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def image_hash(image_path):
    return hashlib.sha256(Path(image_path).read_bytes()).hexdigest()


def ask_with_image(prompt, image_path, schema=None, model=DEFAULT_MODEL,
                   use_cache=True):
    """Send a prompt plus one image.

    Returns parsed JSON if a schema is given, else text. Results are cached
    on disk keyed by the image hash plus the prompt, schema, and model, so
    the transcription and re-check prompts for one photo don't collide.
    """
    key_source = json.dumps(
        [image_hash(image_path), prompt, schema, model, MAX_IMAGE_SIDE])
    key = hashlib.sha256(key_source.encode()).hexdigest()
    cache_path = CACHE_DIR / (key + ".json")
    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return cached["result"]

    request = {
        "model": model,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image",
                 "image_url": image_to_data_url(image_path)},
            ],
        }],
    }
    if schema:
        request["text"] = {"format": {
            "type": "json_schema",
            "name": schema["name"],
            "schema": schema["schema"],
            "strict": True,
        }}

    response = get_client().responses.create(**request)
    text = response.output_text
    result = json.loads(text) if schema else text

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    usage = response.usage.model_dump() if response.usage else None
    entry = {"image": str(image_path), "model": model, "usage": usage,
             "result": result}
    cache_path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    # Smoke test: python -m backend.llm
    print(ask_text("Reply with exactly: pong"))
