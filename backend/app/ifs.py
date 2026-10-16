"""Read-only IFS access: OAuth2 code exchange and paged GET fetches (same endpoints as the migration tool)."""
import asyncio
import os
from urllib.parse import quote, urljoin, urlparse

import httpx
from xml.etree import ElementTree

PROJECTION_ROOT = "main/ifsapplications/projection/v1"
# Test/training IFS hosts often use self-signed certificates. Set IFS_VERIFY_TLS=false to skip
# verification, or IFS_CA_BUNDLE=<path to .pem> to trust a specific certificate.
if os.getenv("IFS_VERIFY_TLS", "true").lower() in ("0", "false", "no"):
    TLS_VERIFY: bool | str = False
else:
    TLS_VERIFY = os.getenv("IFS_CA_BUNDLE") or True

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


async def token_request(token_url: str, data: dict) -> dict:
    require_http_url(token_url, "Token URL")
    async with httpx.AsyncClient(timeout=30, verify=TLS_VERIFY) as client:
        try:
            res = await client.post(token_url, data=data)
        except httpx.HTTPError as exc:
            hint = " Self-signed certificate? Set IFS_VERIFY_TLS=false for the backend." if "CERTIFICATE_VERIFY_FAILED" in str(exc) else ""
            raise IfsError(502, f"Could not reach token endpoint: {exc or type(exc).__name__}.{hint}")
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    if res.status_code >= 400 or "access_token" not in body:
        detail = body.get("error_description") or body.get("error") or ""
        raise IfsError(401, f"Token exchange failed ({res.status_code}). {detail}".strip())
    return {
        "accessToken": body["access_token"],
        "tokenType": body.get("token_type", "Bearer"),
        "expiresIn": body.get("expires_in", 3600),
    }


async def exchange_code(token_url, client_id, client_secret, code, redirect_uri, code_verifier) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    return await token_request(token_url, data)


async def password_grant(token_url, client_id, client_secret, username, password, scope) -> dict:
    """Resource-owner password grant (Postman's "Password Credentials")."""
    data = {
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
        "scope": scope or "openid",
    }
    if client_secret:
        data["client_secret"] = client_secret
    return await token_request(token_url, data)


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


# entity -> projection, root entity set, key field and the documented GET API tree (customer_and_supplier_get_apis.txt).
# "relations" nests navigation properties: {"SupplierInfoAddresses": {"AddressTypes": {}, ...}}. Any further first-level
# navigation property found in the projection's $metadata is fetched too, so nothing connected is missed.
ENTITIES = {
    "supplier": {
        "projection": "SupplierHandling.svc",
        "set": "SupplierInfoGeneralSet",
        "key": "SupplierId",
        "relations": {
            "SupplierInfoAddresses": {
                "AddressTypes": {},
                "AddressCommunicationMethods": {},
                "SupplierInfoContacts": {},
                "SupplierDeliveryTaxInfoArray": {"SupplierDeliveryTaxCodeArray": {}},
                "SupplierAddresses": {},
                "SuppOutboundAddrInfoArray": {},
            },
            "MessageSetups": {},
            "SupplierInvoiceCompanies": {},
            "SupplierPayments": {"PaymentWayArray": {}},
            "SupplierPurchases": {},
            "SrmSupplierInfoArray": {},
        },
    },
    "customer": {
        "projection": "CustomerHandling.svc",
        "set": "CustomerInfoSet",
        "key": "CustomerId",
        "relations": {
            "CustomerInfoAddresses": {
                "AddressTypes": {},
                "CustomerTaxInfoArray": {"CustomerDeliveryTaxInfoArray": {"CustomerDeliveryTaxCodes": {}}},
                "SalesCustomerAddressArray": {},
            },
            "CustomerInvoiceCompanies": {},
            "CustomerPayments": {},
            "CustomerCreditInfoArray": {},
            "CustOrdCustomers": {},
        },
    },
}


ERROR_LIMIT = 20


