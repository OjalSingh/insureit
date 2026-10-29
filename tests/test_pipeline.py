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
