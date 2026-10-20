"""Party master duplicate detection (supplier / customer), after "IFS Party Master Deduplication & Scoring Specification".

Input is what the data pages hold: [{"entity": "supplier"|"customer", "stages": {stage path: {"records": [...]}}}], from
either the IFS API fetch or the Quick Report import. Output is groups of suspected duplicates with a 0-100 score.

Pipeline: build a profile per party -> generate candidate pairs by blocking -> score each pair
(additive signals + anchor override + negative penalties) -> cluster pairs at or above the "possible" band into groups.

Signals not available from the data we collect (cancelled-twin invoices, vendor_part_no overlap, geocodes, credit hierarchy
beyond a parent id column) are not scored; everything else in section 5 of the spec is.
"""
import re
from collections import defaultdict
from itertools import combinations

from . import ifs

# --- spec constants -----------------------------------------------------------------------------------------------
W = {"S01": 55, "S02": 50, "S03": 55, "S04": 30, "S05": 15, "S06": 20, "S07": 20, "S08": 20, "S08_DOMAIN": 12, "S09": 15,
     "S11": 15}
P_CONFLICT, P_HIERARCHY, P_COUNTRY = 35, 40, 25
SYNERGY_FLOOR = 88
ANCHOR_ONLY_CAP = 55
SYNERGY_RATIO = 0.60
NAME_MIN_SIM = 0.75
JW_THRESHOLD = 0.88
BAND_POSSIBLE, BAND_PROBABLE, BAND_DEFINITE = 45, 65, 85
MAX_BLOCK = 300  # blocks larger than this are too generic to be a useful key (e.g. everybody called "THE ...")

LABELS = {"S01": "Tax / VAT no.", "S02": "Association no. (BRN)", "S03": "Bank account / IBAN", "S04": "Legal name",
          "S05": "Phonetic / acronym name", "S06": "Street address", "S07": "Phone number", "S08": "Email",
          "S09": "Shared contact person", "S11": "Legacy Our ID", "P01": "Conflicting tax / BRN",
          "P02": "Branch / hierarchy", "P03": "Different country"}

NOISE_WORDS = {"pvt", "private", "ltd", "limited", "llc", "inc", "incorporated", "corp", "corporation", "plc", "gmbh",
               "ag", "sa", "bv", "nv", "pty", "co", "company", "lanka", "group", "holdings", "holding", "the", "and",
               "of", "sdn", "bhd", "llp", "lp", "se"}
PUBLIC_DOMAINS = {"gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com", "outlook.com", "live.com",
                  "msn.com", "icloud.com", "aol.com", "proton.me", "protonmail.com", "sltnet.lk", "slt.lk", "mail.com"}
STREET_ABBR = {"rd": "road", "mw": "mawatha", "mawata": "mawatha", "st": "street", "ave": "avenue", "av": "avenue",
               "ln": "lane", "pl": "place", "blvd": "boulevard", "hwy": "highway", "dr": "drive", "ctr": "centre",
               "center": "centre", "bldg": "building", "flr": "floor", "no": "", "num": "", "nr": ""}

TAX_KEYS = {"vatno", "vatnumber", "taxno", "taxnumber", "taxidnumber", "taxidno", "taxregno", "taxregistrationno",
            "taxregistrationnumber", "vatregno", "vatregistrationno", "vatregistrationnumber", "tin", "tinno"}
BRN_KEYS = {"associationno", "brn", "businessregistrationno", "registrationno", "companyregno"}
BANK_KEYS = {"account", "accountno", "accountnumber", "bankaccount", "bankaccountno", "bankaccountnumber", "iban",
             "payaccount", "payeeaccount"}
OURID_KEYS = {"ourid"}
PERSON_KEYS = {"personid"}
PARENT_KEYS = {"parentcustomerid", "parentidentity", "parentsupplierid", "parentid", "parentpartyid"}
CREATED_KEYS = {"creationdate", "createdate", "createddate"}
COUNTRY_KEYS = ("countrydb", "countrycode", "country")
NAME_KEYS = ("name",)


