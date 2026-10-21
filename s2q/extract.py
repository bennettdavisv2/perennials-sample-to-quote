"""Turn an inbound request into structured data.

Website requests arrive structured (CartIntake): the customer picked the exact colorway
on a product page, so only emails need reading. For email, two interchangeable
extractors return the same shape:
  * RuleExtractor - deterministic, offline, always available.
  * LLMExtractor  - Claude with structured outputs (JSON schema in output_config.format). Used when
                    ANTHROPIC_API_KEY is set. Its output is validated against the
                    catalog. If the call fails, we fall back to rules.

Output shape (dict):
  method, segment_hint (trade|consumer|student|spam|competitor|unclear), trade_subtype,
  signals [str], project, items [{reference, skus, quantity, unit, ambiguous}],
  wildcard, need_by, urgent, budgetary, revision
"""
from __future__ import annotations

import json
import os
import re

# Short names people actually use ("the stripe", "green velvet").
ALIASES = {
    "Harbor Stripe": ["harbor stripe", "stripe"],
    "Woven Boucle": ["woven boucle", "boucle"],
    "Basketweave": ["basketweave", "basket weave"],
    "Velvet Plush": ["velvet plush", "velvet"],
    "Coastal Linen": ["coastal linen", "linen"],
    "Tidal Herringbone": ["tidal herringbone", "herringbone"],
    "Garden Trellis": ["garden trellis", "trellis"],
    "Canvas Solid": ["canvas solid", "canvas"],
    "Ribbed Chenille": ["ribbed chenille", "chenille"],
    "Sunset Ikat": ["sunset ikat", "ikat"],
    "Rope Texture": ["rope texture"],
    "Mesh Sling": ["mesh sling", "mesh"],
    "Faux Leather": ["faux leather", "leather"],
    "Plaid Check": ["plaid check", "plaid"],
}
COLOR_FAMILIES = {
    "green": ["moss", "celadon", "forest"], "red": ["garnet", "coral"], "blue": ["navy", "indigo"],
    "grey": ["fog", "slate", "graphite", "charcoal"], "gray": ["fog", "slate", "graphite", "charcoal"],
    "brown": ["cognac"], "tan": ["sand", "oat"], "beige": ["sand", "oat"], "cream": ["ivory"],
}
FREE_EMAIL = ("gmail.", "yahoo.", "hotmail.", "outlook.", "icloud.", "aol.", "proton.")

TRADE_KW = ["designer", "interior design", "architect", "specifying", "specifier", "upholster", "hospitality",
            "hotel", "guest room", "lobby", "client", "customer wants", "refit", "yacht", "restaurant", "firm",
            "studio", "library", "banquette", "property", "contract", "project"]
CONSUMER_KW = ["my patio", "my own chair", "for my own", "my house", "my home", "my couch", "my sofa", "for me"]
SPAM_KW = ["seo", "backlink", "page 1 guaranteed", "click here", "crypto", "casino"]
NUM_UNIT = r"(\d+(?:\.\d+)?)\s*(yards|yard|yds|yd|meters|metres|meter|metre|m|feet|foot|ft)?\b"


def _project(text: str) -> str:
    """Short project label for the Opportunity name: first sentence, max ~55 chars."""
    first = re.split(r"(?<=[.!?])\s", text.strip())[0].rstrip(".!?")
    if re.match(r"(?i)(please|can|could|send|need|also|hi|price|just)\b", first) or not first:
        return ""
    if len(first) > 55:
        first = first[:55].rsplit(" ", 1)[0] + "..."
    return first


def is_free_email(email: str) -> bool:
    return any(email.split("@")[-1].startswith(p) for p in FREE_EMAIL)


def _unit(u):
    if not u:
        return None
    return "m" if u.startswith("m") else "ft" if u.startswith("f") else "yd"


