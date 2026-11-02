# Extra labeled claims

41 extra labeled claims (46 images) that target the failure modes seen while tuning the verifier.
They are kept apart from the original dataset so the original sample/test split stays untouched.

## Layout

This folder is a self-contained dataset root, so it can be passed straight to the evaluator:

```bash
python dataset/extra/build_extra.py          # regenerate images + CSVs from dataset/images/sample
python dataset/extra/validate_extra.py       # schema and convention checks
python -m evaluation.evaluate --dataset dataset/extra
```

| File | What it is |
|---|---|
| `sample_claims.csv` | Labeled rows, same 14 columns and quoting as `dataset/sample_claims.csv` |
| `claims.csv` | Same rows, input columns only |
| `user_history.csv` | `dataset/user_history.csv` plus `user_101`–`user_104` |
| `evidence_requirements.csv` | Copy of the original |
| `manifest.csv` | Per case: failure mode, exact source image and transforms, label note |
| `images/extra/case_NNN/img_N.jpg` | Generated images (not committed, like `dataset/images`) |

Image paths in the CSVs are relative to this folder (`images/extra/case_001/img_1.jpg`).

## Where the images come from

Every image is derived from the **labeled sample images** (`dataset/images/sample/`) by a
deterministic transform in `build_extra.py`. No test-set image is used, so nothing here leaks
test labels. The sample images are the competition's own data; some of them carry stock-photo
watermarks, so treat these derived images the same way (internal evaluation only, not for
redistribution). The network policy of the build environment blocked Wikimedia Commons,
Openverse and Hugging Face, so no new openly licensed photos were added yet.

## Coverage

| Failure mode | Cases | What it tests |
|---|---|---|
| Clear close-up supports the claim | 1–6 | Tight crops of real damage with little context must still be `supported` |
| Normal photo, not edited | 7–13 | JPEG recompression, rotation, auto-enhance, crop/resize and clean undamaged photos must not get `possible_manipulation` / `non_original_image` |
| Severity calibration | 14–17 | Same small dent with an exaggerated vs honest chat (14 vs 15); minor dent claimed as crushed laptop |
| Crack vs glass_shatter | 18–20 | "Shattered" and "hairline" wording on cracked-but-intact glass stay `crack` |
| Mismatched images | 21–25 | Close-up and full view from different cars, wrong object class, claimed part not in frame, damage on a different part |
| Image quality | 26–30 | Blurry only, blurry + clear, low light, glare, thumb over the damage |
| Authenticity / injection | 31–35 | Phone-gallery screenshot, stock watermark, copy-pasted damage, instruction written on a sticky note, instruction inside the chat |
| Repeat claimants | 36–39 | Risky history with clear evidence (history adds flags, never overrides the image), same images as a gold sample from a different user |
| Policy exclusions | 40–41 | Pre-existing damage and gradual wear stated in the chat |

## Label conventions

Labels follow the patterns in `dataset/sample_claims.csv`:

- Every `history_flags` value of the user is copied into `risk_flags`, and `user_history_risk`
  always comes with `manual_review_required`. `claim_mismatch` also comes with
  `manual_review_required`.
- Cracked glass still in place is `crack` (gold cases 3, 9 and 13 use `crack`, even for
  "shattered" wording). A smashed side mirror is `broken_part` (gold case 4). `glass_shatter` has
  no example yet; it needs photos of glass that has broken out.
- Exaggerated severity on a real but minor issue is `contradicted` with `claim_mismatch`
  (gold case 5). A wrong object is `contradicted` with issue and part `unknown` (gold case 19).
- `issue_type` describes the claimed part, so when the damage is on another part the row is
  `none` for the claimed part (case 25).

Conventions chosen here, with no gold example to copy:

- Screenshot or watermarked image of matching damage: `not_enough_information`,
  `valid_image=false`, `non_original_image` (cases 31–32).
- Visible copy-paste edit: `not_enough_information`, `valid_image=false`, `possible_manipulation`
  (case 33).
- The spec has no coverage field, so a stated exclusion (pre-existing damage, gradual wear) does
  not change `claim_status`; it only adds `manual_review_required` (cases 40–41).

If any of these should be labeled differently, change the case in `build_extra.py` and rebuild.
