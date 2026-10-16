import pytest

from s2q.data import PricingConfig
from s2q.pricing import price_line, to_yards
from s2q.workflow import Workflow


@pytest.fixture(scope="module")
def wf():
    w = Workflow(mode="rules")
    w.process_all()
    return w


# ---------- pricing ----------
def test_trade_volume_stacks_additively():
    p = price_line(98, 80, True, PricingConfig())
    assert p["total_discount"] == 0.20 and p["unit_price"] == 78.40 and p["line_total"] == 6272.00


def test_cut_fee_under_5_yards():
    assert price_line(78, 3, True, PricingConfig())["line_total"] == round(3 * 66.30 + 25, 2)


def test_non_trade_pays_list_no_volume():
    p = price_line(64, 120, False, PricingConfig())
    assert p["total_discount"] == 0 and p["unit_price"] == 64


def test_meters_round_up_to_quarter_yard():
    assert to_yards(12, "m") == 13.25
    assert to_yards(3, "yd") == 3


def test_feet_convert_to_yards():
    assert to_yards(30, "ft") == 10
    assert to_yards(10, "ft") == 3.5   # 3.33 yd rounds up to the next 1/4


# ---------- end to end ----------
def test_outcomes(wf):
    out = {k: v["outcome"] for k, v in wf.results.items()}
    assert out["WEB-007"] == "Spam filtered"
    assert out["WEB-005"].startswith("Disqualified")
    assert out["WEB-002"].startswith("Non-trade")
    assert out["WEB-009"].startswith("Non-trade")              # student
    assert out["WEB-012"].startswith("Needs review")           # designer on gmail
    assert out["WEB-013"].startswith("Needs review")           # 14 samples > 10
    assert out["WEB-008"] == "Qualified, no eligible samples"  # discontinued
    assert out["EML-017"].endswith("sent")                     # clean quote goes straight out


def test_dedupe_same_person_second_email(wf):
    # WEB-003 comes from d.ruiz@ instead of dana@: must land on the same account + opportunity.
    assert wf.results["WEB-003"]["identity"]["match"].startswith("Same person")
    ruiz = [o for o in wf.crm.opportunities if o["name"].startswith("Ruiz Interiors")]
    assert len(ruiz) == 1 and len(ruiz[0]["sample_orders"]) == 2


def test_spam_writes_nothing_to_crm(wf):
    assert not any("rank-boost" in l["email"] for l in wf.crm.leads)


def test_revision_supersedes_and_rereserves(wf):
    v1 = next(q for q in wf.crm.quotes if q["id"] == "Q-0101-v1")
    v2 = next(q for q in wf.crm.quotes if q["id"] == "Q-0101-v2")
    assert v1["status"] == "Superseded" and v2["total"] == 90 * 78.40 + 20 * 120.70
    so1 = next(s for s in wf.erp.sales_orders if s["id"] == v1["reservation_id"])
    assert so1["status"].startswith("Released")
    # Stripe: 10 pre-existing + 87 held by v2 (only 87 available, 3 short)
    stripe = {l["lot"]: l["reserved"] for l in wf.erp.lots if l["sku"] == "PF-1001"}
    assert stripe == {"L-2401": 62, "L-2417": 35}


def test_budgetary_quote_does_not_reserve(wf):
    assert wf.results["EML-018"]["stages"][6]["status"] == "skipped"


def test_backorder_priced_not_reserved(wf):
    r = wf.results["EML-019"]
    assert r["stages"][6]["status"] == "skipped" and any("Backorder" in f for f in r["flags"])


def test_unique_color_match_is_quoted_without_a_confirmation_hold(wf):
    # "green velvet": Velvet Plush only comes in one green (Moss), so no back-and-forth is needed.
    r = wf.results["EML-015"]
    q = next(q for q in wf.crm.quotes if q["id"] == r["quote_id"])
    assert [l["sku"] for l in q["lines"]] == ["PF-1004"]
    assert not any("interpreted as" in f for f in r["flags"])
    assert "Velvet Plush in Moss" in r["email"]["body"]          # named, so the customer can catch a mistake


def _email(w, base_id, new_id, message):
    base = next(r for r in w.inbox if r["id"] == base_id)
    return {**base, "id": new_id, "message": message, "received": base["received"].replace(month=11)}


def test_ambiguous_color_resolved_from_sample_history():
    # Priya sampled Canvas Solid White (WEB-006); "the canvas" could be White or Black.
    w = Workflow(mode="rules")
    w.process_all()
    res = w.process(_email(w, "EML-016", "EML-T1", "Need 40 yds of the canvas for the cabanas."))
    q = next(q for q in w.crm.quotes if q["id"] == res["quote_id"])
    assert [l["sku"] for l in q["lines"]] == ["PF-1010"]
    assert not any("could be" in f for f in res["flags"])


def test_still_ambiguous_drafts_one_question_with_stock():
    # Mara sampled both Coastal Linen colors (WEB-004), so history can't decide: ask once, with stock.
    w = Workflow(mode="rules")
    w.process_all()
    res = w.process(_email(w, "EML-017", "EML-T2", "Can I get 10 yds of the linen?"))
    assert res["outcome"] == "Needs review: nothing priceable"
    body = res["email"]["body"]
    assert "Sand (" in body and "Charcoal (" in body and "yd in stock" in body


def test_approve_review_places_samples():
    w = Workflow(mode="rules")
    w.process_all()
    rv = next(r for r in w.reviews if r["request"] == "WEB-012")
    w.approve(rv["id"])
    assert w.results["WEB-012"]["outcome"].startswith("Samples sent")


