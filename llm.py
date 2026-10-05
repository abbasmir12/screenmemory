"""Tiny client for any OpenAI-compatible /chat/completions endpoint.

Works with Ollama, LM Studio, Google AI Studio, OpenRouter, vLLM, OpenAI...
Supports images (vision) and tool calling. Standard library only.
"""
import base64
import io
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import config


class LLMError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def image_data_url(path) -> str:
    """Shrink the screenshot (fast uploads on slow internet) and encode it."""
    path = Path(path)
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        data, mime = buf.getvalue(), "image/jpeg"
    except ImportError:
        data = path.read_bytes()
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def chat(messages, tools=None, temperature=0.2) -> dict:
    """Send a conversation, return the assistant message dict (may contain tool_calls)."""
    payload = {"model": config.MODEL, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        f"{config.BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.API_KEY}"},
    )
    last = LLMError("unknown error")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:300]
            last = LLMError(f"HTTP {e.code}: {detail}", e.code)
            if e.code in (400, 401, 403, 404):  # retrying will not help
                raise last
        except Exception as e:
            last = LLMError(str(e))
        time.sleep(6 * (attempt + 1))
    raise last


def ask(prompt: str, image_path=None) -> str:
    """One question (optionally about one image) -> plain text answer."""
    content = [{"type": "text", "text": prompt}]
    if image_path:
        content.append({"type": "image_url", "image_url": {"url": image_data_url(image_path)}})
    return chat([{"role": "user", "content": content}]).get("content") or ""


def parse_json(text, fallback):
    """Pull the first {...} object out of a model reply (models add stray text)."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return fallback
