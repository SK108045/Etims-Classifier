"""Run rankings against real eTIMS catalog. Writes reviewable CSV + honest metrics."""
import argparse
import csv
import json
from time import perf_counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from classifier import Classifier,read_names,evaluate,normalize

ROOT=Path(__file__).resolve().parents[1]

def run(catalog,products,output,mappings=None,gold=None):
    started=perf_counter()
    classifier=Classifier(catalog,mappings)
    names=read_names(products)
    results=[classifier.classify(name) for name in names]
    processing_seconds=round(perf_counter()-started,3)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    columns=["product_name","status","reason","query_hints"]
    for i in range(1,4):columns+= [f"top{i}_code",f"top{i}_category",f"top{i}_ranking_score"]
    with (output/"predictions.csv").open("w",encoding="utf-8",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
        for r in results:
            row={k:r.get(k,"") for k in columns}
            row["query_hints"]="; ".join(r.get("query_hints",[]))
            for i,c in enumerate(r["top"],1):
                if i>3:break
                row.update({f"top{i}_code":c["code"],f"top{i}_category":c["name"],
                            f"top{i}_ranking_score":c["score"]})
            writer.writerow(row)
    review=output/"review_template.csv"
    if not review.exists():
        with review.open("w",encoding="utf-8",newline="") as file:
            writer=csv.writer(file);writer.writerow(["product_name","suggested_top1","correct_code","review_notes"])
            for r in results:
                writer.writerow([r["product_name"],r["top"][0]["code"] if r["top"] else "","",""])
    summary=evaluate(results,gold)
    distinct={}
    for prediction in results:
        distinct.setdefault(normalize(prediction["product_name"]),prediction)
    summary["distinct_normalized_names"]=len(distinct)
    summary["distinct_candidate_coverage"]=round(
        sum(p["status"]!="no_candidate" for p in distinct.values())/max(1,len(distinct)),4)
    summary.update(processing_seconds=processing_seconds,catalog_entries=len(classifier.catalog),catalog_sha256=classifier.catalog_sha256,
                   source_catalog=str(catalog),input_file=str(products),
                   policy="All unverified model suggestions require review. Ranking scores are not probabilities.")
    (output/"metrics.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print("Ranked results:",output/"predictions.csv")
    print("Reviewer gold template:",review)
    return summary

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--catalog",default=ROOT/"data/etims_item_classes.csv",type=Path)
    parser.add_argument("--products",default=ROOT/"data/test_products.csv",type=Path)
    parser.add_argument("--out",default=ROOT/"reports",type=Path)
    parser.add_argument("--mappings",type=Path,help="Optional reviewed product_name,class_code,verified CSV")
    parser.add_argument("--gold",type=Path,help="Optional independent product_name,correct_code labels")
    args=parser.parse_args()
    run(args.catalog,args.products,args.out,args.mappings,args.gold)
