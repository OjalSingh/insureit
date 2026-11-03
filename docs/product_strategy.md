# insureit: product strategy

*Draft, 2026-11-03. Owner: lockedin. Status: for review.*

This document lays out how to turn the `insureit` prototype into a product someone will pay for. It covers who buys it, what the product is (and is not) in its first version, what has to be true technically before it touches real claims, the compliance work, pricing, how to sell it, and a 90-day and 12-month plan.

## 0. Assumptions

Nothing here was confirmed with customers. These are the working assumptions; each one should be tested in the first 30 days.

1. **Geography.** Start in India, sell globally later. India has a large and fast-growing volume of small-ticket claims (e-commerce shipments, device protection, two-wheeler and car motor), cost pressure on claims ops, and a regulator pushing for faster settlement. The US/UK/EU come later, after a reference customer.
2. **Founding team.** One or two technical founders, no insurance sales background yet, pre-revenue, bootstrapped or pre-seed.
3. **Claim types.** The prototype handles `car`, `laptop` and `package` damage claims from photos plus a support chat. We keep exactly these three object types for the first year and go deep rather than wide.
4. **Decision rights.** The product recommends; a human (or a customer-configured rule) decides. We do not sell "auto-approve" until the accuracy and liability story supports it (see section 6).
5. **Model access.** Hosted vision LLMs (Claude, Gemini) remain available via API with enterprise terms, including no training on customer data and regional processing where needed.

## 1. Where the prototype is today

| Area | Current state | Gap to production |
|---|---|---|
| Accuracy | About 64% exact-match on `claim_status` over 20 labeled samples, plus 41 derived cases in `dataset/extra` | Sample is far too small to trust the number either way. Need 1,000+ labeled real claims per object type and a per-class error breakdown |
| Pipeline | One vision call per claim, strict output schema, deterministic post-processing, prompt-injection flagging, caching, retries | Solid base. Missing: confidence scores, calibrated abstention, versioned prompts tied to eval runs |
| Fraud / authenticity | The model flags suspicious images in free text | No dedicated checks for reused images, AI-generated or edited images, EXIF/metadata, or duplicate claims across users |
| Integration | CLI over CSV files | No API, no queue, no UI for reviewers, no webhooks |
| Ops | Free-tier API quotas, single process | No multi-tenant hosting, monitoring, SLAs, or cost tracking per customer |
| Compliance | None | Data processing agreement, DPDP/GDPR posture, security controls, audit log, model documentation |

The honest pitch today is "a working prototype with a clear architecture," not a product. Everything below is about closing that gap with the least wasted work.

## 2. Customers and segments

The three object types map to three different buyers. They are not equally attractive as a first market.

| Segment | Who | Claim pain | Fit for us | Priority |
|---|---|---|---|---|
| **A. E-commerce and logistics damage claims** | Marketplaces and D2C brands handling "arrived damaged" refunds; 3PLs and courier aggregators; shipping-protection insurers | Huge volume, low ticket size (₹300–₹20,000), refund fraud is common, manual review is costly relative to value | Very high. Package photos plus chat is exactly our input. Competitors focus on motor, not parcels | **Wedge (start here)** |
| **B. Device protection and extended warranty** | Device insurers and warranty providers (OneAssist and Onsitego types in India; Assurant-type players globally), OEM protection plans, retailers selling protection | Screen and body damage claims, repeat claimants, staged damage, mismatched device | High. Laptop flow already exists; extends naturally to phones | **Second** |
| **C. Motor own-damage claims** | General insurers, TPAs for motor, surveyor firms, fleet operators, car rental and subscription companies | Slow surveys, leakage, fraud | Medium. Biggest market but crowded with funded specialists, and regulated surveyor involvement. Better as "pre-survey triage" than replacement | **Later, via partners** |
| D. Brokers and insurtech distributors | Digital brokers, embedded-insurance platforms | Want faster claim experience as a differentiator | Channel, not end buyer | Partner channel |
| E. TPAs | Claims administrators working for many insurers | Throughput and SLA pressure | Good buyer once a reference exists; one TPA deal reaches several insurers | Year 1 H2 |

**Ideal first customer:** a mid-sized Indian e-commerce company, logistics aggregator or shipping-protection provider that processes at least 5,000 damage claims a month, reviews them manually from photos, and has a claims-ops leader who owns the cost line. They can decide in weeks, not quarters, and are not bound by insurer-grade procurement.

