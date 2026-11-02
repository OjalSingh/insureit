"""Model backends. Each takes the system prompt, the user text, labelled images and the review
schema, and returns (review dict, input tokens, output tokens). Retryable failures raise Retryable."""
import json
import os
import urllib.error
import urllib.request

import anthropic


class Retryable(Exception):
    pass


class ClaudeBackend:
    default_model = "claude-sonnet-5-5"

    def __init__(self, model: str, client=None):
        self.model = model
        self.client = client or anthropic.Anthropic(max_retries=0)

    def generate(self, system, text, images, tool):
        content = [{"type": "text", "text": text}]
        for image_id, data in images:
            content.append({"type": "text", "text": f"Image {image_id}:"})
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=2000, temperature=0, system=system,
                tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": content}])
        except (anthropic.RateLimitError, anthropic.APIConnectionError,
                anthropic.InternalServerError) as e:
            raise Retryable(str(e)) from e
        review = next(b.input for b in resp.content if b.type == "tool_use")
        return review, resp.usage.input_tokens, resp.usage.output_tokens


class GeminiBackend:
    default_model = "gemini-2.5-flash"
    url = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, model: str, api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY to use the gemini provider.")

    def request_body(self, system, text, images, tool) -> dict:
        parts = [{"text": text}]
        for image_id, data in images:
            parts.append({"text": f"Image {image_id}:"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": data}})
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": tool["input_schema"],
            },
        }

    def generate(self, system, text, images, tool):
        req = urllib.request.Request(
            self.url.format(model=self.model),
            data=json.dumps(self.request_body(system, text, images, tool)).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                raise Retryable(f"HTTP {e.code}") from e
            raise RuntimeError(f"Gemini HTTP {e.code}: {e.read()[:200].decode(errors='replace')}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise Retryable(str(e)) from e
        candidate = (body.get("candidates") or [{}])[0]
        text_out = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []))
        if not text_out:
            raise RuntimeError(f"Gemini returned no content (finishReason={candidate.get('finishReason')})")
        usage = body.get("usageMetadata", {})
        return (json.loads(text_out), usage.get("promptTokenCount", 0),
                usage.get("candidatesTokenCount", 0))


PROVIDERS = {"claude": ClaudeBackend, "gemini": GeminiBackend}


def make_backend(provider: str, model: str | None = None):
    cls = PROVIDERS[provider]
    return cls(model or cls.default_model)
