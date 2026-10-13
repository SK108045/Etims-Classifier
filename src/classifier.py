"""Small, dependency-free eTIMS category retriever. Suggestions are NOT tax rulings."""
from __future__ import annotations
import csv
from difflib import SequenceMatcher
import hashlib
import math
from collections import Counter
from pathlib import Path
import re
import unicodedata

STOP={"and","or","the","of","for","to","with","its","it","a","an","in","on","from","other"}
BRANDS={"lirlee","peglar","powermax","tronics","valdeno","mibao","lodex","carl","gilbert"}
# Search expansions, NOT authoritative assignments. They may suggest a category
# but cannot approve it. Order matters: plumbing adaptor socket != wall socket.
HINTS=(
 (r"\b(adaptor|adapter)\s+(socket|elbow|union)\b|\bbottle\s+traps?\b", "tubes tubing and tube fittings", "plumbing fitting"),
 (r"\b(cable\s+(flex|single|t/e)|flex\s+cable|power\s+cable)\b", "power cable", "electrical"),
 (r"\b(13a\s+.*socket|(?:[1-9]\s*)?gang\s+switch|bell\s+switch|bed\s+switch)\b", "electrical hardware and supplies", "electrical"),
 (r"\badaptor\s+box\b|\bcable\s+clips?\b", "electrical hardware and supplies", "electrical"),
 (r"\b(araldyte|epoxy|bondex)\b", "chemical adhesives", "adhesive"),
 (r"\bnails?\b", "miscellaneous fasteners", "fastener"),
 (r"\bbinding\s+wire\b", "wire", "metal"),
 (r"\bball\s+valve\b|\bangle\s+valve\b|\bbib\s+tap\b", "valve", "plumbing"),
 (r"\bbasin\s+mixture\b|\bshower\b", "plumbing", "bathroom"),
)
HINTS=tuple((re.compile(p, re.I), term, context) for p,term,context in HINTS)

# High-risk retail names for which this snapshot has no exact commodity.
# Do not present unrelated substitutes such as ball bearings for ball valves.
UNSUPPORTED = tuple(re.compile(p,re.I) for p in (
    r"\b(ball\s+valve|angle\s+valve|bib\s+tap|ball\s+cork)\b",
    r"\b(arabic\s+(flex|shower)|basin\s+mixture|basket\s+strainer)\b",
    r"\b(bicycle\s+oil|binding\s+wire|boss\s+white|broom)\b",
    r"\b(allan\s+keys|automatic\s+pump\s+control|asbesto\s+cable)\b",
))
# Some names unambiguously identify a product *family* but not a verified
# KRA commodity. Restrict suggestions to plausible active codes only.
FAMILY_CODES = tuple((re.compile(p,re.I), set(codes)) for p,codes in (
    (r"\b(adaptor|adapter)\s+(socket|elbow|union)\b|\bbottle\s+traps?\b", ("40180000",)),
    (r"\b(cable\s+(flex|single|t/e)|flex\s+cable)\b", ("26121629",)),
    (r"\b(13a\s+.*socket|(?:[1-9]\s*)?gang\s+switch|bell\s+switch|bed\s+switch|adaptor\s+box|cable\s+clips?)\b",("39121700",)),
    (r"\b(araldyte|epoxy|bondex)\b", ("31201601",)),
    (r"\bnails?\b",("31162400",)),
))
NONDISCRIMINATING = {"black","red","green","grean","cross","metal","plastic",
                      "white","handle","single","double","automatic","male","female"}

def normalize(value: str) -> str:
    value=unicodedata.normalize("NFKC",str(value)).lower().replace("&"," and ")
    value=re.sub(r"\b(?:\d+(?:\.\d+)?\s*(?:mm|cm|kg|gm|g|a|inch|inches))\b"," ",value)
    value=re.sub(r"\b\d+\s*x\s*\d+\b"," ",value)
    value=re.sub(r"\b\d+(?:\.\d+)?\b"," ",value)
    value=re.sub(r"[^a-z0-9]+"," ",value)
    tokens=[w for w in value.split() if w not in STOP and w not in BRANDS and len(w)>1]
    return " ".join(tokens)

def words(value: str) -> set[str]:
    return set(normalize(value).split())

