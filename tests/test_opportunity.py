"""Opportunity rule: picks the fastest-growing family with first-time Gen Z that still has stock."""
import contextlib
import io
import unittest


class OpportunityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            import build
            _, data = build.build()
        cls.o = data['opportunity']

    def test_rule_skips_families_short_of_stock(self):
        results = {r[0]: r[-1] for r in self.o['rows']}
        self.assertEqual(results['Brooklyn'], 'Picked')
        self.assertTrue(results['Tabby'].startswith('Excluded'))
        self.assertTrue(results['Pillow Tabby'].startswith('Excluded'))

    def test_recorded_card_passes_and_labels_the_explanation_a_hypothesis(self):
        self.assertEqual(self.o['status'], 'ok')
        kinds = {i['kind'] for s in self.o['card']['sections'] for i in s['items']}
        self.assertIn('hypothesis', kinds)


if __name__ == '__main__':
    unittest.main()
