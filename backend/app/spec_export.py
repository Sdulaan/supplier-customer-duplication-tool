"""Excel report of a spec_model run, laid out like the Inventory Parts Scan export:
Overview | Duplicate Group Details | Group Details | Duplicate Records | Technical Reference."""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

NAVY, SLATE, GREEN, PALE_BLUE, PALE_GREY, PALE_YELLOW, PALE_GREEN = "1F4E78", "5B7894", "548235", "EAF3F8", "F3F5F7", "FFF2CC", "C6EFCE"
INK = "243746"
THIN = Side(style="thin", color="BFC9D1")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GROUP_SHADES = ("FFFFFF", PALE_BLUE)

ACTION = {1: "Strong matching evidence was found. Confirm the records are one supplier, then keep the survivor and archive / expire the others.",
          2: "Likely duplicate. A Data Steward should compare the records and confirm or reject the match.",
          3: "Functional split or hierarchy (withholding-tax, self-billing or parent / payee setup). Finance should review before any consolidation; do not auto-merge.",
          4: "Low confidence. Logged for passive monitoring; review only if other evidence appears."}
TIER_LABEL = {1: "Auto-Confirm Duplicate", 2: "High-Probability Steward Review", 3: "Functional Split / Hierarchy", 4: "Low Confidence Watchlist"}
RULE_ROWS = [
    ("A01", "Deterministic tax / registration anchor", "Association No, Fiscal No, Supplier Utr, Second Tin, Certified Email, Einvoice Receiver Code, Ext Source Supplier Id", "Exact normalized match that passes the entropy filter (length 5+, not sequential, not repeating, not TEST / NONE) and is not shared by more than 5 suppliers", "+55"),
    ("A02", "Cross-reference & EDI routing anchor", "Suppliers Own Id, Customer No, Our Customer No, EDI / E-Invoice message address", "Exact match on the same filtered basis", "+45"),
    ("N01", "Normalized entity name similarity", "Name, Vendor Name", "Legal suffixes and WHT / self-billing tags removed. Exact or token Jaro-Winkler 0.95+: 40; 0.85-0.94: 28; phonetic or acronym: 18", "+40"),
    ("L01", "Physical address & GLN match", "Address1, Address2, City, Zip Code, Country Db, Ean Location", "Same country. Exact Address1 + city / zip: 30; GLN: 25; fuzzy street 0.85+ with same city / zip: 20; city + zip only (name 18+): 10", "+30"),
    ("C01", "Communication method overlap", "Comm Method Value, Method Id Db, Name", "Same phone (last 8 digits) or email: 30; shared corporate email domain or contact name: 15", "+30"),
    ("C02", "Linked contact person overlap", "Person Id", "Linked to 3 or fewer suppliers: 15; 4-6: 5; more than 6: 0", "+15"),
    ("B01", "Operational context booster", "Buyer Code, Supp Grp, Currency Code", "Only when A01+A02+N01+L01+C01 is 20+ : same country, currency and buyer / supplier group", "+5"),
    ("P01", "Hierarchy, branch & functional split", "Other Payee Identity, Invoicing Supplier, Report And Withhold Db, Supplier Branch, Name", "Pointer between the two suppliers: LINKED HIERARCHY; WHT / self-billing tag or differing withholding setup: WHT FUNCTIONAL SPLIT; distinct branches: -25", "-25 / tag"),
]
SURVIVOR_ROWS = [("Party category", "Supplier Category Db = SUPPLIER", "+25"), ("Invoice & approval", "Active and not expired (blocked or expired: -30)", "+20"),
                 ("Payment ledger", "Present and not blocked for payment", "+15"), ("Purchasing maturity", "ORDINARY +15, QUICK +5", "+15"),
                 ("Master data richness", "Association No, Address1 + City, Phone / Email (5 each)", "+15"), ("SRM present", "Present in SrmSuppInfo", "+5"),
                 ("Seniority", "Earliest Creation Date and clean Supplier Id", "+5")]


def band(score: int, tier: int) -> str:
    if tier == 3:
        return "Functional Split"
    return "High Match" if score >= 80 else "Moderate Match" if score >= 60 else "Borderline Match"


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _put(ws, ref: str, value, *, bold=False, color=INK, fill=None, size=None, align="left", wrap=True, valign="center", border=True):
    c = ws[ref]
    c.value = value
    c.font = Font(bold=bold, color=color, size=size or 11)
    if fill:
        c.fill = _fill(fill)
    c.alignment = Alignment(horizontal=align, vertical=valign, wrap_text=wrap)
    if border:
        c.border = BOX
    return c


