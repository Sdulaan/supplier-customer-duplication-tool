import json
from datetime import datetime
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import column_select, dedup, ifs, reports, scan_adapters, spec_export, spec_ml, spec_model, spec_store

app = FastAPI(title="Supplier & Customer Duplication API")

ENV_FILE = Path(os.getenv("ENVIRONMENTS_FILE", Path(__file__).resolve().parent.parent / "environments.json"))


def file_environments() -> list[dict]:
    """Environments defined in backend/environments.json (re-read on every request)."""
    try:
        data = json.loads(ENV_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data.get("environments", []) if isinstance(e, dict) and e.get("name")]


@app.exception_handler(ifs.IfsError)
async def ifs_error_handler(_, exc: ifs.IfsError):
    return JSONResponse({"success": False, "error": exc.message}, status_code=exc.status if exc.status >= 400 else 502)


class TokenRequest(BaseModel):
    tokenUrl: str
    clientId: str
    clientSecret: str | None = None
    envName: str | None = None
    code: str
    redirectUri: str
    codeVerifier: str


class PasswordRequest(BaseModel):
    tokenUrl: str
    clientId: str
    clientSecret: str | None = None
    envName: str | None = None
    username: str
    password: str
    scope: str | None = None


class FetchRequest(BaseModel):
    baseUrl: str
    accessToken: str
    entities: list[Literal["supplier", "customer"]]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/environments")
async def environments():
    """File-defined environments. Client secrets never leave the server."""
    out = []
    for env in file_environments():
        variables = dict(env.get("variables") or {})
        has_secret = bool(variables.pop("clientSecret", ""))
        out.append({"name": env["name"], "variables": variables, "hasSecret": has_secret})
    return {"environments": out}


@app.post("/api/auth/token")
async def token(req: TokenRequest):
    secret = req.clientSecret
    if req.envName:
        env = next((e for e in file_environments() if e["name"] == req.envName), None)
        if env is None:
            raise ifs.IfsError(400, f'Environment "{req.envName}" is not defined in environments.json.')
        secret = (env.get("variables") or {}).get("clientSecret") or secret
    result = await ifs.exchange_code(req.tokenUrl, req.clientId, secret, req.code, req.redirectUri, req.codeVerifier)
    return {"success": True, **result}


@app.post("/api/auth/password")
async def password_token(req: PasswordRequest):
    secret = req.clientSecret
    if req.envName:
        env = next((e for e in file_environments() if e["name"] == req.envName), None)
        if env is None:
            raise ifs.IfsError(400, f'Environment "{req.envName}" is not defined in environments.json.')
        secret = (env.get("variables") or {}).get("clientSecret") or secret
    result = await ifs.password_grant(req.tokenUrl, req.clientId, secret, req.username, req.password, req.scope)
    return {"success": True, **result}


@app.post("/api/ifs/fetch")
async def fetch(req: FetchRequest):
    results = [await ifs.fetch_entity(req.baseUrl, req.accessToken, e) for e in req.entities]
    return {"success": True, "results": results}


@app.get("/api/catalog/{entity}")
async def catalog(entity: Literal["supplier", "customer"]):
    """Data sets of an entity and the Quick Report name that feeds each one."""
    return {"entity": entity, "reports": reports.catalog(entity)}


@app.post("/api/import/{entity}")
async def import_reports(
    entity: Literal["supplier", "customer"], files: list[UploadFile] = File(...), assignments: str = Form("{}")
):
    """Map uploaded IFS Quick Report exports (xlsx / csv) into the same structure as an API fetch.
    `assignments` optionally maps a file name to the report code it should fill."""
    try:
        chosen = json.loads(assignments)
    except ValueError:
        chosen = {}
    uploads = [(f.filename or "", await f.read()) for f in files]
    return {"success": True, "result": reports.parse_uploads(entity, uploads, chosen if isinstance(chosen, dict) else {})}


class ExportRequest(BaseModel):
    result: dict


@app.post("/api/export/{entity}")
async def export_excel(entity: Literal["supplier", "customer"], req: ExportRequest):
    """The mapped data as an Excel workbook (one sheet per data set); it can be re-imported as-is."""
    data = reports.build_workbook(entity, req.result)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{entity}-mapped.xlsx"'},
    )


