import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from kra_reference import ReferenceFormatError,load_reference,audit
from verify_kra import run

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=ROOT/"tests/fixtures/reference_shape_example.json"

class ReferenceTests(unittest.TestCase):
    def test_official_response_structure_from_documentation(self):
        refs,meta=load_reference(SAMPLE)
        self.assertEqual(refs["8411160300"]["name"],"Internal audits")
        self.assertEqual(meta["active_codes"],3)
    def test_code_membership_is_not_correctness(self):
        ref,_=load_reference(SAMPLE)
        # Real code + correct description is still not proof that a random item
        # should be classified as that code.
        rows=audit([dict(product_name="Bicycle oil",
                         top=[dict(code="26121629",name="Power cable",score=.99)])],ref)
        self.assertEqual(rows[0]["catalog_status"],"code_and_name_confirmed")
        self.assertEqual(rows[0]["product_correctness"],"unverified_no_gold_label")
    def test_unknown_code_and_wrong_name_are_distinguished(self):
        ref,_=load_reference(SAMPLE)
        preds=[dict(product_name="Product X",top=[
            dict(code="00000000",name="Unknown"),dict(code="26121629",name="Rubber tyres")])]
        rows=audit(preds,ref)
        self.assertEqual(rows[0]["catalog_status"],"not_in_reference")
        self.assertEqual(rows[1]["catalog_status"],"name_conflict")
    def test_csv_export_supported(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"items.csv"
            with f.open("w",newline="") as stream:
                writer=csv.writer(stream)
                writer.writerow(["ITEM_CLS_CD","ITEM_CLS_NM","USE_YN"])
                writer.writerow(["26121629","Power cable","Y"])
                writer.writerow(["40180000","Tubes tubing and tube fittings","N"])
            ref,_=load_reference(f)
            self.assertEqual(list(ref),["26121629"])
    def test_rejects_malformed_reference(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ref.json"
            path.write_text(json.dumps({"data":{"itemClsList":[{"itemClsCd":"FAKE","itemClsNm":"Invalid"}]}}))
            with self.assertRaises(ReferenceFormatError):
                load_reference(path)
    def test_end_to_end_external_code_report(self):
        with tempfile.TemporaryDirectory() as d:
            result=run(SAMPLE,ROOT/"data/test_products.csv",
                       ROOT/"data/etims_item_classes.csv",Path(d)/"audit")
            self.assertEqual(result["products"],100)
            self.assertFalse(result["product_accuracy_measured"])
            self.assertTrue((Path(d)/"audit/kra_validation.csv").exists())
if __name__=="__main__":
    unittest.main()
