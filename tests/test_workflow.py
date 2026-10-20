import pytest

from s2q.data import PricingConfig
from s2q.pricing import price_line, to_yards
from demo.seed import seed
from s2q.workflow import Workflow


@pytest.fixture(scope="module")
def wf():
    w = seed(Workflow(mode="rules"))
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
    assert out["WEB-002"] == "Disqualified by rep"              # new sender: a rep rejected (homeowner)
    assert out["WEB-009"] == "Disqualified by rep"              # new sender: a rep rejected (student)
    assert out["WEB-012"] == "Needs review: qualification"      # new sender, not yet decided
    assert out["WEB-013"] == "Needs review: over sample limit"  # qualified by a rep, then 14 samples > 10
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
    w = seed(Workflow(mode="rules"))
    res = w.process(_email(w, "EML-016", "EML-T1", "Need 40 yds of the canvas for the cabanas."))
    q = next(q for q in w.crm.quotes if q["id"] == res["quote_id"])
    assert [l["sku"] for l in q["lines"]] == ["PF-1010"]
    assert not any("could be" in f for f in res["flags"])




def test_approve_review_places_samples():
    w = seed(Workflow(mode="rules"))
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
    assert w.extractor.failures == 1          # counted, so the UI can say Claude isn't actually running


def test_llm_output_is_validated_against_catalog(monkeypatch):
    """Stub the Claude client: a hallucinated SKU is dropped and the line is flagged, not trusted."""
    from types import SimpleNamespace as NS

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    w = Workflow(mode="auto")

    import json

    class FakeMessages:
        def create(self, **kw):
            assert kw["output_config"]["format"]["type"] == "json_schema"   # structured outputs, not forced tools
            return NS(stop_reason="end_turn", content=[NS(type="text", text=json.dumps({
                "segment_hint": "trade", "trade_subtype": "Upholsterer", "signals": [], "project": "",
                "items": [{"reference": "green velvet", "skus": ["PF-1004", "PF-9999"], "quantity": 12,
                           "unit": "m", "ambiguous": False, "inferred": False}],
                "wildcard": False, "need_by": None, "urgent": False, "budgetary": False, "revision": False,
                "wants_hold": False, "asks_price_list": False}))])

    w.extractor.llm.client = NS(beta=NS(messages=FakeMessages()))
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
    req = dict(next(r for r in w.inbox if r["id"] == "WEB-004"))   # Mara: an existing trade customer
    req["cart"] = {**req["cart"], "skus": ["PF-1006", "PF-9999"]}
    res = w.process(req)
    assert [i["skus"] for i in res["extraction"]["items"]] == [["PF-1006"]]
    assert any("PF-9999" in f for f in res["flags"])




# ---------- every review comes with a drafted customer message ----------
def test_every_review_except_qualification_has_a_drafted_message(wf):
    others = [rv for rv in wf.reviews if not rv["action"].startswith("qualify_")]
    assert others and all(rv["message"] and rv["message"]["body"] for rv in others)
    assert all(rv["message"] is None for rv in wf.reviews if rv["action"].startswith("qualify_"))  # a rep decides


def test_new_sender_is_qualified_by_a_rep_not_by_what_they_say():
    """Hannah says she's a designer; that alone never qualifies her. A rep clicks Qualify or Reject."""
    w = seed(Workflow(mode="rules"))
    rv = next(r for r in w.reviews if r["request"] == "WEB-012")
    assert rv["action"] == "qualify_and_sample" and rv["message"] is None
    assert not any(a["name"].startswith("Hannah") for a in w.crm.accounts)  # no account, nothing shipped yet
    w.approve(rv["id"])
    assert w.results["WEB-012"]["outcome"].startswith("Samples sent")


def test_rejected_new_sender_gets_nothing():
    w = seed(Workflow(mode="rules"))
    lead = next(l for l in w.crm.leads if l["email"] == "jsmith1987@gmail.example")
    assert lead["status"] == "Disqualified" and w.results["WEB-002"]["email"] is None


def test_over_limit_drafts_pick_your_ten():
    w = seed(Workflow(mode="rules"))
    body = next(r for r in w.reviews if r["request"] == "WEB-013" and r["action"] == "place_samples_capped")["message"]["body"]
    assert "up to 10" in body and "You picked 14" in body




def test_quote_review_cannot_be_sent_as_a_question(wf):
    rv = next(r for r in wf.reviews if r["action"] == "send_quote" and r["status"] == "Open")
    wf.ask(rv["id"])
    assert not rv["asked"] and rv["status"] == "Open"


# ---------- edge-case rows we added to the workbook (WEB-014, EML-022 .. EML-026) ----------
def test_added_rows_outcomes(wf):
    out = {k: v["outcome"] for k, v in wf.results.items()}
    assert len(wf.inbox) == 27
    assert out["WEB-014"].endswith("needs review")              # need-by date to confirm
    assert out["EML-022"] == "Needs review: nothing priceable"   # rules can't read "sixty yards"
    assert out["EML-023"] == "Needs review: nothing priceable"   # color tie
    assert out["EML-024"] == "Needs review: nothing priceable"   # no quantity
    assert out["EML-025"].endswith("needs review")              # discontinued: remaining stock only
    assert out["EML-026"] == "Needs review: qualification"      # still waiting for a rep (WEB-012)


