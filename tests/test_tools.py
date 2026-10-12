"""The chat tools: arguments are checked before anything runs, and results agree with the dashboard's measures."""
import unittest

import pandas as pd

from build import SOURCE
from core.brief import fmt_value, validate
from core.inventory import add_inventory_cols, inventory_view
from core.metrics import MEASURES
from core.periods import add_period_cols, as_of, windows
from core.tools import Toolbox, ToolError


class ToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df = add_period_cols(pd.read_excel(SOURCE, sheet_name='Data'))
        inv = add_inventory_cols(pd.read_excel(SOURCE, sheet_name='Inventory'))
        ref = as_of(df)
        cls.win = windows(df, ref)
        cls.tb = Toolbox(cls.win, inventory_view(df, inv, ref, cls.win['ptd']), fmt_value)

    def run_call(self, tool, **args):
        return self.tb.run(dict(id='c1', tool=tool, args=args))

    def test_rejects_unknown_tool_measure_dimension_and_value(self):
        with self.assertRaises(ToolError):
            self.run_call('forecast', measure='net_sales')
        with self.assertRaises(ToolError):
            self.run_call('compare', measure='profit')
        with self.assertRaises(ToolError):
            self.run_call('breakdown', measure='net_sales', by='store_id')
        with self.assertRaises(ToolError):
            self.run_call('compare', measure='net_sales', where={'age_group': 'Gen Alpha'})
        with self.assertRaises(ToolError):
            self.run_call('stock', families=['Tote'])

    def test_compare_matches_dashboard_measure(self):
        r = self.run_call('compare', measure='net_sales')
        self.assertAlmostEqual(r['facts']['c1_ty']['value'], MEASURES['net_sales']['fn'](self.win['ptd']['ty']))

    def test_breakdown_members_add_up(self):
        whole = self.run_call('compare', measure='customers', where={'age_group': 'Gen Z'})['facts']['c1_ty']['value']
        parts = self.run_call('breakdown', measure='customers', by='customer_type', where={'age_group': 'Gen Z'})['facts']
        self.assertEqual(parts['c1_first_time_ty']['value'] + parts['c1_returning_ty']['value'], whole)

    def test_answer_may_cite_only_its_tool_results(self):
        facts = self.run_call('compare', measure='aov')['facts']
        ok = dict(headline='Orders average {c1_ty}.', sections=[dict(title='A', items=[dict(kind='fact', text='Up {c1_yoy}.')])])
        bad = dict(headline='Orders average {c2_ty}.', sections=[dict(title='A', items=[dict(kind='fact', text='About $300.')])])
        self.assertTrue(validate(ok, facts)['passed'])
        self.assertFalse(validate(bad, facts)['passed'])


if __name__ == '__main__':
    unittest.main()
