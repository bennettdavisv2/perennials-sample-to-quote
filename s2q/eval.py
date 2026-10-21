"""Email-reading evaluation: how often does each reader get the items exactly right?

    python -m s2q.eval            # rules reader, plus Claude when ANTHROPIC_API_KEY is set
    python -m s2q.eval --rules    # rules reader only

The labels below are the hand-checked answer for every email in the workbook: which SKUs, how much, in
which unit. An email counts as correct only when every line matches exactly. Website carts aren't
evaluated: they carry exact SKUs, so there is nothing to read.
"""
from __future__ import annotations

import argparse
import time

from .extract import LLMExtractor, RuleExtractor, items_signature
from .workflow import Workflow

# email id -> the correct lines: (SKUs it could be, quantity, unit). Several SKUs = a genuinely ambiguous line.
LABELS: dict[str, list[tuple[tuple[str, ...], float | None, str | None]]] = {
    "EML-014": [(("PF-1001",), 80, "yd"), (("PF-1002",), 20, "yd")],
    "EML-015": [(("PF-1004",), 12, "m")],
    "EML-016": [(("PF-1010",), 450, "yd"), (("PF-1015",), 120, "yd"), (("PF-1016",), 40, "yd")],
    "EML-017": [(("PF-1007",), 3, "yd")],
    "EML-018": [(("PF-1008",), 60, "yd"), (("PF-1009",), 30, "yd")],
    "EML-019": [(("PF-1014",), 25, "yd")],
    "EML-020": [(("PF-1012",), 2, "yd")],
    "EML-021": [(("PF-1001",), 90, "yd"), (("PF-1002",), 20, "yd")],
    "EML-022": [(("PF-1015",), 60, "yd"), (("PF-1010",), 60, "yd")],   # "sixty yards ... the same of the white"
    "EML-023": [(("PF-1006", "PF-1007"), 10, "yd")],                   # "the linen": two colorways fit
    "EML-024": [(("PF-1017",), None, None)],                           # no quantity given
    "EML-025": [(("PF-1013",), 30, "yd")],
    "EML-026": [(("PF-1005",), 20, "yd")],
}


def expected(rid: str) -> set:
    return {(tuple(sorted(skus)), float(q) if q is not None else None, u) for skus, q, u in LABELS[rid]}


def score(reader, emails: list[dict]) -> dict:
    rows, t0 = [], time.perf_counter()
    for r in emails:
        try:
            got = items_signature(reader.extract(r))
        except Exception as e:  # counted as wrong, and shown
            got = {("error", str(e)[:60])}
        want = expected(r["id"])
        rows.append({"id": r["id"], "ok": got == want, "lines_ok": len(got & want), "lines": len(want),
                     "got": got, "want": want})
    secs = time.perf_counter() - t0
    return {"rows": rows, "emails_ok": sum(r["ok"] for r in rows), "emails": len(rows),
            "lines_ok": sum(r["lines_ok"] for r in rows), "lines": sum(r["lines"] for r in rows),
            "secs_per_email": secs / max(len(rows), 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", action="store_true", help="evaluate the rules reader only")
    a = ap.parse_args()
    w = Workflow(mode="rules")
    emails = [r for r in w.inbox if r["id"] in LABELS]
    catalog = w.erp.items()
    readers = [("rules", RuleExtractor(catalog))]
    if not a.rules:
        try:
            readers.append(("claude", LLMExtractor(catalog)))
        except Exception as e:
            print(f"(Claude skipped: {e})")
    results = {}
    for name, reader in readers:
        res = results[name] = score(reader, emails)
        print(f"{name:7} {res['emails_ok']}/{res['emails']} emails exactly right, "
              f"{res['lines_ok']}/{res['lines']} lines, {res['secs_per_email']:.2f} s per email")
        for r in res["rows"]:
            if not r["ok"]:
                print(f"        {r['id']}: got {sorted(r['got'])}, expected {sorted(r['want'])}")
    if len(results) == 2:
        both = sum(a["ok"] or b["ok"] for a, b in zip(results["rules"]["rows"], results["claude"]["rows"], strict=True))
        agree = sum(a["got"] == b["got"] for a, b in zip(results["rules"]["rows"], results["claude"]["rows"],
                                                         strict=True))
        print(f"agree   {agree}/{len(emails)} emails (any disagreement goes to a rep); "
              f"at least one reader right on {both}/{len(emails)}")


if __name__ == "__main__":
    main()
