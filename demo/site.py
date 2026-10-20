"""What the website and the quotes@perennialsfabrics.com inbox send into the workflow (used by the demo UI).

On perennialsfabrics.com a sample or quote line is added from a product page (one colorway
= one variant SKU), and checkout adds the contact fields. These helpers build the same
request shape the workbook rows use, so the workflow treats a live demo submission exactly
like a seeded one: two front doors (website, email), one pipeline.
"""
from __future__ import annotations

import re
import time
from datetime import timedelta

# Swatch colors for the mock storefront (plain color blocks, no product imagery).
SWATCH = {"Navy": "#1f2a44", "Oat": "#d8cbb0", "Fog": "#b9bec4", "Moss": "#5d6b3a", "Garnet": "#7a1f2b",
          "Sand": "#d9c6a3", "Charcoal": "#3b3d40", "Slate": "#5f6b75", "Celadon": "#a8c3a0", "White": "#f4f2ec",
          "Black": "#1b1b1b", "Ivory": "#efe8d6", "Coral": "#e07a5f", "Indigo": "#2e3a6e", "Graphite": "#4a4d52",
          "Cognac": "#8a4b2a", "Forest": "#2f4a32"}


def fabrics(items: list[dict]) -> list[dict]:
    """Group ERP items (one per SKU) into storefront products (one per fabric, colorways as variants)."""
    out: dict[str, dict] = {}
    for it in items:
        out.setdefault(it["fabric"], {"fabric": it["fabric"], "colorways": []})["colorways"].append(it)
    return list(out.values())


def _next_id(w, prefix: str) -> str:
    nums = [int(m.group(1)) for r in w.inbox if (m := re.fullmatch(prefix + r"-(\d+)", r["id"]))]
    return f"{prefix}-{max(max(nums, default=0) + 1, 101):03d}"


def _now(w):
    """Simulated clock: an hour after the latest request, so live submissions follow the seeded history
    (or the clean start's clock, demo.seed.clean)."""
    return max((r["received"] for r in w.inbox), default=getattr(w, "demo_clock", None)) + timedelta(hours=1)


def _run(w, req: dict) -> dict:
    """Submit one request and time it on the wall clock: how long the customer waits for the answer."""
    t0 = time.perf_counter()
    res = w.submit(req)
    res["elapsed_s"] = time.perf_counter() - t0
    return res


def submit_checkout(w, customer: dict, samples: list[dict], quotes: list[dict], project_name: str = "",
                    note: str = "") -> list[dict]:
    """One checkout -> up to two requests: the sample lines and the quote lines.

    customer: {name, company, email}
    samples:  [{sku, project_type}]                                   ("Add Sample To Cart")
    quotes:   [{sku, length, unit, date_needed, cfa, project_type, project_name}]  ("Request A Quote")
    """
    base = {"name": customer["name"], "company": customer.get("company") or "",
            "email": customer["email"].strip().lower(), "channel": "Website form"}
    results = []
    if samples:
        req = {**base, "id": _next_id(w, "WEB"), "type": "Sample request", "received": _now(w), "message": note,
               "cart": {"skus": [s["sku"] for s in samples], "project_type": samples[0].get("project_type"),
                        "project_name": project_name, "note": note}}
        results.append(_run(w, req))
    if quotes:
        req = {**base, "id": _next_id(w, "WEB"), "type": "Quote request", "received": _now(w), "message": note,
               "cart": {"quote_lines": quotes, "project_type": quotes[0].get("project_type"),
                        "project_name": project_name or quotes[0].get("project_name") or "", "note": note}}
        results.append(_run(w, req))
    return results


def submit_email(w, name: str, company: str, email: str, message: str) -> dict:
    """An email to the shared quotes@perennialsfabrics.com inbox (free text, read by Claude or the rules)."""
    req = {"id": _next_id(w, "EML"), "type": "Quote request", "channel": "Email", "received": _now(w),
           "name": name, "company": company or "", "email": email.strip().lower(), "message": message}
    return _run(w, req)
