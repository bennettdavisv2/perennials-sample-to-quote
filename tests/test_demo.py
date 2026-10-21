"""The demo's storefront / inbox entry points and the old-vs-new comparison."""
import pytest

from demo import baseline, manual, site
from demo.manual import Desk
from demo.seed import clean, seed
from s2q.workflow import Workflow

DANA = {"name": "Dana Ruiz", "company": "Ruiz Interiors", "email": "dana@ruizinteriors.example"}


@pytest.fixture()
def seeded():
    return seed(Workflow(mode="rules"))


def test_storefront_sample_checkout_lands_on_existing_opportunity(seeded):
    w = seeded
    [res] = site.submit_checkout(w, DANA, samples=[{"sku": "PF-1008", "project_type": "hospitality"}], quotes=[])
    assert res["request"]["id"] == "WEB-101" and res["outcome"] == "Samples sent (1)"
    assert res["request"]["received"] > max(r["received"] for r in w.inbox[:-1])
    ruiz = [o for o in w.crm.opportunities if o["account_id"] == "ACC-0101"]
    assert len(ruiz) == 1 and len(ruiz[0]["sample_orders"]) == 3   # WEB-001, WEB-003, and this one


def test_checkout_with_samples_and_a_quote_line_makes_two_requests(seeded):
    w = seeded
    out = site.submit_checkout(w, DANA, samples=[{"sku": "PF-1017", "project_type": "hospitality"}],
                               quotes=[{"sku": "PF-1008", "length": 90, "unit": "Feet", "date_needed": "2026-12-01",
                                        "cfa": "requested", "project_type": "hospitality"}], project_name="Lobby")
    assert [r["request"]["type"] for r in out] == ["Sample request", "Quote request"]
    q = next(q for q in w.crm.quotes if q["id"] == out[1]["quote_id"])
    assert q["lines"][0]["yards"] == 30 and q.get("cfa_order_id")


def test_email_to_quotes_inbox_is_read_and_quoted(seeded):
    w = seeded
    res = site.submit_email(w, **DANA, message="Can you quote 30 yds of the herringbone? Please hold it.")
    assert res["request"]["id"] == "EML-101"
    q = next(q for q in w.crm.quotes if q["id"] == res["quote_id"])
    assert [l["sku"] for l in q["lines"]] == ["PF-1008"] and res["outcome"].endswith("sent")


def test_every_logged_action_has_a_manual_counterpart(seeded):
    w = seeded
    site.submit_checkout(w, DANA, samples=[], quotes=[{"sku": "PF-1008", "length": 20, "unit": "Yards",
                                                       "cfa": "requested", "project_type": "hospitality"}])
    missing = {(e["system"], e["action"]) for e in w.log.events} - set(baseline.MANUAL)
    assert not missing, f"add these to baseline.MANUAL: {missing}"


def test_old_process_costs_more_than_new_for_every_journey(seeded):
    w = seeded
    js = baseline.journeys(w)
    assert js["ACC-0101"] == ["WEB-001", "WEB-003", "EML-014", "EML-021"]
    for rids in js.values():
        t = baseline.totals(w, rids)
        assert t["old"]["people touches"] > t["new"]["people touches"]
        assert t["new"]["fields retyped"] == 0 < t["old"]["fields retyped"]


# ---------------------------------------------------------------------- clean start (what the demo films)
@pytest.fixture()
def day_one():
    return clean(Workflow(mode="rules"))


def test_clean_start_has_accounts_and_inventory_but_no_history(day_one):
    w = day_one
    assert not w.inbox and not w.results and not w.crm.leads and not w.erp.sales_orders
    assert len(w.crm.accounts) == 6 and len(w.erp.lots) == 20
    assert not any(c["email"] == DANA["email"] for c in w.crm.contacts)  # Dana is a new customer


