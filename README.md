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
- On Claude the review is a strict tool (`strict: true`, so the arguments always match the schema)
  called with `tool_choice: auto`, since current models reject forced tool choice and sampling
  parameters. A response without the tool call is retried.
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
python -m insureit.cli dataset/claims.csv output.csv --cascade claude-haiku-5-5   # cheap model first
python -m insureit.cli dataset/claims.csv output.csv --batch  # Message Batches API, half price
python -m pytest tests                                       # offline tests
```

Every run prints its usage: calls, cache hits, tokens (including prompt-cache reads and writes),
cost in USD and cost per 1,000 claims. Add `--no-cache` to measure a cold run.

Evaluation reports exact-match accuracy for `evidence_standard_met`, `issue_type`, `object_part`,
`claim_status`, `valid_image` and `severity`, F1 and exact-match for the set columns `risk_flags` and
`supporting_image_ids`, a `claim_status` confusion table, and the list of rows that differ.

## Cost engineering

Three levers, each reported in the usage block so their effect is measured, not assumed
(`insureit/pricing.py` holds the price table):

- **Prompt caching.** The system prompt and the tool schema are identical for every claim of an
  object type, so they carry a `cache_control` breakpoint. After the first claim they are billed
  at 10% of the input price; only the chat, the history and the images are billed in full.
- **Message Batches API** (`--batch`). For overnight queues: the whole file is one batch at 50% of
  the price, results within 24 hours. Cached claims are skipped and failed requests are retried on
  the next run.
- **Model cascade** (`--cascade claude-haiku-5-5`). Every claim goes to the small model first. Its
  review is kept only when it reports `confidence: high`, reaches a verdict (`supported` or
  `contradicted`), cites a supporting image and raises none of the hard-case flags (mismatch,
  wrong object, manipulation, injected instructions, manual review). Everything else is redone by
  `--model`. The usage block shows each tier's calls and cost and the escalation rate, and
  `evaluation.evaluate` shows whether accuracy held. The levers combine: `--batch --cascade ...`
  runs one batch per tier.

To fill in the comparison, run each configuration on the labelled samples with a cold cache:

```bash
python -m evaluation.evaluate --no-cache                                    # baseline
python -m evaluation.evaluate --no-cache --batch                            # batch
python -m evaluation.evaluate --no-cache --cascade claude-haiku-5-5         # cascade
python -m evaluation.evaluate --no-cache --batch --cascade claude-haiku-5-5 # both
```

| Configuration | claim_status accuracy | Cost per 1,000 claims | Escalation rate |
|---|---|---|---|
| Sonnet 5.5, realtime | _run it_ | _run it_ | n/a |
| Sonnet 5.5, batch | _run it_ | _run it_ | n/a |
| Haiku 5.5 to Sonnet 5.5 cascade | _run it_ | _run it_ | _run it_ |
| Cascade, batch | _run it_ | _run it_ | _run it_ |