**Buyer and users.** Economic buyer: Head of Claims / Head of CX Ops / Head of Risk. Users: claim reviewers. Blockers: InfoSec, Legal (data processing), and in insurers, Compliance.

## 3. Problem and value proposition

**Problem.** Small damage claims are reviewed by people looking at a few photos and a chat. It is slow (hours to days), inconsistent between reviewers, expensive relative to the claim value, and easy to game with reused, edited or mismatched photos and with pressure in the chat.

**Value proposition (one line).** *insureit reviews every damage claim's photos and conversation in seconds, tells your team what the evidence shows and why, and routes only the doubtful ones to people.*

What the customer gets, in their terms:

1. **Lower cost per claim.** Reviewers handle only the claims the system is unsure about or flags as risky. Target: 40–60% of claims cleared as "evidence supports claim, low risk" for a fast-track path.
2. **Faster settlement.** Seconds instead of hours for the fast-track share, which matters for CX scores and, for insurers, regulatory turnaround times.
3. **Less leakage and fraud.** Consistent checks for image reuse, mismatch (wrong object or part), tampering, prompt-style manipulation in chats, and risky claim history.
4. **Consistency and audit.** Every decision carries the images it relied on, a short justification and the rule that applied, so QA and disputes are faster.

**What makes us different** (what we must defend in every sales call):

- Reads the conversation and the images together, so it checks *the claim the customer actually made*, not just "is there damage."
- Works across parcels, devices and vehicles with one API and one review UI.
- Treats customer text and text inside images as untrusted, and flags manipulation attempts. Few competitors talk about this, and it becomes more relevant as customers use AI to write claims.
- Cheap to run on small claims because it uses general vision models rather than bespoke per-insurer training.

## 4. Competitive landscape

Names are examples from public information as of 2026; positions shift quickly, so re-check before any investor or sales deck.

| Category | Examples | Strength | Where we win |
|---|---|---|---|
| Motor AI damage assessment | Tractable, CCC Intelligent Solutions, Solera/Qapter, Claim Genius, Inspektlabs (India), Ravin AI | Deep motor models, repair-cost estimation, insurer relationships | We do not compete head-on in motor year 1. We win on parcels and devices, chat-grounded checks, and price for small tickets |
| Claims fraud analytics | Shift Technology, FRISS, SAS, in-house rules | Network and historical-data fraud scoring | They score claims, not photos-against-chat. Complementary; possible integration partner |
| Image authenticity | Truepic, Attestiv, and similar photo-provenance tools | Capture-time provenance and tamper detection | We embed authenticity checks as one signal; could partner rather than build all of it |
| E-commerce returns / refund fraud | Returns platforms and in-house trust & safety teams at large marketplaces | Owned by marketplaces with large data | Mid-size merchants and logistics firms cannot build this. That is our wedge |
| General-purpose LLMs | Customers prompting a vision model themselves | Cheap and flexible | We sell the evaluation, schema, guardrails, audit trail, UI and accountability, not the model call |
| Status quo | Manual review teams, BPO outsourcing | Trusted, flexible | Cost and speed; we augment the team rather than replace it |

**Moat over time:** labeled, customer-approved decisions (a growing proprietary eval and training set), integrations into claims systems, reviewer workflow lock-in, and a trust record on accuracy and audits. The model itself is not a moat.

## 5. Product scope

### MVP (first paying pilot, about 90 days)

Narrow on purpose: **package damage claims**, with laptop as a stretch.

