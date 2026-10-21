# Demo

A walkthrough of the sample-to-quote workflow across mock versions of the three systems. It runs the shared core in [`../s2q/`](../s2q/) against in-memory CRM and ERP mocks. Nothing in this folder ships to production.

## Run it
From the repo root (see the main README for install):

```bash
streamlit run demo/app.py                      # http://localhost:8501/
# with Claude reading emails (key in a .env one folder above the repo):
set -a; source ../.env; set +a; streamlit run demo/app.py
```

The app starts on **day one**: NetSuite's inventory and price rules and Salesforce's 6 existing accounts, with nothing processed, so a new customer's journey is the only thing on screen. Set **Start from → Workbook history** in the sidebar to load the 27 workbook requests (21 original + 6 edge cases we added); with Claude on, that first load reads the 13 workbook emails (about 10 seconds, once per app run).

| Page | What it is |
|---|---|
| **Website** | Storefront modelled on the real site's flow: colorway, Add Sample + Project Type, Request A Quote (Length in yards / feet / meters, Date Needed, CFA, Project Name), cart, guest checkout |
| **CRM** | Salesforce-style: quotes@perennialsfabrics.com inbox, leads, accounts, opportunity record pages, the rep's task queue with drafted messages |
| **ERP** | NetSuite-style: inventory by dye lot, sales orders (samples, holds, CFA cuttings), customers |
| **Today (manual)** | Today's process with no integration: you play Dana and the CSR in a blank Gmail, Salesforce and NetSuite. A scoreboard measures time, values typed, emails written and system switches; a checklist tracks the 18 CSR steps; quotes are checked against the price rules |
| **Ops console** | Each request's full story, the review queue, the integration log |

| File | What it is |
|---|---|
| `app.py`, `ui/` | Streamlit pages and shared session state |
| `site.py` | What the website checkout and the quotes@perennialsfabrics.com inbox send into the workflow |
| `seed.py`, `data/seed_decisions.json` | The day-one start, and the workbook history with the rep's qualification decisions (Hannah Kim's are left open) |
| `manual.py` | State and live counters behind the Today (manual) page |
| `data/` | The workbook (original + 6 added rows, marked in its Notes column) and the web carts |

## Try it

The new system, one customer from sample to revised quote (Dana Ruiz is a new customer):

1. **Website:** Tidal Herringbone → Add Sample; Canvas Solid, White → Add Sample. Cart → Checkout, fill in as **Dana Ruiz** → Place order.
2. **CRM → Tasks:** click **Qualify**. Her account, contact and opportunity are created and the sample order goes to the ERP.
3. **Website:** Tidal Herringbone → Request A Quote: 30 yards, CFA Requested, a project name → Add to Cart → Checkout → Place order. The quote is priced, held on one dye lot and sent.
4. **CRM → Inbox:** template *Dana: bump the herringbone to 45 yds* → Send. Claude reads the change; the quote is revised, re-held and sent.
5. **ERP:** lot L-2403 shows 45 yd reserved; Sales orders shows the sample order, holds and the CFA cutting.

Today's process, for comparison: open **Today (manual)** and follow its checklist. Each step expands to show exactly what to do.

For the edge cases (ambiguous colors, discontinued and backordered fabric, sample limits, Do Not Sell, duplicates), set **Start from** to **Workbook history**.
