# Demo script (about 5 minutes)

What to say over the recording. The click-by-click steps for both halves are in [README.md](README.md#filming-the-walkthrough-side-by-side).

## Numbers to land

| Claim | Number | Source |
|---|---|---|
| Today, by hand (one customer: samples, quote, one change) | 15 min 22 s · 56 values typed · 6 emails written · 12 system switches | Today (manual) scoreboard |
| With the integration | 0 values typed · 0 emails written · 1 rep decision | Old vs New page |
| Time from request to quote sent | Under a second from the website; about 8 seconds from an email, including Claude | Thank-you page and CRM inbox |
| Email reading accuracy | Claude 13/13 emails, 19/19 lines; rules 12/13 | `python -m s2q.eval` |
| Tested behavior | 53 automated tests, 27 scenarios including 6 added edge cases | `pytest` |
| Path to production | About 9 weeks, starting read-only | `production-handoff/ROADMAP.md` |

## Talk track

**0:00 – 0:30 · The problem, in business terms** (README diagram on screen)
> Perennials' best lead source is samples: a designer orders a swatch, likes it, and comes back for yardage. Today that journey runs across the website, Salesforce and NetSuite, which don't talk to each other, so people carry the data by hand. That's slower quotes, re-keying errors and staff time spent on copy-paste instead of selling. I connected the three systems with one integration layer and kept people only where judgment matters.

**0:30 – 2:30 · Side by side** (manual run on the left, sped up with the clock visible; new system on the right)
- *Dana places a sample order.* "Same website form on both sides. On the left, a notification lands in a shared inbox and someone starts typing."
- *Rep clicks Qualify.* "She's a new customer, so a person decides whether she gets trade pricing. That's one click. Everything after it, the account, the opportunity and the NetSuite sample order, happens on its own."
- *Website quote request.* "Priced from NetSuite's rules, the fabric held on a single dye lot for 14 days, a cutting ordered for approval, and the quote sent, in under a second. On the left that's a holding email, a stock lookup, an email to order ops and a quote typed by hand."
- *Dana emails a change.* "This is where AI earns its place: free text. Claude reads 'bump it to 45 and add 20 of the canvas'. Her sample history settles which canvas she means, and the quote is revised, re-held and sent in about eight seconds."

**2:30 – 3:15 · AI with judgment, and measured**
> I used AI only where the input is unstructured. Website orders already carry exact SKUs, so they never touch a model. Claude reads emails into a fixed schema, its output is checked against the catalog, and a rules parser runs alongside it. I didn't assume it works: on a hand-labeled set of every email in the data, Claude is 13 for 13, the rules parser 12 for 13, and any disagreement goes to a rep. The model never sets a price or qualifies a customer. That's deterministic, tested code.

**3:15 – 3:45 · Where people stay in the loop** (CRM → Tasks)
> Automation takes the clear cases. People keep the judgment calls: qualifying new customers, quotes over $20k, split dye lots, anything ambiguous. And every review arrives with the customer email already drafted, so the rep's next step is one click, not an email thread.

**3:45 – 4:30 · How it reaches production** (ROADMAP.md on screen)
> The core logic is the same tested code in production. Only the adapters change, from mocks to Salesforce and NetSuite. The rollout earns trust before it takes risk: two weeks in shadow mode on real traffic writing nothing, then samples, then quotes with a rep approving every one, then inventory holds, and only then auto-send. About nine weeks for one engineer with part-time admins.

**4:30 – 5:00 · Close** (Old vs New, measured numbers)
> One customer: 15 minutes 22 seconds, 56 values typed and 6 emails written by hand, against zero typed, zero emails written and one decision. With another week I'd connect it to sandboxes in shadow mode, and give every rep an AI assistant over the Salesforce and NetSuite MCP servers, so they can ask "which dye lot covers 45 yards?" and get an answer from the same rules the quotes use.

## If they ask

| Question | Answer |
|---|---|
| Why not have the LLM do everything? | Pricing, holds and qualification have money attached. They must be explainable to finance and testable. The model reads text; code makes decisions. |
| What if Claude is down or wrong? | It falls back to the rules parser and says so in the UI. Wrong readings are caught by the catalog check and the rules cross-check, and disagreements go to a rep. |
| Why not run the pipeline on the MCP servers? | Both Salesforce's and NetSuite's MCP servers require a signed-in user. The unattended pipeline needs service logins; MCP is for the staff assistant, sharing the same pricing tools. |
| How do you know it works on real data? | Shadow mode: two weeks reading live traffic and comparing with what reps actually did, with a 95% agreement bar before anything is written. |
| What's the riskiest part? | Inventory holds. A pending NetSuite order doesn't reserve stock by default, so the hold mechanism is the first decision in the roadmap. |
| What did AI get wrong while you built this? | It modelled the brief instead of the real checkout, its AI path had silently never run, and it automated qualification. I caught and corrected each (AI usage notes). |
