"""Inventory: stock on hand, recent sell rate and weeks of cover per product family, TY vs LY.

Sales in the extract look sampled (weekly units sold are far below units on hand), so absolute weeks of
cover overstate real cover. Read it against LY and as a ranking; the thresholds below are placeholders
to be set from the replenishment lead time.
"""
from core.metrics import MEASURES
from core.periods import TY, LY

RATE_WEEKS = 4         # sell rate = average weekly units over the last N complete weeks
RISK_WEEKS = 4         # cover below this: stock-out risk
OVERSTOCK_WEEKS = 12   # cover above this: overstock


def add_inventory_cols(inv):
    inv = inv.copy()
    inv['WK'] = inv['FISCAL_WK'].str[-2:].astype(int)
    return inv


def status(cover):
    if cover is None: return 'no_sales'
    if cover < RISK_WEEKS: return 'risk'
    if cover > OVERSTOCK_WEEKS: return 'overstock'
    return 'ok'


def _cover(on_hand, rate):
    return on_hand / rate if rate else None


def inventory_view(sales, inv, ref, ptd):
    """One row per STYLE_GROUP plus totals.

    on_hand is the latest snapshot; the sell rate uses the last RATE_WEEKS complete sales weeks
    (the as-of week is excluded while it is still in progress). LY uses the same fiscal weeks.
    """
    units, net_sales = MEASURES['units']['fn'], MEASURES['net_sales']['fn']
    last_full = ref['wk'] if ref['dow'] == 6 else ref['wk'] - 1
    rate_weeks = list(range(last_full - RATE_WEEKS + 1, last_full + 1))
    snap_wk = int(inv[inv.FISCAL_YR == TY].WK.max())
    weeks = sorted(int(w) for w in inv.WK.unique() if w <= snap_wk)

    groups = sorted(set(inv.STYLE_GROUP))
    missing = set(sales.STYLE_GROUP) - set(groups)
    assert not missing, f'style groups with sales but no inventory rows: {missing}'
    meta = sales.drop_duplicates('STYLE_GROUP').set_index('STYLE_GROUP')[['PROD_TYPE', 'PROD_CATEGORY']]

    def side(fy, g=None):
        s = sales[(sales.FISCAL_YR == fy) & sales.WK.isin(rate_weeks)]
        i = inv[inv.FISCAL_YR == fy]
        if g is not None:
            s, i = s[s.STYLE_GROUP == g], i[i.STYLE_GROUP == g]
        rate = units(s) / RATE_WEEKS
        by_wk = i.groupby('WK').ON_HAND_UNITS.sum()
        on_hand = int(by_wk.get(snap_wk, 0))
        return dict(on_hand=on_hand, rate=round(rate, 2), cover=_cover(on_hand, rate),
                    series=[int(by_wk.get(w, 0)) for w in weeks])

    def demand(g=None):
        t, l = ptd['ty'], ptd['ly']
        if g is not None:
            t, l = t[t.STYLE_GROUP == g], l[l.STYLE_GROUP == g]
        a, b = net_sales(t), net_sales(l)
        return dict(ty=a, ly=b, yoy=(a / b - 1) if b else None)

    rows = []
    for g in groups:
        ty, ly = side(TY, g), side(LY, g)
        rows.append(dict(name=g, prod_type=meta.loc[g, 'PROD_TYPE'], category=meta.loc[g, 'PROD_CATEGORY'],
                         ty=ty, ly=ly, status=status(ty['cover']), sales=demand(g)))
    rows.sort(key=lambda r: (r['ty']['cover'] is None, r['ty']['cover'] or 0))

    by_type = {}
    for t in sorted(set(meta.PROD_TYPE)):
        members = [r for r in rows if r['prod_type'] == t]
        tot = {}
        for fy in ('ty', 'ly'):
            oh = sum(r[fy]['on_hand'] for r in members)
            rate = sum(r[fy]['rate'] for r in members)
            tot[fy] = dict(on_hand=oh, rate=round(rate, 2), cover=_cover(oh, rate))
        by_type[t] = tot

    total = dict(ty=side(TY), ly=side(LY))
    return dict(snapshot_week=snap_wk, rate_weeks=rate_weeks, weeks=weeks,
                thresholds=dict(rate_weeks=RATE_WEEKS, risk=RISK_WEEKS, overstock=OVERSTOCK_WEEKS),
                total=total, by_type=by_type, rows=rows,
                counts={s: sum(r['status'] == s for r in rows) for s in ('risk', 'ok', 'overstock', 'no_sales')})


def cover_at(sales, inv, snap_wk, last_rate_wk):
    """This year's weeks of stock left and status per family, as they stood at an earlier snapshot.

    Same definition as inventory_view: stock at snap_wk ÷ average weekly units over the RATE_WEEKS
    complete weeks ending at last_rate_wk. Used to say what changed since last week.
    """
    units = MEASURES['units']['fn']
    weeks = list(range(last_rate_wk - RATE_WEEKS + 1, last_rate_wk + 1))
    s = sales[(sales.FISCAL_YR == TY) & sales.WK.isin(weeks)]
    i = inv[(inv.FISCAL_YR == TY) & (inv.WK == snap_wk)].set_index('STYLE_GROUP').ON_HAND_UNITS
    out = {}
    for g in sorted(set(inv.STYLE_GROUP)):
        rate = units(s[s.STYLE_GROUP == g]) / RATE_WEEKS
        cover = _cover(int(i.get(g, 0)), rate)
        out[g] = dict(cover=cover, status=status(cover))
    return out
