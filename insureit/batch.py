"""Overnight mode: review a whole file through the Anthropic Message Batches API at half price.

Each cascade tier is one batch. Claims already in the cache are skipped, and only the claims the
first tier escalates go into the second batch. Results come back in any order, so they are keyed
by custom_id, never by position."""
import time

from .agent import needs_escalation
from .backends import ClaudeBackend, Retryable
from .postprocess import fallback_review


def _run_batch(client, requests: list[dict], poll_seconds: float, log) -> dict:
    """Submit requests ({custom_id, params}), wait for the batch to end, return results by id."""
    batch = client.messages.batches.create(requests=requests)
    log(f"batch {batch.id}: {len(requests)} requests submitted")
    while batch.processing_status != "ended":
        time.sleep(poll_seconds)
        batch = client.messages.batches.retrieve(batch.id)
        log(f"batch {batch.id}: {batch.processing_status}, "
            f"{batch.request_counts.processing} still processing")
    return {r.custom_id: r.result for r in client.messages.batches.results(batch.id)}


def review_all(reviewer, claims, poll_seconds: float = 30, log=print) -> list[dict]:
    """Reviews for `claims`, in order. A claim whose request fails gets the manual-review fallback."""
    for tier in reviewer.tiers:
        if not isinstance(tier.backend, ClaudeBackend):
            raise ValueError("batch mode needs the claude provider")

    loaded = [reviewer.load(c) for c in claims]
    reviewer.counts["claims"] += len(claims)
    reviewer.counts["images"] += sum(len(images) for images, _ in loaded)
    reviews: list[dict | None] = [None] * len(claims)
    pending = list(range(len(claims)))

    for level, tier in enumerate(reviewer.tiers):
        last = level == len(reviewer.tiers) - 1
        to_send = []
        for i in pending:
            hit = reviewer.cached(tier, claims[i], loaded[i][1])
            if hit is not None:
                reviews[i] = hit
            else:
                to_send.append(i)
        if to_send:
            backend = tier.backend
            requests = [{"custom_id": f"claim-{i}",
                         "params": backend.params(*reviewer.request(claims[i], loaded[i][0]))}
                        for i in to_send]
            results = _run_batch(backend.client, requests, poll_seconds, log)
            for i in to_send:
                result = results.get(f"claim-{i}")
                if result is None or result.type != "succeeded":
                    kind = "missing" if result is None else result.type
                    reviews[i] = fallback_review(f"batch request {kind}")
                    continue
                try:
                    review, usage = ClaudeBackend.parse(result.message)
                except (Retryable, RuntimeError) as e:
                    reviews[i] = fallback_review(f"{type(e).__name__}: {e}")
                    continue
                reviewer.record(tier, usage, batch=True)
                reviewer.store(tier, claims[i], loaded[i][1], review)
                reviews[i] = review
        if last:
            break
        escalate = []
        for i in pending:
            reason = needs_escalation(reviews[i])
            if reason:
                reviewer.note_escalation(claims[i], reason)
                escalate.append(i)
        pending = escalate
    return reviews
