import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import ifs, reports

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
