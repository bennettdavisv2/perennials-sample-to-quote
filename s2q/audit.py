"""Audit log shared by all adapters.

Every call that would hit a real system is recorded with the API call it maps to,
so the PoC doubles as an integration spec for engineering.
"""
from __future__ import annotations

from datetime import datetime


class AuditLog:
    def __init__(self):
        self.events: list[dict] = []
        self.current_request: str | None = None
        self.clock: datetime | None = None  # simulated "now" = time the request was received

    def record(self, system: str, action: str, detail: str, real_api: str = ""):
        self.events.append({
            "seq": len(self.events) + 1,
            "sim_time": self.clock.strftime("%Y-%m-%d %H:%M") if self.clock else "",
            "request": self.current_request or "",
            "system": system,
            "action": action,
            "detail": detail,
            "maps_to": real_api,
        })
