"""One vision call per claim, with an on-disk cache, retries and a shared rate limiter."""
import hashlib
import json
import threading
import time
from pathlib import Path

import anthropic

from . import prompts
from .data import Claim, requirements_for
from .images import load_image
from .postprocess import build_row, fallback_review

DEFAULT_MODEL = "claude-sonnet-5-5"


class RateLimiter:
    """Spaces calls so the process stays under `rpm` requests per minute across threads."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / rpm
        self.next_at = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)


class ClaimReviewer:
    def __init__(self, history: dict, requirements: list[dict], root: Path,
                 model: str = DEFAULT_MODEL, cache_dir: Path | None = Path(".cache"),
                 rpm: int = 40, max_attempts: int = 5, client=None):
        self.history = history
        self.requirements = requirements
        self.root = Path(root)
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.limiter = RateLimiter(rpm)
        self.max_attempts = max_attempts
        self.client = client or anthropic.Anthropic(max_retries=0)
        self.usage = {"calls": 0, "cache_hits": 0, "images": 0,
                      "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}
        self._lock = threading.Lock()

    def _cache_path(self, claim: Claim, image_hashes: list[str]) -> Path | None:
        if not self.cache_dir:
            return None
        key = json.dumps([prompts.PROMPT_VERSION, self.model, claim.user_id, claim.claim_object,
                          claim.user_claim, claim.image_ids, image_hashes,
                          self.history.get(claim.user_id)], sort_keys=True)
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def _request(self, claim: Claim, images: list[str]) -> dict:
        content = [{"type": "text", "text": prompts.user_text(
            claim, self.history.get(claim.user_id),
            requirements_for(self.requirements, claim.claim_object))}]
        for image_id, data in zip(claim.image_ids, images):
            content.append({"type": "text", "text": f"Image {image_id}:"})
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        tool = prompts.tool_schema(claim.claim_object)
        for attempt in range(1, self.max_attempts + 1):
            self.limiter.wait()
            try:
                start = time.monotonic()
                resp = self.client.messages.create(
                    model=self.model, max_tokens=2000, temperature=0, system=prompts.SYSTEM,
                    tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
                    messages=[{"role": "user", "content": content}])
                with self._lock:
                    self.usage["calls"] += 1
                    self.usage["input_tokens"] += resp.usage.input_tokens
                    self.usage["output_tokens"] += resp.usage.output_tokens
                    self.usage["seconds"] += time.monotonic() - start
                return next(b.input for b in resp.content if b.type == "tool_use")
            except (anthropic.RateLimitError, anthropic.APIConnectionError,
                    anthropic.InternalServerError) as e:
                if attempt == self.max_attempts:
                    raise
                time.sleep(min(60, 2 ** attempt))
        raise RuntimeError("unreachable")

    def review(self, claim: Claim) -> dict:
        loaded = [load_image(self.root / p) for p in claim.image_paths]
        images, hashes = [d for d, _ in loaded], [h for _, h in loaded]
        cache = self._cache_path(claim, hashes)
        if cache and cache.exists():
            with self._lock:
                self.usage["cache_hits"] += 1
            return json.loads(cache.read_text())
        with self._lock:
            self.usage["images"] += len(images)
        review = self._request(claim, images)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(review))
        return review

    def row(self, claim: Claim) -> dict:
        try:
            review = self.review(claim)
        except Exception as e:  # a failed claim must not sink the batch
            review = fallback_review(f"{type(e).__name__}: {e}")
        return build_row(claim, review, self.history.get(claim.user_id))