def test_new_customer_journey_samples_qualify_quote_revision(day_one):
    w = day_one
    [s] = site.submit_checkout(w, DANA, samples=[{"sku": "PF-1008", "project_type": "hospitality"},
                                                 {"sku": "PF-1010", "project_type": "hospitality"}], quotes=[])
    assert s["outcome"] == "Needs review: qualification" and "elapsed_s" in s
    [rv] = [r for r in w.reviews if r["status"] == "Open"]
    w.approve(rv["id"])
    assert s["outcome"] == "Samples sent (2)"
    assert [a["name"] for a in w.crm.accounts][-1] == "Ruiz Interiors" and len(w.crm.opportunities) == 1

    [q] = site.submit_checkout(w, DANA, samples=[], quotes=[{"sku": "PF-1008", "length": 30, "unit": "Yards",
                                                            "date_needed": None, "cfa": "requested",
                                                            "project_type": "hospitality"}])
    assert q["outcome"].endswith("sent") and not q["flags"]

    e = site.submit_email(w, **DANA, message="Client signed off on the herringbone. Can you bump it to 45 yds and "
                                             "add 20 yds of the canvas for the cushions?")
    assert e["outcome"] == "Quote Q-0101-v2 sent"
    v2 = next(x for x in w.crm.quotes if x["id"] == "Q-0101-v2")
    assert {l["sku"]: l["yards"] for l in v2["lines"]} == {"PF-1008": 45, "PF-1010": 20}  # canvas: her sampled White
    lot = next(l for l in w.erp.lots if l["lot"] == "L-2403")
    assert lot["reserved"] == 45  # old 30 yd hold released, 45 held
    t = baseline.totals(w, baseline.journeys(w)["ACC-0101"])
    assert t["new"]["people touches"] == 1 and t["old"]["fields retyped"] > 50


# ---------------------------------------------------------------------- the manual desk (today's process)
def test_manual_desk_counts_typing_emails_and_switches():
    d = Desk.new()
    d.web_sample_request(*DANA.values(), ["PF-1008"], "Hospitality")
    assert d.typed == 0 and d.started is None  # the customer's typing isn't the CSR's work
    d.switch("Salesforce")
    assert d.search("ruiz") == []
    lead = d.create_lead("Dana Ruiz", "Ruiz Interiors", DANA["email"], "Web sample request", "Lobby", "", "New")
    acct, con = d.convert_lead(lead["id"], "Ruiz Interiors", "Trade – Hospitality", "Dana Ruiz", DANA["email"])
    d.create_opportunity("Ruiz - Lobby", acct["id"], con["id"], "Sampling", None)
    d.switch("Gmail")
    d.send(manual.QUOTES, manual.ORDERS, "Samples for Ruiz", "Please send PF-1008")
    d.switch("NetSuite")
    cust = d.create_customer("Ruiz Interiors", DANA["email"], acct["id"], "Trade", "Net 30")
    so, errors = d.create_order("Sample", cust["id"], "", [{"sku": "pf-1008", "lot": "", "qty": 1}])
    assert so and not errors
    assert d.switches == 3 and d.emails_written == 1 and d.typed > 20
    done = {step for _, step, ok in d.checklist() if ok}
    assert "Enter the sample order in NetSuite" in done and "Email Dana that samples are on the way" not in done


def test_manual_hold_reserves_the_typed_lot_and_quote_check_catches_mistakes():
    d = Desk.new()
    _, errors = d.create_order("Pending hold", "CUST-0001", "", [{"sku": "PF-1008", "lot": "L-9999", "qty": 30}])
    assert errors == ["PF-1008: no dye lot L-9999"]
    so, _ = d.create_order("Pending hold", "CUST-0001", "", [{"sku": "PF-1008", "lot": "l-2403", "qty": 30}])
    assert next(l for l in d.lots if l["lot"] == "L-2403")["reserved"] == 30
    d.release(so["id"])
    assert next(l for l in d.lots if l["lot"] == "L-2403")["reserved"] == 0
    q = d.create_quote("OPP-0001", [{"sku": "PF-1008", "description": "", "yards": 30, "unit_price": 112,
                                     "line_total": 3360}], 3360)   # forgot the 15% trade discount
    chk = d.check_quote(q)
    assert chk["expected"] == 2856 and len(chk["problems"]) == 2


def test_every_manual_step_has_instructions():
    from demo.ui.manual import HOW
    assert {step for _, step, _ in Desk.new().checklist()} == set(HOW)
