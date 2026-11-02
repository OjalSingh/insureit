"""Score predictions against dataset/sample_claims.csv.

    python -m evaluation.evaluate                 # run the agent on the samples, then score
    python -m evaluation.evaluate --pred out.csv  # score an existing prediction file
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from insureit import cli
from insureit.data import read_csv

ROOT = Path(__file__).resolve().parent.parent
EXACT = ["evidence_standard_met", "issue_type", "object_part", "claim_status", "valid_image",
         "severity"]
SETS = ["risk_flags", "supporting_image_ids"]


def as_set(value: str) -> frozenset:
    return frozenset(v for v in value.split(";") if v and v != "none")


def f1(gold: frozenset, pred: frozenset) -> float:
    if not gold and not pred:
        return 1.0
    hit = len(gold & pred)
    return 0.0 if hit == 0 else 2 * hit / (len(gold) + len(pred))


def score(gold_rows: list[dict], pred_rows: list[dict]) -> dict:
    n = len(gold_rows)
    result = {"rows": n, "exact": {}, "set_f1": {}, "set_exact": {}}
    for col in EXACT:
        result["exact"][col] = sum(g[col] == p[col] for g, p in zip(gold_rows, pred_rows)) / n
    for col in SETS:
        result["set_f1"][col] = sum(f1(as_set(g[col]), as_set(p[col]))
                                    for g, p in zip(gold_rows, pred_rows)) / n
        result["set_exact"][col] = sum(as_set(g[col]) == as_set(p[col])
                                       for g, p in zip(gold_rows, pred_rows)) / n
    result["confusion"] = dict(Counter(
        f"{g['claim_status']} -> {p['claim_status']}" for g, p in zip(gold_rows, pred_rows)))
    result["misses"] = [
        {"row": i + 1, "user_id": g["user_id"],
         **{c: [g[c], p[c]] for c in EXACT + SETS if g[c] != p[c]}}
        for i, (g, p) in enumerate(zip(gold_rows, pred_rows))
        if any(g[c] != p[c] for c in EXACT + SETS)]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", help="existing prediction CSV (skips running the agent)")
    ap.add_argument("--dataset", default=str(ROOT / "dataset"))
    ap.add_argument("--provider", choices=["claude", "gemini"], default="claude")
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rpm", type=int)
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    gold_path = Path(a.dataset) / "sample_claims.csv"
    usage = None
    pred_path = a.pred
    if not pred_path:
        pred_path = out / "sample_predictions.csv"
        _, usage = cli.run(gold_path, pred_path, a.dataset, a.provider, a.model,
                            workers=a.workers, rpm=a.rpm)
    report = score(read_csv(gold_path), read_csv(pred_path))
    report["usage"] = usage
    (out / "sample_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "misses"}, indent=2))
    print(f"{len(report['misses'])} rows differ from gold; details in sample_metrics.json")


if __name__ == "__main__":
    main()