def classify(text: str, company: str | None) -> tuple[str, str, list[str]]:
    """Who is asking, from free text + company: (segment_hint, trade_subtype, signals)."""
    hay = f"{text.lower()} {(company or '').lower()}"
    trade = [k for k in TRADE_KW if k in hay]
    consumer = [k for k in CONSUMER_KW if k in hay]
    spam = [k for k in SPAM_KW if re.search(r"\b" + re.escape(k), hay)]
    caps = sum(1 for w in text.split() if len(w) > 3 and w.isupper()) >= 3
    if spam or caps:
        seg = "spam"
    elif "student" in hay:
        seg = "student"
    elif trade and not consumer:
        seg = "trade"
    elif consumer and not trade:
        seg = "consumer"
    else:
        seg = "unclear"
    subtype = ("Interior Designer" if "design" in hay else "Architect" if "architect" in hay
               else "Upholsterer" if "upholster" in hay else "Hospitality" if "hotel" in hay else "Other")
    signals = [f"trade: {k}" for k in trade] + [f"consumer: {k}" for k in consumer] + [f"spam: {k}" for k in spam]
    if "student" in hay:
        signals.append("student")
    return seg, subtype, signals


class RuleExtractor:
    name = "rules"

    def __init__(self, catalog: list[dict]):
        self.catalog = catalog  # one row per SKU
        self.by_fabric: dict[str, list[dict]] = {}
        for it in catalog:
            self.by_fabric.setdefault(it["fabric"], []).append(it)
        pats = sorted(((a, f) for f, al in ALIASES.items() if f in self.by_fabric for a in al),
                      key=lambda x: -len(x[0]))
        self.alias_re = re.compile(r"\b(" + "|".join(re.escape(a) for a, _ in pats) + r")\b", re.I)
        self.alias_map = {a: f for a, f in pats}

    def _mentions(self, text):
        return [(m.start(), m.end(), self.alias_map[m.group(1).lower()]) for m in self.alias_re.finditer(text)]

    def _colors_in(self, fabric, s):
        """Return (skus, exact). exact=True when colors were named, False when inferred from a family like 'green'."""
        s = s.lower()
        skus = [it for it in self.by_fabric[fabric] if re.search(r"\b" + it["color"].lower() + r"\b", s)]
        if skus:
            return skus, True
        fam = [c for w, cs in COLOR_FAMILIES.items() if re.search(r"\b" + w + r"\b", s) for c in cs]
        return [it for it in self.by_fabric[fabric] if it["color"].lower() in fam], False

    def extract(self, req: dict) -> dict:
        text = req["message"]
        low = text.lower()
        want_qty = req.get("type", "").lower().startswith("quote")
        every_color = bool(re.search(r"every colou?r|all colou?rs|all the colou?rs", low))
        items, mentions = [], self._mentions(text)
        for i, (s, e, fabric) in enumerate(mentions):
            prev_end = mentions[i - 1][1] if i else 0
            next_start = mentions[i + 1][0] if i + 1 < len(mentions) else len(text)
            pre, post = text[prev_end:s], text[e:next_start]
            pre_words = " ".join(pre.split()[-2:])
            options = self.by_fabric[fabric]
            exact = True
            if every_color:
                skus = options
            else:
                skus, exact = self._colors_in(fabric, pre_words)
                if not skus:
                    skus, exact = self._colors_in(fabric, post)
                if not skus and len(options) == 1:
                    skus, exact = options, True
            # Several explicitly named colors ("Linen in Sand and Charcoal") -> one item each.
            split = every_color or (exact and len(skus) > 1)
            ambiguous = not skus or (len(skus) > 1 and not split)
            if not skus:
                skus = options
            qty = unit = None
            if want_qty:
                q = list(re.finditer(NUM_UNIT, pre))
                if q:
                    qty, unit = float(q[-1].group(1)), _unit(q[-1].group(2))
                else:
                    q2 = (re.search(r"\b(?:at|to)\s+(\d+(?:\.\d+)?)", post)
                          or re.search(r"(\d+(?:\.\d+)?)\s*(yards|yard|yds|yd|meters|metres|m|feet|foot|ft)\b", post))
                    if q2:
                        has_unit = q2.lastindex and q2.lastindex > 1
                        qty, unit = float(q2.group(1)), _unit(q2.group(2) if has_unit else None)
                if qty is not None and unit is None:
                    unit = "yd"
            mention = text[s:e]
            for sku in (skus if split else [None]):
                if sku:
                    ref = f"{mention} ({sku['color']})"
                else:
                    lead_word = pre_words.split()[-1] if pre_words and not ambiguous and len(options) > 1 else ""
                    ref = f"{lead_word} {mention}".strip()
                items.append({"reference": ref, "skus": [sku["sku"]] if sku else [x["sku"] for x in skus],
                              "quantity": qty, "unit": unit, "ambiguous": False if sku else ambiguous,
                              "inferred": not exact})
        # de-duplicate on SKU set (e.g. "Sling ... mesh")
        seen, dedup = set(), []
        for it in items:
            k = tuple(it["skus"])
            if k in seen:
                continue
            seen.add(k)
            dedup.append(it)

        seg, subtype, signals = classify(text, req.get("company"))

        need_by = None
        months = "january|february|march|april|may|june|july|august|september|october|november|december"
        m = re.search(rf"\b(?:by|before)\s+((?:early|mid|late)[- ]?)?({months})\b", low)
        if m:
            need_by = m.group(0)
        return {
            "method": "rules",
            "segment_hint": seg, "trade_subtype": subtype, "signals": signals,
            "project": _project(text),
            "items": dedup,
            "wildcard": bool(re.search(r"everything you have|all your|every fabric|full line|entire line", low)),
            "need_by": need_by,
            "urgent": bool(re.search(r"\basap\b|urgent|rush", low)),
            "budgetary": "budgetary" in low or "ballpark" in low,
            "revision": bool(re.search(r"\bupdate\b|make that|change (it|that) to|instead of", low)),
        }


