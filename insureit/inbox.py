"""Reviewer inbox: a small web app where an adjuster works through the model's reviews.

    python -m insureit.inbox output.csv --dataset dataset        # http://127.0.0.1:8000

The queue puts claims that need a human first (manual review, not enough information, risk
flags). For each claim the adjuster sees the chat, every image, the model's decision and flags,
and either approves it or overrides the fields that are wrong. Decisions are stored in SQLite
(`inbox.db` next to the predictions). `/export.csv` writes the reviewed rows in the labelled
14-column format, so every override becomes a new labelled example for `evaluation.evaluate`.
For claims without enough evidence the page drafts a specific request to the customer.

All claim text is customer input and is escaped before it is rendered."""
import argparse
import csv
import html
import io
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from .data import load_requirements, read_csv, requirements_for
from .schema import (CLAIM_STATUS, ISSUE_TYPES, OBJECT_PARTS, OUTPUT_COLUMNS, RISK_FLAGS,
                     SEVERITIES)

NEEDS_HUMAN = {"manual_review_required", "possible_manipulation", "text_instruction_present",
               "wrong_object", "claim_mismatch", "non_original_image", "user_history_risk"}


def priority(row: dict) -> int:
    """Lower is reviewed first."""
    flags = set(row["risk_flags"].split(";"))
    if flags & NEEDS_HUMAN:
        return 0
    if row["claim_status"] != "supported":
        return 1
    return 2


ASKS = {
    "blurry_image": "a sharp photo of the {part} (hold the camera steady and tap to focus)",
    "cropped_or_obstructed": "a photo with the whole {part} in frame and nothing covering it",
    "low_light_or_glare": "a photo of the {part} in good light, without glare or reflections",
    "wrong_angle": "a photo of the {part} taken straight on, from about one metre away",
    "damage_not_visible": "a close-up of the damage on the {part}",
    "wrong_object_part": "a photo of the {part} you are claiming for",
    "wrong_object": "a wide photo of the whole {object} that also shows the damaged {part}, so we "
                    "can match the close-up to it",
    "claim_mismatch": "a wide photo of the whole {object} that also shows the damaged {part}, so we "
                      "can match the close-up to it",
}


def evidence_request(row: dict, requirements: list[dict]) -> str | None:
    """A message asking the customer for exactly the evidence that is missing, or None."""
    if row["claim_status"] != "not_enough_information" and row["evidence_standard_met"] == "true":
        return None
    obj = row["claim_object"]
    part = row["object_part"].replace("_", " ") if row["object_part"] != "unknown" else \
        f"damaged part of the {obj}"
    asks = []
    for flag in row["risk_flags"].split(";"):
        ask = ASKS.get(flag, "").format(part=part, obj=obj, object=obj)
        if ask and ask not in asks:
            asks.append(ask)
    if not asks:
        asks.append(f"a clear, well-lit close-up of the {part}")
    reqs = [r["minimum_image_evidence"] for r in requirements_for(requirements, obj)
            if r["claim_object"] == obj][:1]
    lines = ["Hi, thanks for your claim. We need a bit more before we can decide it. Please send:"]
    lines += [f"- {a[0].upper()}{a[1:]}" for a in asks]
    if reqs:
        lines.append(f"For reference, our standard for {obj} claims: {reqs[0]}")
    lines.append("Please take new photos rather than editing the old ones. Thank you!")
    return "\n".join(lines)


class Store:
    """Reviewer decisions, keyed by row number in the predictions file."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS decisions (
            row INTEGER PRIMARY KEY, user_id TEXT NOT NULL, action TEXT NOT NULL,
            fields TEXT NOT NULL, note TEXT NOT NULL, decided_at TEXT NOT NULL)""")
        self.db.commit()

    def save(self, row: int, user_id: str, action: str, fields: dict, note: str):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                            (row, user_id, action, json.dumps(fields), note,
                             datetime.now(timezone.utc).isoformat(timespec="seconds")))
            self.db.commit()

    def all(self) -> dict[int, dict]:
        with self.lock:
            cur = self.db.execute("SELECT row, user_id, action, fields, note, decided_at "
                                  "FROM decisions")
            return {r[0]: {"user_id": r[1], "action": r[2], "fields": json.loads(r[3]),
                           "note": r[4], "decided_at": r[5]} for r in cur.fetchall()}


