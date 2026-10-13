"""Load a legitimate, separately obtained KRA item-classification response/export.

No authentication, network calls or desktop database mutation are performed here.
KRA's VSCU document describes itemClsCd, itemClsNm, itemClsLvl and taxTyCd.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import re

CODE = re.compile(r"\d{8,10}\Z")
CODES = ("itemClsCd", "ITEM_CLS_CD", "item_cls_cd", "code")
NAMES = ("itemClsNm", "ITEM_CLS_NM", "item_cls_nm", "name")
LISTS = ("itemClsList", "itemClassList", "itemCls", "items", "ItemCls", "itemClasses", "classifications")

class ReferenceFormatError(ValueError):
    pass

def field(row, candidates, default=""):
    for candidate in candidates:
        if candidate in row and row[candidate] is not None:
            return str(row[candidate]).strip()
    return default

def extract_rows(blob):
    if isinstance(blob, list):
        return blob
    if not isinstance(blob, dict):
        raise ReferenceFormatError("Expected an official JSON object/list, or CSV file")
    # KRA-style wrappers: data.itemClsList, data.itemCls, result.itemClsList.
    for key in LISTS:
        if isinstance(blob.get(key), list):
            return blob[key]
    for key in ("data", "result", "response"):
        if isinstance(blob.get(key), (dict, list)):
            try:
                return extract_rows(blob[key])
            except ReferenceFormatError:
                pass
    raise ReferenceFormatError("Could not locate the KRA item classification list")

def load_reference(path):
    """Return (code -> KRA metadata, provenance). This is a code-list, not labeled product truth."""
    path=Path(path)
    raw=path.read_bytes()
    if len(raw)>40_000_000:
        raise ReferenceFormatError("Classification export exceeds 40 MB")
    digest=hashlib.sha256(raw).hexdigest()
    try:
        if path.suffix.lower()==".csv":
            with path.open(newline="",encoding="utf-8-sig") as stream:
                rows=list(csv.DictReader(stream))
        elif path.suffix.lower()==".json":
            rows=extract_rows(json.loads(raw.decode("utf-8-sig")))
        else:
            raise ReferenceFormatError("Use a .json or .csv classification export")
    except (csv.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ReferenceFormatError("Cannot parse classification export") from e
    if not isinstance(rows,list) or not rows:
        raise ReferenceFormatError("Classification export has no records")
    reference={}
    for row in rows:
        if not isinstance(row,dict):
            raise ReferenceFormatError("Expected classification records as objects")
        code=field(row,CODES)
        name=field(row,NAMES)
        if not CODE.fullmatch(code) or not name:
            raise ReferenceFormatError("Missing or malformed official classification code/name")
        active=field(row,("useYn","USE_YN","active"),"Y").upper()
        if active in ("N","FALSE","0"):continue
        if code in reference and reference[code]["name"]!=name:
            raise ReferenceFormatError("One classification code has conflicting names")
        reference[code]={"name":name,"level":field(row,("itemClsLvl","ITEM_CLS_LVL")),
                         "tax_type":field(row,("taxTyCd","TAX_TY_CD")),
                         "origin":"separate_reference_export"}
    if not reference:
        raise ReferenceFormatError("No active classifications in reference")
    return reference,{"sha256":digest,"rows":len(rows),"active_codes":len(reference),
                      "format":path.suffix.lower(),"file":str(path)}

def norm_description(value):
    return " ".join(re.findall(r"[a-z0-9]+",str(value).lower()))

def audit(predictions,reference,gold=None):
    """External catalog confirms existence/name, NEVER independent product correctness."""
    gold=gold or {}
    audited=[]
    for item in predictions:
        product=item["product_name"]
        known=gold.get(product)
        for rank,candidate in enumerate(item.get("top",[]),1):
            code=candidate["code"]
            row=reference.get(code)
            status=("not_in_reference" if row is None else
                    "name_conflict" if norm_description(row["name"])!=norm_description(candidate["name"]) else
                    "code_and_name_confirmed")
            if known is None:product_status="unverified_no_gold_label"
            elif known==code:product_status="matches_independently_reviewed_label"
            else:product_status="different_from_independently_reviewed_label"
            audited.append({"product_name":product,"rank":rank,"predicted_code":code,
                            "predicted_name":candidate["name"],
                            "official_name":row["name"] if row else "",
                            "catalog_status":status,"product_correctness":product_status})
        if not item.get("top"):
            audited.append({"product_name":product,"rank":0,"predicted_code":"",
                            "predicted_name":"","official_name":"",
                            "catalog_status":"no_prediction","product_correctness":"not_classified"})
    return audited
