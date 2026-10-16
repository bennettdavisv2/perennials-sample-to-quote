"""Deterministic pricing. Lives behind the ERP adapter: the ERP owns price.

The LLM never produces a number that reaches a customer; it only proposes which
SKU and how many yards. Everything below is plain arithmetic that can be unit-tested
and reconciled against NetSuite price levels.
"""
from __future__ import annotations

import math

from .data import PricingConfig

M_TO_YD = 1.0936133


def to_yards(qty: float, unit: str | None) -> float:
    """Convert to yards, rounding up to the nearest 1/4 yard (fabric is cut in quarters)."""
    if unit in ("m", "meter", "meters", "metre", "metres"):
        qty = qty * M_TO_YD
    elif unit in ("ft", "foot", "feet"):  # the website quote form offers Yards / Feet / Meters
        qty = qty / 3
    return math.ceil(qty * 4 - 1e-9) / 4


def price_line(list_price: float, yards: float, is_trade: bool, cfg: PricingConfig) -> dict:
    base = cfg.trade_discount if is_trade else cfg.non_trade_discount
    vol = 0.0
    # Assumption: volume tiers are "on top of trade discount", so they apply to trade only,
    # and they stack additively (15% + 5% = 20% off list), not compounded.
    if is_trade:
        for min_yards, extra in cfg.volume_tiers:
            if yards >= min_yards:
                vol = extra
                break
    discount = base + vol
    unit_price = round(list_price * (1 - discount), 2)
    extended = round(unit_price * yards, 2)
    cut_fee = cfg.cut_fee if 0 < yards < cfg.cut_fee_under_yards else 0.0
    return {
        "list_price": list_price,
        "trade_discount": base,
        "volume_discount": vol,
        "total_discount": round(discount, 4),
        "unit_price": unit_price,
        "yards": yards,
        "extended": extended,
        "cut_fee": cut_fee,
        "line_total": round(extended + cut_fee, 2),
    }
