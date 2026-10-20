from app import dedup


def party(entity, pid, name, **kw):
    """Minimal result record set for one party."""
    key = "SupplierId" if entity == "supplier" else "CustomerId"
    stages = {"general": {"records": [{key: pid, "Name": name, "Country": kw.get("country", "LK"), **({"AssociationNo": kw["brn"]} if kw.get("brn") else {})}]}}
    if kw.get("addr"):
        stages["Addresses"] = {"records": [{"_" + key: pid, "Address1": kw["addr"], "ZipCode": kw.get("zip", ""), "City": kw.get("city", "")}]}
    comm = [{"_" + key: pid, "MethodId": "PHONE", "Value": kw["phone"]}] if kw.get("phone") else []
    comm += [{"_" + key: pid, "MethodId": "E_MAIL", "Value": kw["email"]}] if kw.get("email") else []
    if comm:
        stages["AddressCommunicationMethods"] = {"records": comm}
    if kw.get("bank"):
        stages["SupplierPayments"] = {"records": [{"_" + key: pid, "Account": kw["bank"]}]}
    if kw.get("person"):
        stages["Contacts"] = {"records": [{"_" + key: pid, "PersonId": kw["person"]}]}
    return stages


def merge(*stage_sets, entity="supplier"):
    out = {}
    for st in stage_sets:
        for k, v in st.items():
            out.setdefault(k, {"records": []})["records"] += v["records"]
    return {"entity": entity, "stages": out}


def score(a, b):
    ps = dedup.build_parties([merge(a, b)])
    return dedup.score_pair(ps[0], ps[1])


def test_case_a_typo_same_bank():
    a = party("supplier", "S1", "Sooriya Logistics Pvt Ltd", bank="LK12-3456-7890", phone="+94 77 123 4567")
    b = party("supplier", "S2", "Surya Logistic", bank="LK1234567890", phone="0771234567")
    r = score(a, b)
    assert r["score"] >= 85, r


def test_case_b_fuzzy_name_address_contact():
    a = party("supplier", "S1", "Apex Industrial Eng.", addr="No. 45/2 Galle Rd", city="Colombo", email="a@apex.lk", person="P9")
    b = party("supplier", "S2", "Apex Ind Engineering", addr="45-2 Galle Road", city="Colombo", email="b@apex.lk", person="P9")
    r = score(a, b)
    assert r["score"] >= 65, r


def test_case_c_branch_same_brn():
    a = party("supplier", "S1", "Singer Sri Lanka - Colombo", brn="PV 4412")
    b = party("supplier", "S2", "Singer - Kandy", brn="PV4412")
    r = score(a, b)
    assert r["score"] < 45, r


def test_group_vat_unrelated_names_stays_in_review_band():
    a = party("supplier", "S1", "Alpha Foods", brn="PV 100200")
    b = party("supplier", "S2", "Zenith Steel", brn="PV100200")
    r = score(a, b)
    assert 45 <= r["score"] <= 55, r


def test_different_country_penalty_and_unique():
    a = party("supplier", "S1", "Acme Trading", country="LK")
    b = party("supplier", "S2", "Acme Trading", country="IN")
    assert score(a, b)["score"] < 65
    c = party("supplier", "S3", "Completely Different Name")
    assert score(a, c)["score"] < 45


def test_find_duplicates_groups_and_cross_role():
    res = [merge(party("supplier", "S1", "Acme Holdings Ltd", brn="PV 1234"), party("supplier", "S2", "ACME Holdings Limited", brn="PV1234")),
           merge(party("customer", "C1", "Acme Holdings", brn="PV1234"), entity="customer")]
    out = dedup.find_duplicates(res)
    assert out["stats"]["parties"] == 3
    assert len(out["groups"]) == 1
    g = out["groups"][0]
    assert g["entity"] == "cross" and len(g["records"]) == 3 and g["confidence"] == "HIGH"
