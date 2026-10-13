import csv
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from classifier import Classifier,evaluate,read_names

ROOT=Path(__file__).resolve().parents[1]
class ClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=Classifier(ROOT/"data/etims_item_classes.csv")
    def test_real_catalog_is_present(self):
        self.assertGreater(len(self.model.catalog),1000)
        self.assertIn("26121629",self.model.catalog)
    def test_cables_retrieve_active_power_cable(self):
        r=self.model.classify("1.5mm Cable Flex")
        self.assertIn("26121629",[x["code"] for x in r["top"]])
        self.assertEqual(r["status"],"needs_review")
    def test_plumbing_socket_is_not_wall_socket(self):
        r=self.model.classify("Adaptor Socket 20x1/2 female")
        self.assertIn("40180000",[x["code"] for x in r["top"]])
    def test_no_off_catalog_codes_can_appear(self):
        for name in read_names(ROOT/"data/test_products.csv"):
            r=self.model.classify(name)
            self.assertTrue(all(c["code"] in self.model.catalog for c in r["top"]))
    def test_no_ground_truth_means_no_accuracy_claim(self):
        r=[self.model.classify("1.0mm Cable Flex")]
        e=evaluate(r)
        self.assertIsNone(e["verified_top1_accuracy"])
        self.assertIsNone(e["verified_top3_accuracy"])
    def test_verified_mapping_takes_priority_and_validates_code(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"verified.csv"
            with path.open("w",newline="") as f:
                w=csv.writer(f);w.writerow(["product_name","class_code","verified"])
                w.writerow(["Workshop SKU","26121629","true"])
                w.writerow(["Invalid SKU","00000000","true"])
            m=Classifier(ROOT/"data/etims_item_classes.csv",path)
            self.assertEqual(m.classify("Workshop SKU")["status"],"verified_mapping")
            self.assertEqual(m.classify("Workshop SKU")["top"][0]["code"],"26121629")
            self.assertNotEqual(m.classify("Invalid SKU")["status"],"verified_mapping")
    def test_ground_truth_evaluation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"gold.csv"
            with path.open("w",newline="") as f:
                w=csv.writer(f);w.writerow(["product_name","correct_code"])
                w.writerow(["1.0mm Cable Flex","26121629"])
            r=[self.model.classify("1.0mm Cable Flex")]
            metrics=evaluate(r,path)
            self.assertEqual(metrics["labeled_count"],1)
            self.assertEqual(metrics["verified_top3_accuracy"],1.0)
if __name__=="__main__":unittest.main()
