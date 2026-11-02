"""One vision call per claim, with an on-disk cache, retries and a shared rate limiter."""
import hashlib
import json
import threading
import time
from pathlib import Path

from . import prompts
from .data import Claim, requirements_for
from .backends import QuotaExhausted, Retryable, make_backend
from .images import load_image
from .postprocess import build_row, fallback_review


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
                 provider: str = "claude", model: str | None = None,
                 cache_dir: Path | None = Path(".cache"), rpm: int | None = None, max_attempts: int = 8,
                 backend=None):
        self.history = history
        self.requirements = requirements
        self.root = Path(root)
        self.backend = backend or make_backend(provider, model)
        self.model = f"{provider}:{self.backend.model}"
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.limiter = RateLimiter(rpm or getattr(self.backend, "default_rpm", 40))
        self.max_attempts = max_attempts
        self.usage = {"calls": 0, "cache_hits": 0, "images": 0,
                      "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}
        self._lock = threading.Lock()
        self.quota_error: QuotaExhausted | None = None

    def _cache_path(self, claim: Claim, image_hashes: list[str]) -> Path | None:
        if not self.cache_dir:
            return None
        key = json.dumps([prompts.PROMPT_VERSION, self.model, claim.user_id, claim.claim_object,
                          claim.user_claim, claim.image_ids, image_hashes,
                          self.history.get(claim.user_id)], sort_keys=True)
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def _request(self, claim: Claim, images: list[str]) -> dict:
        text = prompts.user_text(claim, self.history.get(claim.user_id),
                                 requirements_for(self.requirements, claim.claim_object))
        tool = prompts.tool_schema(claim.claim_object)
        labelled = list(zip(claim.image_ids, images))
        for attempt in range(1, self.max_attempts + 1):
            if self.quota_error:  # stop spending calls once the daily quota is gone
                raise self.quota_error
            self.limiter.wait()
            try:
                start = time.monotonic()
                review, tokens_in, tokens_out = self.backend.generate(
                    prompts.SYSTEM, text, labelled, tool)
            except QuotaExhausted as e:
                self.quota_error = e
                raise
            except Retryable as e:
                if attempt == self.max_attempts:
                    raise
                time.sleep(min(90, e.retry_after or 2 ** attempt))
                continue
            with self._lock:
                self.usage["calls"] += 1
                self.usage["input_tokens"] += tokens_in
                self.usage["output_tokens"] += tokens_out
                self.usage["seconds"] += time.monotonic() - start
            return review
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
