"""Weekly scan: find the slices of the business whose sales move in a notable way, by fixed rules.

The brief's facts are chosen by hand, so on their own they only cover the angles someone thought of. The scan
goes through every region, product family, store vs online, full-price vs outlet and customer group, alone and in
pairs, and flags a slice when one of these patterns holds over the complete weeks:

  - streak:   the latest weeks in a row all above (or all below) the same week last year
  - speed:    the change vs last year in the latest weeks is much stronger or weaker than in the earlier weeks
  - against:  the slice moves the other way from the business as a whole

Small groups are left out (fewer than SMALL_BASE customers in either year), and so are slices whose change is
too small to matter. What remains is ranked by how far the slice's sales sit from what its parent's trend would
give it: the total for a single slice, and for a pair (say first-time Gen Z in North America) the closer of its
two parents, so a pair only ranks high when it differs from both. The list leads with what is different, not with
what is simply large. The scan only picks
and measures; the brief may cite its values like any other fact.
"""
import itertools

from core.metrics import SEGMENTS, SMALL_BASE

DIMS = {'GEO_REGION': 'Region', 'STYLE_GROUP': 'Product family', 'CHANNEL_DETAIL': 'Store vs online',
        'SALES_CHANNEL': 'Full-price vs outlet', 'SEG': 'Customer group'}
NAMES = {'CHANNEL_DETAIL': {'Retail Store': 'stores', 'eComm': 'online'},
         'SALES_CHANNEL': {'RETAIL': 'full-price stores', 'OUTLET': 'outlets'},
         'SEG': {'gen_z_new': 'first-time Gen Z', 'gen_z_repeat': 'returning Gen Z',
                 'other_new': 'first-time customers of other generations',
                 'other_repeat': 'returning customers of other generations'}}
STREAK_MIN = 4          # weeks in a row
SPEED_GAP = 0.25        # points of change vs last year between the earlier and the latest weeks
AGAINST_MIN = 0.10      # a slice moving the other way must be at least this far from last year
IMPACT_SHARE = 0.02     # change in sales must be at least this share of total growth
RECENT_WEEKS = 3        # the latest complete weeks; the earlier complete weeks are the rest
TOP_SINGLE = 4          # single slices kept (one region, one family, one customer group...)
TOP_PAIR = 4            # pairs kept, ranked separately so single slices don't crowd them out


def label(parts):
    """Plain name for a slice: 'Greater China stores', 'Tabby online', 'First-time Gen Z · North America'."""
    by = dict(parts)
    cap = lambda t: t[0].upper() + t[1:]
    seg = NAMES['SEG'].get(by.pop('SEG', None))
    channel = [NAMES[c][by.pop(c)] for c in ('CHANNEL_DETAIL', 'SALES_CHANNEL') if c in by]
    rest = list(by.values())
    if seg:
        return cap(' · '.join([seg] + rest + channel))
    if rest and channel:
        return f"{rest[0]} {channel[0]}"
    return cap(' · '.join(rest + channel))


def _yoy(a, b):
    return a / b - 1 if b else None


def _gap(diff, base, parent_yoys):
    """Dollars above or below what the parent's trend would give; with two parents, the smaller gap."""
    gaps = [diff - base * y for y in parent_yoys if y is not None]
    return min(gaps, key=abs) if gaps else diff


