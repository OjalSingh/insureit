"""Offline tests for the Claude request shape, cost accounting, the cascade and batch mode."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from insureit import prompts
from insureit.agent import ClaimReviewer, needs_escalation
from insureit.backends import ClaudeBackend, Retryable
from insureit.batch import review_all
from insureit.data import load_claims, load_history, load_requirements
from insureit.pricing import cost_usd

DATASET = Path(__file__).parent.parent / "dataset"
CONFIDENT = {"claim_status": "supported", "confidence": "high", "risk_flags": [],
             "supporting_image_ids": ["img_1"],
             "image_observations": [{"image_id": "img_1", "supports_claim": True}]}


def _message(review=None, stop_reason="tool_use", cache_read=0):
    content = [NS(type="tool_use", name="submit_review", input=review)] if review else \
        [NS(type="text", text="I think it is supported.")]
    usage = NS(input_tokens=100, output_tokens=50, cache_creation_input_tokens=0,
               cache_read_input_tokens=cache_read)
    return NS(content=content, stop_reason=stop_reason, usage=usage)


def test_claude_request_uses_auto_tool_choice_strict_schema_and_caching():
    backend = ClaudeBackend("claude-sonnet-5-5", client=object(), effort="medium")
    params = backend.params("sys", "text", [("img_1", "QUJD")], prompts.tool_schema("car"))
    assert params["tool_choice"] == {"type": "auto"}
    assert "temperature" not in params
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    tool = params["tools"][0]
    assert tool["strict"] is True
    schema = tool["input_schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["image_observations"]["items"]["additionalProperties"] is False
    assert "confidence" in schema["required"]
    assert params["output_config"] == {"effort": "medium"}
    # The tool schema handed to Gemini stays free of the strict-mode additions.
    assert "additionalProperties" not in prompts.tool_schema("car")["input_schema"]


def test_parse_reads_cache_usage_and_rejects_missing_tool_call():
    review, usage = ClaudeBackend.parse(_message(CONFIDENT, cache_read=900))
    assert review == CONFIDENT and usage["cache_read_input_tokens"] == 900
    with pytest.raises(Retryable):
        ClaudeBackend.parse(_message(None, stop_reason="end_turn"))
    with pytest.raises(RuntimeError):
        ClaudeBackend.parse(_message(None, stop_reason="refusal"))


def test_cost_counts_cache_and_batch_discounts():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000,
             "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0}
    # Sonnet 5.5: $2 in, $10 out, cache reads at 10% of input.
    assert cost_usd("claude:claude-sonnet-5-5", usage) == pytest.approx(2 + 1 + 0.2)
    assert cost_usd("claude:claude-sonnet-5-5", usage, batch=True) == pytest.approx(1.6)
    assert cost_usd("gemini:unknown-model", usage) is None


@pytest.mark.parametrize("change,escalates", [
    ({}, False),
    ({"confidence": "medium"}, True),
    ({"claim_status": "not_enough_information"}, True),
    ({"risk_flags": ["text_instruction_present"]}, True),
    ({"image_observations": [{"image_id": "img_1", "supports_claim": False}]}, True),
])
def test_needs_escalation(change, escalates):
    assert bool(needs_escalation({**CONFIDENT, **change})) is escalates


class Scripted:
    """Backend that returns a fixed review and counts calls."""

    def __init__(self, model, review):
        self.model, self.review, self.calls = model, review, 0

    def generate(self, system, text, images, tool):
        self.calls += 1
        return self.review, {"input_tokens": 1000, "output_tokens": 100}


def _setup(tmp_path, n=2):
    claims = load_claims(DATASET / "sample_claims.csv")[:n]
    for c in claims:
        for p in c.image_paths:
            (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), "blue").save(tmp_path / p)
    kwargs = dict(history=load_history(DATASET / "user_history.csv"),
                  requirements=load_requirements(DATASET / "evidence_requirements.csv"),
                  root=tmp_path, cache_dir=tmp_path / "cache", rpm=60000)
    return claims, kwargs


def test_cascade_only_escalates_uncertain_claims(tmp_path):
    claims, kwargs = _setup(tmp_path)
    small = Scripted("claude-haiku-5-5", CONFIDENT)
    large = Scripted("claude-sonnet-5-5", {**CONFIDENT, "claim_status": "contradicted"})
    reviewer = ClaimReviewer(**kwargs, backend=large, cascade_backend=small)
    assert reviewer.review(claims[0])["claim_status"] == "supported"
    assert (small.calls, large.calls) == (1, 0)

    small.review = {**CONFIDENT, "confidence": "low"}
    assert reviewer.review(claims[1])["claim_status"] == "contradicted"
    assert (small.calls, large.calls) == (2, 1)

    usage = reviewer.usage
    assert usage["escalated"] == 1 and usage["escalation_rate"] == 0.5
    haiku = usage["tiers"]["claude:claude-haiku-5-5"]["cost_usd"]
    sonnet = usage["tiers"]["claude:claude-sonnet-5-5"]["cost_usd"]
    assert haiku == pytest.approx(2 * (1000 * 0.10 + 100 * 0.50) / 1e6)
    assert sonnet == pytest.approx((1000 * 2 + 100 * 10) / 1e6)
    assert usage["cost_per_1000_claims_usd"] == pytest.approx((haiku + sonnet) / 2 * 1000, rel=1e-3)


class FakeBatches:
    def __init__(self, respond):
        self.respond, self.submitted = respond, []

    def create(self, requests):
        self.submitted.append(requests)
        return NS(id=f"b{len(self.submitted)}", processing_status="in_progress")

    def retrieve(self, batch_id):
        return NS(id=batch_id, processing_status="ended", request_counts=NS(processing=0))

    def results(self, batch_id):
        requests = self.submitted[int(batch_id[1:]) - 1]
        # Out of order on purpose: results must be matched by custom_id.
        return [NS(custom_id=r["custom_id"], result=self.respond(r))
                for r in reversed(requests)]


def test_batch_mode_runs_one_batch_per_tier_and_matches_by_id(tmp_path):
    claims, kwargs = _setup(tmp_path, n=3)

    def respond(request):
        model, idx = request["params"]["model"], int(request["custom_id"].split("-")[1])
        if idx == 2 and model == "claude-haiku-5-5":
            return NS(type="errored")
        review = {**CONFIDENT, "claim_status": "contradicted" if idx == 1 else "supported",
                  "confidence": "low" if idx == 1 and model == "claude-haiku-5-5" else "high"}
        return NS(type="succeeded", message=_message(review))

    batches = FakeBatches(respond)
    client = NS(messages=NS(batches=batches))
    reviewer = ClaimReviewer(**kwargs, backend=ClaudeBackend("claude-sonnet-5-5", client=client),
                             cascade_backend=ClaudeBackend("claude-haiku-5-5", client=client))
    reviews = review_all(reviewer, claims, poll_seconds=0, log=lambda _: None)

    assert [len(b) for b in batches.submitted] == [3, 2]  # claims 1 and 2 escalated
    assert [r["claim_status"] for r in reviews] == ["supported", "contradicted", "supported"]
    usage = reviewer.usage
    assert usage["tiers"]["claude:claude-sonnet-5-5"]["batch_calls"] == 2
    # Batch calls are billed at half price: 2 Sonnet calls of 100 in / 50 out tokens.
    assert usage["tiers"]["claude:claude-sonnet-5-5"]["cost_usd"] == pytest.approx(
        2 * (100 * 2 + 50 * 10) / 1e6 * 0.5)

    # A second run is served from the cache; only the request that failed is sent again.
    review_all(reviewer, claims, poll_seconds=0, log=lambda _: None)
    assert [[r["custom_id"] for r in b] for b in batches.submitted[2:]] == [["claim-2"]]
