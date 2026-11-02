"""python -m insureit.cli dataset/claims.csv output.csv"""
import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import ClaimReviewer
from .data import load_claims, load_history, load_requirements
from .schema import OUTPUT_COLUMNS


def run(claims_csv, output_csv, dataset, provider="claude", model=None, workers=4, rpm=None,
        cache_dir=".cache", limit=None, reviewer=None):
    dataset = Path(dataset)
    claims = load_claims(claims_csv)[:limit]
    reviewer = reviewer or ClaimReviewer(
        load_history(dataset / "user_history.csv"),
        load_requirements(dataset / "evidence_requirements.csv"),
        root=dataset, provider=provider, model=model, cache_dir=cache_dir, rpm=rpm)
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
    p.add_argument("--provider", choices=["claude", "gemini"], default="claude")
    p.add_argument("--model", help="defaults to the provider's default model")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--rpm", type=int, help="requests per minute (default: 40 for claude, 10 for gemini)")
    p.add_argument("--limit", type=int)
    a = p.parse_args()
    _, usage = run(a.claims_csv, a.output_csv, a.dataset, a.provider, a.model, a.workers, a.rpm,
                   limit=a.limit)
    print(json.dumps(usage, indent=2))


if __name__ == "__main__":
    main()
