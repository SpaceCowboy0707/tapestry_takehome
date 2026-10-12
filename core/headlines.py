"""Plain-language answers for each section, written from computed numbers by fixed rules (no model).

Every sentence is a template filled from the data dict, and each claim it makes is checked in code
before it is written (for example "every week beat last year" only appears if every week's YoY is > 0).
"""

# Plain names for the customer segments, shared with the page.
SEGMENT_NAMES = {
    'gen_z_new': 'First-time Gen Z', 'gen_z_repeat': 'Returning Gen Z',
    'other_new': 'First-time, other generations', 'other_repeat': 'Returning, other generations',
    'millennial_new': 'First-time Millennial', 'millennial_repeat': 'Returning Millennial',
    'gen_x_new': 'First-time Gen X', 'gen_x_repeat': 'Returning Gen X',
    'boomer_new': 'First-time Boomer', 'boomer_repeat': 'Returning Boomer',
    'gen_z': 'Gen Z', 'other': 'Other generations', 'millennial': 'Millennial', 'gen_x': 'Gen X',
    'boomer': 'Boomer', 'new': 'First-time customers', 'repeat': 'Returning customers', 'all': 'All customers',
}
BASE_SEGMENTS = ['gen_z_new', 'gen_z_repeat', 'other_new', 'other_repeat']


def usd(v):
    a = abs(v)
    s = f'${a / 1000:,.1f}K' if a >= 1000 else f'${a:,.0f}'
    return s


def signed_usd(v):
    return ('+' if v >= 0 else '−') + usd(v)


def pct(v):
    return f'{abs(v) * 100:.1f}%'


def products(ptd_drill, inventory):
    """Product families by dollar change since the start of the period, with their stock position."""
    stock = {r['name']: r for r in inventory['rows']}
    out = []
    for r in ptd_drill['all']['dims']['STYLE_GROUP']:
        s = stock[r['name']]
        out.append(dict(name=r['name'], prod_type=s['prod_type'], ty=r['ty'], ly=r['ly'], diff=r['diff'],
                        yoy=r['yoy'], cover=s['ty']['cover'], cover_ly=s['ly']['cover'], status=s['status']))
    out.sort(key=lambda r: r['diff'], reverse=True)
    return out


def headlines(flash, trend, products_rows, inventory, start_label):
    ptd, wtd = flash['ptd'], flash['wtd']
    h = {}

    # 1. How are we doing?
    s = f"Sales since {start_label} are {usd(ptd['ty'])}, {pct(ptd['yoy'])} {'ahead of' if ptd['yoy'] >= 0 else 'behind'} last year"
    if all(r['yoy'] is not None and r['yoy'] > 0 for r in trend):
        s += ', and every week has beaten the same week last year'
    wow = wtd['vs_last_week']['yoy']
    s += f". This week so far is {pct(wow)} {'ahead of' if wow >= 0 else 'behind'} the same days last week."
    h['performance'] = s

    # 2. Who is buying?
    d = ptd['drill']
    growth = ptd['ty'] - ptd['ly']
    top = max(BASE_SEGMENTS, key=lambda k: d[k]['diff'])
    s = f"Since {start_label}, {SEGMENT_NAMES[top][0].lower() + SEGMENT_NAMES[top][1:]} customers added {usd(d[top]['diff'])}"
    if growth > 0 and d[top]['diff'] > 0:
        s += f", {d[top]['diff'] / growth:.0%} of the growth"
    s += '.'
    falling = [k for k in BASE_SEGMENTS if d[k]['diff'] < 0]
    for k in falling:
        s += f" {SEGMENT_NAMES[k]} customers spent {usd(d[k]['diff'])} less than last year."
    h['customers'] = s

    # 3. What's selling?
    up = [r for r in products_rows if r['diff'] > 0][:2]
    down = sorted([r for r in products_rows if r['diff'] < 0], key=lambda r: r['diff'])[:2]
    parts = []
    if up:
        parts.append(' and '.join(f"{r['name']} ({signed_usd(r['diff'])})" for r in up) + ' added the most')
    if down:
        parts.append(' and '.join(f"{r['name']} ({signed_usd(r['diff'])})" for r in down) + ' fell the most')
    s = f'Since {start_label}, ' + '; '.join(parts) + '.'
    at_risk = [r['name'] for r in up if r['status'] == 'risk']
    if len(at_risk) == len(up) and up:
        s += f" {'Both' if len(up) == 2 else 'The'} top {'sellers are' if len(up) == 2 else 'seller is'} close to running out of stock."
    elif at_risk:
        s += f" {' and '.join(at_risk)} {'is' if len(at_risk) == 1 else 'are'} close to running out of stock."
    h['products'] = s

    # 4. Is stock in the right place?
    th = inventory['thresholds']
    risk = [r['name'] for r in inventory['rows'] if r['status'] == 'risk']
    over = [r['name'] for r in inventory['rows'] if r['status'] == 'overstock']
    s = (f"{len(risk)} {'family' if len(risk) == 1 else 'families'} could run out within {th['risk']} weeks at the current pace"
         + (f" ({', '.join(risk)})" if risk else '')
         + f"; {len(over)} {'has' if len(over) == 1 else 'have'} more than {th['overstock']} weeks of stock"
         + (f" ({', '.join(over)})" if over else '') + '.')
    h['stock'] = s
    return h
