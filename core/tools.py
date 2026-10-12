"""Tools the chat model may call. The model chooses a tool and its arguments; this code runs it.

Every tool reads the same measures as the dashboard (core/metrics.py) and returns two things:
a small table for the evidence trace, and named facts the answer may cite as {call_id}_{key}.
Arguments are checked against the schema below before anything runs, so a tool call that names an
unknown measure, column or value is rejected instead of guessed at.

Run the tool calls in a recorded chat file and print their results (to paste back to the model):
    python -m core.tools ai/recorded/chat_FY26W30.json
"""
import math
import re

from core.metrics import MEASURES, SMALL_BASE

PERIODS = {'since_jun28': 'ptd', 'this_week': 'wtd'}
PERIOD_LABEL = {'since_jun28': 'since Jun 28 vs the same days last year',
                'this_week': 'this week so far vs the same days last year'}

# Dimension name -> how to derive it from the raw columns (plain-language values).
DIMENSIONS = {
    'age_group':      lambda d: d.CUST_AGE_GROUP,
    'customer_type':  lambda d: d.COHORT_STATUS.map(lambda s: 'First-time' if s == 'New' else 'Returning'),
    'insider':        lambda d: d.INSIDER_FLAG.map({'Y': 'Member', 'N': 'Non-member'}),
    'region':         lambda d: d.GEO_REGION,
    'channel':        lambda d: d.CHANNEL_DETAIL.map({'Retail Store': 'Store', 'eComm': 'Online'}),
    'store_type':     lambda d: d.SALES_CHANNEL.map({'RETAIL': 'Full-price', 'OUTLET': 'Outlet'}),
    'category':       lambda d: d.PROD_CATEGORY.str.replace(r'^\d+\.', '', regex=True),
    'product_type':   lambda d: d.PROD_TYPE,
    'product_family': lambda d: d.STYLE_GROUP,
}

# Measure -> display format of its value and of its change vs last year.
FORMATS = {
    'net_sales': ('money', 'money_signed'), 'transactions': ('int', 'int_signed'), 'units': ('int', 'int_signed'),
    'customers': ('int', 'int_signed'), 'new_customers': ('int', 'int_signed'), 'repeat_customers': ('int', 'int_signed'),
    'repeat_share': ('pct0', 'pts_signed'), 'insider_share': ('pct0', 'pts_signed'), 'gen_z_share': ('pct0', 'pts_signed'),
    'aov': ('money', 'money_signed'), 'units_per_order': ('dec1', None),
}
# Plain names for the trace.
MEASURE_NAMES = {
    'net_sales': 'net sales', 'transactions': 'orders', 'units': 'units', 'customers': 'customers',
    'new_customers': 'first-time customers', 'repeat_customers': 'returning customers',
    'repeat_share': 'share who are returning customers', 'insider_share': 'share who are Insider members',
    'gen_z_share': 'Gen Z share of customers', 'aov': 'average order value', 'units_per_order': 'units per order',
}
ADDITIVE = {'net_sales', 'transactions', 'units', 'customers', 'new_customers', 'repeat_customers'}

SCHEMA = {
    'compare':     dict(required=['measure'], optional=['where', 'period'],
                        doc='One measure for a filtered group, this year vs last year.'),
    'breakdown':   dict(required=['measure', 'by'], optional=['where', 'period', 'sort_by', 'top'],
                        doc='One measure split by a dimension, this year vs last year; sort_by ty or diff; top N rows.'),
    'order_value': dict(required=['by'], optional=['where', 'period'],
                        doc='Average order value by a dimension this year, with a likely range (95% interval) and order count.'),
    'stock':       dict(required=['families'], optional=[],
                        doc='Weeks of stock left for product families, this year and last year.'),
}


class ToolError(ValueError):
    pass


def slug(name):
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')


def _prep(df):
    df = df.copy()
    for k, f in DIMENSIONS.items():
        df[k] = f(df)
    return df


def _check(call, values):
    tool, args = call.get('tool'), call.get('args', {})
    if tool not in SCHEMA:
        raise ToolError(f'unknown tool "{tool}"')
    spec = SCHEMA[tool]
    for k in spec['required']:
        if k not in args:
            raise ToolError(f'{tool}: missing argument "{k}"')
    for k in args:
        if k not in spec['required'] + spec['optional']:
            raise ToolError(f'{tool}: unknown argument "{k}"')
    if 'measure' in args and args['measure'] not in FORMATS:
        raise ToolError(f'{tool}: unknown measure "{args["measure"]}"')
    if 'by' in args and args['by'] not in DIMENSIONS:
        raise ToolError(f'{tool}: unknown dimension "{args["by"]}"')
    if args.get('period', 'since_jun28') not in PERIODS:
        raise ToolError(f'{tool}: unknown period "{args["period"]}"')
    if args.get('sort_by', 'ty') not in ('ty', 'diff'):
        raise ToolError(f'{tool}: sort_by must be ty or diff')
    for dim, want in args.get('where', {}).items():
        if dim not in DIMENSIONS:
            raise ToolError(f'{tool}: unknown filter "{dim}"')
        for v in (want if isinstance(want, list) else [want]):
            if v not in values[dim]:
                raise ToolError(f'{tool}: "{v}" is not a value of {dim}')
    for fam in args.get('families', []):
        if fam not in values['product_family']:
            raise ToolError(f'{tool}: unknown product family "{fam}"')