1. **Claim review API.** `POST /claims` with images, chat text, object type and optional user history; returns the existing 14-column review plus a confidence score and a recommended route (`fast_track`, `review`, `reject_suggested`). Async with webhook callback.
2. **Reviewer console (web).** Queue of routed claims; side-by-side images, chat, the model's decision, highlighted supporting images and flags. Reviewer accepts or overrides with a reason. Overrides feed the eval set.
3. **Configurable policy rules.** Per customer: evidence requirements (today's `evidence_requirements.csv` becomes editable), thresholds for fast-track, which flags force manual review, claim value caps for fast-track.
4. **Authenticity v1.** Exact and near-duplicate image detection across all of a customer's claims (perceptual hashing), EXIF/metadata checks, reverse-image search against known stock or web images where licensing allows, and the existing model-based "looks edited or generated" flag.
5. **Audit trail.** Immutable log per claim: inputs (hashes), model and prompt version, output, reviewer action, timestamps. Exportable.
6. **Explainability.** Short justifications grounded in specific image IDs (already in the schema), plus which evidence requirement was or was not met.
7. **Batch mode.** CSV upload for pilots, since many first customers will start with exports, not API integration.

Explicitly **out of MVP**: auto-settlement without human sign-off, repair-cost estimation, motor claims, customer-facing capture app, on-prem deployment, languages other than English and Hindi/Hinglish chat.

### Later (months 4–12)

- Laptop and phone device claims at production quality; then motor as pre-survey triage.
- Guided photo capture SDK/link for claimants (correct angles, live capture, provenance signing), which raises evidence quality and cuts fraud at the source.
- Integrations: Zendesk/Freshdesk/Salesforce Service Cloud apps (where chat lives), and claims systems (Guidewire, Duck Creek, and Indian core systems) via partners.
- Cost/severity estimation for devices and parcels (replacement value bands).
- Cross-customer fraud signals (opt-in, privacy-preserving hash sharing).
- Regional languages for chat (Hindi, Tamil, Bengali, Marathi, etc.).
- Private deployment (customer cloud / VPC) for insurers that require it.

### Human-in-the-loop design

- Every claim gets a route, not a final verdict. Default config: only `supported` + high confidence + no risk flags + under a value cap goes to fast-track; everything else goes to a person.
- The customer decides whether fast-track means "auto-approve" or "one-click approve by a reviewer." We recommend the latter until 3 months of audited agreement data exist.
- Sampling QA: a configurable percentage (default 5%) of fast-tracked claims are randomly sent to reviewers to measure live error.
- Rejections are never automatic in the MVP. A suggested rejection always needs a human, which also matters for regulation and fairness (section 7).

## 6. Technical roadmap to production grade

### 6.1 Accuracy targets

Exact-match on all 14 columns is the wrong headline metric for a buyer. What matters is the cost of each type of mistake.

| Metric | Today | Pilot entry | Production (paid, fast-track on) |
|---|---|---|---|
| `claim_status` accuracy on customer's own labeled set | ~64% on 20 samples | ≥ 85% | ≥ 92% |
| Precision of `supported` in fast-track route (wrongly paying a bad claim) | not measured | ≥ 95% | ≥ 98% |
| False "contradicted" rate (wrongly suspecting a genuine customer) | not measured | ≤ 5% | ≤ 2% |
| Share of claims eligible for fast-track at that precision | not measured | ≥ 30% | 40–60% |
| Authenticity: recall on reused/duplicate images | not measured | ≥ 90% | ≥ 97% |
| p95 latency per claim | seconds (single call) | < 30 s | < 15 s |

The key idea is **selective prediction**: the system does not need to be right on everything, it needs to know when it is right. Calibrated confidence plus abstention turns a 85%-accurate model into a 98%-precise fast-track lane on a portion of claims.

### 6.2 How to get there

1. **Real data first (weeks 1–6).** Sign a design partner and get 2,000–5,000 historical claims with their final human decisions (anonymised). This beats any modelling change. Build a labeling guide from `problem_statement.md` and have two reviewers label a subset to measure human agreement; our target ceiling is human-to-human agreement, not 100%.
2. **Eval harness as the product's spine.** Extend `evaluation/evaluate.py`: per-object and per-issue breakdowns, a confusion matrix weighted by business cost, precision/recall at each confidence threshold, and regression gates in CI so no prompt or model change ships if it drops a key metric.
3. **Error analysis loop.** Weekly: sample errors, classify them (missed damage, wrong part, misread chat, over-cautious "not enough info", history over-weighted), fix the most common class through prompt, evidence rules or post-processing.
4. **Decompose the call where it helps.** Keep the single call as default for cost, but add a second, cheaper "verifier" pass for borderline cases (for example a second model or a self-consistency vote) and route disagreements to humans.
5. **Confidence calibration.** Get confidence from agreement across 2–3 samples or two models, plus rule-based features (image quality, number of images, flags); calibrate on held-out data with isotonic regression.
6. **Specialised models where the LLM is weak.** Perceptual hashing and nearest-neighbour search for reuse; a small fine-tuned classifier (or open-weights vision model) for "is this the claimed object" and "is the claimed part visible" if those dominate errors and are cheap to train with pilot data.
7. **Robustness.** Red-team set for prompt injection in chats and in images (extend existing cases), adversarial photos (screens of screens, stock photos, AI-generated damage), and low-quality images.

### 6.3 Fraud and image-tamper detection

Layered, cheapest first:

1. **Duplicate and reuse:** perceptual hash (pHash/dHash) plus embedding similarity across all claims of the tenant; flag same image used by different users or different claims.
2. **Metadata:** EXIF presence, capture time vs. claim time, device model consistency, editing software tags, missing metadata on images that should have it. Weak signal alone (messaging apps strip EXIF), useful in combination.
3. **Web provenance:** reverse-image lookups for stock or web images (via a licensed API).
4. **Manipulation and generation:** model-based check for edits, splices and AI generation; error-level and noise analysis; C2PA content credentials when present. Treat as a risk flag, never sole grounds for rejection.
5. **Behavioural:** claim history, velocity, linked accounts, address and device overlaps (customer-provided data).
6. **Capture-time provenance (later):** guided capture link with live photo, location consent and signed images, which makes most of the above unnecessary for those claims.

### 6.4 Model choice and cost per claim

- Keep the provider switch (`insureit/backends.py`). Benchmark Claude and Gemini models on the real pilot set and choose per object type on cost-adjusted accuracy.
- Use a **cheap fast model for the first pass** and a **stronger model only for low-confidence or high-value claims** (cascade). Expect 70–80% of claims to stop at the first pass.
- Cost drivers: number of images, image resolution (already downscaled to 1568 px), output length, and number of passes. Use prompt caching for the long fixed instructions and evidence rules.
- **Budget target: under ₹2 (about US$0.02) model cost per claim on average for parcels, under ₹8 for devices/motor.** Price list numbers change often, so recompute from the providers' current price pages before quoting a customer; the eval script should log tokens and cost per run to make this a measured number, not an estimate.
- Gross-margin target: model + infra cost ≤ 15% of price per claim.

### 6.5 Scaling beyond free API quotas

1. Move to paid, enterprise API tiers immediately for any pilot (free tiers have low rate limits and data-use terms unsuitable for customer data).
2. Use cloud-provider routes where they help with data residency and quotas (Claude via AWS Bedrock or Google Vertex AI; Gemini via Vertex AI), ideally in Indian regions for Indian customers.
3. Architecture: API service → durable queue → worker pool with per-tenant and per-provider rate limiters (the existing limiter generalised) → result store → webhook. Batch APIs for non-urgent CSV jobs at lower cost.
4. Multi-provider failover for availability, with the eval gate ensuring both providers meet the bar.
5. Observability: per-claim trace, cost, latency, provider errors, drift in decision mix per tenant.

### 6.6 Platform basics

Multi-tenant Postgres + object storage with per-tenant encryption keys, SSO for the reviewer console, role-based access, data retention settings per tenant, infra as code, staging environment with the eval gate, and incident runbooks.

## 7. Data, privacy, regulation and liability

Not legal advice. Budget for an Indian insurance/data-protection lawyer in month 1 and an EU/UK specialist before selling there.

### 7.1 Data protection

- **India, DPDP Act 2023 and its Rules.** We will usually be a *data processor* for the customer (the *data fiduciary*). Needs: data processing agreement, purpose limitation, security safeguards, breach notification support, deletion on request and at contract end, and clarity on cross-border transfer (prefer Indian-region hosting and model endpoints for Indian customers).
- **GDPR / UK GDPR (later markets).** Processor role, DPA with standard contractual clauses for transfers, sub-processor list (model providers, cloud), DPIA support for customers. **Article 22**: decisions with significant effects based solely on automated processing need safeguards, which the human-in-the-loop design provides.
- **Photos contain personal data** beyond the object: faces, number plates, addresses on labels, people in the background. MVP: blur faces and redact address text on labels before long-term storage where the customer opts in; minimise what we keep (hashes and decisions long-term, images only for the agreed retention period).
- **Model providers:** use zero-retention or no-training enterprise terms; list them as sub-processors.

### 7.2 Insurance regulation (India first)

- **IRDAI** rules apply to our insurer customers, and they pass obligations to us through contracts: outsourcing guidelines (we must not perform "core" insurance functions such as final claim decisions on their behalf without their control), information and cyber security guidelines for insurers and their vendors, and claim settlement timelines under the policyholder-protection regulations. Positioning as a decision-support tool under the insurer's control keeps us out of core functions.
- **Motor surveys:** licensed surveyor and loss assessor requirements apply to motor claims above set thresholds. In motor we support surveyors (triage, pre-inspection), we do not replace them.
- **Non-insurer customers (segment A)** are not insurance-regulated for refund decisions, which is another reason to start there; consumer protection rules on fair handling of complaints and refunds still apply.
- **Later markets:** EU AI Act (risk classification for insurance uses; property and parcel damage review is likely outside the high-risk category that covers life and health pricing, but document the assessment and follow transparency duties), US state unfair-claims-practices laws and NAIC AI model bulletin adopted by many states, UK FCA Consumer Duty.

### 7.3 Fairness

- The system must judge photos and the claim, not the person. Do not use protected attributes, names, language style or location as decision inputs. User history is used only as a risk flag that routes to a human, which matches the current design.
- Monitor outcome rates by available proxies the customer can share (region, language of chat, device type) and investigate gaps.
- Accessibility: claimants with poor cameras or connectivity should get "not enough information, please send X" rather than a rejection.

### 7.4 Security and certifications

- MVP: security questionnaire answers, pen test, encryption in transit and at rest, SSO, audit logs, least-privilege access, vendor risk documentation.
- By month 9–12: **ISO 27001** (commonly asked by Indian insurers and banks) and/or **SOC 2 Type I → Type II** for global buyers.

### 7.5 Liability

- Contract: we provide recommendations; the customer retains decision authority. Liability capped (for example 12 months' fees), no liability for claim payouts, warranties limited to documented accuracy on the agreed eval set with a service-credit remedy.
- Get professional indemnity (tech E&O) and cyber insurance before the first production contract.
- Model documentation for each release: intended use, eval results, known limitations, change log. This doubles as sales collateral for compliance teams.

## 8. Pricing and business model

**Model:** B2B SaaS with a platform fee plus usage per claim reviewed. Usage pricing matches the customer's own cost line (cost per claim) and scales with value.

| Plan | Who | Price (assumption to test) | Includes |
|---|---|---|---|
| Pilot | First 3–5 design partners | ₹3–5 lakh fixed for 8–12 weeks, credited against year 1 if they convert | Batch + console, up to 20k claims, weekly accuracy reports |
| Growth | Mid-size e-commerce, logistics, device protection | ₹50,000/month platform + ₹4–10 per parcel claim, ₹15–40 per device claim | API, console, rules, authenticity v1, standard SLA |
| Enterprise | Insurers, TPAs, large marketplaces | Annual contract, ₹30 lakh – ₹1.5 crore+, volume tiers | Private deployment option, custom integrations, data residency, premium SLA, compliance pack |
| Global (later) | US/UK/EU | US$0.25–1.50 per claim + platform fee | Same, priced to local manual review cost |

**Pricing logic:** a manual review of a small claim in India costs the customer roughly ₹30–100 in loaded staff time; fraud and leakage often cost far more. Charging ₹4–40 per claim leaves the customer a clear saving while keeping our gross margin above 80% if model cost stays at the section 6.4 target. Validate both numbers with each design partner in discovery.

**Optional later:** outcome-based pricing (share of measured fraud savings) for customers who trust the measurement; resale through BPOs and claims-outsourcing firms.

## 9. Go-to-market and sales plan

### 9.1 Motion

Founder-led sales to design partners, then a repeatable mid-market motion in India, then enterprise and international via partners.

1. **Discovery (weeks 1–4).** 30 conversations with claims/CX ops leaders in segments A and B. Goals: confirm volume, current cost per claim, fraud share, data availability, decision process. Script outcome: "Would you give us 2,000 past claims to measure us, free, in exchange for a report?"
2. **Free benchmark offer.** Run the customer's historical claims in batch and deliver a report: accuracy vs. their reviewers, fast-track share at 98% precision, duplicate images found, estimated savings. This is the main sales asset; it costs us little and is concrete.
3. **Paid pilot.** Live shadow mode first (system runs, humans decide as usual, we compare), then assisted mode (reviewers see our recommendation).
4. **Convert.** Annual contract with usage tiers once pilot metrics (section 10) are met.

### 9.2 Channels

- Direct outreach on LinkedIn and via warm intros to claims, CX and risk heads at Indian e-commerce, logistics and device-protection companies.
- Partnerships: helpdesk platforms' app marketplaces (Freshdesk, Zendesk), logistics aggregators that already handle damage disputes for many merchants, BPOs that run claims review for insurers, and insurtech accelerators/sandboxes (IRDAI regulatory sandbox for insurer pilots).
- Content: publish the eval methodology and a public "damage claim review benchmark" built from licensable images, write about prompt injection in claims, and share anonymised pilot results. Credible content matters a lot to compliance-heavy buyers.
- Events: India Insurance Summit-type conferences, insurtech meetups, e-commerce ops forums.

### 9.3 Sales collateral needed

One-page overview, benchmark report template, security & compliance pack (architecture, data flow, DPA, sub-processors, pen test summary), model card, ROI calculator, demo environment with synthetic claims, case study after first pilot.

### 9.4 Positioning statement

For claims and CX operations teams that review high volumes of small damage claims from photos, insureit is a claim-review copilot that checks the photos against what the customer actually said, catches reused or manipulated evidence, and fast-tracks the clear cases, unlike motor-only damage AI or generic fraud scoring, because it is built for small-ticket parcel and device claims with an audit trail and humans in control.

## 10. Pilots and success metrics

**Pilot structure (8–12 weeks):** 2 weeks setup and historical benchmark, 4 weeks shadow mode, 4 weeks assisted mode on a subset of reviewers.

| Metric | Measured how | Pilot success threshold |
|---|---|---|
| Agreement with final human decision | Shadow-mode comparison | ≥ 85% overall, ≥ 98% precision on fast-track lane |
| Fast-track share | Share of claims in the high-confidence lane | ≥ 30% |
| Reviewer handling time | Console timestamps vs. baseline | −30% or better |
| Duplicate / suspicious images caught | Confirmed by customer's team | Report count and value; any confirmed catch the customer missed is a win |
| Time to decision | Submission to decision | −50% on fast-track lane |
| Reviewer satisfaction | Short survey | ≥ 7/10 "would keep using" |
| Cost per claim (ours) | Logged tokens and infra | Within section 6.4 targets |

**Company metrics (12 months):** number of paying customers, ARR, claims processed per month, gross margin, pilot-to-paid conversion rate, live fast-track precision from QA sampling, net revenue retention.

## 11. Team and budget

### 11.1 Team (12 months)

| Role | When | Why |
|---|---|---|
| Founder(s): product/engineering and sales | Now | Founder-led sales and core build |
| ML/CV engineer | Month 1–2 | Eval harness, calibration, authenticity checks |
| Full-stack engineer | Month 2–3 | API, console, multi-tenant platform |
| Claims domain advisor (part-time, ex-insurer or ex-claims ops) | Month 1 | Credibility, labeling guidelines, intros |
| Annotators / reviewers (contract) | Month 2+ | Labeling pilot data, QA sampling |
| Compliance/legal counsel (fractional) | Month 1, then as needed | DPA, contracts, DPDP, IRDAI |
| Account executive / BD (India) | Month 6–8 | After 2 conversions show a repeatable pitch |
| DevOps/security (fractional, then full) | Month 6+ | ISO 27001 / SOC 2, private deployments |

### 11.2 Budget (India-based team, rough, 12 months)

| Item | Estimate |
|---|---|
| Salaries (3–5 people ramping, India market rates) | ₹70 lakh – ₹1.2 crore |
| Annotation and QA labor | ₹5–10 lakh |
| Model API + cloud (pilots and dev) | ₹6–12 lakh |
| Legal, DPA, contracts, insurance (E&O, cyber) | ₹6–10 lakh |
| Security: pen test, ISO 27001 / SOC 2 readiness and audit | ₹10–20 lakh |
| Sales and marketing: travel, events, content | ₹8–15 lakh |
| Buffer (15%) | ₹15–25 lakh |
| **Total** | **≈ ₹1.2 – 2.1 crore (about US$145k–255k)** |

A lean founder-only version of the first 90 days needs about ₹8–15 lakh, mostly API, legal and a part-time ML or labeling helper. A pre-seed round of US$300–500k covers 12–18 months with margin.

## 12. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Accuracy stalls below what buyers need | Medium | High | Sell selective fast-tracking rather than full automation; real data early; cascade models; specialised classifiers for weak spots |
| Cannot get real labeled data | Medium | High | Free benchmark offer; synthetic and licensed data for demos; small paid labeling projects |
| Wrong decision causes financial loss or customer harm, with blame on us | Medium | High | Human sign-off on rejections, value caps on fast-track, QA sampling, contractual liability caps, E&O insurance |
| Funded motor-AI competitor moves into parcels/devices | Medium | Medium | Move fast in the wedge, own integrations and workflow, price for small tickets |
| Model provider price, policy or quality changes | Medium | Medium | Multi-provider abstraction (already exists), eval gate, option for open-weights models in private deployments |
| Data protection breach | Low | Very high | Minimisation, encryption, per-tenant keys, retention limits, pen tests, incident plan |
| Long enterprise sales cycles drain runway | High (insurers) | High | Start with non-insurer segment A; insurers via TPAs/partners; keep burn low |
| Regulator views tool as performing core insurance function | Low–Medium | High | Decision-support positioning, customer control and audit trail, early legal review, IRDAI sandbox route |
| Adversaries adapt (AI-generated damage photos, injection) | High | Medium | Layered authenticity checks, capture-time provenance SDK, red-team set in CI |
| Bias against certain claimant groups | Low–Medium | High | No personal attributes as inputs, outcome monitoring, human review for adverse outcomes |

## 13. Timeline

### First 90 days

| Weeks | Product and tech | Market and company |
|---|---|---|
| 1–2 | Expand eval harness (per-class breakdown, cost logging, confidence thresholds); pick package flow as MVP focus | Draft ICP list of 100 companies; start discovery calls; engage counsel for DPA template |
| 3–4 | Duplicate-image detection and EXIF checks; confidence via multi-sample agreement; paid API tier | 30 discovery calls done; offer free benchmarks; target 3 data-sharing agreements |
| 5–6 | Run first historical benchmarks; error analysis loop; batch CSV upload with web results page | Deliver 2–3 benchmark reports; pilot proposals to the best 2 |
| 7–9 | Reviewer console v1 (queue, accept/override, audit log); async API with webhooks; Indian-region hosting | Sign 1–2 paid pilots; security questionnaire answers and pen test booked; E&O and cyber quotes |
| 10–12 | Shadow mode live at pilot 1; configurable rules; QA sampling; model card v1 | Weekly pilot reports; first case-study draft; decide on pre-seed raise using pilot data |

**90-day exit criteria:** one paid pilot live in shadow or assisted mode, ≥ 85% agreement on the customer's data, a fast-track lane at ≥ 95% precision covering ≥ 30% of claims, and a signed DPA template accepted by at least one customer's legal team.

### 12 months

| Quarter | Milestones |
|---|---|
| Q1 (months 1–3) | As above. Package MVP, 1–2 paid pilots |
| Q2 (months 4–6) | First production contract; laptop/phone device claims to pilot quality; helpdesk integration (Freshdesk or Zendesk); 3–5 customers in pilot or paid; raise pre-seed if pursued |
| Q3 (months 7–9) | Guided capture link/SDK; ISO 27001 or SOC 2 Type I; first TPA or insurer pilot (device or motor triage); hire AE; regional-language chat support |
| Q4 (months 10–12) | 6–10 paying customers, ₹1–2 crore ARR run-rate target; motor pre-survey triage pilot with a partner; private deployment option; first international design partner (UK or Southeast Asia) |

## 14. Immediate next steps (this week)

1. Add per-class metrics, confidence thresholds and token/cost logging to `evaluation/evaluate.py`, and re-run on the 61 labeled cases to get a real baseline with error categories.
2. Write the one-page overview and the free-benchmark offer.
3. List 50 target companies in segment A and 25 in segment B; send the first 20 outreach messages.
4. Book a call with a data-protection lawyer for the DPA and DPDP posture.
5. Decide whether to stay bootstrapped through the first pilot or start pre-seed conversations now.