class DuplicatesRequest(BaseModel):
    results: list[dict]
    minScore: int = dedup.BAND_POSSIBLE


@app.post("/api/duplicates/find")
async def find_duplicates(req: DuplicatesRequest):
    """Score candidate pairs of the fetched / imported suppliers and customers and return suspected duplicate groups."""
    return {"success": True, **dedup.find_duplicates(req.results, req.minScore)}


@app.post("/api/duplicates/upload")
async def duplicates_from_files(files: list[UploadFile] = File(...), minScore: int = Form(dedup.BAND_POSSIBLE)):
    """Find duplicates straight from uploaded Excel / csv files, e.g. the combined workbook exported from this tool
    (sheets SUP01_..., CUS01_...) or the raw Quick Report exports. Supplier and customer sheets are told apart by code."""
    uploads = [(f.filename or "", await f.read()) for f in files]
    results, loaded = [], {}
    for entity in ("supplier", "customer"):
        res = reports.parse_uploads(entity, uploads, strict_prefix=True)
        n = len(res["stages"]["general"]["records"])
        if n:
            results.append(res)
            loaded[entity] = n
    if not results:
        return JSONResponse({"success": False, "error": "No supplier or customer general data found (a sheet named SUP01_... / CUS01_... is needed)."}, status_code=400)
    return {"success": True, "loaded": loaded, **dedup.find_duplicates(results, minScore)}


@app.post("/api/spec-dedup/inspect")
async def spec_dedup_inspect(files: list[UploadFile] = File(...), entity: Literal["supplier", "customer"] = Form("supplier")):
    """The columns of every recognised Quick Report (one tab each) so the user can choose which ones the scan uses."""
    uploads = [(f.filename or "", await f.read()) for f in files]
    return {"success": True, "tabs": column_select.inspect(entity, uploads)}


@app.post("/api/spec-dedup/validate")
async def spec_dedup_validate(files: list[UploadFile] = File(...), entity: Literal["supplier", "customer"] = Form("supplier"), columns: str = Form("")):
    """Check the files and the column choice without running the scan."""
    uploads = [(f.filename or "", await f.read()) for f in files]
    try:
        selection = column_select.parse_selection(columns)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    return {"success": True, **column_select.validate(entity, uploads, selection)}


@app.post("/api/spec-dedup/upload")
async def spec_dedup(files: list[UploadFile] = File(...), useMl: bool = Form(True), name: str = Form(""), conditions: str = Form(""),
                     entity: Literal["supplier", "customer"] = Form("supplier"), columns: str = Form("")):
    """Supplier duplicate detection on the 10 IFS Quick Report exports of the 10-table specification
    (rule matrix A01..P01, tiers, survivor scorecard, plus the learned layer when a trained model exists)."""
    uploads = [(f.filename or "", await f.read()) for f in files]
    try:
        selection = column_select.parse_selection(columns)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    if entity == "customer":
        try:
            out = scan_adapters.customer_scan_from_files(uploads, selection)
        except ValueError as exc:
            return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
        return {"success": True, "scan": spec_store.save_scan(out, name, "customer", "reports"), **out}
    model = spec_ml.PairModel.load() if useMl else None
    try:
        chosen = tuple(c for c in conditions.split(",") if c in spec_model.CONDITIONS) if conditions else spec_model.ALL_CONDITIONS
        out = spec_model.run_files(uploads, model, chosen, selection)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    out["model"] = None if not model else {**{k: v for k, v in model.meta.items() if k != "features"}, "canSurface": model.can_surface}
    scan = spec_store.save_scan(out, name, "supplier", "reports")
    return {"success": True, "scan": scan, **out}


class FetchScanRequest(BaseModel):
    entity: Literal["supplier", "customer"]
    baseUrl: str
    accessToken: str
    name: str = ""
    conditions: list[str] | None = None
    useMl: bool = True