def _filter(df, where):
    for dim, want in (where or {}).items():
        df = df[df[dim].isin(want if isinstance(want, list) else [want])]
    return df


def _where_text(where):
    if not where:
        return 'all customers'
    return ', '.join(f"{k} = {' or '.join(v) if isinstance(v, list) else v}" for k, v in where.items())


def _signature(call):
    a = call['args']
    parts = [f'{k}: {_where_text(v) if k == "where" else ", ".join(v) if isinstance(v, list) else v}' for k, v in a.items()]
    return f"{call['tool']}({'; '.join(parts)})"


class Toolbox:
    """Runs tool calls against the windows the dashboard uses."""

    def __init__(self, win, inventory, fmt_value):
        self.frames = {k: dict(ty=_prep(win[k]['ty']), ly=_prep(win[k]['ly'])) for k in ('ptd', 'wtd')}
        both = self.frames['ptd']
        self.values = {d: set(both['ty'][d]) | set(both['ly'][d]) for d in DIMENSIONS}
        self.inventory = {r['name']: r for r in inventory['rows']}
        self.values['product_family'] |= set(self.inventory)
        self.fmt = fmt_value

    def catalog(self):
        """Tool and value lists for the prompt."""
        lines = ['Tools:']
        for name, s in SCHEMA.items():
            lines.append(f"- {name}({', '.join(s['required'])}{''.join(', [' + o + ']' for o in s['optional'])}): {s['doc']}")
        lines += ['', 'Measures: ' + ', '.join(f'{k} ({v})' for k, v in MEASURE_NAMES.items()),
                  'Periods: ' + ', '.join(PERIODS), '', 'Dimensions and their values (for by and where):']
        for d in DIMENSIONS:
            lines.append(f"- {d}: {', '.join(sorted(map(str, self.values[d])))}")
        return '\n'.join(lines)

    def run(self, call):
        _check(call, self.values)
        out = dict(id=call['id'], tool=call['tool'], purpose=call.get('purpose', ''), signature=_signature(call),
                   args=call['args'], facts={}, columns=[], rows=[])
        getattr(self, '_' + call['tool'])(call['id'], call['args'], out)
        return out

    # --- facts ---
    def _fact(self, out, key, value, fmt, label):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return
        out['facts'][f"{out['id']}_{key}"] = dict(value=value, fmt=fmt, label=label,
                                                  source=f"Tool {out['id']}: {out['signature']}")

    def _side(self, measure, sub_ty, sub_ly):
        fn = MEASURES[measure]['fn']
        a, b = fn(sub_ty), fn(sub_ly)
        diff = None if a is None or b is None else a - b
        small = measure in ADDITIVE and b is not None and b < (1000 if measure == 'net_sales' else SMALL_BASE)
        yoy = (a / b - 1) if (measure in ADDITIVE or measure == 'aov') and b and not small else None
        return a, b, diff, yoy, small

    def _cells(self, measure, a, b, diff, yoy, small):
        vf, df_ = FORMATS[measure]
        t = lambda v, f: '–' if v is None or f is None else self.fmt(v, f)
        return [t(a, vf), t(b, vf), t(diff, df_), t(yoy, 'pct_signed') + (' (small base)' if small else '')]

    # --- tools ---
    def _compare(self, cid, args, out):
        m, fr = args['measure'], self.frames[PERIODS[args.get('period', 'since_jun28')]]
        a, b, diff, yoy, small = self._side(m, _filter(fr['ty'], args.get('where')), _filter(fr['ly'], args.get('where')))
        vf, df_ = FORMATS[m]
        name = f"{MEASURE_NAMES[m]}, {_where_text(args.get('where'))}"
        self._fact(out, 'ty', a, vf, f'{name}, this year')
        self._fact(out, 'ly', b, vf, f'{name}, last year')
        if df_:
            self._fact(out, 'diff', diff, df_, f'{name}, change vs last year')
        self._fact(out, 'yoy', yoy, 'pct_signed', f'{name}, % change vs last year')
        out['columns'] = ['', 'This year', 'Last year', 'Change', '% change']
        out['rows'] = [[_where_text(args.get('where'))] + self._cells(m, a, b, diff, yoy, small)]

    def _breakdown(self, cid, args, out):
        m, by, fr = args['measure'], args['by'], self.frames[PERIODS[args.get('period', 'since_jun28')]]
        ty, ly = _filter(fr['ty'], args.get('where')), _filter(fr['ly'], args.get('where'))
        vf, df_ = FORMATS[m]
        rows = []
        for member in sorted(set(ty[by]) | set(ly[by]), key=str):
            a, b, diff, yoy, small = self._side(m, ty[ty[by] == member], ly[ly[by] == member])
            rows.append((member, a, b, diff, yoy, small))
        key = 3 if args.get('sort_by') == 'diff' else 1
        rows.sort(key=lambda r: (r[key] is None, -(r[key] or 0)))
        if args.get('top'):
            rows = rows[:int(args['top'])]
        for rank, (member, a, b, diff, yoy, small) in enumerate(rows, 1):
            s, name = slug(member), f"{MEASURE_NAMES[m]}, {member} ({_where_text(args.get('where'))})"
            self._fact(out, f'rank{rank}', member, 'text', f'Rank {rank} by {args.get("sort_by", "ty")}')
            self._fact(out, f'{s}_ty', a, vf, f'{name}, this year')
            self._fact(out, f'{s}_ly', b, vf, f'{name}, last year')
            if df_:
                self._fact(out, f'{s}_diff', diff, df_, f'{name}, change vs last year')
            self._fact(out, f'{s}_yoy', yoy, 'pct_signed', f'{name}, % change vs last year')
        out['columns'] = [by.replace('_', ' ').capitalize(), 'This year', 'Last year', 'Change', '% change']
        out['rows'] = [[str(r[0])] + self._cells(m, *r[1:]) for r in rows]

    def _order_value(self, cid, args, out):
        by, fr = args['by'], self.frames[PERIODS[args.get('period', 'since_jun28')]]
        ty = _filter(fr['ty'], args.get('where'))
        rows = []
        for member, g in ty.groupby(by):
            orders = g.groupby('TXN_ID').DEMAND_AMT.sum()
            n, mean = len(orders), float(orders.mean())
            half = 1.96 * float(orders.std()) / math.sqrt(n) if n > 1 else None
            rows.append((member, mean, mean - half, mean + half, n))
        rows.sort(key=lambda r: -r[1])
        for member, mean, lo, hi, n in rows:
            s, name = slug(member), f"average order value, {member}"
            self._fact(out, f'{s}_aov', mean, 'money', f'{name}, this year')
            self._fact(out, f'{s}_low', lo, 'money', f'{name}, low end of likely range')
            self._fact(out, f'{s}_high', hi, 'money', f'{name}, high end of likely range')
            self._fact(out, f'{s}_orders', n, 'int', f'{name}, number of orders')
        out['columns'] = [by.replace('_', ' ').capitalize(), 'Avg order', 'Likely range (95%)', 'Orders']
        out['rows'] = [[str(m), self.fmt(a, 'money'), f"{self.fmt(lo, 'money')} – {self.fmt(hi, 'money')}", self.fmt(n, 'int')]
                       for m, a, lo, hi, n in rows]

    def _stock(self, cid, args, out):
        out['columns'] = ['Product family', 'Weeks left', 'Last year', 'Units in stock']
        for fam in args['families']:
            r, s = self.inventory[fam], slug(fam)
            self._fact(out, f'{s}_cover', r['ty']['cover'], 'weeks', f'{fam}, weeks of stock left')
            self._fact(out, f'{s}_cover_ly', r['ly']['cover'], 'weeks', f'{fam}, weeks of stock left last year')
            self._fact(out, f'{s}_stock', r['ty']['on_hand'], 'int', f'{fam}, units in stock')
            c = lambda v: '–' if v is None else self.fmt(v, 'weeks')
            out['rows'].append([fam, c(r['ty']['cover']), c(r['ly']['cover']), self.fmt(r['ty']['on_hand'], 'int')])


if __name__ == '__main__':
    import io, contextlib, json, sys
    with contextlib.redirect_stdout(io.StringIO()):
        import build
        _, data = build.build()
    rec = json.load(open(sys.argv[1], encoding='utf-8'))
    for run in data['chat']['runs']:
        print(f"\n## {run['question']}")
        for c in run.get('trace', []):
            print(f"\n{c['id']}: {c['signature']}")
            for fid, f in c['facts'].items():
                print(f"  {fid} = {f['text']}  ({f['label']})")
