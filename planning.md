# Provenance Guard — Planning Document

---

## Detection Signals

### Signal 1: LLM-Based Classification (Groq)

**What it measures:**
Sends the submitted text to Groq's `llama-3.3-70b-versatile` model with a structured prompt asking it to assess whether the writing reads as human or AI-generated. Captures semantic coherence, stylistic consistency, and overall writing quality holistically.

**Why it differs between human and AI writing:**
AI-generated text tends to be well-structured, tonally consistent, and free of the kind of micro-level irregularities humans produce naturally. Human writing is more idiosyncratic — irregular rhythm, unexpected word choices, emotional texture that doesn't follow a predictable pattern.

**Output format:**
A float between 0 and 1 representing the probability the text is AI-generated. The model is prompted to return a JSON object: `{"ai_probability": 0.84, "reasoning": "..."}`. The `ai_probability` field is the signal score.

**Blind spot:**
A skilled human writer who writes formally or analytically (academic essays, technical writing) can look like AI to the model. Heavily edited or lightly paraphrased AI output can also slip through if the edits introduce enough variation.

---

### Signal 2: Stylometric Heuristics (Python)

**What it measures:**
Statistical properties of the text's structure, computed entirely in Python with no external libraries:
- **Sentence length variance** — standard deviation of word counts across sentences. AI text is more uniform; human text has more variation.
- **Type-token ratio (TTR)** — unique words divided by total words. AI text tends to repeat common vocabulary; human writing uses a broader, less predictable word set.
- **Punctuation density** — punctuation marks per 100 words. AI text is punctuated correctly and predictably; humans use punctuation more freely and inconsistently.

**Why it differs between human and AI writing:**
AI models are trained to produce readable, well-formed output. That training pressure creates statistical regularity — consistent sentence lengths, predictable vocabulary. Human writing reflects individual voice and doesn't optimize for uniformity.

**Output format:**
Each metric is normalized to a 0–1 scale and combined into a single `style_score` float. Higher score = more AI-like (more uniform).

**Blind spot:**
Technical or academic human writing scores high on uniformity — formal essays, legal documents, and structured reports can look AI-generated to heuristics. Casual or informal AI output (short social posts, simple sentences) can score as human.

---

### Combining the Signals

```
combined_score = (0.6 × llm_score) + (0.4 × style_score)
```

The LLM carries more weight because it evaluates semantic and stylistic coherence holistically. The stylometric signal adds a structural cross-check that the LLM alone might miss.

---

## Uncertainty Representation

### What a confidence score of 0.6 means

A score of 0.6 means the system leans toward AI-generated but is not confident. Both signals are pointing in the same general direction but not strongly enough to make a definitive call. The label for a 0.6 is "Uncertain" — not "Likely AI." This is intentional.

### Thresholds

| Score Range | Attribution | Label Variant |
|---|---|---|
| 0.00 – 0.35 | `likely_human` | High-confidence human |
| 0.35 – 0.70 | `uncertain` | Uncertain |
| 0.70 – 1.00 | `likely_ai` | High-confidence AI |

### Why these thresholds reflect asymmetry

A false positive — labeling a human's work as AI-generated — is more harmful than a false negative on a creative platform. It damages creator reputation and trust. The bar for calling something AI is therefore set at 0.70, not 0.50. A score of 0.65 produces an "Uncertain" label, not an accusation. When in doubt, the system defers to the creator.

### Calibration approach

Raw signal scores are tested against clearly human and clearly AI text samples before deployment. If clearly human text is scoring above 0.4 consistently, the weights or normalization are adjusted. The goal is that genuinely borderline text lands in the 0.40–0.60 range, not at the extremes.

---

## Transparency Label Design

All three variants are written for a semi-technical audience — clear and honest, not clinical.

### Variant 1: High-Confidence AI (score > 0.70)

> **Attribution: Likely AI-Generated**
> This content shows strong indicators of AI generation (confidence: [X]%). Our analysis detected consistent sentence structure and limited stylistic variation typical of AI-generated writing. If this is your original work, you have the right to appeal this classification below.

### Variant 2: Uncertain (score 0.35–0.70)

> **Attribution: Uncertain**
> We could not confidently determine the origin of this content (confidence: [X]%). The writing shows mixed signals — some characteristics associated with AI generation, some consistent with human authorship. No action has been taken. This label is shown for transparency only.

### Variant 3: High-Confidence Human (score < 0.35)

> **Attribution: Likely Human-Written**
> This content appears to be human-written (confidence: [X]%). Our analysis found natural variation in style and structure consistent with human authorship.

*Note: `[X]%` is replaced at runtime with the actual confidence score expressed as a percentage (e.g., a combined score of 0.82 → "82%").*

---

## Appeals Workflow

### Who can appeal
Any creator who submitted content via `POST /submit`. They appeal using the `content_id` returned in the original submission response.

