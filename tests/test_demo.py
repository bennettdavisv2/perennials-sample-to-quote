"""The demo's storefront / inbox entry points and the old-vs-new comparison."""
import pytest

from demo import baseline, site
from s2q.workflow import Workflow

DANA = {"name": "Dana Ruiz", "company": "Ruiz Interiors", "email": "dana@ruizinteriors.example"}


@pytest.fixture()
def seeded():
    w = Workflow(mode="rules")
    w.process_all()
    return w


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
