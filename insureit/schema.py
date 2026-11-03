"""Allowed output values and the 14-column output row."""

OUTPUT_COLUMNS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason", "risk_flags",
    "issue_type", "object_part", "claim_status", "claim_status_justification",
    "supporting_image_ids", "valid_image", "severity",
]

CLAIM_STATUS = ["supported", "contradicted", "not_enough_information"]

ISSUE_TYPES = [
    "dent", "scratch", "crack", "glass_shatter", "broken_part", "missing_part",
    "torn_packaging", "crushed_packaging", "water_damage", "stain", "none", "unknown",
]

OBJECT_PARTS = {
    "car": ["front_bumper", "rear_bumper", "door", "hood", "windshield", "side_mirror",
            "headlight", "taillight", "fender", "quarter_panel", "body", "unknown"],
    "laptop": ["screen", "keyboard", "trackpad", "hinge", "lid", "corner", "port",
               "base", "body", "unknown"],
    "package": ["box", "package_corner", "package_side", "seal", "label", "contents",
                "item", "unknown"],
}

RISK_FLAGS = [
    "blurry_image", "cropped_or_obstructed", "low_light_or_glare", "wrong_angle",
    "wrong_object", "wrong_object_part", "damage_not_visible", "claim_mismatch",
    "possible_manipulation", "non_original_image", "text_instruction_present",
    "user_history_risk", "manual_review_required",
]

SEVERITIES = ["none", "low", "medium", "high", "unknown"]

CONFIDENCE = ["high", "medium", "low"]  # model self-report; drives the cascade, not an output column