_NULLABLE_STR = {"type": ["string", "null"]}

# Structured output schema (output_config.format): the API guarantees the reply is JSON matching this.
EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "segment_hint": {"type": "string", "enum": ["trade", "consumer", "student", "spam", "competitor", "unclear"],
                         "description": "Who is asking. trade = designer/architect/upholsterer/hospitality/"
                                        "specifier buying for a client project."},
        "trade_subtype": {"type": "string",
                          "description": "e.g. Interior Designer, Architect, Upholsterer, Hospitality, Marine, Other"},
        "signals": {"type": "array", "items": {"type": "string"},
                    "description": "Short phrases from the message that justify segment_hint."},
        "project": {"type": "string", "description": "One-line project description, or empty."},
        "items": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "reference": {"type": "string", "description": "How the customer referred to it, verbatim"},
            "skus": {"type": "array", "items": {"type": "string"},
                     "description": "Catalog SKUs this could mean. More than one only if ambiguous or 'every color'."},
            "quantity": {"type": ["number", "null"]},
            "unit": {"anyOf": [{"type": "string", "enum": ["yd", "m", "ft"]}, {"type": "null"}]},
            "ambiguous": {"type": "boolean"},
            "inferred": {"type": "boolean",
                         "description": "True if the SKU was inferred from a loose description (e.g. 'green velvet') "
                                        "rather than named."}},
            "required": ["reference", "skus", "quantity", "unit", "ambiguous", "inferred"]}},
        "wildcard": {"type": "boolean", "description": "Asked for everything / all fabrics without naming them."},
        "need_by": _NULLABLE_STR,
        "urgent": {"type": "boolean"},
        "budgetary": {"type": "boolean", "description": "Customer says rough/budgetary pricing is fine."},
        "revision": {"type": "boolean", "description": "Changes a quantity or item from an earlier request."},
    },
    "required": ["segment_hint", "trade_subtype", "signals", "project", "items", "wildcard", "need_by",
                 "urgent", "budgetary", "revision"],
}


