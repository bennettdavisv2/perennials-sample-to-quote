# Demo

A walkthrough of the sample-to-quote workflow across mock versions of the three systems. It runs the shared core in [`../s2q/`](../s2q/) against in-memory CRM and ERP mocks. Nothing in this folder ships to production.

## Run it
From the repo root (see the main README for install):

```bash
streamlit run demo/app.py                      # http://localhost:8501/
# with Claude reading emails (key in a .env one folder above the repo):
set -a; source ../.env; set +a; streamlit run demo/app.py
```

The app starts **seeded**: the 27 workbook requests (21 original + 6 edge cases we added) are already processed. With Claude on, the first load reads the 13 seeded emails (about 10 seconds, once per app run); reloads and **↺ Reset demo** are instant after that.

| Page | What it is |
|---|---|
| 🛍 **Website** | Storefront modelled on the real site's flow: colorway, Add Sample + Project Type, Request A Quote (Length in yards / feet / meters, Date Needed, CFA, Project Name), cart, guest checkout |
| ☁️ **CRM** | Salesforce-style: quotes@perennialsfabrics.com inbox, leads, accounts, opportunity record pages, the rep's task queue with drafted messages |
| 🏭 **ERP** | NetSuite-style: inventory by dye lot, sales orders (samples, holds, CFA cuttings), customers |
| ⚖️ **Old vs New** | One customer's journey: each automated step next to the manual step it replaces |
| 🛠 **Ops console** | Each request's full story, the review queue, the integration log |

| File | What it is |
|---|---|
| `app.py`, `ui/` | Streamlit pages and shared session state |
| `site.py` | What the website checkout and the quotes@perennialsfabrics.com inbox send into the workflow |
| `seed.py`, `data/seed_decisions.json` | Seeds the history with the rep's qualification decisions (qualification is manual for new senders); Hannah Kim's are left open |
| `baseline.py` | Today's manual steps per automated action (illustrative estimates) |
| `data/` | The workbook (original + 6 added rows, marked in its Notes column) and the web carts |

## Filming the walkthrough (about 4½ minutes)

**Before recording**
- Open http://localhost:8501/ (the root URL; `/website` shows a "Page not found" popup) and let the first load finish.
- Click **↺ Reset demo** so you start from the seeded history.
- Navigate only with the sidebar and the in-page links: a reload or a typed URL starts a fresh session.
- Pause about a second between clicks.

| # | Do this | Say this |
|---|---|---|
| 0 | GitHub README, top diagrams | Today the website, Salesforce and NetSuite don't talk; people retype data and email customers back and forth. This puts one integration layer between them, with people only for judgment. |
| 1 | **Website** → Tidal Herringbone → **Hospitality** → Add Sample → Cart → Checkout (Dana pre-filled) → **Place order** | Like the real site, the customer picks an exact colorway, so there's nothing to interpret. |
| 2 | Thank-you page | Matched to her existing contact, qualified from her trade account, sample order created in NetSuite on her existing opportunity, and nobody retyped anything. |
| 3 | **See it in the CRM** → **Opportunities** (opens on Ruiz Interiors) | One opportunity, with the new sample next to her earlier ones and her quotes. |
| 4 | **Inbox (quotes@perennialsfabrics.com)** → *Dana: 30 yds of the herringbone* → **Send to quotes@perennialsfabrics.com** | While Claude reads it (about 10 seconds): email is where AI earns its place, reading free text into SKU and quantity, checked against the catalog and cross-checked by rules. Pricing and stock are plain code. Then: priced, held and sent, with no one involved. |
| 5 | **ERP** → Inventory: lot L-2403 shows 30 yd reserved | NetSuite holds the fabric from one dye lot for 14 days. |
| 6 | **CRM → Tasks**: open EML-023's drafted message, then click **Qualify** on EML-026 (Hannah) | When the system isn't sure about a quote, it drafts one message for the rep to send in one click. Qualifying is always a person's call for a new sender: Hannah says she's a designer, but a rep decides. One click on Qualify and her quote is priced, held and drafted. |
| 7 | **Old vs New** → Ruiz Interiors | About 50 manual steps, 117 retyped values and 12 emails today, against 3 rep clicks: qualifying Dana once and approving two flagged quotes (labelled estimates). |
| 8 | GitHub → `production-handoff/` | What engineering builds: the system-by-system list and skeleton building blocks. The customer's accept / decline is the next step, out of scope here. |
