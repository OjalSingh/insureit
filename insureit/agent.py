"""One vision call per claim, with an on-disk cache, retries, a shared rate limiter and an optional
small-to-large model cascade."""
import hashlib
import json
import threading
import time
from pathlib import Path

from . import prompts
from .backends import QuotaExhausted, Retryable, make_backend
from .data import Claim, requirements_for
from .images import load_image
from .postprocess import build_row, fallback_review
from .pricing import TOKEN_KEYS, cost_usd

# A first-tier review with any of these flags goes to the next tier: they mark the hard cases
# (mismatched objects, manipulation, injected instructions) where a cheap model is least reliable.
ESCALATE_FLAGS = {"manual_review_required", "possible_manipulation", "text_instruction_present",
                  "claim_mismatch", "wrong_object", "non_original_image"}


def needs_escalation(review: dict) -> str | None:
    """Why a first-tier review should be redone by the stronger model, or None to keep it."""
    if review.get("confidence") != "high":
        return f"confidence {review.get('confidence') or 'missing'}"
    if review.get("claim_status") not in ("supported", "contradicted"):
        return "not enough information"
    flags = ESCALATE_FLAGS.intersection(review.get("risk_flags", []))
    if flags:
        return "flags " + ",".join(sorted(flags))
    observations = review.get("image_observations") or []
    if review["claim_status"] == "supported" and not any(o.get("supports_claim") for o in observations):
        return "supported without a supporting image"
    return None


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


class Tier:
    """One model in the cascade, with its own usage counters."""

    def __init__(self, backend, provider: str):
        self.backend = backend
        self.model = f"{provider}:{backend.model}"
        self.usage = {"calls": 0, "cache_hits": 0, **{k: 0 for k in TOKEN_KEYS},
                      "batch_calls": 0, "batch_usage": {k: 0 for k in TOKEN_KEYS}}

    def cost(self) -> float | None:
        realtime = {k: self.usage[k] - self.usage["batch_usage"][k] for k in TOKEN_KEYS}
        a, b = cost_usd(self.model, realtime), cost_usd(self.model, self.usage["batch_usage"], True)
        return None if a is None or b is None else a + b


