"""Fiscal calendar helpers: as-of date, WTD and PTD windows aligned to the same fiscal days LY."""
import pandas as pd

TY, LY = 'FY26', 'FY25'
DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']


def add_period_cols(df):
    df = df.copy()
    df['WK'] = df['FISCAL_WK'].str[-2:].astype(int)
    df['DOW'] = (df['TXN_DT'].dt.dayofweek + 1) % 7  # fiscal weeks run Sun (0) to Sat (6)
    return df


def as_of(df):
    """The reporting date is the last date with TY data, never the system clock."""
    ty = df[df.FISCAL_YR == TY]
    d = ty.TXN_DT.max()
    row = ty[ty.TXN_DT == d].iloc[0]
    return dict(date=d, wk=int(row.WK), dow=int(row.DOW))


def _ly_date(df, wk, dow):
    ly = df[(df.FISCAL_YR == LY) & (df.WK == wk) & (df.DOW == dow)]
    return ly.TXN_DT.min() if len(ly) else None


def windows(df, ref):
    """Return the TY and LY slices for Yesterday, WTD and PTD.

    LY is matched on fiscal week and weekday (Wed W30 vs Wed W30), not on calendar date.
    Yesterday has no LY slice: single-day samples are too small for a YoY read.
    """
    wk, dow = ref['wk'], ref['dow']
    ty, ly = df[df.FISCAL_YR == TY], df[df.FISCAL_YR == LY]
    to_date = lambda x: x[(x.WK < wk) | ((x.WK == wk) & (x.DOW <= dow))]
    first_wk = int(df.WK.min())
    wtd_ty, wtd_ly = ty[(ty.WK == wk) & (ty.DOW <= dow)], ly[(ly.WK == wk) & (ly.DOW <= dow)]
    return {
        'yesterday': dict(ty=ty[ty.TXN_DT == ref['date']], ly=None,
                          label=f"{DAY_NAMES[dow]} {ref['date']:%b %-d}"),
        'wtd': dict(ty=wtd_ty, ly=wtd_ly,
                    label=f"W{wk} {DAY_NAMES[0]}–{DAY_NAMES[dow]}",
                    ty_range=(wtd_ty.TXN_DT.min(), wtd_ty.TXN_DT.max()),
                    ly_range=(wtd_ly.TXN_DT.min(), wtd_ly.TXN_DT.max())),
        # Last week on the same weekdays, so a week in progress is never compared with a full week.
        'last_week': dict(ty=ty[(ty.WK == wk - 1) & (ty.DOW <= dow)]),
        'ptd': dict(ty=to_date(ty), ly=to_date(ly),
                    label=f"W{first_wk}–W{wk} {DAY_NAMES[dow]}",
                    ty_range=(to_date(ty).TXN_DT.min(), to_date(ty).TXN_DT.max()),
                    ly_range=(to_date(ly).TXN_DT.min(), to_date(ly).TXN_DT.max())),
    }