class Classifier:
    def __init__(self, catalog_path: str | Path, mapping_path: str | Path | None = None):
        path=Path(catalog_path)
        self.catalog_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding="utf-8-sig",newline="") as stream:
            data=list(csv.DictReader(stream))
        self.catalog={row["ITEM_CLS_CD"].strip():row for row in data
                      if row.get("USE_YN","Y").strip()=="Y" and row.get("ITEM_CLS_CD","").strip()}
        self.entries=[]
        for code,row in self.catalog.items():
            name=row["ITEM_CLS_NM"].strip()
            self.entries.append((code,name,words(name),normalize(name)))
        frequency=Counter(t for _,_,tokens,_ in self.entries for t in tokens)
        count=len(self.entries)
        self.idf={t:math.log(1+(count+1)/(freq+1)) for t,freq in frequency.items()}
        self.memory={}
        if mapping_path and Path(mapping_path).exists():
            with Path(mapping_path).open(encoding="utf-8-sig",newline="") as stream:
                for row in csv.DictReader(stream):
                    if row.get("verified","").strip().lower() not in ("true","yes","1"):
                        continue
                    code=row.get("class_code","").strip()
                    if code in self.catalog and row.get("product_name","").strip():
                        self.memory[normalize(row["product_name"])]=code

    def _hints(self, product: str) -> list[str]:
        return [term for pattern,term,_ in HINTS if pattern.search(product)]

    def classify(self, product: str, top_k: int=3) -> dict:
        original=product.strip()
        normalized=normalize(original)
        if not normalized:
            return dict(product_name=original,status="no_candidate",top=[],reason="Empty product name")
        remembered=self.memory.get(normalized)
        if remembered:
            row=self.catalog[remembered]
            return dict(product_name=original,status="verified_mapping",reason="Reviewed mapping; validated against active catalog",
                        top=[dict(code=remembered,name=row["ITEM_CLS_NM"],score=1.0)])
        if any(p.search(original) for p in UNSUPPORTED):
            return dict(product_name=original,status="no_candidate",
                        reason="No sufficiently specific active commodity for this product in the supplied catalog",top=[])
        family=next((codes for pattern,codes in FAMILY_CODES if pattern.search(original)),None)
        hints=self._hints(original)
        product_terms=words(original)
        hint_terms=set().union(*(words(h) for h in hints)) if hints else set()
        candidates=[]
        for code,name,c_terms,norm_name in self.entries:
            if family and code not in family:continue
            if code.startswith("99") and normalized!=norm_name:continue
            direct=product_terms & c_terms
            # Words like "metal", "cross" and "white" by themselves are not
            # sufficient to associate an unknown retail item with a KRA class.
            if not family and not hints and not (direct-NONDISCRIMINATING):
                continue
            expanded=hint_terms & c_terms
            denom=sum(self.idf.get(w,1) for w in product_terms) or 1
            lexical=sum(self.idf.get(w,1) for w in direct)/denom
            hint_cov=(len(expanded)/max(len(hint_terms),1)) if hint_terms else 0
            hinted=any(normalize(h)==norm_name for h in hints)
            seq=SequenceMatcher(None,normalized,norm_name).ratio()
            # Scoring is ranking evidence, NOT a calibrated probability.
            score=.49*min(1,lexical)+.23*hint_cov+.22*seq+(.31 if hinted else 0)
            if "service" in c_terms and "service" not in product_terms:score-=.12
            if code.startswith("99") and not direct:score-=.12
            if not direct and not expanded and not hinted:score*=.45
            if score >= .16:
                candidates.append((score,code,name))
        candidates.sort(key=lambda v:(-v[0],v[1]))
        top=[dict(code=code,name=name,score=round(min(score,1.0),3))
             for score,code,name in candidates[:top_k]]
        if not top or top[0]["score"]<.32:
            status="no_candidate";reason="No sufficiently relevant active classification found"
        else:
            status="needs_review";reason="Unverified suggestion; confirm intended item classification"
        return dict(product_name=original,status=status,reason=reason,query_hints=hints,top=top)

def read_names(path: str | Path) -> list[str]:
    with Path(path).open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream)
        field="name" if "name" in reader.fieldnames else "product_name"
        if field not in (reader.fieldnames or []):
            raise ValueError("Input CSV must have a name or product_name column")
        return [r[field].strip() for r in reader if r.get(field,"").strip()]

def evaluate(predictions: list[dict], gold_file: str | Path | None = None) -> dict:
    stats=Counter(p["status"] for p in predictions)
    result=dict(total=len(predictions),status_counts=dict(stats),
                candidate_coverage=round(sum(bool(p["top"]) and p["status"]!="no_candidate" for p in predictions)/max(1,len(predictions)),4),
                verified_top1_accuracy=None,verified_top3_accuracy=None,
                labeled_count=0,remark="No independently verified classification labels were supplied.")
    if not gold_file:return result
    with Path(gold_file).open(encoding="utf-8-sig",newline="") as stream:
        gold={normalize(r["product_name"]):r["correct_code"].strip() for r in csv.DictReader(stream)
              if r.get("correct_code","").strip()}
    labeled=[(p,gold[normalize(p["product_name"])]) for p in predictions
             if normalize(p["product_name"]) in gold]
    result["labeled_count"]=len(labeled)
    if labeled:
        result["verified_top1_accuracy"]=round(sum(bool(p["top"]) and p["top"][0]["code"]==code for p,code in labeled)/len(labeled),4)
        result["verified_top3_accuracy"]=round(sum(any(c["code"]==code for c in p["top"]) for p,code in labeled)/len(labeled),4)
        result["remark"]="Accuracy measured only against explicitly supplied reviewer labels."
    return result