def _merge(ws, rng: str, value=None, **kw):
    first = rng.split(":")[0]
    ws.merge_cells(rng)
    _put(ws, first, value, **kw)
    for row in ws[rng]:
        for c in row:
            c.border = BOX
            if kw.get("fill"):
                c.fill = _fill(kw["fill"])


def _table_header(ws, headers: list[str], green: set[str] = frozenset()):
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _fill(GREEN if c.value in green else NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
    ws.row_dimensions[1].height = 30


def _widths(ws, widths: list[int]):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _records(g: dict) -> list[dict]:
    return g["records"]


def _conditions_text(result: dict) -> str:
    from .spec_model import CONDITIONS
    chosen = result["stats"].get("conditions") or list(CONDITIONS)
    return "\n".join(["Supplier name (always)"] + [CONDITIONS[c][1] for c in CONDITIONS if c in chosen])


def _noun(result: dict) -> str:
    return result.get("entity") or "supplier"


def _overview(wb: Workbook, result: dict, now: datetime, decisions: dict) -> None:
    ws = wb.active
    ws.title = "Overview"
    st = result["stats"]
    groups = result["groups"]
    by = st["byTier"]
    _widths(ws, [14] * 8)
    _merge(ws, "A1:H2", f"{_noun(result).title()} Duplicate Scan", bold=True, color="FFFFFF", fill=NAVY, size=20, align="center")
    _merge(ws, "A3:H3", f"IFS {_noun(result)} master: rule-scored duplicate groups", color="FFFFFF", fill=SLATE, align="center")
    _merge(ws, "A5:H5", "SCAN INFORMATION", bold=True, color="FFFFFF", fill=NAVY)
    _merge(ws, "A6:D6", "Scan Date", bold=True, color="FFFFFF", fill=SLATE)
    _merge(ws, "E6:H6", f"{_noun(result).title()}s Analysed", bold=True, color="FFFFFF", fill=SLATE)
    _merge(ws, "A7:D8", now.strftime("%d %b %Y, %H:%M"), bold=True, size=12, fill="FFFFFF")
    _merge(ws, "E7:H8", st["eligible"], bold=True, size=12, fill="FFFFFF")
    _merge(ws, "A10:D10", "Duplicate-checking Conditions", bold=True, color="FFFFFF", fill=SLATE)
    _merge(ws, "E10:H10", "Excluded From Matching", bold=True, color="FFFFFF", fill=SLATE)
    _merge(ws, "A11:D12", _conditions_text(result), fill="FFFFFF")
    ex = st["excluded"]
    _merge(ws, "E11:H12", f"Template: {ex['template']}\nOne-time: {ex['oneTime']}\nInternal (inter-site): {ex['internal']}", fill="FFFFFF")
    ws.row_dimensions[11].height = ws.row_dimensions[12].height = 36

    _merge(ws, "A14:H14", "COLUMN COLOUR KEY", bold=True, color="FFFFFF", fill=NAVY)
    _merge(ws, "A15:B15", "Green", bold=True, color="FFFFFF", fill=GREEN, align="center")
    _merge(ws, "C15:H15", "Duplicate-checking condition columns: Supplier Id, Name, Country, Association No, Address, Phone / Email. These are compared when candidate pairs are generated.", fill="FFFFFF")
    _merge(ws, "A16:B16", "Blue", bold=True, color="FFFFFF", fill=NAVY, align="center")
    _merge(ws, "C16:H16", "All other columns: group details, scoring, survivor and review columns.", fill="FFFFFF")
    _merge(ws, "A17:B17", "Shading", bold=True, fill=PALE_BLUE, align="center")
    _merge(ws, "C17:H17", "Groups alternate between white and light blue on Duplicate Group Details so each group reads as one block.", fill="FFFFFF")
    for r in (15, 16):
        ws.row_dimensions[r].height = 36

    _merge(ws, "A18:H18", "FINDINGS AT A GLANCE", bold=True, color="FFFFFF", fill=NAVY)
    dup = [g for g in groups if g["lane"] == "dup"]
    _merge(ws, "A19:B19", "Duplicate Groups", bold=True, color="FFFFFF", fill=NAVY, align="center")
    _merge(ws, "C19:E19", "Tier 1 Auto-Confirm", bold=True, color="FFFFFF", fill=NAVY, align="center")
    _merge(ws, "F19:H19", "Tier 2 Steward Review", bold=True, color="FFFFFF", fill=NAVY, align="center")
    _merge(ws, "A20:B21", len(dup), bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")
    _merge(ws, "C20:E21", by.get("1", 0), bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")
    _merge(ws, "F20:H21", by.get("2", 0), bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")
    _merge(ws, "A23:D23", "Records in Duplicate Groups", bold=True, color="FFFFFF", fill=NAVY, align="center")
    _merge(ws, "E23:H23", "Records Outside Duplicate Groups", bold=True, color="FFFFFF", fill=NAVY, align="center")
    inside = len({r["id"] for g in dup for r in _records(g)})
    _merge(ws, "A24:D25", inside, bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")
    _merge(ws, "E24:H25", max(st["eligible"] - inside, 0), bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")

    _merge(ws, "A27:H27", "REVIEW QUEUES", bold=True, color="FFFFFF", fill=NAVY)
    _merge(ws, "A28:D28", "Functional Split / Hierarchy (Tier 3)", bold=True, color="FFFFFF", fill=SLATE, align="center")
    _merge(ws, "E28:H28", "Audit Watchlist (Tier 4)", bold=True, color="FFFFFF", fill=SLATE, align="center")
    _merge(ws, "A29:D30", by.get("3", 0), bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")
    _merge(ws, "E29:H30", by.get("4", 0), bold=True, color=NAVY, fill=PALE_BLUE, size=18, align="center")
    _merge(ws, "A32:H33", "Scores come from a deterministic rule matrix (see Technical Reference) and are not a probability of duplication. "
           "Tier 3 groups must not be auto-merged. Fill in Human Decision / Human Comment as groups are reviewed.", bold=True, fill=PALE_YELLOW)
    _merge(ws, "A35:H35", "HOW TO USE THIS WORKBOOK", bold=True, color="FFFFFF", fill=NAVY)
    _merge(ws, "A36:H38", "1. Open Duplicate Group Details and inspect each group; the SURVIVOR row is the supplier to keep.\n"
           "2. Record your decision in Human Decision / Human Comment.\n3. Use Duplicate Records for a flat, filterable list of every supplier in a group.", fill="FFFFFF")
    _merge(ws, "A40:H40", "REPORT DETAILS / TECHNICAL FOOTER", bold=True, color="FFFFFF", fill=SLATE, size=10)
    rows = [(f"{_noun(result).title()}s Loaded", st["suppliers"]), ("Candidate Pairs", st["candidatePairs"]), ("Scored Pairs", st["scoredPairs"]),
            ("Groups", st["groups"]), ("Groups With a Human Decision", len(decisions)), ("ML Layer", "Off" if not result.get("model") else f"On, CV AUC {result['model'].get('cvAuc')}")]
    for i, (k, v) in enumerate(rows, 41):
        _merge(ws, f"A{i}:B{i}", k, bold=True, color=NAVY, fill=PALE_GREY, size=11)
        _merge(ws, f"C{i}:H{i}", v, bold=True, fill="FFFFFF")
    _merge(ws, "A48:H48", "DETERMINISTIC MATCH STRENGTH", bold=True, color="FFFFFF", fill=NAVY)
    counts = {"High": 0, "Moderate": 0, "Borderline": 0}
    for g in dup:
        counts["High" if g["score"] >= 80 else "Moderate" if g["score"] >= 60 else "Borderline"] += 1
    counts["Borderline"] += by.get("4", 0)
    for i, (label, key) in enumerate((("High Match (80-100)", "High"), ("Moderate Match (60-<80)", "Moderate"), ("Borderline Match (40-<60)", "Borderline")), 49):
        _merge(ws, f"A{i}:F{i}", label, bold=True, fill="FFFFFF")
        _merge(ws, f"G{i}:H{i}", counts[key], bold=True, color=NAVY, fill="FFFFFF", size=12, align="right")
    _merge(ws, "A53:H55", "Match Strength summarizes deterministic comparison evidence. It is not a probability of duplication and does not replace human review.",
           color=SLATE, fill=PALE_GREY, size=9)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A6"


def _group_details(wb: Workbook, groups: list[dict], decisions: dict) -> None:
    ws = wb.create_sheet("Duplicate Group Details")
    green = {"Supplier Id", "Name", "Country", "Association No", "Address", "City", "Phones", "Emails"}
    headers = ["Group", "Match Strength", "Match Band", "Tier", "Tags", "Member Number", "Supplier Id", "Name", "Country", "Category", "Created",
               "Association No", "Address", "City", "Phones", "Emails", "Survivor", "Survivor Score", "Review Consideration",
               "Relationship Evidence", "Supplier Pair", "Pair Match Score", "Rule Points", "ML Probability", "Human Decision", "Human Comment"]
    _table_header(ws, headers, green)
    _widths(ws, [12, 13, 16, 24, 22, 11, 18, 32, 9, 12, 12, 18, 30, 16, 20, 30, 11, 11, 44, 50, 34, 12, 30, 12, 26, 32])
    merged_cols = [1, 2, 3, 4, 5, 19, 25, 26]  # group-level columns, merged down the group's rows
    row = 2
    for n, g in enumerate(groups):
        recs, pairs = _records(g), g["pairs"]
        span = max(len(recs), len(pairs))
        shade = GROUP_SHADES[n % 2]
        for i in range(span):
            r = row + i
            for col in range(1, len(headers) + 1):
                c = ws.cell(r, col)
                c.fill, c.border = _fill(shade), BOX
                c.alignment = Alignment(vertical="top", wrap_text=True)
            if i < len(recs):
                rec = recs[i]
                vals = {6: i + 1, 7: rec["id"], 8: rec["name"], 9: rec["country"], 10: rec["category"], 11: rec["created"],
                        12: ", ".join(rec["anchors"].get("Association No", [])), 13: rec["address"], 14: rec["city"],
                        15: ", ".join(rec["phones"]), 16: ", ".join(rec["emails"]),
                        17: "SURVIVOR" if rec["id"] == g.get("survivor") else "", 18: rec["survivorScore"]}
                for col, v in vals.items():
                    ws.cell(r, col).value = v
                if vals[17]:
                    ws.cell(r, 17).fill, ws.cell(r, 17).font = _fill(PALE_GREEN), Font(bold=True, color="1E7145")
            if i < len(pairs):
                p = pairs[i]
                evid = " | ".join(x for x in [*p["details"]["A01"], *p["details"]["A02"], p["details"]["N01"], p["details"]["L01"], *p["details"]["C"]] if x)
                ws.cell(r, 20).value = evid
                ws.cell(r, 21).value = f"{p['a']} ↔ {p['b']}"
                ws.cell(r, 22).value = p["score"]
                ws.cell(r, 23).value = " · ".join(f"{k} {v:+g}" for k, v in p["rules"].items())
                ws.cell(r, 24).value = None if p["ml"] is None else f"{p['ml'] * 100:.0f}%"
        d = decisions.get(g["id"], {})
        values = {25: d.get("decision"), 26: d.get("comment"), 1: g["id"], 2: g["score"], 3: band(g["score"], g["tier"]), 4: f"Tier {g['tier']} · {TIER_LABEL[g['tier']]}",
                  5: ", ".join(g["tags"]), 19: ACTION[g["tier"]]}
        for col, v in values.items():
            ws.cell(row, col).value = v
        ws.cell(row, 3).fill = _fill(PALE_GREEN if g["tier"] in (1, 2) else PALE_YELLOW)
        for col in (1, 2, 3):
            ws.cell(row, col).font = Font(bold=True, color=NAVY)
        if span > 1:
            for col in merged_cols:
                ws.merge_cells(start_row=row, start_column=col, end_row=row + span - 1, end_column=col)
        for col in merged_cols:
            ws.cell(row, col).alignment = Alignment(vertical="center", wrap_text=True, horizontal="center" if col <= 3 else "left")
        for i in range(span):
            ws.row_dimensions[row + i].height = 48
        row += span
    ws.freeze_panes = "G2"


def _group_summary(wb: Workbook, groups: list[dict], decisions: dict) -> None:
    ws = wb.create_sheet("Group Details")
    _table_header(ws, ["Group", "Evidence Tier", "Match Strength", "Match Band", "Members", "Countries", "Survivor", "Tags", "Review Consideration",
                       "Human Decision", "Human Comment"])
    _widths(ws, [12, 32, 14, 16, 10, 12, 20, 24, 60, 26, 32])
    for g in groups:
        recs = _records(g)
        ws.append([g["id"], f"Tier {g['tier']} · {TIER_LABEL[g['tier']]}", g["score"], band(g["score"], g["tier"]), len(recs),
                   ", ".join(sorted({r["country"] for r in recs if r["country"]})), g.get("survivor") or "", ", ".join(g["tags"]),
                   ACTION[g["tier"]], decisions.get(g["id"], {}).get("decision"), decisions.get(g["id"], {}).get("comment")])
        r = ws.max_row
        ws.row_dimensions[r].height = 40
        for c in ws[r]:
            c.border, c.alignment = BOX, Alignment(vertical="center", wrap_text=True)
        tier_cell = ws.cell(r, 2)
        tier_cell.fill = _fill(PALE_GREEN if g["tier"] in (1, 2) else PALE_YELLOW)
        tier_cell.font = Font(bold=True, color="1E7145")
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions


def _records_sheet(wb: Workbook, groups: list[dict], decisions: dict) -> None:
    ws = wb.create_sheet("Duplicate Records")
    green = {"Tier", "Survivor", "Human Decision", "Human Comment"}
    _table_header(ws, ["Group", "Member Number", "Tier", "Survivor", "Human Decision", "Human Comment", "Supplier Id", "Name", "Country", "Category",
                       "Created", "Association No", "Address", "City", "Phones", "Emails", "Survivor Score"], green)
    _widths(ws, [12, 10, 24, 12, 26, 32, 18, 32, 9, 12, 12, 18, 30, 16, 20, 30, 11])
    for g in groups:
        for i, r in enumerate(_records(g), 1):
            ws.append([g["id"], i, f"Tier {g['tier']}", "SURVIVOR" if r["id"] == g.get("survivor") else "", decisions.get(g["id"], {}).get("decision"), decisions.get(g["id"], {}).get("comment"), r["id"], r["name"], r["country"],
                       r["category"], r["created"], ", ".join(r["anchors"].get("Association No", [])), r["address"], r["city"],
                       ", ".join(r["phones"]), ", ".join(r["emails"]), r["survivorScore"]])
            for c in ws[ws.max_row]:
                c.border = BOX
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _technical(wb: Workbook) -> None:
    ws = wb.create_sheet("Technical Reference")
    _widths(ws, [16, 38, 52, 70, 12])
    _put(ws, "A1", "WEIGHTED SCORING MATRIX", bold=True, color="FFFFFF", fill=NAVY)
    ws.merge_cells("A1:E1")
    for i, h in enumerate(["Rule", "Signal", "Source columns", "Matching logic", "Max points"], 1):
        _put(ws, f"{get_column_letter(i)}2", h, bold=True, color="FFFFFF", fill=SLATE)
    for r in RULE_ROWS:
        ws.append(list(r))
        for c in ws[ws.max_row]:
            c.border, c.alignment = BOX, Alignment(vertical="top", wrap_text=True)
        ws.cell(ws.max_row, 1).font = Font(bold=True, color=NAVY)
        ws.cell(ws.max_row, 1).fill = _fill(PALE_GREY)
    ws.append([])
    start = ws.max_row + 1
    _put(ws, f"A{start}", "ACTION TIERS", bold=True, color="FFFFFF", fill=NAVY)
    ws.merge_cells(f"A{start}:E{start}")
    for t, text in ((1, "Score 80+. Auto-confirm duplicate."), (2, "Score 60-79. Data Steward review."),
                    (3, "Tagged LINKED HIERARCHY or WHT FUNCTIONAL SPLIT (score 40+). Finance review."), (4, "Score 40-59. Audit watchlist.")):
        ws.append([f"Tier {t}", TIER_LABEL[t], text])
        for c in ws[ws.max_row]:
            c.border, c.alignment = BOX, Alignment(vertical="top", wrap_text=True)
    ws.append([])
    start = ws.max_row + 1
    _put(ws, f"A{start}", "SURVIVOR SCORECARD (100 points)", bold=True, color="FFFFFF", fill=NAVY)
    ws.merge_cells(f"A{start}:E{start}")
    for name, rule, pts in SURVIVOR_ROWS:
        ws.append([name, rule, None, None, pts])
        for c in ws[ws.max_row]:
            c.border, c.alignment = BOX, Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A3"


def report_filename(now: datetime | None = None, entity: str = "supplier") -> str:
    return f"{entity.title()} Duplicates Scan_{(now or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"


def build_report(result: dict, now: datetime | None = None, decisions: dict | None = None) -> bytes:
    now = now or datetime.now()
    groups = result["groups"]
    decisions = decisions or {}
    wb = Workbook()
    _overview(wb, result, now, decisions)
    _group_details(wb, groups, decisions)
    _group_summary(wb, groups, decisions)
    _records_sheet(wb, groups, decisions)
    _technical(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
