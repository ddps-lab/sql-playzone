import importlib.machinery
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("regrade", str(ROOT / "scripts" / "regrade-challenges"))
spec = importlib.util.spec_from_loader("regrade", loader)
regrade = importlib.util.module_from_spec(spec)
loader.exec_module(regrade)


class ReviewHeuristicsTests(unittest.TestCase):
    def test_order_by_columns(self):
        self.assertIsNone(regrade.order_by_columns("SELECT a FROM t"))
        self.assertEqual(regrade.order_by_columns("SELECT a, b FROM t ORDER BY b DESC, t.a LIMIT 10"), ["b", "a"])
        self.assertEqual(regrade.order_by_columns("SELECT a FROM t ORDER BY ABS(a - 1) DESC, a;"), ["a"])
        self.assertEqual(regrade.order_by_columns("SELECT a FROM t ORDER BY 1"), ["1"])

    def test_tie_rows(self):
        rows = [["190", "Kim"], ["190", "Lee"], ["180", "Park"]]
        self.assertEqual(regrade.tie_rows(["HEIGHT"], ["HEIGHT", "NAME"], rows), 2)
        self.assertEqual(regrade.tie_rows(["height", "name"], ["HEIGHT", "NAME"], rows), 0)
        self.assertIsNone(regrade.tie_rows(["missing"], ["HEIGHT", "NAME"], rows))
        self.assertEqual(regrade.tie_rows(["1"], ["HEIGHT", "NAME"], rows), 2)

    def test_review_findings(self):
        ok = {"status": "ok", "rows": [["190", "Kim"], ["190", "Lee"]], "columns": ["HEIGHT", "NAME"], "row_count": 2, "elapsed_ms": 100}
        findings = regrade.review_findings({"solution_query": "SELECT HEIGHT, NAME FROM P ORDER BY HEIGHT DESC"}, ok, 1500)
        self.assertTrue(any("정렬 키 값이 같은 행 2개" in f for f in findings))
        findings = regrade.review_findings({"solution_query": "SELECT HEIGHT, NAME FROM P ORDER BY HEIGHT DESC, NAME"}, ok, 1500)
        self.assertEqual(findings, [])
        findings = regrade.review_findings({"solution_query": "SELECT AVG(H) FROM P"}, {"status": "ok", "rows": [["183.0901"]], "columns": ["AVG(H)"], "row_count": 1, "elapsed_ms": 2000}, 1500)
        self.assertTrue(any("ROUND" in f for f in findings) and any("2000ms" in f for f in findings))
        self.assertTrue(regrade.review_findings({"solution_query": "SELECT 1"}, {"status": "query_error", "error": "boom"}, 1500)[0].startswith("실행 실패"))

    def test_numeric_equal_tolerates_precision(self):
        self.assertTrue(regrade.numeric_equal("72220.1111", "72220.11111111111"))
        self.assertFalse(regrade.numeric_equal("1", "2"))


if __name__ == "__main__":
    unittest.main()
