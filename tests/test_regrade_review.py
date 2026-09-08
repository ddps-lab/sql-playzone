import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('regrade', str(Path(__file__).resolve().parents[1] / 'scripts/regrade-challenges'))
spec = importlib.util.spec_from_loader(loader.name, loader)
regrade = importlib.util.module_from_spec(spec)
loader.exec_module(regrade)

class ReviewTests(unittest.TestCase):
    def test_missing_policy_cannot_pass_deployment_review(self):
        with patch.object(regrade.urllib.request, 'urlopen') as network:
            result = regrade.call_judge('http://unused', {'id':1}, 1)
        network.assert_not_called()
        self.assertEqual(result['status'], 'policy_required')

    def test_declared_bag_and_ties_do_not_require_invented_tiebreakers(self):
        challenge={'solution_query':'SELECT AVG(h) FROM t', 'grading_policy':{'version':1,'order_by':[],'exact_format_columns':[]}}
        result={'status':'ok','rows':[['1.00'],['1.00']],'columns':['avg'],'row_count':2,'elapsed_ms':100}
        self.assertEqual(regrade.review_findings(challenge,result,1500),[])
        result['elapsed_ms']=2000
        self.assertEqual(len(regrade.review_findings(challenge,result,1500)),1)

    def test_numeric_reporting_cannot_hide_rounding_differences_or_null(self):
        for left,right in [('72220.1111','72220.11111111111'),('183.0901','183.0900900900901'),('1000000','1000001'),('NaN','NaN'),(None,'NULL')]:
            self.assertFalse(regrade.numeric_equal(left,right))
        self.assertTrue(regrade.numeric_equal('8510700.00','8510700'))
        self.assertTrue(regrade.numeric_equal('4017733','4.017733e+06'))
        self.assertEqual(regrade.compare({'status':'ok','rows':[[None]]},{'status':'ok','rows':[['NULL']]} )['diff'],'value')
