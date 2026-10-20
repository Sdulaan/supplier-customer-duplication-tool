"""Second data-collection path: IFS Quick Report exports (xlsx / csv) mapped into the same structure the API fetch
produces, plus the Excel export of that mapped structure (which can be re-imported as-is).

Each Quick Report is named <PREFIX><NN>_<Name> (SUP01_General, CUS04_Addresses, ...). The code is what ties a file
(or a sheet of a workbook) to a data set; see catalog().
"""
import csv
import io
import re
from datetime import date, datetime, time

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import ifs

PREFIX = {"supplier": "SUP", "customer": "CUS"}
CODE_RE = re.compile(r"^\s*([A-Za-z]{3})\s*[-_ ]?\s*(\d{2})")

# Columns that are IFS plumbing, not business data.
HIDDEN = {"luname", "keyref", "objgrants", "objid", "objversion", "objkey", "rowkey", "objstate", "objevents", "rowversion"}
# Quick Report column names that differ from the API property of the same meaning.
ALIASES = {"VendorNo": "SupplierId", "CustomerNo": "CustomerId", "AddrNo": "AddressId"}


def _paths(tree: dict, prefix: tuple = ()) -> list[tuple]:
    out: list[tuple] = []
    for name, children in tree.items():
        out.append(prefix + (name,))
        out += _paths(children, prefix + (name,))
    return out


def catalog(entity: str) -> list[dict]:
    """Ordered data sets of an entity with the report name that feeds each one."""
    spec = ifs.ENTITIES[entity]
    prefix = PREFIX[entity]
    rows = [{"code": f"{prefix}01", "stage": "general", "label": "General", "collection": spec["set"]}]
    for i, path in enumerate(_paths(spec["relations"]), start=2):
        rows.append({"code": f"{prefix}{i:02d}", "stage": "/".join(path), "label": path[-1], "collection": "/".join(path)})
    for r in rows:
        r["name"] = f"{r['code']}_{r['label']}"
    return rows


def is_hidden(key: str) -> bool:
    return key.startswith("@odata") or key.startswith("_") or key.lower() in HIDDEN


def pascal(header: str) -> str:
    """'Supplier Id' / SUPPLIER_ID -> SupplierId; headers that are already PascalCase are kept."""
    h = str(header).strip()
    if not h:
        return ""
    if re.search(r"[\s_]", h) or h.isupper() or h.islower():
        h = "".join(p.capitalize() if (p.isupper() or p.islower()) else p[:1].upper() + p[1:] for p in re.split(r"[_\s]+", h) if p)
    return ALIASES.get(h, h)


