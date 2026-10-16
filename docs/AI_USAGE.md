# AI usage notes

## Inside the workflow

- **Claude only reads email.** Website requests come from the real site's cart (exact variant SKU per product page, plus Project Type), so there is nothing to interpret; `CartIntake` maps them directly. Using an LLM there would add cost and a way to be wrong with no benefit.
- **Claude (Anthropic API) for email extraction** (`s2q/extract.py`). A forced tool call (`record_request`) with a JSON schema returns the segment, project, items (SKUs + quantity + unit), and intent flags (budgetary, revision, urgency, need-by). The catalog goes in the system prompt so the model maps informal names ("navy stripe", "green velvet") to real SKUs.
- **Guardrails around it:**
  - Output is validated against the catalog. Unknown SKUs are dropped and the line is flagged.
  - A deterministic rules extractor always runs as a cross-check. Disagreement on items or quantities sends the request to review.
  - If the API fails, the request falls back to rules and the note is logged.
  - The model never prices, decides qualification, or writes customer-facing numbers.
- **Why not more AI?** Qualification and pricing need to be explainable to sales ops and finance, and testable. An LLM is good at reading messy text and poor at being a policy engine. A natural next use is polishing email tone with numbers locked as placeholders, and classifying intent on a shared inbox.

## Building it

Built with **Claude** as a coding agent. I gave it the case study and the workbook and chose the scope, stack (Python + Streamlit) and the LLM-with-fallback approach. It drafted the architecture, code, tests and docs, and I reviewed the outputs.

**Where it helped:** reading all 21 requests and turning each into an edge case (dedupe on WEB-003, Do Not Sell on WEB-005, dye-lot splits, the revision in EML-021). It also handled boilerplate (adapters, UI, audit log with API mappings) and wrote tests against the expected outcome of every row.

**Where it needed correcting** (found by running the pipeline and reading every output, not by trusting the first pass):

- **Revision bug.** The first version priced Dana's 90 yd revision *before* releasing the v1 hold, so it reported 83 yd short instead of 3. Fixed by releasing the prior hold first; there is a test for it.
- **Quantity parsing on sample requests.** "140 guest rooms" and "60' yacht" were read as yardage. Quantities are now only parsed on quote requests.
- **Multi-color requests.** "Coastal Linen in Sand and Charcoal" was first treated as one ambiguous item instead of two samples.
- **Inferred colors, twice.** "Green velvet" first resolved silently to Moss; the fix then over-corrected by holding the quote for confirmation, which recreated the back-and-forth the project exists to remove. Final rule: a unique match is quoted and named in the email; several matches are settled from the customer's sample history; only a real tie becomes one drafted question.
- **Wording.** Emails said "your samples are on the way" when none were eligible, and told a student consumer about "your client".
- **Website intake modelled on the brief, not the product.** The first draft parsed web sample requests as free text with regex/LLM, because the brief says "free text form". Checking perennialsfabrics.com showed samples are added per colorway from product pages, and the quote form has Length + Yards/Feet/Meters, Date Needed and CFA. Web intake is now structured, AI is email-only, and feet and CFA are supported.
- **First UI was hard to follow.** Emoji status strings, raw JSON panels and every stage shown even when n/a. Rebuilt as a request list plus a top-to-bottom story per request, with review actions next to the issue they resolve.
- **UI.** Streamlit rendered "$34,912 > $20,000" as LaTeX math. Fixed by escaping `$`.

- **Demo layer.** Claude also built the walkthrough app (mock storefront, CRM, ERP, old-vs-new pages) on top of the same workflow, and the README diagrams. The old-process numbers in `s2q/baseline.py` are estimates it proposed and I labelled as such.

<!-- Add your own notes here: anything you changed, decisions you'd defend differently, time spent. -->
