import json

from evaluation.gate import main


def _metrics(path, claim_status, rows=20):
    path.write_text(json.dumps({
        "rows": rows, "exact": {"claim_status": claim_status, "severity": 0.5},
        "set_f1": {"risk_flags": 0.7}, "set_exact": {"risk_flags": 0.4}, "usage": None}))
    return str(path)


def test_gate_fails_on_drop_and_passes_within_tolerance(tmp_path):
    base = tmp_path / "baseline.json"
    assert main([_metrics(tmp_path / "b.json", 0.9), "--baseline", str(base), "--update"]) == 0
    summary = tmp_path / "summary.md"
    assert main([_metrics(tmp_path / "r.json", 0.85), "--baseline", str(base),
                 "--summary", str(summary)]) == 1
    assert "fell from 90.0% to 85.0%" in summary.read_text()
    assert main([_metrics(tmp_path / "r.json", 0.85), "--baseline", str(base),
                 "--tolerance", "0.05"]) == 0
    assert main([_metrics(tmp_path / "r.json", 0.95), "--baseline", str(base)]) == 0


def test_gate_without_baseline_passes(tmp_path):
    assert main([_metrics(tmp_path / "r.json", 0.5), "--baseline", str(tmp_path / "none.json")]) == 0
