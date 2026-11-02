"""Deterministic clean-up of the model output into a valid output row."""
from .schema import (CLAIM_STATUS, ISSUE_TYPES, OBJECT_PARTS, OUTPUT_COLUMNS, RISK_FLAGS,
                     SEVERITIES)


def history_flags(history: dict | None) -> list[str]:
    if not history:
        return []
    return [f for f in history.get("history_flags", "").split(";") if f and f != "none"]


def build_row(claim, review: dict, history: dict | None) -> dict:
    ids = claim.image_ids
    parts = OBJECT_PARTS[claim.claim_object]

    flags = [f for f in review.get("risk_flags", []) if f in RISK_FLAGS and f != "none"]
    flags += history_flags(history)
    if "user_history_risk" in flags:
        flags.append("manual_review_required")
    # Keep the canonical order from the schema, without duplicates.
    flags = [f for f in RISK_FLAGS if f in flags]

    support = [i for i in review.get("supporting_image_ids", []) if i in ids]
    status = review.get("claim_status")
    if status not in CLAIM_STATUS:
        status = "not_enough_information"
        flags = [f for f in RISK_FLAGS if f in flags + ["manual_review_required"]]
    issue = review.get("issue_type")
    part = review.get("object_part")
    severity = review.get("severity")

    row = {
        "user_id": claim.user_id,
        "image_paths": ";".join(claim.image_paths),
        "user_claim": claim.user_claim,
        "claim_object": claim.claim_object,
        "evidence_standard_met": str(bool(review.get("evidence_standard_met"))).lower(),
        "evidence_standard_met_reason": review.get("evidence_standard_met_reason", "").strip(),
        "risk_flags": ";".join(flags) or "none",
        "issue_type": issue if issue in ISSUE_TYPES else "unknown",
        "object_part": part if part in parts else "unknown",
        "claim_status": status,
        "claim_status_justification": review.get("claim_status_justification", "").strip(),
        "supporting_image_ids": ";".join(support) or "none",
        "valid_image": str(bool(review.get("valid_image", True))).lower(),
        "severity": severity if severity in SEVERITIES else "unknown",
    }
    return {c: row[c] for c in OUTPUT_COLUMNS}


def fallback_review(error: str) -> dict:
    """Used when the model call fails for good: route to a human instead of guessing."""
    return {
        "evidence_standard_met": False,
        "evidence_standard_met_reason": f"Automated review failed: {error[:120]}",
        "risk_flags": ["manual_review_required"],
        "issue_type": "unknown", "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": "Automated review could not be completed; needs manual review.",
        "supporting_image_ids": [], "valid_image": False, "severity": "unknown",
    }