# --- string helpers -----------------------------------------------------------------------------------------------
def _n(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0 if a else 0.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    window = max(max(la, lb) // 2 - 1, 0)
    ma, mb = [False] * la, [False] * lb
    matches = 0
    for i, ca in enumerate(a):
        for j in range(max(0, i - window), min(lb, i + window + 1)):
            if not mb[j] and b[j] == ca:
                ma[i] = mb[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    t, k = 0, 0
    for i in range(la):
        if ma[i]:
            while not mb[k]:
                k += 1
            t += a[i] != b[k]
            k += 1
    jaro = (matches / la + matches / lb + (matches - t / 2) / matches) / 3
    prefix = 0
    for ca, cb in zip(a[:4], b[:4]):
        if ca != cb:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def tokens_of(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.lower().replace("&", " and "))


def clean_tokens(name: str) -> list[str]:
    toks = tokens_of(name)
    kept = [t for t in toks if t not in NOISE_WORDS]
    return kept or toks


def phonetic(token: str) -> str:
    """Simplified phonetic key (a stand-in for Double Metaphone): equates transliterations such as Surya / Sooriya."""
    t = re.sub(r"[^a-z0-9]", "", token.lower())
    if len(t) > 3 and t.endswith("s"):
        t = t[:-1]
    for pat, rep in (("ph", "f"), ("ck", "k"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("sh", "s"), ("ch", "c"),
                     ("wh", "w"), ("oo", "u"), ("ou", "u"), ("ee", "i"), ("ea", "i"), ("aa", "a"), ("x", "ks"),
                     ("z", "s"), ("q", "k"), ("y", "i"), ("w", "v")):
        t = t.replace(pat, rep)
    t = re.sub(r"c(?=[eiy])", "s", t).replace("c", "k")
    if not t:
        return ""
    code = t[0] + re.sub(r"[aeiou]", "", t[1:])
    return re.sub(r"(.)\1+", r"\1", code)


def initials(tokens: list[str]) -> str:
    return "".join(t[0] for t in tokens if t)


# --- normalizers --------------------------------------------------------------------------------------------------
def norm_id(value: str) -> str:
    """Tax / BRN / bank number: alphanumeric only, no 'VAT' marker, no 2-letter country prefix (LK-114290-VAT -> 114290)."""
    s = re.sub(r"[^A-Z0-9]", "", _text(value).upper())
    s = re.sub(r"VAT$", "", s)
    if len(s) > 5 and re.match(r"^[A-Z]{2}\d", s):
        s = s[2:]
    return s if len(s) >= 4 else ""


def norm_bank(value: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", _text(value).upper())
    return s if len(s) >= 6 else ""


def norm_phone(value: str) -> str:
    """Core subscriber number: digits only, international / trunk prefixes dropped, last 9 digits."""
    d = re.sub(r"\D", "", _text(value))
    d = d[2:] if d.startswith("00") else d
    return d[-9:] if len(d) >= 9 else ""


def norm_address(a1: str, a2: str, zip_: str, city: str) -> dict:
    raw = f"{a1} {a2}".lower()
    raw = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1-\2", raw)  # No. 45/2 -> 45-2
    toks = []
    for t in re.findall(r"[a-z0-9-]+", raw):
        t = STREET_ABBR.get(t, t)
        if t:
            toks.append(t)
    return {"tokens": frozenset(toks), "zip": re.sub(r"\W", "", _text(zip_).lower()), "city": re.sub(r"\W", "", _text(city).lower()),
            "text": ", ".join(x for x in (_text(a1), _text(a2)) if x), "city_text": _text(city)}


# --- profiles -----------------------------------------------------------------------------------------------------
class Party:
    __slots__ = ("entity", "id", "name", "country", "created", "tokens", "clean", "base_clean", "suffix", "phon", "acro",
                 "taxes", "brns", "banks", "ourids", "phones", "emails", "domains", "persons", "addrs", "parents",
                 "raw", "key")

    def __init__(self, entity: str, pid: str, raw: dict):
        self.entity, self.id, self.raw = entity, pid, raw
        self.key = (entity, pid)
        self.taxes, self.brns, self.banks, self.ourids = set(), set(), set(), set()
        self.phones, self.emails, self.domains, self.persons, self.parents = set(), set(), set(), set(), set()
        self.addrs: list[dict] = []
        self.name = ""
        self.country = ""
        self.created = ""


def _first(rec: dict, keys) -> str:
    wanted = {_n(k): k for k in rec}
    for k in keys:
        if k in wanted and _text(rec[wanted[k]]):
            return _text(rec[wanted[k]])
    return ""


def _split_branch(name: str) -> tuple[str, str]:
    parts = re.split(r"\s+[-–—]\s+", name.strip(), maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (name, "")


def build_parties(results: list[dict]) -> list[Party]:
    parties: dict[tuple, Party] = {}
    for res in results:
        entity = res.get("entity")
        if entity not in ifs.ENTITIES:
            continue
        id_key = ifs.ENTITIES[entity]["key"]
        stages = res.get("stages") or {}
        for rec in (stages.get("general") or {}).get("records", []):
            pid = _text(rec.get(id_key))
            if not pid:
                continue
            p = Party(entity, pid, rec)
            p.name = _first(rec, NAME_KEYS)
            p.country = _first(rec, COUNTRY_KEYS).lower()
            p.created = _first(rec, CREATED_KEYS)
            parties[(entity, pid)] = p
        owner_keys = [f"_{id_key}", id_key, "Identity"]
        for path, stage in stages.items():
            is_comm = "communicationmethod" in path.lower() or "commmethod" in path.lower()
            for rec in stage.get("records", []):
                owner = next((_text(rec[k]) for k in owner_keys if rec.get(k) not in (None, "")), "")
                p = parties.get((entity, owner))
                if not p:
                    continue
                _absorb(p, rec, path, is_comm)
    out = list(parties.values())
    for p in out:
        _finish(p)
    return out


def _absorb(p: Party, rec: dict, path: str, is_comm: bool) -> None:
    for k, v in rec.items():
        nk = _n(k)
        s = _text(v)
        if not s or k.startswith("@odata"):
            continue
        if nk in TAX_KEYS and norm_id(s):
            p.taxes.add(norm_id(s))
        elif nk in BRN_KEYS and norm_id(s):
            p.brns.add(norm_id(s))
        elif nk in BANK_KEYS and norm_bank(s):
            p.banks.add(norm_bank(s))
        elif nk in OURID_KEYS:
            p.ourids.add(re.sub(r"\W", "", s.upper()))
        elif nk in PERSON_KEYS:
            p.persons.add(s.upper())
        elif nk in PARENT_KEYS:
            p.parents.add(s)
    if is_comm:
        value = _text(rec.get("Value"))
        method = _first(rec, ("methodiddb", "methodid", "name", "commmethod")).upper()
        if "@" in value:
            p.emails.add(value.lower())
            p.domains.add(value.lower().rsplit("@", 1)[1])
        elif value and "FAX" not in method and "WWW" not in method and "URL" not in method and norm_phone(value):
            p.phones.add(norm_phone(value))
    a1 = _first(rec, ("address1",))
    if a1:
        p.addrs.append(norm_address(a1, _first(rec, ("address2",)), _first(rec, ("zipcode", "postcode")), _first(rec, ("city",))))
        if not p.country:
            p.country = _first(rec, COUNTRY_KEYS).lower()


def _finish(p: Party) -> None:
    base, suffix = _split_branch(p.name)
    p.suffix = " ".join(tokens_of(suffix))
    p.tokens = clean_tokens(p.name)
    p.clean = " ".join(sorted(p.tokens))
    p.base_clean = " ".join(sorted(clean_tokens(base))) if suffix else p.clean
    p.phon = " ".join(sorted(c for c in (phonetic(t) for t in p.tokens) if c))
    p.acro = initials(p.tokens)


# --- pair scoring -------------------------------------------------------------------------------------------------
def name_similarity(a: str, b: str) -> float:
    """Hybrid token-sort + Jaro-Winkler; a token that abbreviates a token of the other name (ind / industrial) counts as equal."""
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return 0.0
    ta = [next((x for x in tb if len(t) >= 3 and x.startswith(t) and x != t), t) for t in ta]
    tb = [next((x for x in ta if len(t) >= 3 and x.startswith(t) and x != t), t) for t in tb]
    sa, sb = " ".join(sorted(ta)), " ".join(sorted(tb))
    return max(jaro_winkler(sa, sb), jaro_winkler(a, b))


def _acronym_match(a: Party, b: Party) -> bool:
    def lead_letters(p: Party) -> str:
        run = ""
        for t in p.tokens:
            if len(t) != 1:
                break
            run += t
        return run

    for x, y in ((a, b), (b, a)):
        lead = lead_letters(x)
        rest = [t for t in y.tokens]
        if len(lead) >= 2 and len(rest) >= len(lead) and initials(rest[: len(lead)]) == lead:
            return True
        if len(x.tokens) == 1 and 2 <= len(x.tokens[0]) <= 6 and len(y.tokens) >= 2 and initials(y.tokens) == x.tokens[0]:
            return True
    return False


def _address_ratio(a: Party, b: Party) -> tuple[float, str]:
    best, why = 0.0, ""
    for x in a.addrs:
        for y in b.addrs:
            if not x["tokens"] or not y["tokens"]:
                continue
            jac = len(x["tokens"] & y["tokens"]) / len(x["tokens"] | y["tokens"])
            r = 0.6 * jac + (0.2 if x["zip"] and x["zip"] == y["zip"] else 0) + (0.2 if x["city"] and x["city"] == y["city"] else 0)
            if r > best:
                best = r
                why = " ".join(sorted(x["tokens"] & y["tokens"]))
    return best, why


def _same_country(a: Party, b: Party) -> bool | None:
    if not a.country or not b.country:
        return None
    return a.country == b.country or a.country in b.country or b.country in a.country


def score_pair(a: Party, b: Party) -> dict:
    signals: list[dict] = []

    def add(code: str, ratio: float, detail: str, weight: int | None = None, label: str | None = None):
        w = weight if weight is not None else W[code]
        signals.append({"code": code, "label": label or LABELS[code], "ratio": round(ratio, 2), "points": round(w * ratio, 1), "detail": detail})

    # Ring 1: deterministic anchors
    anchors = []
    for code, mine, theirs in (("S01", a.taxes, b.taxes), ("S02", a.brns, b.brns), ("S03", a.banks, b.banks)):
        hit = mine & theirs
        if hit:
            add(code, 1.0, next(iter(hit)))
            anchors.append(code)
    # Ring 2: linguistic and spatial
    base_a, base_b = a.base_clean, b.base_clean
    branch = bool(a.suffix and b.suffix and a.suffix != b.suffix)
    sim = name_similarity(base_a, base_b) if branch else name_similarity(a.clean, b.clean)
    if sim >= NAME_MIN_SIM:
        add("S04", sim, f'"{a.clean}" ~ "{b.clean}"' + (" (branch suffix ignored)" if branch else ""))
    if a.phon and b.phon:
        ps = jaro_winkler(a.phon, b.phon)
        if ps >= JW_THRESHOLD and a.clean != b.clean:
            add("S05", 1.0, f"sounds alike: {a.phon} ~ {b.phon}")
        elif _acronym_match(a, b):
            add("S05", 1.0, "initials match the other name")
    ar, why = _address_ratio(a, b)
    if ar >= SYNERGY_RATIO:
        add("S06", ar, why or "same street")
    # Ring 3: contact graph
    shared_phone = a.phones & b.phones
    if shared_phone:
        add("S07", 1.0, next(iter(shared_phone)))
    shared_mail = a.emails & b.emails
    shared_dom = {d for d in a.domains & b.domains if d not in PUBLIC_DOMAINS}
    if shared_mail:
        add("S08", 1.0, next(iter(shared_mail)), 20, "Exact email")
    elif shared_dom:
        add("S08", 1.0, next(iter(shared_dom)), W["S08_DOMAIN"], "Corporate email domain")
    shared_person = a.persons & b.persons
    if shared_person:
        add("S09", 1.0, next(iter(shared_person)))
    shared_our = a.ourids & b.ourids
    if shared_our:
        add("S11", 1.0, next(iter(shared_our)))

    # Penalties
    penalties = []
    for mine, theirs in ((a.taxes, b.taxes), (a.brns, b.brns)):
        if mine and theirs and not (mine & theirs) and all(levenshtein(x, y) > 2 for x in mine for y in theirs):
            penalties.append({"code": "P01", "label": LABELS["P01"], "points": -P_CONFLICT, "detail": f"{sorted(mine)[0]} vs {sorted(theirs)[0]}"})
            break
    hierarchy = None
    if a.entity == b.entity and (a.id in b.parents or b.id in a.parents or (a.parents & b.parents)):
        hierarchy = "linked via parent id"
    elif branch:
        hierarchy = f'site suffix "{a.suffix}" vs "{b.suffix}"'
    if hierarchy:
        penalties.append({"code": "P02", "label": LABELS["P02"], "points": -P_HIERARCHY, "detail": hierarchy})
    if _same_country(a, b) is False:
        penalties.append({"code": "P03", "label": LABELS["P03"], "points": -P_COUNTRY, "detail": f"{a.country} vs {b.country}"})

    total = sum(s["points"] for s in signals)
    override = None
    if anchors:
        synergy = any(s["code"] in ("S04", "S05", "S06", "S07", "S08", "S09") and s["ratio"] >= SYNERGY_RATIO for s in signals)
        if hierarchy:
            pass  # a known branch / group member keeps its additive score
        elif synergy:
            override = SYNERGY_FLOOR
            total = max(total, SYNERGY_FLOOR)
        else:
            total = min(total, max(s["points"] for s in signals if s["code"] in anchors), ANCHOR_ONLY_CAP)
            override = "anchor only"
    score = max(0, min(100, round(total + sum(p["points"] for p in penalties))))
    return {"score": score, "signals": signals, "penalties": penalties, "anchors": anchors, "override": override}


def band(score: int) -> str:
    if score >= BAND_DEFINITE:
        return "HIGH"
    if score >= BAND_PROBABLE:
        return "MEDIUM"
    return "LOW"


BAND_NAME = {"HIGH": "Definite duplicate", "MEDIUM": "Probable duplicate", "LOW": "Possible / hierarchy"}


# --- candidate blocking -------------------------------------------------------------------------------------------
def candidate_pairs(parties: list[Party]) -> tuple[set[tuple[int, int]], int]:
    blocks: dict[tuple, list[int]] = defaultdict(list)
    for i, p in enumerate(parties):
        for brn in p.brns | p.taxes:
            blocks[("id", brn)].append(i)
        compact = re.sub(r"\s", "", p.clean)
        if len(compact) >= 4:
            blocks[("n4", compact[:4], p.country)].append(i)
        if p.phon:
            blocks[("ph", p.phon.split()[0])].append(i)
        for x in p.phones | p.banks:
            blocks[("pb", x)].append(i)
        for x in p.ourids:
            blocks[("our", x)].append(i)
    pairs: set[tuple[int, int]] = set()
    skipped = 0
    for members in blocks.values():
        if len(members) < 2:
            continue
        if len(members) > MAX_BLOCK:
            skipped += 1
            continue
        pairs.update(combinations(sorted(set(members)), 2))
    return pairs, skipped


# --- grouping -----------------------------------------------------------------------------------------------------
def _survivor_rank(p: Party):
    # (1) validated tax / bank setup, (2) invoices / orders (not collected), (3) oldest creation date
    return (-(bool(p.taxes) + bool(p.banks)), p.created or "9999", p.id)


def _record_view(p: Party) -> dict:
    addr = p.addrs[0] if p.addrs else {}
    return {
        "id": p.id, "role": p.entity, ("supplierId" if p.entity == "supplier" else "customerId"): p.id,
        "name": p.name, "taxNo": ", ".join(sorted(p.taxes | p.brns)), "bank": ", ".join(sorted(p.banks)),
        "phone": ", ".join(sorted(p.phones)), "email": ", ".join(sorted(p.emails)),
        "country": p.country.upper() if len(p.country) <= 3 else p.country.title(),
        "address": addr.get("text", ""), "city": addr.get("city_text", ""), "created": p.created,
    }


def find_duplicates(results: list[dict], min_score: int = BAND_POSSIBLE) -> dict:
    parties = build_parties(results)
    pairs_idx, skipped = candidate_pairs(parties)
    scored = []
    for i, j in pairs_idx:
        a, b = parties[i], parties[j]
        s = score_pair(a, b)
        if s["score"] >= min_score:
            scored.append((i, j, s))

    parent = list(range(len(parties)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _ in scored:
        parent[find(i)] = find(j)
    comps: dict[int, list[int]] = defaultdict(list)
    pair_by_comp: dict[int, list] = defaultdict(list)
    for i, j, s in scored:
        pair_by_comp[find(i)].append((i, j, s))
    for i in {x for i, j, _ in scored for x in (i, j)}:
        comps[find(i)].append(i)

    groups = []
    for root, members in comps.items():
        members.sort(key=lambda m: _survivor_rank(parties[m]))
        plist = sorted(pair_by_comp[root], key=lambda t: -t[2]["score"])
        best = plist[0][2]
        entities = {parties[m].entity for m in members}
        entity = entities.pop() if len(entities) == 1 else "cross"
        score = best["score"]
        reasons = [f"{s['label']}: {s['detail']}" for s in sorted(best["signals"], key=lambda s: -s["points"])]
        reasons += [f"{p['label']} ({p['points']}): {p['detail']}" for p in best["penalties"]]
        groups.append({
            "entity": entity, "score": score, "confidence": band(score), "classification": BAND_NAME[band(score)],
            "status": "open", "reasons": reasons or ["No signals"],
            "records": [_record_view(parties[m]) for m in members],
            "pairs": [{"a": parties[i].id, "b": parties[j].id, "aRole": parties[i].entity, "bRole": parties[j].entity,
                       "score": s["score"], "signals": s["signals"], "penalties": s["penalties"], "override": s["override"]}
                      for i, j, s in plist],
        })
    groups.sort(key=lambda g: (-g["score"], g["records"][0]["id"]))
    for n, g in enumerate(groups, 1):
        g["id"] = f"G{n:04d}"
    return {
        "groups": groups,
        "stats": {"parties": len(parties), "candidatePairs": len(pairs_idx), "scoredPairs": len(scored),
                  "skippedBlocks": skipped, "groups": len(groups)},
    }
