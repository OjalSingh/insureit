"""python -m insureit.cli dataset/claims.csv output.csv"""
import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import DEFAULT_MODEL, ClaimReviewer
from .data import load_claims, load_history, load_requirements
from .schema import OUTPUT_COLUMNS


def run(claims_csv, output_csv, dataset, model=DEFAULT_MODEL, workers=4, rpm=40,
        cache_dir=".cache", limit=None, reviewer=None):
    dataset = Path(dataset)
    claims = load_claims(claims_csv)[:limit]
    reviewer = reviewer or ClaimReviewer(
        load_history(dataset / "user_history.csv"),
        load_requirements(dataset / "evidence_requirements.csv"),
        root=dataset, model=model, cache_dir=cache_dir, rpm=rpm)
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(reviewer.row, claims))
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    return rows, reviewer.usage


def main():
    p = argparse.ArgumentParser()
    p.add_argument("claims_csv")
    p.add_argument("output_csv")
    p.add_argument("--dataset", default="dataset")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--rpm", type=int, default=40)
    p.add_argument("--limit", type=int)
    a = p.parse_args()
    _, usage = run(a.claims_csv, a.output_csv, a.dataset, a.model, a.workers, a.rpm,
                   limit=a.limit)
    print(json.dumps(usage, indent=2))


if __name__ == "__main__":
    main()
