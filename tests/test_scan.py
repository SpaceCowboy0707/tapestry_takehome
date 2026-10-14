"""The weekly scan must flag a steady pattern in a large enough group and leave small groups out."""
import unittest

import pandas as pd

from core.scan import label, sales_scan


def frame():
    """Two regions over weeks 1-5. Region A: 40 customers a year, every week up. Region B: 5 customers, tripled."""
    rows, cid = [], 0
    for fy, scale in (('FY25', 1.0), ('FY26', 1.5)):
        for wk in range(1, 6):
            for i in range(8):
                cid += 1
                rows.append(dict(FISCAL_YR=fy, WK=wk, DOW=1, DEMAND_AMT=100 * scale, CUST_ID=cid, GEO_REGION='A',
                                 STYLE_GROUP='X', CHANNEL_DETAIL='Retail Store', SALES_CHANNEL='RETAIL',
                                 CUST_AGE_GROUP='Gen X', COHORT_STATUS='Retained'))
        for i in range(5):
            cid += 1
            rows.append(dict(FISCAL_YR=fy, WK=1 + i, DOW=1, DEMAND_AMT=200 * (3 if fy == 'FY26' else 1), CUST_ID=cid,
                             GEO_REGION='B', STYLE_GROUP='Y', CHANNEL_DETAIL='eComm', SALES_CHANNEL='RETAIL',
                             CUST_AGE_GROUP='Gen X', COHORT_STATUS='Retained'))
    return pd.DataFrame(rows)


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.out = sales_scan(frame(), dict(wk=5, dow=6), [1, 2, 3, 4, 5])

    def test_flags_a_steady_rise_in_a_large_group(self):
        a = next(f for f in self.out['top'] if f['parts'] == [('GEO_REGION', 'A')])
        self.assertEqual(a['pattern'], 'streak_up')
        self.assertEqual(a['streak'], 5)

    def test_leaves_small_groups_out_and_counts_them(self):
        self.assertFalse(any(('GEO_REGION', 'B') in f['parts'] for f in self.out['top']))
        self.assertGreater(self.out['small_excluded'], 0)

    def test_labels_read_plainly(self):
        self.assertEqual(label([('GEO_REGION', 'Greater China'), ('CHANNEL_DETAIL', 'Retail Store')]), 'Greater China stores')
        self.assertEqual(label([('SEG', 'gen_z_new'), ('GEO_REGION', 'Europe')]), 'First-time Gen Z · Europe')


if __name__ == '__main__':
    unittest.main()
