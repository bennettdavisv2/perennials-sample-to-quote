"""Customer-facing drafts. Templates on purpose: every number comes from the ERP pricing
result, never from free-form generation. (An LLM could polish tone later, with
numbers locked as placeholders.)"""
from __future__ import annotations


def _first(name):
    return (name or "there").split()[0]


def sample_confirmation(name, skus_desc, excluded, notes, opp_name):
    body = [f"Hi {_first(name)},", "", "Thanks for reaching out to Perennials."]
    if skus_desc:
        body += ["Your memo samples are on the way:", ""] + [f"  - {d}" for d in skus_desc]
    if excluded:
        body += ["", "We couldn't include:"] + [f"  - {d}" for d in excluded]
    if notes:
        body += ["", *notes]
    body += ["", f"We've noted this under '{opp_name}'. When you're ready for yardage, just reply with "
             "quantities and we'll send a quote.", "", "Best,", "Perennials Trade Team"]
    subj = "Your Perennials samples are on the way" if skus_desc else "Your Perennials sample request"
    return {"subject": subj, "body": "\n".join(body)}


def non_trade_reply(name, wildcard):
    body = [f"Hi {_first(name)},", "",
            "Thanks for your interest in Perennials! Complimentary memo samples are reserved for our design-trade "
            "partners (designers, architects, upholsterers and hospitality specifiers).",
            "",
            "You can still order individual samples on our website, or we can point you to a showroom or retailer near you.",
            ]
    if wildcard:
        body += ["", "Tell us a bit about your project (outdoor or indoor, colors you like) and we'll suggest a short list."]
    body += ["", "If you're working with a designer or are in the trade yourself, reply here and we'll set you up.",
             "", "Best,", "Perennials Customer Care"]
    return {"subject": "Your Perennials sample request", "body": "\n".join(body)}


def quote_email(name, quote, lines_desc, notes, valid_until, budgetary, trade=True):
    kind = "budgetary quote" if budgetary else "quote"
    body = [f"Hi {_first(name)},", "", f"Here is your {kind} {quote['id']}:", ""]
    for d in lines_desc:
        body.append(f"  {d}")
    body += ["", f"  Total: ${quote['total']:,.2f}  (excl. shipping and tax)", ""]
    if notes:
        body += ["Notes:"] + [f"  - {n}" for n in notes] + [""]
    body += [f"Pricing is valid until {valid_until:%B %d, %Y}."]
    if quote.get("reservation_id"):
        who = "your client signs off" if trade else "you're ready to order"
        body.append(f"We've placed a 14-day hold on the in-stock yardage so it's ready when {who}.")
    body += ["", "Best,", "Perennials Trade Team" if trade else "Perennials Customer Care"]
    return {"subject": f"Perennials {kind} {quote['id']}", "body": "\n".join(body)}


def clarifying_question(name, questions):
    """One email instead of a thread: the options and stock come from the ERP."""
    body = [f"Hi {_first(name)},", "", "Thanks for the quote request. One quick question so we can price it:", ""]
    body += [f"  - {q}" for q in questions]
    body += ["", "Reply with the color and we'll send the quote right away.", "", "Best,", "Perennials Trade Team"]
    return {"subject": "Quick question on your Perennials quote", "body": "\n".join(body)}


def sample_pick(name, items_desc, max_samples):
    """Too many (or 'everything'): ask once which ones to send first."""
    body = [f"Hi {_first(name)},", "", f"Thanks for your sample request. We can send up to {max_samples} memo samples "
            "per request so each one arrives quickly."]
    if items_desc:
        body += ["", f"You picked {len(items_desc)}:", ""] + [f"  - {d}" for d in items_desc]
        body += ["", f"Reply with the {max_samples} you'd like first and we'll ship them right away; the rest can "
                 "follow in a second shipment."]
    else:
        body += ["", "Tell us a little about the project (indoor or outdoor, colors, how the fabric will be used) and "
                 f"we'll pick the {max_samples} that fit best."]
    body += ["", "Best,", "Perennials Trade Team"]
    return {"subject": "Which Perennials samples should we send first?", "body": "\n".join(body)}
