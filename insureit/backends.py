"""Model backends. Each takes the system prompt, the user text, labelled images and the review
schema, and returns (review dict, usage dict). Usage holds input_tokens, output_tokens and, where the
provider reports them, cache_creation_input_tokens and cache_read_input_tokens. Retryable failures
raise Retryable."""
import json
import os
import urllib.error
import urllib.request

import anthropic


class Retryable(Exception):
    """A failure worth retrying. `retry_after` is the server's suggested wait in seconds, if any."""

    def __init__(self, msg, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class QuotaExhausted(RuntimeError):
    """The provider's daily quota is used up. Not retried; the batch should stop calling."""


def _gemini_retry_delay(body: bytes) -> float | None:
    """Reads google.rpc.RetryInfo ("retryDelay": "17s") from a Gemini error body."""
    try:
        details = json.loads(body).get("error", {}).get("details", [])
    except ValueError:
        return None
    for d in details:
        delay = d.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    return None


def strict_schema(schema):
    """Copy of a JSON schema with `additionalProperties: false` on every object, as strict tool
    use requires."""
    if isinstance(schema, dict):
        out = {k: strict_schema(v) for k, v in schema.items()}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


class ClaudeBackend:
    """Claude via the Messages API.

    - The system prompt and tool schema are the same for every claim of an object type, so they
      are marked for prompt caching: after the first claim only the chat and images are billed at
      the full input price.
    - Current models reject forced `tool_choice` and sampling parameters, so the call uses
      `tool_choice: auto` with a strict tool (schema-valid arguments guaranteed) and checks that the
      tool was actually called.
    - `params()` and `parse()` are shared with the Message Batches path (`insureit/batch.py`)."""

    default_model = "claude-sonnet-5-5"
    default_rpm = 40

    def __init__(self, model: str, client=None, effort: str | None = None):
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic(max_retries=0)

    def params(self, system, text, images, tool) -> dict:
        content = [{"type": "text", "text": text}]
        for image_id, data in images:
            content.append({"type": "text", "text": f"Image {image_id}:"})
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        params = {
            "model": self.model,
            "max_tokens": 16000,
            # tools render before system, so this breakpoint caches both.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": [{**tool, "input_schema": strict_schema(tool["input_schema"]), "strict": True}],
            "tool_choice": {"type": "auto"},
            "messages": [{"role": "user", "content": content}],
        }
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        return params

    @staticmethod
    def parse(message, tool_name: str = "submit_review") -> tuple[dict, dict]:
        if message.stop_reason == "refusal":
            raise RuntimeError("model declined to review the claim")
        review = next((b.input for b in message.content
                       if b.type == "tool_use" and b.name == tool_name), None)
        if review is None:
            raise Retryable(f"model did not call {tool_name} (stop_reason={message.stop_reason})")
        u = message.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
        return review, usage

    def generate(self, system, text, images, tool):
        try:
            message = self.client.messages.create(**self.params(system, text, images, tool))
        except (anthropic.RateLimitError, anthropic.APIConnectionError,
                anthropic.InternalServerError) as e:
            raise Retryable(str(e)) from e
        return self.parse(message, tool["name"])


class GeminiBackend:
    default_model = "gemini-3.5-flash"
    default_rpm = 10  # the free tier allows roughly 10 requests per minute for Flash models
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
            err = e.read()
            if e.code in (429, 500, 502, 503, 504):
                delay = _gemini_retry_delay(err)
                if delay and delay > 600:  # a daily quota, not a per-minute one: retrying is futile
                    raise QuotaExhausted(f"Gemini quota exhausted for {self.model}; "
                                         f"resets in about {delay / 3600:.0f} h") from e
                raise Retryable(f"HTTP {e.code}", delay) from e
            raise RuntimeError(f"Gemini HTTP {e.code}: {err[:200].decode(errors='replace')}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise Retryable(str(e)) from e
        candidate = (body.get("candidates") or [{}])[0]
        text_out = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []))
        if not text_out:
            raise RuntimeError(f"Gemini returned no content (finishReason={candidate.get('finishReason')})")
        usage = body.get("usageMetadata", {})
        return json.loads(text_out), {"input_tokens": usage.get("promptTokenCount", 0),
                                      "output_tokens": usage.get("candidatesTokenCount", 0)}


PROVIDERS = {"claude": ClaudeBackend, "gemini": GeminiBackend}


def make_backend(provider: str, model: str | None = None, **kwargs):
    cls = PROVIDERS[provider]
    return cls(model or cls.default_model, **kwargs)
