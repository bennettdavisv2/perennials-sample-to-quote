"""Generate docs/diagrams/new-flow.svg: the new sample-to-quote flow in system lanes.

Hand-placed layout (Mermaid can't keep lanes fixed without crossing arrows).
Run:  python docs/diagrams/new_flow.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

P, BOX_H = 52, 34                  # row pitch, box height
R = {i: 66 + (i - 1) * P for i in range(1, 13)}   # row centers 1..12
W, H = 900, R[12] + BOX_H // 2 + 70
BOX_W = 140
LANES = [  # (title, x0, x1)
    ("Website / Email", 10, 190),
    ("Integration service (AWS)", 200, 410),
    ("CRM (Salesforce)", 420, 740),
    ("ERP (NetSuite)", 750, 890),
]
X = {"web": 100, "int": 305, "crm_a": 495, "crm_b": 665, "erp": 815}
STYLE = {  # fill, stroke
    "input": ("#ffffff", "#667085"),
    "auto": ("#e6f4ea", "#1e8e3e"),
    "decision": ("#e6f4ea", "#1e8e3e"),
    "person": ("#fff4e5", "#d97706"),
    "result": ("#e8f0fe", "#1a73e8"),
}

out: list[str] = []


def text(x, y, s, size=13, weight="normal", anchor="middle", fill="#1d2939"):
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
               f'fill="{fill}">{escape(s)}</text>')


def box(col, row, label, kind, w=BOX_W):
    x, y = X[col], R[row]
    fill, stroke = STYLE[kind]
    rx = BOX_H / 2 if kind == "decision" else 5
    out.append(f'<rect x="{x - w / 2}" y="{y - BOX_H / 2}" width="{w}" height="{BOX_H}" rx="{rx}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    lines = label.split("\n")
    for i, line in enumerate(lines):
        text(x, y + 4.5 + (i - (len(lines) - 1) / 2) * 14, line, size=12.5,
             weight="600" if kind == "decision" else "normal")


def arrow(points, label=None, at=None, anchor="start"):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    out.append(f'<path d="{d}" fill="none" stroke="#475467" stroke-width="1.4" marker-end="url(#a)"/>')
    if label:
        lx, ly = at
        text(lx, ly, label, size=11, anchor=anchor, fill="#475467")


out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">')
out.append('<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#475467"/></marker></defs>')
out.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
for title, x0, x1 in LANES:
    out.append(f'<rect x="{x0}" y="10" width="{x1 - x0}" height="{H - 58}" rx="8" fill="#f8f9fb" stroke="#d0d5dd"/>')
    text((x0 + x1) / 2, 30, title, size=13.5, weight="700")

# ---- boxes (column, row) ----
box("web", 1, "Sample order", "input")
box("web", 2, "Quote form", "input")
box("web", 3, "Quote email", "input")
box("int", 2, "Known customer?", "decision", w=150)
box("int", 3, "AI reads the email", "auto", w=150)
box("int", 4, "Spam dropped", "result", w=150)
box("crm_a", 4, "Closed, owner told", "result", w=130)
box("crm_a", 5, "Rep qualifies", "person", w=130)
box("crm_b", 5, "Rejected", "result", w=130)
box("crm_a", 6, "Lead → Opportunity", "auto", w=130)
box("int", 7, "Up to 10 samples?", "decision", w=150)
box("erp", 7, "Sample order", "result", w=130)
box("int", 8, "Quote clear?", "decision", w=150)
box("crm_a", 8, "Drafted question", "result", w=130)
box("erp", 9, "Price + dye lot", "auto", w=130)
box("erp", 10, "Fabric hold, 14 days", "auto", w=130)
box("int", 11, "Flags or over $20k?", "decision", w=150)
box("crm_b", 11, "Quote sent", "result", w=130)
box("crm_a", 12, "Rep reviews", "person", w=130)

# ---- arrows (no crossings) ----
h = BOX_H // 2
gap = P - BOX_H
arrow([(170, R[1]), (305, R[1]), (305, R[2] - h)])                         # sample order -> known customer
arrow([(170, R[2]), (230, R[2])])                                          # quote form -> known customer
arrow([(170, R[3]), (230, R[3])])                                          # quote email -> AI
arrow([(305, R[3] - h), (305, R[2] + h)])                                  # AI -> known customer
arrow([(380, R[2] - 7), (495, R[2] - 7), (495, R[4] - h)], "Do Not Sell", (501, R[3] + 4))
arrow([(380, R[2]), (410, R[2]), (410, R[5]), (430, R[5])], "new or non-trade", (394, R[5] - 4), "end")
arrow([(380, R[2] + 7), (400, R[2] + 7), (400, R[6] - 8), (430, R[6] - 8)], "trade account", (394, R[6] - 12), "end")
arrow([(380, R[2] + 14), (390, R[2] + 14), (390, R[4]), (380, R[4])], "spam", (386, R[4] - h - 4), "end")
arrow([(560, R[5]), (600, R[5])], "reject", (580, R[5] - 6), "middle")
arrow([(495, R[5] + h), (495, R[6] - h)], "qualify", (501, R[5] + h + gap / 2 + 4))
arrow([(430, R[6] + 1), (212, R[6] + 1), (212, R[8]), (230, R[8])], "quote", (232, R[6] - 3))
arrow([(430, R[6] + 10), (222, R[6] + 10), (222, R[7]), (230, R[7])], "sample", (232, R[6] + 23))
arrow([(380, R[7]), (750, R[7])], "yes", (580, R[7] - 6), "middle")
arrow([(230, R[7] + 8), (198, R[7] + 8), (198, R[12]), (430, R[12])], "over 10", (204, R[12] - 6))
arrow([(380, R[8]), (430, R[8])], "unclear", (405, R[8] - 6), "middle")
arrow([(305, R[8] + h), (305, R[9]), (750, R[9])], "yes · a revision replaces the old quote and its hold", (311, R[8] + h + 13))
arrow([(815, R[9] + h), (815, R[10] - h)])                                 # price -> hold (placed before review)
arrow([(815, R[10] + h), (815, R[10] + h + gap / 2), (305, R[10] + h + gap / 2), (305, R[11] - h)])  # hold -> flags
arrow([(380, R[11] - 6), (600, R[11] - 6)], "no", (590, R[11] - 11), "end")
arrow([(380, R[11] + 8), (470, R[11] + 8), (470, R[12] - h)], "yes", (476, R[11] + h + 12))

# ---- key ----
ky = H - 22
for i, (label, kind) in enumerate([("Customer input", "input"), ("Automated", "auto"),
                                   ("A person decides", "person"), ("Result", "result")]):
    fill, stroke = STYLE[kind]
    x = 140 + i * 170
    out.append(f'<rect x="{x}" y="{ky - 12}" width="22" height="16" rx="3" fill="{fill}" stroke="{stroke}"/>')
    text(x + 30, ky + 1, label, size=12.5, anchor="start")
out.append("</svg>")

Path(__file__).with_name("new-flow.svg").write_text("\n".join(out))
print("wrote", Path(__file__).with_name("new-flow.svg"))