### What they provide
- `content_id` — ties the appeal to the original classification
- `creator_reasoning` — free-text field where the creator explains why they believe the classification is wrong

### What the system does on appeal
1. Looks up the original record in the audit log by `content_id`
2. Updates the content's `status` field from `"classified"` to `"under_review"`
3. Appends the appeal details to the audit log entry: `appeal_reasoning`, `appeal_timestamp`
4. Returns a confirmation to the creator

No automated re-classification occurs. A human reviewer handles appeals manually.

### What a human reviewer would see
When reviewing the audit log (via `GET /log`), each appealed entry includes:
- Original classification, confidence score, and both signal scores
- The creator's reasoning
- The timestamp of the appeal
- Current status: `"under_review"`

This gives the reviewer enough context to make an informed decision without re-running the pipeline.

---

## Anticipated Edge Cases

### Edge Case 1: Formal human writing flagged as AI
A non-native English speaker or academic writer who writes in structured, uniform prose may trigger both signals — the LLM sees consistent style, the heuristics see low sentence length variance and high TTR. This writer could receive a high-confidence AI label despite being a human author. The appeals workflow is the safety valve here, and the label copy explicitly acknowledges this possibility.

### Edge Case 2: Lightly edited AI output scored as human
A user who takes AI-generated text and manually rewrites portions of it — varying sentence length, adding informal phrasing, introducing typos — can fool the stylometric signal. The LLM may still detect underlying AI patterns, but if edits are extensive enough the combined score may fall into the "uncertain" range. The system will not catch this reliably, which is an acknowledged limitation.

---

## Architecture

```
SUBMISSION FLOW
───────────────
Client
  │
  │  POST /submit {text, creator_id}
  ▼
Flask App
  │
  ├──► Signal 1: Groq LLM
  │       └── returns llm_score (0–1)
  │
  ├──► Signal 2: Stylometric Heuristics
  │       └── returns style_score (0–1)
  │
  ├──► Confidence Scoring
  │       └── combined = (0.6 × llm_score) + (0.4 × style_score)
  │
  ├──► Label Generator
  │       └── maps score → label text (3 variants)
  │
  ├──► Audit Log (SQLite)
  │       └── writes: content_id, creator_id, timestamp,
  │                   attribution, confidence, llm_score,
  │                   style_score, status
  │
  └──► Response {content_id, attribution, confidence, label}


APPEAL FLOW
───────────
Client
  │
  │  POST /appeal {content_id, creator_reasoning}
  ▼
Flask App
  │
  ├──► Lookup content_id in Audit Log
  │
  ├──► Update status → "under_review"
  │
  ├──► Audit Log
  │       └── appends: appeal_reasoning, appeal_timestamp
  │
  └──► Response {status: "received", message: "..."}
```

**Submission flow narrative:** A piece of text enters through `POST /submit`, is analyzed by two independent signals (LLM semantic and stylometric structural), combined into a single confidence score, mapped to a transparency label, written to the audit log, and returned to the caller with a unique `content_id`.

**Appeal flow narrative:** A creator posts to `POST /appeal` with their `content_id` and reasoning. The system updates the record's status to `under_review`, appends the appeal details to the audit log, and returns a confirmation. No automated re-classification occurs.

---

## AI Tool Plan

### Milestone 3 — Submission Endpoint + First Signal

**Spec sections to provide:** Detection Signals (Signal 1 only), Architecture diagram (submission flow)

**What to ask for:**
- Flask app skeleton with `POST /submit` route stub that accepts `{text, creator_id}` and returns a hardcoded JSON response
- A `classify_with_llm(text)` function that calls Groq and returns a `{"ai_probability": float, "reasoning": str}` object

**How to verify:**
- Run `POST /submit` with a curl command and confirm JSON response includes `content_id`, `attribution`, `confidence`, `label`
- Call `classify_with_llm()` directly in a Python shell with 2–3 test inputs and inspect raw output before wiring into the endpoint

---

### Milestone 4 — Second Signal + Confidence Scoring

**Spec sections to provide:** Detection Signals (Signal 2), Uncertainty Representation, Architecture diagram

**What to ask for:**
- A `compute_stylometric_score(text)` function returning a normalized 0–1 float
- A `compute_confidence(llm_score, style_score)` function implementing the weighted formula and returning `{score, attribution}`

**How to verify:**
- Test `compute_stylometric_score()` on the same inputs used for Signal 1 — note where they agree and disagree
- Run all 4 test inputs (clearly AI, clearly human, two borderline) through the full pipeline and confirm scores vary meaningfully across the range

---

### Milestone 5 — Production Layer

**Spec sections to provide:** Transparency Label Design, Appeals Workflow, Architecture diagram (both flows)

**What to ask for:**
- A `generate_label(score, attribution)` function that returns the correct label variant text
- The full `POST /appeal` endpoint implementation