def _clean(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        # keep the text exactly as IFS has it: IDs that differ only by a leading space are different records
        return value if value.strip() else None
    return value


class Records(list):
    """Records plus the number of columns in the source sheet (empty columns included)."""

    ncols = 0


def _records(rows) -> list[dict]:
    rows = iter(rows)
    headers = next(rows, None)
    if not headers:
        return Records()
    keys = [pascal(h) if h is not None else "" for h in headers]
    drop = [not k or is_hidden(k) for k in keys]
    out = Records()
    out.ncols = sum(1 for d in drop if not d)
    for row in rows:
        rec = {}
        for key, skip, value in zip(keys, drop, row):
            value = _clean(value)
            if not skip and value is not None:
                rec[key] = value
        if rec:
            out.append(rec)
    return out


def _sheets(filename: str, content: bytes) -> list[tuple[str, list[dict]]]:
    """[(name used to find the report code, records)] for one uploaded file."""
    if filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        return [(filename, _records(csv.reader(io.StringIO(text), dialect)))]
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheets = [(ws.title, _records(ws.iter_rows(values_only=True))) for ws in wb.worksheets]
    # A workbook is a multi-report file when its sheet names carry report codes; otherwise it is one report named by the file.
    if len(sheets) > 1 and all(CODE_RE.match(t) for t, _ in sheets):
        return sheets
    first = next((s for s in sheets if s[1]), sheets[0])
    return [(filename, first[1])]


# What each kind of report looks like, so files with generic names (QuickReportOverview_<timestamp>.xlsx) can be
# recognised from their columns. Role -> report code per entity.
ROLE_CODES = {
    "supplier": {"general": "SUP01", "address": "SUP02", "addrtype": "SUP03", "comm": "SUP04", "contact": "SUP05",
                 "msg": "SUP10", "invoice": "SUP11", "pay": "SUP12", "purchase": "SUP14", "srm": "SUP15"},
    "customer": {"general": "CUS01", "address": "CUS02", "addrtype": "CUS03", "invoice": "CUS08", "pay": "CUS09",
                 "custord": "CUS11"},
}


def guess_role(columns: set[str], owner: str) -> str | None:
    c = {re.sub(r"[^a-z0-9]", "", k.lower()) for k in columns}
    own = owner.lower()
    if c & {"vendorno", "vendorname", "buyercode", "suppgrp"}:
        return "purchase"
    if "commid" in c:
        return "comm"
    if own in c and "personid" in c:
        return "contact"
    if own in c and ("mediacode" in c or "messageclass" in c):
        return "msg"
    if own in c and "addresstypecode" in c:
        return "addrtype"
    if {"company", "identity"} <= c:
        if c & {"payterm", "paytermid", "invoicefee", "groupid", "defauthorizer"}:
            return "invoice"
        if c & {"priority", "blockedforpayment", "otherpayeeidentity", "paymentdelay"}:
            return "pay"
    if own in c and "addressid" in c and c & {"eanlocation", "address"}:
        return "address"
    if own in c and c & {"name", "creationdate"} and "addressid" not in c and c & {"associationno", "party", "defaultdomain"}:
        return "general"
    if own in c and c & {"turnover", "segmentcode", "geographycode", "mainrepresentative"}:
        return "srm"
    if own in c and "creditlimit" in c:
        return "custord"
    return None


def parse_uploads(entity: str, files: list[tuple[str, bytes]], assignments: dict | None = None, strict_prefix: bool = False) -> dict:
    """Build the same {"entity", "stages"} result as the API fetch from uploaded Quick Report files.

    A file is tied to a data set by (1) an explicit assignment, (2) the report code in its name/sheet name
    (SUP01_General), or (3) its columns. When two files land on the same data set, the one with more columns wins.
    """
    assignments = assignments or {}
    cat = catalog(entity)
    by_code = {c["code"]: c for c in cat}
    owner = ifs.ENTITIES[entity]["key"]
    stages = {c["stage"]: {"collection": c["collection"], "records": [], "errors": []} for c in cat}
    chosen: dict[str, dict] = {}  # code -> best candidate
    unmatched = []
    for filename, content in files:
        try:
            sheets = _sheets(filename, content)
        except Exception as exc:  # unreadable workbook / csv
            unmatched.append({"file": filename, "reason": f"Could not read the file ({exc})."})
            continue
        for name, records in sheets:
            how = "assigned"
            code = (assignments.get(filename) or "").upper() or None
            if not code:
                m = CODE_RE.match(name.replace("\\", "/").split("/")[-1])
                if strict_prefix and m and m.group(1).upper() in PREFIX.values() and m.group(1).upper() != PREFIX[entity]:
                    continue  # a sheet of the other entity in a combined workbook
                code = f"{m.group(1).upper()}{m.group(2)}" if m else None
                how = "name"
            if code not in by_code:
                columns = {k for r in records[:50] for k in r}
                role = guess_role(columns, owner)
                code, how = ROLE_CODES[entity].get(role), "content"
            if code not in by_code:
                unmatched.append({"file": filename, "reason": "Could not tell which report this is. Pick the report for it in the list, or start the file name with its code (e.g. " + PREFIX[entity] + "01_General)."})
                continue
            width = getattr(records, "ncols", 0)
            rank = {"assigned": 2, "name": 1, "content": 0}[how]
            best = chosen.get(code)
            if best and (best["rank"], best["width"]) >= (rank, width):
                unmatched.append({"file": filename, "reason": f"Skipped: {best['file']} already fills {code} (same or more columns)."})
                continue
            if best:
                unmatched.append({"file": best["file"], "reason": f"Skipped: {filename} fills {code} with more columns."})
            chosen[code] = {"file": filename, "records": records, "how": how, "width": width, "rank": rank}
    report = []
    for code, item in chosen.items():
        stages[by_code[code]["stage"]]["records"] = item["records"]
        report.append({"code": code, "file": item["file"], "rows": len(item["records"]), "how": item["how"]})
    report.sort(key=lambda r: r["code"])
    return {"entity": entity, "source": "reports", "stages": stages, "report": report, "unmatched": unmatched}


def build_workbook(entity: str, result: dict) -> bytes:
    """Mapped Excel workbook: one sheet per data set (named by report code), headers = API property names."""
    root_key = f"_{ifs.ENTITIES[entity]['key']}"
    id_key = ifs.ENTITIES[entity]["key"]
    wb = Workbook()
    wb.remove(wb.active)
    head_fill = PatternFill("solid", fgColor="5B3FD6")
    for c in catalog(entity):
        stage = (result.get("stages") or {}).get(c["stage"])
        records = (stage or {}).get("records") or []
        if not records and c["stage"] != "general":
            continue
        columns: list[str] = []
        for r in records:
            for k in r:
                if not is_hidden(k) and k not in columns:
                    columns.append(k)
        if c["stage"] != "general" and id_key not in columns and "Identity" not in columns:
            columns.insert(0, id_key)  # keep every row tied to its supplier / customer
        ws = wb.create_sheet(c["name"][:31])
        ws.append(columns)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
        for r in records:
            row = []
            for k in columns:
                v = r.get(k, r.get(root_key) if k == id_key else None)
                row.append(v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
            ws.append(row)
        ws.freeze_panes = "A2"
        if columns and records:
            ws.auto_filter.ref = ws.dimensions
        for i, col in enumerate(columns, start=1):
            width = max([len(col)] + [len(str(r.get(col, ""))) for r in records[:200]])
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 50)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
