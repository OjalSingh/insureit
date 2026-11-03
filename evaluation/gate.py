"""Compare an evaluation run with the committed baseline and fail if accuracy dropped.

    python -m evaluation.gate evaluation/results/sample_metrics.json [--baseline evaluation/baseline.json]

Writes a Markdown table (for the PR comment) to --summary and exits 1 when `claim_status`
exact-match accuracy is more than --tolerance below the baseline. Other columns are reported but
do not fail the gate. `--update` rewrites the baseline from the run, for a deliberate change."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATED = "claim_status"


def rows(run: dict, base: dict) -> list[tuple[str, float, float | None]]:
    out = [(c, v, base.get("exact", {}).get(c)) for c, v in run["exact"].items()]
    out += [(f"{c} (F1)", v, base.get("set_f1", {}).get(c)) for c, v in run["set_f1"].items()]
    return out


def table(run: dict, base: dict) -> str:
    lines = ["| Column | Baseline | This PR | Change |", "|---|---|---|---|"]
    for name, now, before in rows(run, base):
        if before is None:
            lines.append(f"| {name} | n/a | {now:.1%} | |")
            continue
        delta = now - before
        mark = "" if abs(delta) < 1e-9 else ("▲ " if delta > 0 else "▼ ")
        bold = "**" if name == GATED else ""
        lines.append(f"| {bold}{name}{bold} | {before:.1%} | {now:.1%} | {mark}{delta:+.1%} |")
    usage = run.get("usage") or {}
    if usage:
        extra = [f"{usage.get('calls', 0)} calls", f"{usage.get('cache_hits', 0)} cache hits"]
        if usage.get("cost_usd") is not None:
            extra.append(f"${usage['cost_usd']:.4f}")
        lines.append("")
        lines.append(f"{run['rows']} labelled claims, " + ", ".join(extra) + ".")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("metrics")
    ap.add_argument("--baseline", default=str(ROOT / "evaluation" / "baseline.json"))
    ap.add_argument("--tolerance", type=float, default=0.0,
                    help="allowed drop in claim_status accuracy, e.g. 0.05 for 5 points")
    ap.add_argument("--summary", help="write the Markdown report here")
    ap.add_argument("--update", action="store_true", help="overwrite the baseline with this run")
    a = ap.parse_args(argv)

    run = json.loads(Path(a.metrics).read_text())
    base_path = Path(a.baseline)
    base = json.loads(base_path.read_text()) if base_path.exists() else {}
    report = table(run, base)
    now, before = run["exact"][GATED], base.get("exact", {}).get(GATED)
    failed = before is not None and now < before - a.tolerance - 1e-9
    verdict = (f"❌ `{GATED}` accuracy fell from {before:.1%} to {now:.1%}." if failed else
               "✅ No drop in `claim_status` accuracy." if before is not None else
               "ℹ️ No baseline yet; this run can become it with `--update`.")
    report = f"### insureit eval\n\n{verdict}\n\n{report}\n"
    print(report)
    if a.summary:
        Path(a.summary).write_text(report)
    if a.update:
        keep = {k: run[k] for k in ("rows", "exact", "set_f1", "set_exact")}
        base_path.write_text(json.dumps(keep, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