def reviewed_row(row: dict, decision: dict | None) -> dict:
    return {**row, **(decision or {}).get("fields", {})}


CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--card:#fff;--line:#e7e5e4;--accent:#2563eb;
--warn:#b45309;--bad:#b91c1c;--good:#15803d}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--card:#292524;
--line:#44403c;--accent:#60a5fa;--warn:#fbbf24;--bad:#f87171;--good:#4ade80}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);
color:var(--fg)}main{max-width:1100px;margin:0 auto;padding:16px}a{color:var(--accent)}
h1{font-size:20px}table{width:100%;border-collapse:collapse;background:var(--card)}
td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.tag{display:inline-block;padding:0 6px;margin:1px;border-radius:4px;border:1px solid var(--line);
font-size:12px}.p0{color:var(--bad)}.p1{color:var(--warn)}.p2{color:var(--good)}
.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:760px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
img{max-width:100%;border-radius:6px}label{display:block;margin:6px 0 2px;font-weight:600}
select,textarea{width:100%;padding:6px;background:var(--bg);color:var(--fg);
border:1px solid var(--line);border-radius:6px}select[multiple]{height:auto}
button{padding:8px 14px;border-radius:6px;border:0;background:var(--accent);color:#fff;
font-weight:600;cursor:pointer}button.secondary{background:var(--muted)}
pre{white-space:pre-wrap;background:var(--bg);padding:8px;border-radius:6px}
"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'>"
                        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
                        f"<body><main>{body}</main></body></html>")


def tags(value: str) -> str:
    return "".join(f"<span class='tag'>{html.escape(v)}</span>" for v in value.split(";")
                   if v and v != "none") or "<span class='muted'>none</span>"


def select(name: str, options: list[str], current: str, multiple: bool = False) -> str:
    chosen = set(current.split(";")) if multiple else {current}
    opts = "".join(f"<option{' selected' if o in chosen else ''}>{html.escape(o)}</option>"
                   for o in options)
    size = f" multiple size={min(len(options), 8)}" if multiple else ""
    return (f"<label for='{name}'>{name.replace('_', ' ')}</label>"
            f"<select id='{name}' name='{name}'{size}>{opts}</select>")