class LLMExtractor:
    name = "llm"

    def __init__(self, catalog: list[dict], model: str | None = None):
        import anthropic  # imported lazily so rules mode needs no SDK
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("S2Q_MODEL", "claude-opus-5-5")
        self.catalog = catalog
        self.valid = {c["sku"] for c in catalog}
        cat = "\n".join(f"{c['sku']} | {c['fabric']} | {c['color']} | {c['status']}" for c in catalog)
        self.system = (
            "You read inbound requests for Perennials, a performance-fabric company that sells to the design trade. "
            "Extract exactly what the customer asked for. Map every fabric reference to SKUs from this catalog only "
            "(SKU | Fabric | Color | Status):\n" + cat + "\n\n"
            "Rules: informal names count ('navy stripe' = Harbor Stripe Navy; 'green velvet' = Velvet Plush Moss). "
            "If a fabric has several colors and none is given, list all its SKUs and set ambiguous=true. "
            "'Every color of X' means one item per SKU of X. Do not compute prices. Do not invent SKUs. "
            "Quantities: keep the customer's unit (yd, m or ft); "
            "a bare number next to a fabric in a yardage request is yards. "
            "Sample requests have quantity null.")

    def extract(self, req: dict) -> dict:
        msg = (f"Request type: {req['type']}\nChannel: {req['channel']}\nName: {req['name']}\n"
               f"Company: {req['company']}\nEmail: {req['email']}\nMessage: {req['message']}")
        resp = self.client.beta.messages.create(
            model=self.model, max_tokens=16000, system=self.system,
            # A simple extraction: low effort keeps it fast. Structured outputs guarantee schema-valid JSON.
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
            # If a safety classifier declines, the API retries on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            messages=[{"role": "user", "content": msg}])
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"model declined ({getattr(resp.stop_details, 'category', None)})")
        out = json.loads(next(b.text for b in resp.content if b.type == "text"))
        # Validate: drop SKUs that are not in the catalog rather than trusting the model.
        for it in out.get("items", []):
            bad = [s for s in it.get("skus", []) if s not in self.valid]
            it["skus"] = [s for s in it.get("skus", []) if s in self.valid]
            if bad:  # model named a SKU that doesn't exist: keep the valid ones, force a human check
                it["inferred"] = it["needs_confirm"] = True
                it["ambiguous"] = len(it["skus"]) != 1
                it["reference"] += f" (dropped unknown SKUs {bad})"
        out["items"] = [it for it in out.get("items", []) if it["skus"]]
        out["method"] = f"llm:{self.model}"
        return out


UNITS = {"yards": "yd", "yard": "yd", "yd": "yd", "feet": "ft", "foot": "ft", "ft": "ft",
         "meters": "m", "metres": "m", "meter": "m", "m": "m"}


class CartIntake:
    """Website submissions are structured, so there is nothing to guess about the fabric.

    On perennialsfabrics.com a sample is added from a product page ("Add Sample To Cart"
    on one colorway = one variant SKU, with a Project Type), and "Request A Quote" sends
    Length + unit (Yards / Feet / Meters), Date Needed, CFA Waived / Requested and Project
    Name. Only the order note is free text, and it is read for who is asking, not for SKUs.

    Cart shape (demo/data/web_cart_submissions.json):
      skus [str], project_type (residential|hospitality|None), project_name, note,
      quote_lines [{sku, length, unit, date_needed, cfa}]  (quote form only)
    """
    name = "web cart"

    def __init__(self, catalog: list[dict]):
        self.by_sku = {c["sku"]: c for c in catalog}

    def extract(self, req: dict) -> dict:
        cart = req["cart"]
        note = cart.get("note") or ""
        seg, subtype, signals = classify(note, req.get("company"))
        ptype = cart.get("project_type")
        if ptype:
            signals.append(f"project type: {ptype}")
            if ptype == "hospitality":
                seg = "trade" if seg == "unclear" else seg
                subtype = "Hospitality" if subtype == "Other" else subtype

        lines = cart.get("quote_lines") or [{"sku": s} for s in cart.get("skus", [])]
        items, invalid, seen = [], [], set()
        for ln in lines:
            sku = ln["sku"]
            if sku in seen:
                continue
            seen.add(sku)
            it = self.by_sku.get(sku)
            if not it:  # e.g. a stale cart line for a retired product: never guess a substitute
                invalid.append(sku)
                continue
            items.append({"reference": f"{it['fabric']} {it['color']}", "skus": [sku],
                          "quantity": ln.get("length"), "unit": UNITS.get(str(ln.get("unit") or "yards").lower(), "yd")
                          if ln.get("length") is not None else None,
                          "ambiguous": False, "inferred": False})
        dates = sorted(ln["date_needed"] for ln in lines if ln.get("date_needed"))
        return {
            "method": "web cart",
            "segment_hint": seg, "trade_subtype": subtype, "signals": signals,
            "project": cart.get("project_name") or "",
            "project_type": ptype,
            "items": items,
            "invalid_skus": invalid,
            "wildcard": False,
            "need_by": dates[0] if dates else None,
            "urgent": False,
            "budgetary": False,
            "revision": False,
            "cfa_requested": any(str(ln.get("cfa", "")).lower() == "requested" for ln in lines),
        }