def test_llm_failure_falls_back_to_rules(monkeypatch):
    w = Workflow(mode="rules")

    class Boom:
        model = "x"

        def extract(self, req):
            raise RuntimeError("api down")

    w.extractor.llm = Boom()
    res = w.process(next(r for r in w.inbox if r["id"] == "EML-015"))
    assert res["extraction"]["method"] == "rules"
    assert any("failed" in n for n in res["extract_notes"])


def test_llm_output_is_validated_against_catalog(monkeypatch):
    """Stub the Claude client: a hallucinated SKU is dropped and the line is flagged, not trusted."""
    from types import SimpleNamespace as NS

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    w = Workflow(mode="auto")

    class FakeMessages:
        def create(self, **kw):
            assert kw["tool_choice"]["name"] == "record_request"
            return NS(content=[NS(type="tool_use", input={
                "segment_hint": "trade", "trade_subtype": "Upholsterer", "signals": [], "project": "",
                "items": [{"reference": "green velvet", "skus": ["PF-1004", "PF-9999"], "quantity": 12,
                           "unit": "m", "ambiguous": False, "inferred": False}],
                "wildcard": False, "need_by": None, "urgent": False, "budgetary": False, "revision": False,
                "wants_hold": False, "asks_price_list": False})])

    w.extractor.llm.client = NS(messages=FakeMessages())
    res = w.process(next(r for r in w.inbox if r["id"] == "EML-015"))
    assert res["extraction"]["items"][0]["skus"] == ["PF-1004"]
    assert res["quote_id"] and any("confirm" in f for f in res["flags"])


# ---------- website intake is structured ----------
def test_web_cart_items_are_exact_skus(wf):
    ext = wf.results["WEB-010"]["extraction"]
    assert ext["method"] == "web cart"
    assert [i["skus"] for i in ext["items"]] == [["PF-1015"], ["PF-1010"]]
    assert not any(i["ambiguous"] or i["inferred"] for i in ext["items"])


def test_web_requests_never_call_the_llm():
    w = Workflow(mode="rules")

    class MustNotBeCalled:
        model = "x"

        def extract(self, req):
            raise AssertionError(f"LLM called for website request {req['id']}")

    w.extractor.llm = MustNotBeCalled()
    for r in w.inbox:
        if r["id"].startswith("WEB"):
            w.process(r)


def test_unknown_cart_sku_is_flagged_not_substituted():
    w = Workflow(mode="rules")
    req = dict(next(r for r in w.inbox if r["id"] == "WEB-001"))
    req["cart"] = {**req["cart"], "skus": ["PF-1001", "PF-9999"]}
    res = w.process(req)
    assert [i["skus"] for i in res["extraction"]["items"]] == [["PF-1001"]]
    assert any("PF-9999" in f for f in res["flags"])


def test_web_quote_form_with_cfa_and_feet():
    """The site's Request A Quote form: Length in Feet, Date Needed, CFA Requested."""
    w = Workflow(mode="rules")
    base = next(r for r in w.inbox if r["id"] == "EML-017")  # Mara Lowe, existing trade contact
    req = {**base, "id": "WEB-Q01", "channel": "Website form", "message": "",
           "cart": {"project_name": "Malibu beach house", "project_type": "residential", "note": "",
                    "quote_lines": [{"sku": "PF-1006", "length": 30, "unit": "Feet",
                                     "date_needed": "2026-11-20", "cfa": "requested"}]}}
    res = w.process(req)
    q = next(q for q in w.crm.quotes if q["id"] == res["quote_id"])
    assert q["lines"][0]["yards"] == 10
    cfa = next(s for s in w.erp.sales_orders if s["id"] == q["cfa_order_id"])
    assert cfa["type"] == "CFA" and cfa["lines"][0]["sku"] == "PF-1006"
    assert res["extraction"]["need_by"] == "2026-11-20"


# ---------- every review comes with a drafted customer message ----------
def test_every_review_has_a_drafted_message(wf):
    assert wf.reviews and all(rv["message"] and rv["message"]["body"] for rv in wf.reviews)


def test_gray_zone_lead_drafts_trade_verification_and_stays_open_until_decided():
    w = Workflow(mode="rules")
    w.process_all()
    rv = next(r for r in w.reviews if r["request"] == "WEB-012")
    assert "resale certificate" in rv["message"]["body"] and "Velvet Plush - Garnet" in rv["message"]["body"]
    w.ask(rv["id"])
    assert rv["asked"] and rv["status"] == "Open"                        # the customer's reply decides it
    assert any(e["action"] == "Email question" and e["request"] == "WEB-012" for e in w.log.events)
    w.approve(rv["id"])                                                  # proof arrived: qualify and ship
    assert w.results["WEB-012"]["outcome"].startswith("Samples sent")


def test_over_limit_drafts_pick_your_ten():
    w = Workflow(mode="rules")
    w.process_all()
    body = next(r for r in w.reviews if r["request"] == "WEB-013")["message"]["body"]
    assert "up to 10" in body and "You picked 14" in body


def test_missing_quantity_becomes_a_question_and_approve_sends_it():
    w = Workflow(mode="rules")
    w.process_all()
    base = next(r for r in w.inbox if r["id"] == "EML-017")
    res = w.process({**base, "id": "EML-T3", "message": "Could you price the herringbone for me?"})
    rv = next(r for r in w.reviews if r["request"] == "EML-T3")
    assert rv["action"] == "send_question" and "How much Tidal Herringbone" in rv["message"]["body"]
    w.approve(rv["id"])
    assert rv["status"].startswith("Question sent") and res["outcome"] == "Question sent: waiting on customer"


def test_quote_review_cannot_be_sent_as_a_question(wf):
    rv = next(r for r in wf.reviews if r["action"] == "send_quote" and r["status"] == "Open")
    wf.ask(rv["id"])
    assert not rv["asked"] and rv["status"] == "Open"
