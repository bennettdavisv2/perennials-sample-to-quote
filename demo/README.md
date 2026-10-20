# Demo

A walkthrough of the sample-to-quote workflow across mock versions of the three systems. It runs the shared core in [`../s2q/`](../s2q/) against in-memory CRM and ERP mocks. Nothing in this folder ships to production.

## Run it
From the repo root (see the main README for install):

```bash
streamlit run demo/app.py                      # http://localhost:8501/
# with Claude reading emails (key in a .env one folder above the repo):
set -a; source ../.env; set +a; streamlit run demo/app.py
```

The app starts on **day one**: NetSuite's inventory and price rules and Salesforce's 6 existing accounts, with nothing processed, so the journey you film is the only thing on screen. Set **Start from → Workbook history** in the sidebar to load the 27 workbook requests (21 original + 6 edge cases we added) for Q&A; with Claude on, that first load reads the 13 workbook emails (about 10 seconds, once per app run).

| Page | What it is |
|---|---|
| **Website** | Storefront modelled on the real site's flow: colorway, Add Sample + Project Type, Request A Quote (Length in yards / feet / meters, Date Needed, CFA, Project Name), cart, guest checkout |
| **CRM** | Salesforce-style: quotes@perennialsfabrics.com inbox, leads, accounts, opportunity record pages, the rep's task queue with drafted messages |
| **ERP** | NetSuite-style: inventory by dye lot, sales orders (samples, holds, CFA cuttings), customers |
| **Today (manual)** | Today's process with no integration: you play Dana and the CSR in a blank Gmail, Salesforce and NetSuite. A scoreboard measures time, values typed, emails written and system switches; a checklist tracks the 18 CSR steps; quotes are checked against the price rules |
| **Old vs New** | The manual run's measured numbers next to the new system's, then one customer's journey step by step (manual side: illustrative estimates) |
| **Ops console** | Each request's full story, the review queue, the integration log |

| File | What it is |
|---|---|
| `app.py`, `ui/` | Streamlit pages and shared session state |
| `site.py` | What the website checkout and the quotes@perennialsfabrics.com inbox send into the workflow |
| `seed.py`, `data/seed_decisions.json` | The day-one start, and the workbook history with the rep's qualification decisions (Hannah Kim's are left open) |
| `manual.py` | State and live counters behind the Today (manual) page |
| `baseline.py` | Today's manual steps per automated action (illustrative estimates) |
| `data/` | The workbook (original + 6 added rows, marked in its Notes column) and the web carts |

## Filming the walkthrough: side by side

Record the two halves separately, then put them side by side in the edit. Both start from the same day one: Dana Ruiz of Ruiz Interiors is a new customer, and she orders samples, asks for a quote, then changes it.

**Before recording**
- Start the app, open http://localhost:8501/ (the root URL; `/website` shows a "Page not found" popup), and click **↺ Reset demo**.
- Use two browser windows: the new system in one, http://localhost:8501/manual in the other. Each window keeps its own state; the Old vs New page reads the manual run's numbers from either.
- Navigate only with the sidebar and the in-page links: a reload or a typed URL starts a fresh session.

**Left: today, by hand** (Today (manual) page; about 10–15 minutes, speed it up in the edit and keep the clock visible)

| # | You are | Do this |
|---|---|---|
| 1 | Dana | **Website**: Place order (herringbone + canvas samples, prefilled) |
| 2 | CSR | **Gmail**: open the website notification. **Salesforce**: search for her, create the lead, convert it, create the opportunity |
| 3 | CSR | **Gmail**: email orders@ the sample request. **NetSuite**: create the customer (copy the Salesforce account ID), enter the sample order. **Gmail**: confirm to Dana |
| 4 | Dana | **Website**: Submit quote request (30 yd herringbone, CFA) |
| 5 | CSR | **Gmail**: "checking stock and pricing" to Dana. **NetSuite**: search the herringbone, note the lot and list price. **Gmail**: ask orders@ for a hold. **NetSuite**: enter the pending hold on L-2403 |
| 6 | CSR | Work out 15% trade off $112 by hand; **Salesforce → Quotes**: type the lines and total. **Gmail**: email Dana the quote |
| 7 | Dana | **Dana's inbox**: send the change (45 yd + 20 yd canvas, prefilled) |
| 8 | CSR | **NetSuite**: release the old hold, enter the new one. **Salesforce**: new quote. **Gmail**: send it. Then **Stop the clock** |

Say: every value on screen is typed by hand into a system that already has it somewhere else; the scoreboard counts them. Any pricing slip shows up under Salesforce → Quotes.

**Right: the new system** (about 3 minutes)

| # | Do this | Say this |
|---|---|---|
| 1 | **Website** → Tidal Herringbone → Add Sample, Canvas Solid White → Add Sample → Cart → Checkout as **Dana Ruiz** → Place order | Same form the customer uses today. |
| 2 | Thank-you page | A lead is in Salesforce, and because she's new, a rep decides whether she's trade. Nothing else waits on a person. |
| 3 | **CRM → Tasks** → **Qualify** | One click: account, contact and opportunity created, the sample order is in NetSuite, the confirmation is drafted. |
| 4 | **Website** → Tidal Herringbone → Request A Quote: 30 yards, CFA Requested, a project name → Add to Cart → Checkout → Place order | Priced from NetSuite's rules, held on one dye lot for 14 days, CFA cutting ordered, quote sent, in about a second. |
| 5 | **CRM → Inbox** → *Dana: bump the herringbone to 45 yds* → Send | Email is where AI earns its place: Claude reads the change, and her sample history settles which canvas. The quote is revised, the hold moved, the new quote sent. |
| 6 | **ERP** → Inventory (L-2403: 45 reserved) and Sales orders | NetSuite shows exactly what the CSR typed by hand on the left. |
| 7 | **Old vs New** | Measured on camera: the manual run's time, values typed, emails and switches against 0 typed, 0 written and 1 rep click. |
| 8 | GitHub → `production-handoff/ROADMAP.md` | What engineering builds, in order. |

For Q&A, switch **Start from** to **Workbook history** for the edge cases: ambiguous colors, discontinued and backordered fabric, sample limits, Do Not Sell, duplicates and Hannah's open qualification.