def _local(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _type_name(value: str) -> str:
    inner = value[len("Collection("):-1] if value.startswith("Collection(") else value
    return inner.rsplit(".", 1)[-1]


async def load_metadata(client: httpx.AsyncClient, base_url: str, token: str, spec: dict) -> dict:
    """Entity types of the projection: key properties, property types and navigation targets ($metadata)."""
    url = f"{base_url.rstrip('/')}/{PROJECTION_ROOT}/{spec['projection']}/$metadata"
    meta = {"types": {}, "set_type": None}
    try:
        res = await client.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/xml"})
        if res.status_code >= 400:
            return meta
        root = ElementTree.fromstring(res.content)
    except (httpx.HTTPError, ElementTree.ParseError):
        return meta
    for el in root.iter():
        name = _local(el)
        if name == "EntitySet" and el.get("Name") == spec["set"]:
            meta["set_type"] = _type_name(el.get("EntityType") or "")
        elif name == "EntityType" and el.get("Name"):
            info = {"keys": [], "props": {}, "navs": {}}
            for child in el:
                cn = _local(child)
                if cn == "Key":
                    info["keys"] = [r.get("Name") for r in child if _local(r) == "PropertyRef"]
                elif cn == "Property":
                    info["props"][child.get("Name")] = child.get("Type") or "Edm.String"
                elif cn == "NavigationProperty":
                    info["navs"][child.get("Name")] = _type_name(child.get("Type") or "")
            meta["types"][el.get("Name")] = info
    return meta


def key_predicate(record: dict, info: dict | None, fallback_keys: list[str]) -> str | None:
    """OData key predicate for a record, e.g. SupplierId='X',AddressId='1' (None if a key value is missing)."""
    keys = (info or {}).get("keys") or fallback_keys
    props = (info or {}).get("props") or {}
    parts = []
    for key in keys:
        value = record.get(key)
        if value is None:
            return None
        kind = props.get(key, "Edm.String")
        if kind == "Edm.String":
            literal = "'" + quote(str(value).replace("'", "''"), safe="") + "'"
        elif kind.startswith("Edm."):
            literal = str(value).lower() if isinstance(value, bool) else quote(str(value), safe=":-")
        else:  # enumeration: IfsApp.Projection.EnumType'Value'
            literal = f"{kind}'{quote(str(value), safe='')}'"
        parts.append(f"{key}={literal}")
    return ",".join(parts) or None


async def fetch_entity(base_url: str, token: str, entity: str) -> dict:
    """Fetch every record plus all connected data, following the documented GET paths parent by parent
    (IFS answers 501 to $expand on these relations)."""
    spec = ENTITIES[entity]
    tree = {k: dict(v) for k, v in spec["relations"].items()}
    stages: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=120, verify=TLS_VERIFY) as client:
        meta = await load_metadata(client, base_url, token, spec)
        root_type = meta["set_type"]
        root_info = meta["types"].get(root_type)
        # Extra relations found in $metadata. "...Ref" ones are single-record lookups of reference data
        # (the id is already a column on the parent) and IFS rejects them as standalone GETs, so skip them.
        for nav in (root_info or {}).get("navs", {}):
            if not nav.endswith("Ref"):
                tree.setdefault(nav, {})

        root_url = projection_url(base_url, spec["projection"], spec["set"])
        parents = await get_all(client, root_url, token)
        stages["general"] = {"collection": spec["set"], "records": parents, "errors": []}

        # item = (record, its own URL, entity type name, root key value, index of the record in its own stage)
        items = []
        for idx, rec in enumerate(parents):
            pred = key_predicate(rec, root_info, [spec["key"]])
            if pred:
                items.append((rec, f"{root_url}({pred})", root_type, rec.get(spec["key"]), idx))

        sem = asyncio.Semaphore(CHILD_CONCURRENCY)

        async def walk(subtree: dict, parent_items: list, prefix: tuple):
            async def one_nav(nav: str, children: dict):
                path = prefix + (nav,)
                out = {"collection": "/".join(path), "records": [], "errors": []}
                stages["/".join(path)] = out
                found = []

                async def one_parent(item):
                    rec, url, type_name, root_id, parent_idx = item
                    target = (meta["types"].get(type_name) or {}).get("navs", {}).get(nav)
                    info = meta["types"].get(target)
                    async with sem:
                        try:
                            rows = await get_all(client, f"{url}/{nav}", token)
                        except IfsError as exc:
                            if len(out["errors"]) < ERROR_LIMIT:
                                out["errors"].append({"parent": str(root_id), "error": exc.message})
                            return
                    for row in rows:
                        out["records"].append({f"_{spec['key']}": root_id, "_parent": parent_idx, **row})
                        pred = key_predicate(row, info, [])
                        if pred and children:
                            found.append((row, f"{url}/{nav}({pred})", target, root_id, len(out["records"]) - 1))

                await asyncio.gather(*(one_parent(i) for i in parent_items))
                if children:
                    await walk(children, found, path)

            await asyncio.gather(*(one_nav(n, c) for n, c in subtree.items()))

        await walk(tree, items, ())
    ordered = {"general": stages["general"], **{k: v for k, v in sorted(stages.items()) if k != "general"}}
    return {"entity": entity, "stages": ordered}
