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


def test_green_velvet_flagged_for_confirmation(wf):
    assert any("interpreted as" in f for f in wf.results["EML-015"]["flags"])


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
    res = w.process_next()
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