def sales_scan(df, ref, weeks):
    from core.periods import TY, LY
    d = df.copy()
    d['SEG'] = ''
    for (age, cohort), mask in SEGMENTS.items():
        d.loc[mask(d), 'SEG'] = f'{age}_{cohort}'
    partial = ref['wk'] if ref['dow'] < 6 else None
    same = lambda x: x[(x.WK != partial) | (x.DOW <= ref['dow'])] if partial is not None else x
    ty = same(d[(d.FISCAL_YR == TY) & d.WK.isin(weeks)])
    ly = same(d[(d.FISCAL_YR == LY) & d.WK.isin(weeks)])
    full = [w for w in weeks if w != partial]
    early, recent = full[:-RECENT_WEEKS], full[-RECENT_WEEKS:]
    total_ty, total_ly = ty.DEMAND_AMT.sum(), ly.DEMAND_AMT.sum()
    total_yoy, growth = total_ty / total_ly - 1, total_ty - total_ly

    one_yoy = {}
    for col in DIMS:
        a, b = ty.groupby(col).DEMAND_AMT.sum(), ly.groupby(col).DEMAND_AMT.sum()
        for v in a.index.union(b.index):
            one_yoy[(col, v)] = _yoy(float(a.get(v, 0)), float(b.get(v, 0)))

    found, small = [], 0
    for n in (1, 2):
        for cols in itertools.combinations(DIMS, n):
            cols = list(cols)
            wt = ty.groupby(cols + ['WK']).DEMAND_AMT.sum()
            wl = ly.groupby(cols + ['WK']).DEMAND_AMT.sum()
            ct, cl = ty.groupby(cols).CUST_ID.nunique(), ly.groupby(cols).CUST_ID.nunique()
            st, sl = ty.groupby(cols).DEMAND_AMT.sum(), ly.groupby(cols).DEMAND_AMT.sum()
            for key in st.index.union(sl.index):
                k = key if isinstance(key, tuple) else (key,)
                a, b = float(st.get(key, 0)), float(sl.get(key, 0))
                diff = a - b
                if abs(diff) < IMPACT_SHARE * abs(growth) or not b:
                    continue
                if ct.get(key, 0) < SMALL_BASE or cl.get(key, 0) < SMALL_BASE:
                    small += 1
                    continue
                week = lambda s, w: float(s.get(k + (w,), 0))
                wk_yoy = [_yoy(week(wt, w), week(wl, w)) for w in full]
                sum_ = lambda s, ws: sum(week(s, w) for w in ws)
                e_yoy, r_yoy = _yoy(sum_(wt, early), sum_(wl, early)), _yoy(sum_(wt, recent), sum_(wl, recent))
                streak = 0
                sign = (wk_yoy[-1] or 0) > 0
                for y in reversed(wk_yoy):
                    if y is None or (y > 0) != sign or y == 0:
                        break
                    streak += 1
                yoy = a / b - 1
                pattern = None
                if (yoy > 0) != (total_yoy > 0) and abs(yoy) >= AGAINST_MIN:
                    pattern = 'against'
                elif streak >= STREAK_MIN:
                    pattern = 'streak_up' if sign else 'streak_down'
                elif e_yoy is not None and r_yoy is not None and abs(r_yoy - e_yoy) >= SPEED_GAP:
                    pattern = 'speeding_up' if r_yoy > e_yoy else 'slowing'
                if not pattern:
                    continue
                found.append(dict(parts=list(zip(cols, k)), name=label(zip(cols, k)), pattern=pattern,
                                  ty=a, ly=b, diff=diff, yoy=yoy, streak=streak, streak_dir='up' if sign else 'down',
                                  early_yoy=e_yoy, recent_yoy=r_yoy, customers=int(ct.get(key, 0)), customers_ly=int(cl.get(key, 0)),
                                  gap=_gap(diff, b, [total_yoy] if n == 1 else [one_yoy.get(pc) for pc in zip(cols, k)])))
    found.sort(key=lambda f: -abs(f['gap']))
    top = [f for f in found if len(f['parts']) == 1][:TOP_SINGLE] + [f for f in found if len(f['parts']) == 2][:TOP_PAIR]
    return dict(top=top, candidates=len(found), small_excluded=small, total_yoy=total_yoy,
                early_weeks=early, recent_weeks=recent,
                rules=dict(streak_min=STREAK_MIN, speed_gap=SPEED_GAP, against_min=AGAINST_MIN,
                           impact_share=IMPACT_SHARE, min_customers=SMALL_BASE, top_single=TOP_SINGLE, top_pair=TOP_PAIR))


def stock_scan(df, inventory, ref):
    """Families whose selling pace changed most between the two halves of the sell-rate window, this year."""
    from core.periods import TY, LY
    rw = inventory['rate_weeks']
    prior, latest = rw[:len(rw) // 2], rw[len(rw) // 2:]
    rows = []
    for r in inventory['rows']:
        f = r['name']
        units = lambda fy, ws: float(df[(df.FISCAL_YR == fy) & (df.STYLE_GROUP == f) & df.WK.isin(ws)].UNIT_QTY.sum()) / len(ws)
        p, l = units(TY, prior), units(TY, latest)
        if p + l < 10 or not p:
            continue
        rows.append(dict(name=f, rate_prior=p, rate_latest=l, change=l / p - 1,
                         rate_prior_ly=units(LY, prior), rate_latest_ly=units(LY, latest),
                         cover=r['ty']['cover'], status=r['status']))
    up = sorted([r for r in rows if r['change'] > 0], key=lambda r: -r['change'])[:2]
    down = sorted([r for r in rows if r['change'] < 0], key=lambda r: r['change'])[:2]
    return dict(up=up, down=down, prior_weeks=prior, latest_weeks=latest)
