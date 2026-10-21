"""Bridges between the data-collection paths (Quick Report files, IFS fetch) and the scan engines.

- Supplier scans run on the 10-table model (spec_model). Quick reports go straight in; an IFS fetch is mapped to the same tables.
- Customer scans run on the party-master engine (dedup) and its groups are reshaped to the supplier result shape so the same
  scan pages, history, decisions and Excel report work for both.
"""
import re
from collections import Counter

from . import dedup, reports


def _lower_keys(rec: dict) -> dict:
    return {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in rec.items() if v not in (None, "") and not k.startswith("@odata")}


def tables_from_fetched(result: dict) -> dict[str, list[dict]]:
    """Map the stages of an IFS supplier fetch onto the table roles of the 10-table model. Reports the projection does not
    expose (purchasing, payment ledger, invoicing, SRM, messaging) stay empty and are skipped by the scan."""
    tables: dict[str, list[dict]] = {}
    for path, stage in (result.get("stages") or {}).items():
        leaf = path.split("/")[-1].lower()
        role = ("general" if path == "general" else "addrtype" if leaf == "addresstypes" else "comm" if leaf == "addresscommunicationmethods"
                else "contact" if leaf == "supplierinfocontacts" else "address" if leaf == "supplierinfoaddresses" else None)
        if not role:
            continue
        for rec in stage.get("records", []):
            row = _lower_keys(rec)
            owner = rec.get("_SupplierId") or rec.get("SupplierId") or rec.get("Identity")
            if owner is None:
                continue
            row["supplierid"] = str(owner)
            if role == "comm":
                row["identity"] = str(owner)
                row.setdefault("methodiddb", str(rec.get("MethodIdDb") or rec.get("MethodId") or "").upper().replace("-", "_"))
            tables.setdefault(role, []).append(row)
    return tables


def customer_scan(results: list[dict]) -> dict:
    """Run the party-master engine on customer data and reshape its output like a supplier scan result."""
    out = dedup.find_duplicates(results)
    tier = {"HIGH": 1, "MEDIUM": 2, "LOW": 4}
    names = {1: "Auto-Confirm Duplicate", 2: "High-Probability Steward Review", 4: "Low Confidence Watchlist"}
    groups = []
    for g in out["groups"]:
        t = tier[g["confidence"]]
        recs = [{"id": r["id"], "name": r["name"], "country": r["country"], "category": "", "created": r["created"], "address": r["address"],
                 "city": r["city"], "phones": [p for p in r["phone"].split(", ") if p], "emails": [e for e in r["email"].split(", ") if e],
                 "anchors": {"Tax / Reg. No.": [x for x in r["taxNo"].split(", ") if x]}, "survivorScore": 0, "survivorBreakdown": {}}
                for r in g["records"]]
        pairs = []
        for p in g["pairs"]:
            rules = {s["code"]: s["points"] for s in p["signals"]}
            rules.update({x["code"]: x["points"] for x in p["penalties"]})
            pairs.append({"a": p["a"], "b": p["b"], "score": p["score"], "tier": t, "tags": [], "rules": rules,
                          "details": {"A01": [], "A02": [], "N01": "", "L01": "",
                                      "C": [f"{s['label']}: {s['detail']}" for s in p["signals"]] + [f"{x['label']}: {x['detail']}" for x in p["penalties"]]},
                          "ml": None, "mlOnly": False})
        groups.append({"id": g["id"], "lane": "dup" if t < 4 else "watch", "tier": t, "tierName": names[t], "score": g["score"], "tags": [],
                       "survivor": recs[0]["id"], "records": recs, "pairs": pairs})
    st = out["stats"]
    by = Counter(g["tier"] for g in groups)
    return {"entity": "customer", "groups": groups,
            "stats": {"suppliers": st["parties"], "eligible": st["parties"], "candidatePairs": st["candidatePairs"], "skippedBlocks": st["skippedBlocks"],
                      "scoredPairs": st["scoredPairs"], "groups": len(groups), "conditions": [], "byTier": dict(sorted(by.items())),
                      "excluded": {"template": 0, "oneTime": 0, "internal": 0}}}


def customer_scan_from_files(uploads: list[tuple[str, bytes]], selection: dict | None = None) -> dict:
    res = reports.parse_uploads("customer", uploads)
    if selection is not None:
        from .column_select import apply_selection
        role_of = {code: role for role, code in reports.ROLE_CODES["customer"].items()}
        stage_of = {c["code"]: c["stage"] for c in reports.catalog("customer")}
        for item in res["report"]:
            stage = res["stages"][stage_of[item["code"]]]
            stage["records"] = apply_selection(stage["records"], selection.get(role_of.get(item["code"])))
    if not res["stages"]["general"]["records"]:
        raise ValueError("No customer general report found (a sheet named CUS01_... or one with Customer Id / Name / Association No columns is needed).")
    out = customer_scan([res])
    out["files"] = [{"file": r["file"], "role": r["code"], "rows": r["rows"], "note": ""} for r in res["report"]] + \
                   [{"file": u["file"], "role": None, "rows": 0, "note": u["reason"]} for u in res["unmatched"]]
    out["missingReports"] = []
    return out
