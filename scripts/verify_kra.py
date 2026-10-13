"""Compare classifier suggestions to a separate authorized KRA classification export.

This checks whether predicted category codes and labels agree with the export.
It DOES NOT prove the original retail product was assigned the correct category.
"""
from pathlib import Path
import argparse
import csv
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from classifier import Classifier,read_names,normalize
from kra_reference import audit,load_reference

ROOT=Path(__file__).resolve().parents[1]
def run(reference_file,products_file,catalog_file,out_dir,gold_file=None):
    ref,provenance=load_reference(reference_file)
    classifier=Classifier(catalog_file)
    predictions=[classifier.classify(n) for n in read_names(products_file)]
    gold={}
    if gold_file:
        with Path(gold_file).open(encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                name=row.get("product_name","").strip()
                code=row.get("correct_code","").strip()
                if name and code: gold[name]=code
    rows=audit(predictions,ref,gold)
    out_dir=Path(out_dir)
    out_dir.mkdir(parents=True,exist_ok=True)
    cols=["product_name","rank","predicted_code","predicted_name","official_name",
          "catalog_status","product_correctness"]
    with (out_dir/"kra_validation.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
    top1=[row for row in rows if row["rank"]==1]
    from collections import Counter
    stats=Counter(r["catalog_status"] for r in top1)
    report={"products":len(predictions),"suggested_top1":len(top1),
            "top1_catalog_status_counts":dict(stats),"reference":provenance,
            "independent_product_labels_provided":len(gold),
            "product_accuracy_measured":False if not gold else True,
            "warning":"KRA catalog membership validates a code, not the semantic assignment of a SKU.",
            "external_source": "provided_export_only; no live KRA API query performed"}
    if gold:
        labeled=[r for r in top1 if r["product_name"] in gold]
        report["top1_product_accuracy_on_labeled_predictions"]=(
            round(sum(r["predicted_code"]==gold[r["product_name"]] for r in labeled)/len(labeled),4)
            if labeled else None)
        report["labeled_predictions"]=len(labeled)
        # Include missing predictions as errors when reporting all labeled product accuracy.
        by_name={p["product_name"]:p for p in predictions}
        evaluated=[(name,p) for name,p in by_name.items() if name in gold]
        report["top1_accuracy_on_all_labeled_products"]=(
            round(sum(bool(p["top"]) and p["top"][0]["code"]==gold[name] for name,p in evaluated)/len(evaluated),4)
            if evaluated else None)
    (out_dir/"kra_validation_summary.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--official-export",type=Path,required=True,
                        help="Authorized KRA item classification JSON response or portal CSV export; do not use guessed data")
    parser.add_argument("--products",type=Path,default=ROOT/"data/test_products.csv")
    parser.add_argument("--catalog",type=Path,default=ROOT/"data/etims_item_classes.csv")
    parser.add_argument("--out",type=Path,default=ROOT/"reports")
    parser.add_argument("--gold",type=Path,help="Independent product_name,correct_code reviewer labels")
    args=parser.parse_args()
    run(args.official_export,args.products,args.catalog,args.out,args.gold)
