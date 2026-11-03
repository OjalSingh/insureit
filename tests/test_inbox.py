import csv
import io
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from insureit.data import load_requirements, read_csv
from insureit.inbox import create_app, evidence_request, priority

DATASET = Path(__file__).parent.parent / "dataset"


def _client(tmp_path):
    preds = tmp_path / "preds.csv"
    shutil.copy(DATASET / "sample_claims.csv", preds)
    shutil.copy(DATASET / "evidence_requirements.csv", tmp_path / "evidence_requirements.csv")
    first = read_csv(preds)[0]
    for p in first["image_paths"].split(";"):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), "red").save(tmp_path / p)
    return TestClient(create_app(preds, tmp_path, tmp_path / "inbox.db")), read_csv(preds)


def test_queue_puts_risky_claims_first_and_escapes_text(tmp_path):
    client, rows = _client(tmp_path)
    page = client.get("/").text
    risky = next(i for i, r in enumerate(rows) if priority(r) == 0)
    safe = next(i for i, r in enumerate(rows) if priority(r) == 2)
    assert page.index(f"/claims/{risky}'") < page.index(f"/claims/{safe}'")
    assert "<script" not in client.get("/claims/0").text.lower()


def test_override_is_stored_and_exported_as_labelled_row(tmp_path):
    client, rows = _client(tmp_path)
    r = rows[0]
    form = {k: r[k] for k in ["claim_status", "issue_type", "object_part", "severity",
                              "evidence_standard_met", "valid_image"]}
    resp = client.post("/claims/0", data={**form, "action": "override", "severity": "high",
                                          "risk_flags": ["manual_review_required", "blurry_image"],
                                          "supporting_image_ids": r["supporting_image_ids"],
                                          "note": "deeper dent than it looks"},
                       follow_redirects=False)
    assert resp.status_code == 303
    client.post("/claims/1", data={**{k: rows[1][k] for k in form}, "action": "approve"})

    exported = list(csv.DictReader(io.StringIO(client.get("/export.csv").text)))
    assert len(exported) == 2
    assert exported[0]["severity"] == "high"
    assert exported[0]["risk_flags"] == "blurry_image;manual_review_required"  # canonical order
    assert exported[1] == rows[1]
    stats = client.get("/api/stats").json()
    assert stats["reviewed"] == 2 and stats["overridden"] == 1
    assert stats["overrides_by_field"] == {"severity": 1, "risk_flags": 1}
    assert "/claims/0'" not in client.get("/").text  # reviewed claims leave the pending queue


def test_invalid_values_are_rejected(tmp_path):
    client, rows = _client(tmp_path)
    form = {k: rows[0][k] for k in ["claim_status", "issue_type", "object_part", "severity",
                                    "evidence_standard_met", "valid_image"]}
    assert client.post("/claims/0", data={**form, "claim_status": "maybe",
                                          "action": "override"}).status_code == 422


def test_images_are_limited_to_the_claims(tmp_path):
    client, rows = _client(tmp_path)
    assert client.get("/images/" + rows[0]["image_paths"].split(";")[0]).status_code == 200
    assert client.get("/images/../preds.csv").status_code == 404
    assert client.get("/images/evidence_requirements.csv").status_code == 404


def test_evidence_request_names_the_missing_photo():
    reqs = load_requirements(DATASET / "evidence_requirements.csv")
    row = {"claim_status": "not_enough_information", "evidence_standard_met": "false",
           "claim_object": "car", "object_part": "rear_bumper",
           "risk_flags": "blurry_image;wrong_angle;manual_review_required"}
    text = evidence_request(row, reqs)
    assert "sharp photo of the rear bumper" in text and "straight on" in text
    assert evidence_request({**row, "claim_status": "supported",
                             "evidence_standard_met": "true"}, reqs) is None