class ClaimReviewer:
    def __init__(self, history: dict, requirements: list[dict], root: Path,
                 provider: str = "claude", model: str | None = None,
                 cache_dir: Path | None = Path(".cache"), rpm: int | None = None, max_attempts: int = 8,
                 backend=None, cascade: str | None = None, cascade_backend=None,
                 effort: str | None = None):
        """`cascade` names a cheaper model of the same provider that reviews every claim first;
        only reviews that `needs_escalation` flags are redone by `model`."""
        self.history = history
        self.requirements = requirements
        self.root = Path(root)
        kwargs = {"effort": effort} if effort and provider == "claude" else {}
        main = Tier(backend or make_backend(provider, model, **kwargs), provider)
        self.tiers = [main]
        if cascade or cascade_backend:
            self.tiers.insert(0, Tier(cascade_backend or make_backend(provider, cascade, **kwargs),
                                      provider))
        self.model = main.model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.limiter = RateLimiter(rpm or getattr(main.backend, "default_rpm", 40))
        self.max_attempts = max_attempts
        self.counts = {"claims": 0, "images": 0, "escalated": 0, "seconds": 0.0}
        self.escalations: list[dict] = []
        self._lock = threading.Lock()
        self.quota_error: QuotaExhausted | None = None

    # -- request building, shared with the batch path ------------------------------------------

    def request(self, claim: Claim, images: list[str]):
        """(system, text, labelled images, tool) for one claim."""
        text = prompts.user_text(claim, self.history.get(claim.user_id),
                                 requirements_for(self.requirements, claim.claim_object))
        return prompts.SYSTEM, text, list(zip(claim.image_ids, images)), \
            prompts.tool_schema(claim.claim_object)

    def load(self, claim: Claim) -> tuple[list[str], list[str]]:
        loaded = [load_image(self.root / p) for p in claim.image_paths]
        return [d for d, _ in loaded], [h for _, h in loaded]

    def cache_path(self, tier: Tier, claim: Claim, image_hashes: list[str]) -> Path | None:
        if not self.cache_dir:
            return None
        key = json.dumps([prompts.PROMPT_VERSION, tier.model, claim.user_id, claim.claim_object,
                          claim.user_claim, claim.image_ids, image_hashes,
                          self.history.get(claim.user_id)], sort_keys=True)
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def cached(self, tier: Tier, claim: Claim, hashes: list[str]) -> dict | None:
        path = self.cache_path(tier, claim, hashes)
        if path and path.exists():
            with self._lock:
                tier.usage["cache_hits"] += 1
            return json.loads(path.read_text())
        return None

    def store(self, tier: Tier, claim: Claim, hashes: list[str], review: dict):
        path = self.cache_path(tier, claim, hashes)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(review))

    def record(self, tier: Tier, usage: dict, batch: bool = False):
        with self._lock:
            tier.usage["calls"] += 1
            for k in TOKEN_KEYS:
                tier.usage[k] += usage.get(k, 0)
                if batch:
                    tier.usage["batch_usage"][k] += usage.get(k, 0)
            if batch:
                tier.usage["batch_calls"] += 1

    def note_escalation(self, claim: Claim, reason: str):
        with self._lock:
            self.counts["escalated"] += 1
            self.escalations.append({"user_id": claim.user_id, "reason": reason})

    # -- realtime path -------------------------------------------------------------------------

    def _call(self, tier: Tier, claim: Claim, images: list[str]) -> dict:
        for attempt in range(1, self.max_attempts + 1):
            if self.quota_error:  # stop spending calls once the daily quota is gone
                raise self.quota_error
            self.limiter.wait()
            try:
                start = time.monotonic()
                review, usage = tier.backend.generate(*self.request(claim, images))
            except QuotaExhausted as e:
                self.quota_error = e
                raise
            except Retryable as e:
                if attempt == self.max_attempts:
                    raise
                time.sleep(min(90, e.retry_after or 2 ** attempt))
                continue
            self.record(tier, usage)
            with self._lock:
                self.counts["seconds"] += time.monotonic() - start
            return review
        raise RuntimeError("unreachable")

    def review(self, claim: Claim) -> dict:
        images, hashes = self.load(claim)
        with self._lock:
            self.counts["claims"] += 1
            self.counts["images"] += len(images)
        for i, tier in enumerate(self.tiers):
            review = self.cached(tier, claim, hashes)
            if review is None:
                review = self._call(tier, claim, images)
                self.store(tier, claim, hashes, review)
            if i < len(self.tiers) - 1:
                reason = needs_escalation(review)
                if not reason:
                    return review
                self.note_escalation(claim, reason)
        return review

    def row(self, claim: Claim, review: dict | None = None) -> dict:
        if review is None:
            try:
                review = self.review(claim)
            except Exception as e:  # a failed claim must not sink the batch
                review = fallback_review(f"{type(e).__name__}: {e}")
        return build_row(claim, review, self.history.get(claim.user_id))

    # -- reporting -----------------------------------------------------------------------------

    @property
    def usage(self) -> dict:
        tiers = {}
        total_cost = 0.0
        for t in self.tiers:
            c = t.cost()
            tiers[t.model] = {**{k: v for k, v in t.usage.items() if k != "batch_usage"},
                              "cost_usd": None if c is None else round(c, 6)}
            total_cost = None if c is None or total_cost is None else total_cost + c
        totals = {k: sum(t.usage[k] for t in self.tiers) for k in ["calls", "cache_hits", *TOKEN_KEYS]}
        claims = self.counts["claims"]
        report = {**totals, **self.counts, "seconds": round(self.counts["seconds"], 2),
                  "cost_usd": None if total_cost is None else round(total_cost, 6),
                  "cost_per_1000_claims_usd": (None if total_cost is None or not claims
                                               else round(total_cost / claims * 1000, 4))}
        if len(self.tiers) > 1:
            report["tiers"] = tiers
            report["escalation_rate"] = round(self.counts["escalated"] / claims, 4) if claims else 0
        return report