def test_web_quote_form_feet_and_cfa(wf):
    r = wf.results["WEB-014"]
    q = next(q for q in wf.crm.quotes if q["id"] == r["quote_id"])
    assert q["lines"][0]["yards"] == 30                         # 90 ft
    cfa = next(s for s in wf.erp.sales_orders if s["id"] == q["cfa_order_id"])
    assert cfa["type"] == "CFA" and cfa["lines"][0]["sku"] == "PF-1006"
    assert r["extraction"]["need_by"] == "2026-11-20"


def test_numbers_in_words_become_questions_under_rules(wf):
    body = wf.results["EML-022"]["email"]["body"]
    assert "How much Mesh Sling in Graphite" in body and "How much Canvas Solid in White" in body


def test_color_tie_asks_and_does_not_supersede_the_open_linen_quote(wf):
    body = wf.results["EML-023"]["email"]["body"]
    assert "Sand (" in body and "Charcoal (" in body and "yd in stock" in body
    linen = next(q for q in wf.crm.quotes if q["id"] == wf.results["WEB-014"]["quote_id"])
    assert linen["status"] != "Superseded" and linen["reservation_id"]   # hold kept


def test_missing_quantity_question_is_sent_on_approve():
    w = seed(Workflow(mode="rules"))
    rv = next(r for r in w.reviews if r["request"] == "EML-024")
    assert rv["action"] == "send_question" and "How much Plaid Check" in rv["message"]["body"]
    w.approve(rv["id"])
    assert rv["status"].startswith("Question sent")
    assert w.results["EML-024"]["outcome"] == "Question sent: waiting on customer"


def test_discontinued_quotes_only_remaining_stock(wf):
    q = next(q for q in wf.crm.quotes if q["id"] == wf.results["EML-025"]["quote_id"])
    assert q["lines"][0]["yards"] == 22 and q["lines"][0]["requested_yards"] == 30


def test_pending_qualification_is_not_requalified_by_a_new_message(wf):
    r = wf.results["EML-026"]
    assert "already waiting for a rep" in r["qualification"]["reasons"][0]
    assert not any(a["name"].startswith("Hannah Kim") for a in wf.crm.accounts)   # no account until a rep decides


def test_qualify_then_quote():
    """Approving a new sender's quote request qualifies them, then prices and quotes as usual."""
    w = seed(Workflow(mode="rules"))
    rv = next(r for r in w.reviews if r["request"] == "EML-026")
    assert rv["action"] == "qualify_and_quote"
    w.approve(rv["id"])
    res = w.results["EML-026"]
    q = next(q for q in w.crm.quotes if q["id"] == res["quote_id"])
    assert [l["sku"] for l in q["lines"]] == ["PF-1005"] and q["lines"][0]["yards"] == 20


def test_new_sender_always_goes_to_a_rep_whatever_the_message_says():
    from s2q import qualify
    for seg in ("trade", "consumer", "student", "unclear"):
        d = qualify.decide({"segment_hint": seg, "signals": []}, {"account": None, "lead": None},
                           {"email": "x@studio.example"})
        assert d["decision"] == "review"



def test_llm_readings_are_reused_not_refetched():
    """The demo reads the seeded emails once per server run; a new session reuses them with no LLM calls."""
    calls = []

    class CountingLLM:
        model = "fake"

        def __init__(self, rules):
            self.rules = rules

        def extract(self, req):
            calls.append(req["id"])
            return {**self.rules.extract(req), "method": "llm:fake"}

    first = Workflow(mode="rules")
    first.extractor.llm = CountingLLM(first.extractor.rules)
    readings = first.extractor.prefetch(first.pending())
    emails = [r["id"] for r in first.inbox if not r.get("cart")]
    assert sorted(calls) == sorted(emails) and set(readings) == set(emails)

    calls.clear()
    second = Workflow(mode="rules")
    second.extractor.llm = CountingLLM(second.extractor.rules)
    second.extractor.use_readings(readings)
    second.process_all()
    assert calls == []                                            # nothing re-read
    assert all(second.results[e]["extraction"]["method"] == "llm:fake" for e in emails)


def test_do_not_sell_quote_request_notifies_account_owner():
    w = Workflow(mode="rules")
    base = next(r for r in w.inbox if r["id"] == "WEB-005")          # Fabric Depot Outlet: Do Not Sell
    res = w.process({**base, "id": "EML-T9", "type": "Quote request", "channel": "Email",
                     "message": "Please quote 40 yds of Canvas Solid White."})
    assert res["outcome"] == "Blocked (disqualified)" and "quote_id" not in res
    assert any(t["owner"] == "Account owner" and "EML-T9" in t["subject"] for t in w.crm.tasks)