def items_signature(ext: dict) -> set:
    return {(tuple(sorted(i["skus"])), i.get("quantity"), i.get("unit")) for i in ext["items"]}


class Extractor:
    """Website carts are already structured. Emails go to the LLM when available, with rules
    as a cross-check (rules alone otherwise)."""

    def __init__(self, catalog: list[dict], mode: str = "auto"):
        self.cart = CartIntake(catalog)
        self.rules = RuleExtractor(catalog)
        self._prefetched: dict[str, dict | Exception] = {}
        self.failures = 0  # LLM calls that fell back to rules (shown in the UI so a broken key/model isn't silent)
        self.llm = None
        self.status = "rules only"
        if mode in ("auto", "llm") and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                self.llm = LLMExtractor(catalog)
                self.status = f"Claude ({self.llm.model}) + rules cross-check"
            except Exception as e:  # SDK missing etc.
                self.status = f"rules only (LLM unavailable: {e})"
        elif mode in ("auto", "llm"):
            self.status = "rules only (no ANTHROPIC_API_KEY)"

    def prefetch(self, reqs: list[dict], workers: int = 16) -> dict[str, dict]:
        """Read many emails with the LLM in parallel (each call is independent); results are used by extract().
        Returns the successful readings, so a caller can reuse them (see use_readings)."""
        todo = [r for r in reqs if self.llm and not r.get("cart") and r["id"] not in self._prefetched]
        if todo:
            self._fetch(todo, workers)
        return {k: v for k, v in self._prefetched.items() if not isinstance(v, Exception)}

    def use_readings(self, readings: dict[str, dict]):
        """Reuse LLM readings made earlier (e.g. the demo's seeded emails, read once per server run)."""
        self._prefetched.update(readings)

    def _fetch(self, todo: list[dict], workers: int):
        from concurrent.futures import ThreadPoolExecutor

        def one(r):
            try:
                return r["id"], self.llm.extract(r)
            except Exception as e:  # surfaced (and logged as a fallback note) when the request is processed
                return r["id"], e
        with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as pool:
            self._prefetched.update(pool.map(one, todo))

    def extract(self, req: dict) -> tuple[dict, list[str]]:
        notes = []
        if req.get("cart"):
            ext = self.cart.extract(req)
            notes += [f"Cart line {s} is not an item in the ERP: left out, not substituted"
                      for s in ext["invalid_skus"]]
            return ext, notes
        rules = self.rules.extract(req)
        if not self.llm:
            return rules, notes
        try:
            ext = self._prefetched.pop(req["id"], None) or self.llm.extract(req)
            if isinstance(ext, Exception):
                raise ext
        except Exception as e:
            self.failures += 1
            notes.append(f"LLM extraction failed ({type(e).__name__}: {str(e)[:120]}); used rules")
            return rules, notes
        if items_signature(ext) != items_signature(rules):
            notes.append("LLM and rules disagree on items/quantities: rep should confirm. "
                         f"rules={json.dumps(rules['items'])}")
        if ext["segment_hint"] != rules["segment_hint"]:
            ext["segment_alt"] = rules["segment_hint"]  # qualification sends this to review when there's no CRM account
            notes.append(f"LLM segment '{ext['segment_hint']}' vs rules '{rules['segment_hint']}'")
        return ext, notes