@app.post("/api/spec-dedup/fetch")
async def spec_dedup_fetch(req: FetchScanRequest):
    """Fetch the entity from an IFS environment (GET only) and scan it."""
    fetched = await ifs.fetch_entity(req.baseUrl, req.accessToken, req.entity)
    if req.entity == "customer":
        out = scan_adapters.customer_scan([fetched])
    else:
        model = spec_ml.PairModel.load() if req.useMl else None
        chosen = tuple(c for c in (req.conditions or []) if c in spec_model.CONDITIONS) if req.conditions is not None else spec_model.ALL_CONDITIONS
        tables = scan_adapters.tables_from_fetched(fetched)
        if not tables.get("general"):
            return JSONResponse({"success": False, "error": "The IFS environment returned no suppliers."}, status_code=400)
        out = spec_model.run(tables, model, chosen)
        out["files"] = [{"file": f"IFS {role}", "role": role, "rows": len(rows), "note": ""} for role, rows in tables.items()]
        out["missingReports"] = [r for r in spec_model.ROLE_FILE if r not in tables]
        out["model"] = None if not model else {k: v for k, v in model.meta.items() if k != "features"}
    return {"success": True, "scan": spec_store.save_scan(out, req.name, req.entity, "ifs"), **out}


@app.post("/api/spec-dedup/train")
async def spec_dedup_train(files: list[UploadFile] = File(...), labels: str = Form("[]")):
    """Train and save the pair model from the exports. `labels` is an optional JSON list of steward decisions
    [{"a": "<supplier id>", "b": "<supplier id>", "duplicate": true}]."""
    tables, _ = spec_model.load_tables([(f.filename or "", await f.read()) for f in files])
    if "general" not in tables:
        return JSONResponse({"success": False, "error": "The SupplierInfoGeneral report is required."}, status_code=400)
    try:
        model = spec_ml.train(tables, json.loads(labels or "[]"))
    except (ValueError, json.JSONDecodeError) as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    model.save()
    return {"success": True, "meta": {k: v for k, v in model.meta.items() if k != "features"}, "canSurface": model.can_surface,
            "weights": model.weights()}


@app.get("/api/spec-dedup/conditions")
def spec_dedup_conditions():
    """Duplicate-checking conditions a scan can use (the supplier name is always compared)."""
    return [{"id": k, "rule": v[0], "label": v[1], "detail": v[2]} for k, v in spec_model.CONDITIONS.items()]


@app.get("/api/spec-dedup/scans")
def spec_dedup_scans(entity: Literal["supplier", "customer"] | None = None):
    """Previous scans, newest first (optionally only one entity)."""
    return spec_store.list_scans(entity)


@app.get("/api/spec-dedup/scans/{scan_id}")
def spec_dedup_scan(scan_id: int):
    found = spec_store.get_scan(scan_id)
    if not found:
        return JSONResponse({"success": False, "error": "Scan not found."}, status_code=404)
    return {"success": True, "scan": found[0], "decisions": spec_store.get_decisions(scan_id), **found[1]}


class DecisionRequest(BaseModel):
    decision: str = ""
    comment: str = ""


@app.put("/api/spec-dedup/scans/{scan_id}/groups/{group_id}/decision")
def spec_dedup_decision(scan_id: int, group_id: str, req: DecisionRequest):
    """Save the reviewer's decision / comment for a group (empty decision clears it)."""
    try:
        saved = spec_store.set_decision(scan_id, group_id, req.decision, req.comment)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    if saved is None:
        return JSONResponse({"success": False, "error": "Scan not found."}, status_code=404)
    return {"success": True, "decision": saved}


@app.get("/api/spec-dedup/scans/{scan_id}/export")
def spec_dedup_scan_export(scan_id: int):
    """Excel report of a saved scan (same layout as the Inventory Parts Scan export)."""
    found = spec_store.get_scan(scan_id)
    if not found:
        return JSONResponse({"success": False, "error": "Scan not found."}, status_code=404)
    created = datetime.fromisoformat(found[0]["createdAt"])
    filename = spec_export.report_filename(created, found[0]["entity"])
    return Response(spec_export.build_report(found[1], created, spec_store.get_decisions(scan_id)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.delete("/api/spec-dedup/scans/{scan_id}")
def spec_dedup_scan_delete(scan_id: int):
    return {"success": spec_store.delete_scan(scan_id)}