**How to verify:**
- Submit inputs that produce all three label variants and confirm the text matches the spec exactly
- Submit a `POST /appeal` with a real `content_id`, then call `GET /log` and confirm the entry shows `status: "under_review"` and `appeal_reasoning` populated

---

## Stretch Feature: Multi-Modal Support

### Second Content Type: Image Descriptions

Extend `POST /submit` to accept an optional `content_type` field (`"text"` or `"image_description"`). When `content_type` is `"image_description"`, the pipeline uses a specialized LLM prompt calibrated for that format.

**Why image descriptions need different detection:**
AI-generated image descriptions tend to be clinically precise, formulaic, and impersonal — "A woman sits at a minimalist desk with a laptop, bathed in warm afternoon light." Human descriptions are more casual, subjective, and contextual — "my friend took this at sunset, you can barely see us but the lighting was insane." The same stylometric signals apply, but the LLM prompt is rewritten to look for these format-specific patterns.

**Signals:**
- LLM prompt adapted to evaluate image description conventions vs. prose conventions
- Stylometric heuristics remain unchanged — sentence variance and TTR still differentiate AI from human descriptions
- Word length signal unchanged — AI image descriptions also favor formal vocabulary

**Audit log:** `content_type` is stored in every log entry so detection patterns can be analyzed per content type via `GET /analytics`.

---

## Stretch Feature: Analytics Dashboard

A `GET /analytics` endpoint returning aggregated stats from the audit log.

**Detection patterns** — count and percentage breakdown of `likely_ai`, `uncertain`, and `likely_human` classifications across all submissions.

**Appeal rate** — total appeals filed and rate as a percentage of total submissions. High appeal rates signal the system may be misclassifying frequently enough to frustrate creators.

**Third metric: Average confidence by attribution** — the mean confidence score within each attribution category. This shows how decisive the system is when it commits to a call. A `likely_ai` average of 0.78 vs an `uncertain` average of 0.51 validates that the threshold boundaries are producing meaningful distinctions, not arbitrary ones.

**Bonus:** Verified creator count — how many creators hold a provenance certificate.

---

## Stretch Feature: Provenance Certificate

### Design

A "verified human" credential that a creator can earn through a two-step process:

1. **Eligibility check** — the creator must have at least one `likely_human` classification on record in the audit log. This uses the system's own data as evidence rather than requiring external identity verification.
2. **Verification request** — the creator calls `POST /verify` with their `creator_id` and a signed declaration. The system issues a certificate with a unique ID and timestamp.

### Storage

A new `verified_creators` table in SQLite:
- `creator_id` — links to submissions in the audit log
- `certificate_id` — unique UUID issued at verification time
- `verified_at` — ISO timestamp
- `verification_statement` — the creator's declaration (stored for audit purposes)

### Display

When a verified creator submits content, the response includes a `provenance_certificate` block:

```json
{
  "provenance_certificate": {
    "status": "verified_human",
    "certificate_id": "cert-xxxxxxxx",
    "verified_at": "2026-06-30T00:00:00+00:00",
    "display_badge": "Verified Human Creator"
  }
}
```

### Endpoints

- `POST /verify` — accepts `{creator_id, verification_statement}`, checks eligibility, issues certificate
- `GET /certificate/<creator_id>` — returns current certificate for a creator

---

## Stretch Feature: Ensemble Detection

### Signal 3 — Lexical Sophistication (Average Word Length)

**What it measures:**
Average character length of all words in the text, normalized to a 0–1 score. AI text tends to favor longer, more sophisticated vocabulary ("transformative", "paradigm", "implications"). Human casual writing uses shorter, everyday words ("fine", "ok", "went", "said").

**Why it differs between human and AI writing:**
Language models are trained on formal text and tend to generate more "impressive" word choices even when a simpler word would do. Human writing, especially informal writing, skews toward shorter words naturally.

**Output format:**
A float between 0 and 1. Average word length of 3 chars or less → score 0.0 (very human-like). Average word length of 7+ chars → score 1.0 (very AI-like).

**Blind spot:**
Technical human writing (code documentation, academic papers) uses long domain-specific words. A human developer or academic writer would score high on this metric despite being genuinely human.

### Updated Weighting Approach

With three signals, the confidence formula becomes:

```
combined_score = (0.50 × llm_score) + (0.30 × style_score) + (0.20 × word_len_score)
```

**Rationale:**
- LLM retains the highest weight (50%) — it evaluates holistic semantic and stylistic quality that neither structural metric can replicate.
- Stylometric drops from 40% to 30% — it remains the primary structural signal but yields weight to the new third signal.
- Word length takes 20% — it adds a genuinely new dimension (lexical sophistication) without dominating the result.

All three signals are independent: LLM is semantic, stylometric is structural, word length is lexical. The combination makes the pipeline meaningfully harder to fool than any single signal.
