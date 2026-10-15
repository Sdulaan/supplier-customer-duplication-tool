"""Read-only IFS access: OAuth2 code exchange and paged GET fetches (same endpoints as the migration tool)."""
import asyncio
from urllib.parse import quote, urljoin, urlparse

import httpx

PROJECTION_ROOT = "main/ifsapplications/projection/v1"
MAX_PAGES = 500
CHILD_CONCURRENCY = 8


class IfsError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def require_http_url(value: str, name: str) -> str:
    parsed = urlparse(value or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise IfsError(400, f"{name} must be a full http(s) URL.")
    return value


def projection_url(base_url: str, projection: str, path: str) -> str:
    require_http_url(base_url, "Base URL")
    return f"{base_url.rstrip('/')}/{PROJECTION_ROOT}/{projection}/{path}"


def key_literal(value: str) -> str:
    return quote(str(value).replace("'", "''"), safe="")


def error_message(text: str) -> str:
    try:
        import json

        err = (json.loads(text) or {}).get("error") or {}
        parts = [err.get("message", "")]
        parts += [": ".join(filter(None, [d.get("code"), d.get("message")])) for d in err.get("details", []) or []]
        return " ".join(p for p in parts if p)
    except Exception:
        return text[:200]


async def exchange_code(token_url, client_id, client_secret, code, redirect_uri, code_verifier) -> dict:
    require_http_url(token_url, "Token URL")
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.post(token_url, data=data)
        except httpx.HTTPError as exc:
            raise IfsError(502, f"Could not reach token endpoint: {exc}")
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    if res.status_code >= 400 or "access_token" not in body:
        detail = body.get("error_description") or body.get("error") or ""
        raise IfsError(401, f"Token exchange failed ({res.status_code}). {detail}".strip())
    return {
        "accessToken": body["access_token"],
        "tokenType": body.get("token_type", "Bearer"),
        "expiresIn": body.get("expires_in", 3600),
    }


async def get_all(client: httpx.AsyncClient, url: str, token: str) -> list[dict]:
    """GET a collection, following @odata.nextLink. A single-entity response comes back as one record."""
    records: list[dict] = []
    next_url: str | None = url
    for _ in range(MAX_PAGES):
        if not next_url:
            break
        try:
            res = await client.get(next_url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise IfsError(502, f"Could not reach IFS: {exc}")
        if res.status_code >= 400:
            raise IfsError(res.status_code, f"Request failed ({res.status_code}). {error_message(res.text)}".strip())
        try:
            data = res.json()
        except ValueError:
            raise IfsError(502, f"IFS answered {res.status_code} but the body isn't JSON.")
        if isinstance(data.get("value"), list):
            records.extend(data["value"])
        elif isinstance(data, dict):
            records.append({k: v for k, v in data.items() if k != "@odata.context"})
        link = data.get("@odata.nextLink")
        next_url = urljoin(next_url, link) if link else None
    return records


# entity -> projection, root entity set, key field, and child stages fetched per parent record.
ENTITIES = {
    "supplier": {
        "projection": "SupplierHandling.svc",
        "set": "SupplierInfoGeneralSet",
        "key": "SupplierId",
        "children": [
            ("supplier_address", "SupplierInfoAddresses"),
            ("supplier_payment", "SupplierPayments"),
        ],
    },
    "customer": {
        "projection": "CustomerHandling.svc",
        "set": "CustomerInfoSet",
        "key": "CustomerId",
        "children": [],
    },
}


async def fetch_entity(base_url: str, token: str, entity: str) -> dict:
    spec = ENTITIES[entity]
    stages: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        root_url = projection_url(base_url, spec["projection"], spec["set"])
        parents = await get_all(client, root_url, token)
        stages["general"] = {"collection": spec["set"], "records": parents, "errors": []}

        sem = asyncio.Semaphore(CHILD_CONCURRENCY)
        for stage_id, collection in spec["children"]:
            out = {"collection": collection, "records": [], "errors": []}

            async def one(parent):
                pid = parent.get(spec["key"])
                if not pid:
                    return
                path = f"{spec['set']}({spec['key']}='{key_literal(pid)}')/{collection}"
                async with sem:
                    try:
                        out["records"].extend(
                            await get_all(client, projection_url(base_url, spec["projection"], path), token)
                        )
                    except IfsError as exc:
                        out["errors"].append({"parent": pid, "error": exc.message})

            await asyncio.gather(*(one(p) for p in parents))
            stages[stage_id] = out
    return {"entity": entity, "stages": stages}
