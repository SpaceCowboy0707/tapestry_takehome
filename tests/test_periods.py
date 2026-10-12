"""The week in progress must be compared with the same weekdays, never with a full week."""
import unittest

import pandas as pd

from core.periods import add_period_cols, as_of, windows


def frame():
    rows = []
    # Last year: weeks 29 and 30 complete (Sun 2025-08-10 .. Sat 2025-08-23); this year: week 29 complete, week 30 Sun-Wed.
    for fy, start, days in (('FY25', '2025-08-10', 14), ('FY26', '2026-08-09', 11)):
        for i, d in enumerate(pd.date_range(start, periods=days)):
            wk = 29 if i < 7 else 30
            rows.append(dict(TXN_DT=d, FISCAL_YR=fy, FISCAL_WK=f'{fy} W{wk}', DEMAND_AMT=100.0))
    return add_period_cols(pd.DataFrame(rows))


class Periods(unittest.TestCase):
    def test_as_of_is_the_last_date_with_this_years_data(self):
        ref = as_of(frame())
        self.assertEqual((str(ref['date'].date()), ref['wk'], ref['dow']), ('2026-08-19', 30, 3))

    def test_week_to_date_uses_the_same_weekdays_last_year(self):
        w = windows(frame(), as_of(frame()))
        self.assertEqual(len(w['wtd']['ty']), 4)
        self.assertEqual(len(w['wtd']['ly']), 4)   # Sun-Wed only, not the full LY week

    def test_period_to_date_stops_on_the_same_weekday_last_year(self):
        w = windows(frame(), as_of(frame()))
        self.assertEqual(len(w['ptd']['ty']), 11)
        self.assertEqual(len(w['ptd']['ly']), 11)

    def test_last_week_is_trimmed_to_the_same_weekdays(self):
        w = windows(frame(), as_of(frame()))
        self.assertEqual(len(w['last_week']['ty']), 4)


if __name__ == '__main__':
    unittest.main()
