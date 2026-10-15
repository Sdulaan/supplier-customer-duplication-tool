import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import ifs

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


@app.post("/api/ifs/fetch")
async def fetch(req: FetchRequest):
    results = [await ifs.fetch_entity(req.baseUrl, req.accessToken, e) for e in req.entities]
    return {"success": True, "results": results}
