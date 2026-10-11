"""Measures: each takes an already-filtered DataFrame and returns one number.

This is the single definition used by the dashboard, the facts file and the AI brief.
"""


def net_sales(df):      return round(float(df['DEMAND_AMT'].sum()), 2)
def transactions(df):   return int(df['TXN_ID'].nunique())
def customers(df):      return int(df['CUST_ID'].nunique())
def new_customers(df):  return customers(df[df.COHORT_STATUS == 'New'])
def gen_z_new(df):      return new_customers(df[df.CUST_AGE_GROUP == 'Gen Z'])
def repeat_customers(df): return customers(df[df.COHORT_STATUS != 'New'])


def repeat_share(df):
    c = customers(df)
    return repeat_customers(df) / c if c else None


def gen_z_share_of_new(df):
    n = new_customers(df)
    return gen_z_new(df) / n if n else None


MEASURES = {
    'net_sales':          dict(fn=net_sales,          label='Net sales'),
    'transactions':       dict(fn=transactions,       label='Transactions'),
    'customers':          dict(fn=customers,          label='Customers'),
    'new_customers':      dict(fn=new_customers,      label='New customers'),
    'gen_z_new':          dict(fn=gen_z_new,          label='Gen Z new customers'),
    'gen_z_share_of_new': dict(fn=gen_z_share_of_new, label='Gen Z share of new customers'),
    'repeat_customers':   dict(fn=repeat_customers,   label='Repeat customers'),
    'repeat_share':       dict(fn=repeat_share,       label='Repeat customer share'),
}

# Below this LY base a percentage change is misleading, so show the absolute difference.
SMALL_BASE = 30


def _is_gen_z(df): return df.CUST_AGE_GROUP == 'Gen Z'
def _is_new(df):   return df.COHORT_STATUS == 'New'


# Gen Z and New overlap, so contributions are split on the 2x2 grid of both; the four cells add up to the total.
SEGMENTS = {
    ('gen_z', 'new'):    lambda d: _is_gen_z(d) & _is_new(d),
    ('gen_z', 'repeat'): lambda d: _is_gen_z(d) & ~_is_new(d),
    ('other', 'new'):    lambda d: ~_is_gen_z(d) & _is_new(d),
    ('other', 'repeat'): lambda d: ~_is_gen_z(d) & ~_is_new(d),
}


# Row totals, column totals and the corner of the 2x2 grid, so every cell of the table can be drilled.
GROUPS = {
    'gen_z':  lambda d: _is_gen_z(d),
    'other':  lambda d: ~_is_gen_z(d),
    'new':    lambda d: _is_new(d),
    'repeat': lambda d: ~_is_new(d),
    'all':    lambda d: d.index == d.index,
}

DRILL_DIMS = {
    'GEO_REGION':     'Region',
    'CHANNEL_DETAIL': 'Store vs online',
    'SALES_CHANNEL':  'Retail vs outlet',
    'PROD_CATEGORY':  'Category',
    'PROD_TYPE':      'Product type',
    'STYLE_GROUP':    'Product family',
}


def drill(window, key='net_sales'):
    """For every cell and total of the 2x2 grid, split its YoY points by each drill dimension.

    Only additive measures can be split this way: members of a dimension partition the segment,
    so their points add up to the segment's points. The base stays total LY sales of the window.
    """
    fn = MEASURES[key]['fn']
    ty, ly = window['ty'], window['ly']
    base = fn(ly)
    masks = {f'{a}_{c}': m for (a, c), m in SEGMENTS.items()} | GROUPS
    out = {}
    for seg, mask in masks.items():
        st, sl = ty[mask(ty)], ly[mask(ly)]
        dims = {}
        for col in DRILL_DIMS:
            names = sorted(set(st[col]) | set(sl[col]))
            rows = []
            for n in names:
                a, b = fn(st[st[col] == n]), fn(sl[sl[col] == n])
                rows.append(dict(name=n, ty=a, ly=b, diff=round(a - b, 2), pp=(a - b) / base if base else None))
            rows.sort(key=lambda r: r['pp'], reverse=True)
            dims[col] = rows
        a, b = fn(st), fn(sl)
        out[seg] = dict(ty=a, ly=b, diff=round(a - b, 2), pp=(a - b) / base if base else None, dims=dims)
    return out


def contribution(window, key='net_sales'):
    """Split the YoY change into percentage points by segment: (TY_seg - LY_seg) / LY_total."""
    fn = MEASURES[key]['fn']
    ty, ly = window['ty'], window['ly']
    base = fn(ly)
    cells = {}
    for (age, cohort), mask in SEGMENTS.items():
        a, b = fn(ty[mask(ty)]), fn(ly[mask(ly)])
        cells[f'{age}_{cohort}'] = dict(ty=a, ly=b, diff=round(a - b, 2), pp=(a - b) / base if base else None)
    return cells


def compare(window, key):
    fn = MEASURES[key]['fn']
    ty = fn(window['ty'])
    if window.get('ly') is None:
        return dict(ty=ty)
    ly = fn(window['ly'])
    out = dict(ty=ty, ly=ly, diff=None if ty is None or ly is None else ty - ly)
    out['yoy'] = (ty / ly - 1) if ly else None
    return out
