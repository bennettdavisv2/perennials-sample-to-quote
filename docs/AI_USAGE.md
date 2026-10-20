# AI usage notes

## Tools

| Tool | Used for |
|---|---|
| **Claude Code** (Claude Opus 5.5) | Coding agent: wrote the code, tests, docs and diagrams under my direction |
| **Claude in Chrome** (through Claude Code) | Clicking through the demo to check layout, and rendering the Mermaid diagrams to confirm they display |
| **Claude API** (inside the product) | Reading free-text quote emails into structured requests (see below) |

## How I worked with it

There were two phases. First, Claude produced a rough draft from the brief and the workbook. Second, I reviewed that draft and directed every change. Each change followed the same loop: Claude proposed a plan, I approved or redirected it, Claude built it, the tests and the running app were checked, and then I committed. Every commit after the first one in the repo history is from the review phase.

## Decisions I made

| Decision | Why |
|---|---|
| **Keep every change tied to the brief's goal**: manual handoffs and back-and-forth with customers | Mid-project I re-centred the work on that sentence of the brief. It's why the later work went into drafted customer messages and the old-vs-new comparison rather than more UI polish. |
| **Model the website as structured, like the real site** | The brief says "free text form". I had Claude check perennialsfabrics.com: samples are added per colorway from product pages, so a customer can't name the wrong fabric. AI is now used only for email. |
| **Make qualification manual for new senders** | Trade status decides free samples and trade pricing, so for anyone without a CRM account a rep clicks **Qualify** or **Reject**, and the system offers no suggestion. Known accounts, Do Not Sell and spam stay automatic. The demo's seeded history records the rep's decisions in a labelled file. |
| **Allow guest sample checkout** | The real site uses a trade login. Keeping guest checkout keeps lead qualification meaningful for the exercise; it's stated as an assumption. |
| **Two front doors, one pipeline** | Website and email are the two intake channels; everything after intake is shared. I folded the email demo into the CRM's quotes@perennialsfabrics.com inbox instead of a separate mock mail app. |
| **Extend the provided data with 6 edge cases** | So reviewers can see the harder cases tested, not just the provided rows. Two of them exposed real gaps: an ambiguous "the linen" could supersede an open quote and release its hold, and Claude reading a Gmail sender as a consumer bypassed her open trade review and auto-sent a list-price quote. Both fixed and tested. |
| **Separate the demo from the production handoff** | The repo is split into the shared core (`s2q/`), the walkthrough (`demo/`) and engineering's building blocks (`production-handoff/`), so reviewers can see what is demo-only and what would ship. The production files are skeletons and specs, labelled as not yet run against real systems. |
| **Demo and handoff scope** | A Streamlit multipage demo seeded with the workbook, labelled estimates for today's process, and a handoff that assumes a custom AWS service, Google Workspace, and checklist-level specs. |

## Where it helped

- Turned all 21 original requests into concrete edge cases and tests, then helped design 6 more for cases the data didn't cover: dedupe across two email addresses, a Do Not Sell account, dye-lot splits, a quote revision.
- Wrote the adapters, the demo pages, and an integration log that maps every mock call to the real Salesforce or NetSuite API.
- Surfaced real-system details I'd want an engineer to hear early:
  - Salesforce quote lines need each item as a Product with a price-book entry.
  - Lead conversion needs a small Apex endpoint.
  - A pending NetSuite order doesn't hold inventory by default.
  - One customer's requests must be processed in order.

## Where I had to correct it

- **The first UI was confusing.** I told it so, in those words. It rebuilt the app around one request at a time, with review actions next to each issue.
- **It modelled the brief, not the product.** It parsed web sample requests as free text because the brief says so. I pointed it at the real checkout, and it moved web intake to structured carts.
- **It over-corrected on colors.** It held quotes to "confirm" a color when only one catalog color fit ("green velvet" can only be Moss), which recreated the back-and-forth the project is meant to remove. I asked how a color selection could even be wrong. The final rule: quote a unique match and name it in the email, settle ties from the customer's own sample history, and only then ask one question.
- **It proposed a screen that added nothing.** A separate mock email app. I questioned it, and email went into the CRM inbox instead.
- **The Claude path had never actually run.** When I asked what was missing and supplied an API key, every call failed: current models reject the forced tool call the code used. The app had been quietly falling back to rules, so nothing looked wrong. It was fixed with structured outputs, failures now show in the UI, and it was measured afterwards: Claude and the rules agree on every SKU, quantity and unit across 13 emails.

It also caught some of its own mistakes while checking its work:
- a find-and-replace that stripped table widths;
- a diagram that rendered unreadably;
- summary tiles that cut off quote totals.

The first draft's own testing had already fixed:
- a revision priced before the old hold was released;
- "140 guest rooms" being read as yardage;
- emails saying "your samples are on the way" when none were eligible.

## AI inside the workflow

- **Claude reads only email.** Website carts already carry exact SKUs, so an LLM there would add cost and a way to be wrong.
- **How it reads:** structured outputs (a JSON schema in `output_config.format`, `claude-opus-5-5` at low effort) return the customer type, the items (SKU, quantity, unit) and intent (budgetary, revision, urgency, need-by). The catalog is in the system prompt, so informal names like "the navy stripe" map to real SKUs.
- **Guardrails:**
  - Output is checked against the catalog; unknown SKUs are dropped and flagged.
  - A rules extractor always runs as a cross-check; disagreement sends the request to review.
  - API failures fall back to rules and are shown, not hidden.
  - Server-side refusal fallbacks are enabled.
  - The model never sets prices, qualifies anyone (a rep qualifies every new sender), or writes customer-facing numbers.
- **Why not more AI:** qualification and pricing must be explainable to sales ops and finance, and testable. Next candidates: classifying intent on the shared inbox, and polishing email tone with the numbers locked.

## What I'd do differently

- Look at the real product before modelling it. That would have saved a rework of the website intake.
- Run the AI path with a real key on day one, and make any fallback loud from the start.
- **Time spent:** _[fill in]_. The brief time-boxes this at 3–4 hours. The repo shows the review phase running from 13:53 to 16:19 on Oct 16, on top of the first draft. The core PoC came first; the demo and handoff layers were added after.
