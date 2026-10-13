# Oraforge eTIMS Classifier — lightweight benchmark

**Goal:** rank real eTIMS item classifications for retail product names without a large ML model, GPU or paid AI API. This is a research prototype, not a KRA-approved classification service.

## Included

- **Real classification data:** [data/etims_item_classes.csv](data/etims_item_classes.csv) copied from the [eTIMS Companion item-class snapshot](https://github.com/SK108045/Etims-companion/blob/main/product-import-helper/item-classes.csv). It has 1,379 classification rows, including 1,378 marked active. These codes are not guaranteed to match another merchant's current eTIMS installation.
- **Real hardware-shop products:** [data/test_products.csv](data/test_products.csv) has the 100 product names from the supplied Supabase CSV. Prices were omitted because selling prices do not determine product categories.
- **Classifier:** [src/classifier.py](src/classifier.py) is Python-standard-library only: normalization, keyword matching, lexical similarity, product-family checks, code validation, reviewed mapping memory and safe abstention. No neural model downloads.
- **Benchmark:** [scripts/benchmark.py](scripts/benchmark.py) writes ranked suggestions, reviewer templates and metrics.
- **CI:** [GitHub Actions](https://github.com/SK108045/Etims-Classifier/actions/workflows/test.yml) runs tests and publishes a downloadable benchmark ZIP.

## Run it

Python 3.10+ — no pip dependencies.

    python -m unittest discover -s tests -v
    python scripts/benchmark.py --out reports

You can also run the original user export directly:

    python scripts/benchmark.py --products "Supabase Snippet Untitled query.csv" --out reports

Output:
- **reports/predictions.csv:** suggested top-1/top-2/top-3 codes and names for each product; scores are ranking signals, NOT probabilities.
- **reports/review_template.csv:** fill the correct_code column after independent review.
- **reports/metrics.json:** total rows, suggested-candidate coverage, status counts and catalog fingerprint.

## Measure actual correctness

The input file has names and prices but **no verified correct classification codes**. Therefore, model accuracy, precision and recall CANNOT be claimed from this CSV alone. The reported candidate coverage is not accuracy.

To compute evaluated top-1/top-3 accuracy, independently fill correct_code in the review template and run:

    python scripts/benchmark.py --gold reports/review_template.csv --out reports

To reuse separately verified matches later, pass a CSV with columns: product_name,class_code,verified. The model reads rows where verified is true and the code is currently active.

    python scripts/benchmark.py --mappings verified_mappings.csv --out reports

All unverified predictions remain **needs_review**. The engine abstains when the matching product category isn't adequately covered. In particular, tests reject known absurd matches like *ball valve → ball bearings*, *angle valve → Red Cross supply*, and *bicycle oil → microscope immersion oil*.

## Safety and actual eTIMS integration

The code never creates tax invoices or changes any KRA/eTIMS records. It only studies a local catalog snapshot. The KRA desktop's **active ITEM_CLASS** codes remain authoritative when registering products; a correct external UNSPSC code can still be absent from the installed client. Classification, tax treatment and merchant SKU registration are separate concerns.

Use a supported classification-master-data refresh where needed. Don't inject unsupported codes or force approximate categories. For real-client deployment, require an independently verified mapping and revalidate it against the merchant's active eTIMS code list before registration.


## Verify predictions against a separate, authoritative KRA classification export

KRA's official VSCU Specification v2.0, section 3.3.2.2 ItemCls, documents the classification endpoint **/itemClass/selectItemsClass**. It returns item class code (itemClsCd), name (itemClsNm), and level (itemClsLvl). The request contains a taxpayer PIN, branch ID, and last-request timestamp. The eTIMS Online Portal also provides an authenticated **Search item classification** interface.

Official sources:
- [KRA VSCU Specification](https://www.kra.go.ke/images/publications/VSCU_Specification_Document_v2.0.pdf)
- [KRA Online Portal guide](https://www.kra.go.ke/images/publications/eTIMS-Onlineportal-User-guide-2024.pdf)
- [2026 Online Portal guide](https://www.kra.go.ke/images/publications/NEW-Online-Portal-Userguide-2026.pdf)

An actual current official KRA catalog export must be obtained through an authorized KRA interface or integration. This repository has **NO live authenticated KRA access**. The bundled CSV is a snapshot of an installed eTIMS client, not a fetched live public API. The tiny JSON response in tests/fixtures is strictly a format-test fixture, NOT a current full catalog.

After obtaining an approved official JSON response (with an itemClsList list) or an official classification CSV, run:

    python scripts/verify_kra.py --official-export "my_authorized_kra_classifications.json" --out reports/kra_check

Outputs:
- reports/kra_check/kra_validation.csv: per-product code, class name, catalog membership, product verification status.
- reports/kra_check/kra_validation_summary.json: source SHA-256, category/code coverage, explicit warnings.

**Code-and-name confirmed** means the separate KRA catalog recognizes the suggested code/name. It does not prove that your hardware-shop product belongs in that category. A product's actual correct class needs a documented independent reference/reviewer label. To measure accuracy against reviewed original product labels:

    python scripts/verify_kra.py --official-export "my_authorized_kra_classifications.json" --gold reviewed_product_codes.csv --out reports/kra_check
    python scripts/benchmark.py --gold reviewed_product_codes.csv --out reports

The reviewer labels CSV needs two columns: product_name,correct_code. The correct code must be independently chosen from the official classes, not blindly copied from our suggested top-1. Real classification accuracy and precision are currently UNKNOWN.

Security: **do not commit tax identifiers, seller credentials, personal data, or private raw API responses into this public GitHub repo**. Use sanitized classification-only exports where permitted.