def create_app(predictions: Path, dataset: Path, db_path: Path | None = None) -> FastAPI:
    predictions, dataset = Path(predictions), Path(dataset)
    rows = read_csv(predictions)
    requirements = load_requirements(dataset / "evidence_requirements.csv")
    store = Store(db_path or predictions.with_suffix(".inbox.db"))
    allowed_images = {p for r in rows for p in r["image_paths"].split(";")}
    app = FastAPI(title="insureit reviewer inbox")

    def get_row(i: int) -> dict:
        if not 0 <= i < len(rows):
            raise HTTPException(404, "no such claim")
        return rows[i]

    @app.get("/", response_class=HTMLResponse)
    def queue(show: str = "pending"):
        decisions = store.all()
        order = sorted(range(len(rows)), key=lambda i: (priority(rows[i]), i))
        if show == "pending":
            order = [i for i in order if i not in decisions]
        done = len(decisions)
        overrides = sum(d["action"] == "override" for d in decisions.values())
        body = [f"<h1>Claims inbox</h1><p class='muted'>{done} of {len(rows)} reviewed, "
                f"{overrides} overridden. "
                f"<a href='/?show={'all' if show == 'pending' else 'pending'}'>"
                f"{'Show all' if show == 'pending' else 'Show pending only'}</a> · "
                f"<a href='/export.csv'>Export reviewed rows</a></p>",
                "<table><tr><th>#</th><th>Claim</th><th>Model decision</th><th>Flags</th>"
                "<th>Reviewer</th></tr>"]
        for i in order:
            r, d = rows[i], decisions.get(i)
            p = priority(r)
            status = d["action"] if d else "<span class='muted'>pending</span>"
            body.append(
                f"<tr><td><a href='/claims/{i}'>{i + 1}</a></td>"
                f"<td>{html.escape(r['user_id'])} · {html.escape(r['claim_object'])}<br>"
                f"<span class='muted'>{html.escape(r['user_claim'][:110])}…</span></td>"
                f"<td class='p{p}'>{html.escape(r['claim_status'])}<br>"
                f"<span class='muted'>{html.escape(r['issue_type'])} / "
                f"{html.escape(r['object_part'])} / {html.escape(r['severity'])}</span></td>"
                f"<td>{tags(r['risk_flags'])}</td><td>{status}</td></tr>")
        if not order:
            body.append("<tr><td colspan='5'>Nothing left to review.</td></tr>")
        body.append("</table>")
        return page("Claims inbox", "".join(body))

    @app.get("/claims/{i}", response_class=HTMLResponse)
    def claim(i: int):
        r = get_row(i)
        d = store.all().get(i)
        current = reviewed_row(r, d)
        images = "".join(
            f"<figure><img src='/images/{html.escape(p)}' alt='{html.escape(Path(p).stem)}'>"
            f"<figcaption class='muted'>{html.escape(Path(p).stem)}</figcaption></figure>"
            for p in r["image_paths"].split(";"))
        chat = html.escape(r["user_claim"]).replace(" | ", "<br>")
        request = evidence_request(r, requirements)
        ask = (f"<div class='card'><h3>Evidence request draft</h3>"
               f"<pre>{html.escape(request)}</pre></div>") if request else ""
        decided = (f"<p class='muted'>Last decision: {html.escape(d['action'])} at "
                   f"{html.escape(d['decided_at'])}</p>") if d else ""
        image_ids = [Path(p).stem for p in r["image_paths"].split(";")]
        form = (
            f"<form method='post' action='/claims/{i}' class='card'><h3>Your decision</h3>"
            + select("claim_status", CLAIM_STATUS, current["claim_status"])
            + select("issue_type", ISSUE_TYPES, current["issue_type"])
            + select("object_part", OBJECT_PARTS[r["claim_object"]], current["object_part"])
            + select("severity", SEVERITIES, current["severity"])
            + select("evidence_standard_met", ["true", "false"], current["evidence_standard_met"])
            + select("valid_image", ["true", "false"], current["valid_image"])
            + select("risk_flags", ["none", *RISK_FLAGS], current["risk_flags"], multiple=True)
            + select("supporting_image_ids", ["none", *image_ids], current["supporting_image_ids"],
                     multiple=True)
            + "<label for='note'>note</label><textarea id='note' name='note' rows='2'>"
            + html.escape(d["note"] if d else "") + "</textarea><p>"
            "<button name='action' value='approve' class='secondary'>Approve model decision</button> "
            "<button name='action' value='override'>Save my changes</button></p></form>")
        nav = ("<p><a href='/'>← Inbox</a>"
               + (f" · <a href='/claims/{i + 1}'>Next claim →</a>" if i + 1 < len(rows) else "")
               + "</p>")
        body = (
            f"{nav}<h1>Claim {i + 1}: {html.escape(r['user_id'])} · "
            f"{html.escape(r['claim_object'])}</h1>{decided}"
            f"<div class='grid'><div><div class='card'><h3>Conversation</h3><p>{chat}</p></div>"
            f"<div class='card'><h3>Images</h3>{images}</div></div>"
            f"<div><div class='card'><h3>Model decision</h3>"
            f"<p class='p{priority(r)}'><b>{html.escape(r['claim_status'])}</b> · "
            f"{html.escape(r['issue_type'])} on {html.escape(r['object_part'])}, "
            f"severity {html.escape(r['severity'])}</p>"
            f"<p>{html.escape(r['claim_status_justification'])}</p>"
            f"<p class='muted'>Evidence: {html.escape(r['evidence_standard_met_reason'])}</p>"
            f"<p>Flags: {tags(r['risk_flags'])}</p>"
            f"<p>Supporting images: {tags(r['supporting_image_ids'])}</p></div>"
            f"{ask}{form}</div></div>")
        return page(f"Claim {i + 1}", body)

    @app.post("/claims/{i}")
    def decide(i: int, action: str = Form(...), claim_status: str = Form(...),
               issue_type: str = Form(...), object_part: str = Form(...),
               severity: str = Form(...), evidence_standard_met: str = Form(...),
               valid_image: str = Form(...), risk_flags: list[str] = Form(["none"]),
               supporting_image_ids: list[str] = Form(["none"]), note: str = Form("")):
        r = get_row(i)
        image_ids = [Path(p).stem for p in r["image_paths"].split(";")]
        checks = [(claim_status, CLAIM_STATUS), (issue_type, ISSUE_TYPES),
                  (object_part, OBJECT_PARTS[r["claim_object"]]), (severity, SEVERITIES),
                  (evidence_standard_met, ["true", "false"]), (valid_image, ["true", "false"])]
        if action not in ("approve", "override") or any(v not in ok for v, ok in checks):
            raise HTTPException(422, "invalid value")
        flags = [f for f in RISK_FLAGS if f in risk_flags]  # canonical order, drops "none"
        support = [s for s in image_ids if s in supporting_image_ids]
        new = {"claim_status": claim_status, "issue_type": issue_type, "object_part": object_part,
               "severity": severity, "evidence_standard_met": evidence_standard_met,
               "valid_image": valid_image, "risk_flags": ";".join(flags) or "none",
               "supporting_image_ids": ";".join(support) or "none"}
        changed = {k: v for k, v in new.items() if v != r[k]}
        if action == "approve" or not changed:
            action, changed = "approve", {}
        store.save(i, r["user_id"], action, changed, note.strip())
        nxt = next((j for j in range(i + 1, len(rows)) if j not in store.all()), None)
        return RedirectResponse(f"/claims/{nxt}" if nxt is not None else "/", status_code=303)

    @app.get("/images/{path:path}")
    def image(path: str):
        if path not in allowed_images:  # only files the predictions refer to
            raise HTTPException(404)
        file = dataset / path
        if not file.is_file():
            raise HTTPException(404, "image not found; unpack the images into the dataset folder")
        return FileResponse(file)

    @app.get("/export.csv")
    def export():
        decisions = store.all()
        buf = io.StringIO()
        w = csv.DictWriter(buf, OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for i in sorted(decisions):
            w.writerow({c: reviewed_row(rows[i], decisions[i])[c] for c in OUTPUT_COLUMNS})
        return Response(buf.getvalue(), media_type="text/csv", headers={
            "Content-Disposition": "attachment; filename=reviewed_claims.csv"})

    @app.get("/api/stats")
    def stats():
        decisions = store.all()
        fields = {}
        for d in decisions.values():
            for k in d["fields"]:
                fields[k] = fields.get(k, 0) + 1
        return {"claims": len(rows), "reviewed": len(decisions),
                "overridden": sum(d["action"] == "override" for d in decisions.values()),
                "overrides_by_field": fields}

    return app


def main():
    p = argparse.ArgumentParser()
    p.add_argument("predictions", help="a CSV written by insureit.cli")
    p.add_argument("--dataset", default="dataset", help="folder the image paths are relative to")
    p.add_argument("--db", help="SQLite file for decisions (default: next to the predictions)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    import uvicorn
    uvicorn.run(create_app(Path(a.predictions), Path(a.dataset), a.db and Path(a.db)),
                host=a.host, port=a.port)


if __name__ == "__main__":
    main()
