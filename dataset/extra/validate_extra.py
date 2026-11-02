"""Check dataset/extra/sample_claims.csv against the allowed values and the gold conventions.

    python dataset/extra/validate_extra.py [extra_dir] [dataset_dir]

Checks: same columns as dataset/sample_claims.csv, allowed values from problem_statement.md,
object_part valid for the object, every image path exists, supporting ids are submitted ids,
history flags are carried into risk_flags, and user_history_risk implies manual_review_required.
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
extra = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent
spec = (dataset / "problem_statement.md").read_text()


def allowed(label):
    line = [m for m in re.finditer(re.escape(label) + r": (.+)", spec)][-1].group(1)
    return set(re.findall(r"`([a-z_]+)`", line))


ISSUES, STATUSES, FLAGS = allowed("`issue_type`"), allowed("`claim_status`"), allowed("`risk_flags`")
PARTS = {o: allowed(f"{o.capitalize()} `object_part`") for o in ("car", "laptop", "package")}
history = {r["user_id"]: r for r in csv.DictReader(open(extra / "user_history.csv"))}
gold_cols = next(csv.reader(open(dataset / "sample_claims.csv")))
rows = list(csv.DictReader(open(extra / "sample_claims.csv")))
errors = []
if list(rows[0]) != gold_cols:
    errors.append("columns differ from dataset/sample_claims.csv")
for i, r in enumerate(rows, 1):
    def bad(msg):
        errors.append(f"row {i} ({r['user_id']}): {msg}")
    ids = []
    for p in r["image_paths"].split(";"):
        if not (extra / p).exists():
            bad(f"missing image {p}")
        ids.append(Path(p).stem)
    if r["user_id"] not in history:
        bad("user not in user_history.csv")
        continue
    if r["issue_type"] not in ISSUES:
        bad(f"issue_type {r['issue_type']}")
    if r["claim_status"] not in STATUSES:
        bad(f"claim_status {r['claim_status']}")
    if r["object_part"] not in PARTS[r["claim_object"]]:
        bad(f"object_part {r['object_part']} for {r['claim_object']}")
    flags = r["risk_flags"].split(";")
    if any(f not in FLAGS for f in flags) or ("none" in flags and len(flags) > 1):
        bad(f"risk_flags {r['risk_flags']}")
    for f in history[r["user_id"]]["history_flags"].split(";"):
        if f != "none" and f not in flags:
            bad(f"history flag {f} missing from risk_flags")
    if "user_history_risk" in flags and "manual_review_required" not in flags:
        bad("user_history_risk without manual_review_required")
    supp = r["supporting_image_ids"]
    if supp != "none" and any(s not in ids for s in supp.split(";")):
        bad(f"supporting_image_ids {supp} not among {ids}")
    if r["severity"] not in {"none", "low", "medium", "high", "unknown"}:
        bad(f"severity {r['severity']}")
    for c in ("evidence_standard_met", "valid_image"):
        if r[c] not in ("true", "false"):
            bad(f"{c} {r[c]}")
print("\n".join(errors) or f"{len(rows)} rows OK")
sys.exit(1 if errors else 0)
