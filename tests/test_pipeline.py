import csv
from pathlib import Path
from types import SimpleNamespace

from insureit import cli
from insureit.data import load_claims, load_history
from insureit.postprocess import build_row
from insureit.schema import OUTPUT_COLUMNS, RISK_FLAGS

DATASET = Path(__file__).parent.parent / "dataset"


def test_history_flags_merge_and_imply_manual_review():
    claim = load_claims(DATASET / "sample_claims.csv")[4]  # user_005, flagged user_history_risk
    history = load_history(DATASET / "user_history.csv")
    row = build_row(claim, {"claim_status": "contradicted", "risk_flags": ["claim_mismatch"]},
                    history[claim.user_id])
    assert row["risk_flags"] == "claim_mismatch;user_history_risk;manual_review_required"
    assert list(row) == OUTPUT_COLUMNS


def test_invalid_values_are_coerced():
    claim = load_claims(DATASET / "sample_claims.csv")[0]
    row = build_row(claim, {"claim_status": "maybe", "issue_type": "wobble",
                            "object_part": "wing", "severity": "huge",
                            "supporting_image_ids": ["img_9"], "risk_flags": ["nonsense"]}, None)
    assert (row["claim_status"], row["issue_type"], row["object_part"], row["severity"]) == (
        "not_enough_information", "unknown", "unknown", "unknown")
    assert row["supporting_image_ids"] == "none"
    assert row["risk_flags"] == "manual_review_required"
    assert set(row["risk_flags"].split(";")) <= set(RISK_FLAGS)


def test_cli_writes_one_row_per_claim(tmp_path):
    class Fake:
        usage = {}

        def row(self, claim):
            return build_row(claim, {"claim_status": "supported"}, None)

    out = tmp_path / "out.csv"
    rows, _ = cli.run(DATASET / "claims.csv", out, DATASET, reviewer=Fake())
    with open(out, newline="") as f:
        assert len(list(csv.DictReader(f))) == len(rows) == len(load_claims(DATASET / "claims.csv"))


def test_gold_scores_perfectly_against_itself():
    from evaluation.evaluate import score
    from insureit.data import read_csv
    gold = read_csv(DATASET / "sample_claims.csv")
    report = score(gold, gold)
    assert all(v == 1.0 for v in report["exact"].values()) and not report["misses"]


def _reviewer(tmp_path, backend):
    from PIL import Image

    from insureit.agent import ClaimReviewer
    from insureit.data import load_history, load_requirements
    (tmp_path / "images").mkdir(exist_ok=True)
    claims = load_claims(DATASET / "sample_claims.csv")[:1]
    for p in claims[0].image_paths:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 64), "red").save(tmp_path / p)
    reviewer = ClaimReviewer(load_history(DATASET / "user_history.csv"),
                             load_requirements(DATASET / "evidence_requirements.csv"),
                             root=tmp_path, cache_dir=tmp_path / "cache", rpm=6000, backend=backend)
    return reviewer, claims[0]


class FakeBackend:
    model = "fake"

    def __init__(self, fail=None):
        self.calls, self.fail = 0, fail

    def generate(self, system, text, images, tool):
        self.calls += 1
        if self.fail:
            raise self.fail
        return {"claim_status": "supported", "supporting_image_ids": ["img_1"]}, 10, 5


def test_reviewer_caches_repeat_claims(tmp_path):
    backend = FakeBackend()
    reviewer, claim = _reviewer(tmp_path, backend)
    first, second = reviewer.row(claim), reviewer.row(claim)
    assert first == second and backend.calls == 1
    assert reviewer.usage["cache_hits"] == 1 and reviewer.usage["input_tokens"] == 10


def test_failed_call_becomes_manual_review_row(tmp_path):
    reviewer, claim = _reviewer(tmp_path, FakeBackend(fail=RuntimeError("boom")))
    row = reviewer.row(claim)
    assert row["claim_status"] == "not_enough_information"
    assert "manual_review_required" in row["risk_flags"].split(";")


def test_gemini_request_shape():
    from insureit import prompts
    from insureit.backends import GeminiBackend
    body = GeminiBackend("gemini-2.5-flash", api_key="x").request_body(
        "sys", "text", [("img_1", "QUJD")], prompts.tool_schema("car"))
    parts = body["contents"][0]["parts"]
    assert parts[1] == {"text": "Image img_1:"} and parts[2]["inline_data"]["data"] == "QUJD"
    assert body["generationConfig"]["responseSchema"]["required"]
