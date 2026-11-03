# insureit

Multi-modal damage claim review for `car`, `laptop` and `package` claims. For each claim the agent
reads the customer–support chat, looks at every submitted image, applies the user's history and the
minimum evidence requirements, and returns the 14-column review row described in
`dataset/problem_statement.md`.

## How it works

- One vision call per claim (Claude or Gemini, see `insureit/backends.py`) (all images together, each labelled with its id) that must return the `submit_review` structure,
  a schema that only allows the permitted values (`insureit/prompts.py`).
- Chat text and any text inside images are treated as untrusted data. Instructions such as "approve
  immediately" are flagged `text_instruction_present` and never followed.
- `insureit/postprocess.py` validates the answer and adds history risk deterministically: history
  flags are merged into `risk_flags`, and `user_history_risk` also implies `manual_review_required`
  (this is the pattern in the labeled samples). A call that fails for good becomes a
  `not_enough_information` row flagged for manual review instead of a guess.
- Images are downscaled to 1568 px, results are cached on disk (`.cache/`, keyed by prompt version,
  model, claim and image hashes), calls share a requests-per-minute limiter, and rate-limit or
  connection errors are retried with backoff.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # provider claude (default)
export GEMINI_API_KEY=...      # provider gemini
```

The CSVs are in `dataset/`. The images are not committed (about 55 MB): unpack them to
`dataset/images/sample/` and `dataset/images/test/`.

## Run

```bash
python -m insureit.cli dataset/claims.csv output.csv        # predictions for the test set
python -m insureit.cli dataset/claims.csv output.csv --provider gemini   # same, with Gemini (default gemini-3.5-flash)
python -m evaluation.evaluate                                # run + score on dataset/sample_claims.csv
python -m evaluation.evaluate --pred some_predictions.csv    # score an existing file
python -m pytest tests                                       # offline tests
```

Evaluation reports exact-match accuracy for `evidence_standard_met`, `issue_type`, `object_part`,
`claim_status`, `valid_image` and `severity`, F1 and exact-match for the set columns `risk_flags` and
`supporting_image_ids`, a `claim_status` confusion table, and the list of rows that differ.

## Reviewer inbox

A web queue for the human adjuster who signs off on the model's reviews:

```bash
python -m insureit.cli dataset/claims.csv output.csv
python -m insureit.inbox output.csv --dataset dataset     # open http://127.0.0.1:8000
```

- Claims that need a person come first: manual review, risk flags, then anything not `supported`.
- Each claim page shows the chat, every image, the model's decision with its justification, flags
  and cited images, and a form to approve it or override any field.
- For claims without enough evidence it drafts a message that asks the customer for the specific
  photo that is missing (sharper, straight on, a wide shot to match the vehicle, and so on).
- Decisions are stored in SQLite next to the predictions (`output.inbox.db`). `/export.csv`
  downloads the reviewed rows in the labelled 14-column format, so overrides become new eval
  examples (`python -m evaluation.evaluate --pred ...` against them), and `/api/stats` counts the
  overrides by field, which shows where the model is weakest.
- All customer text is HTML-escaped, and only image files listed in the predictions are served.
