"""This week's growth opportunity: a fixed rule picks it, the model only explains it.

Target: first-time Gen Z customers (the business's stated top priority).
Rule: among product families with at least RISK_WEEKS of stock left, pick the one whose sales to first-time
Gen Z customers grew the most vs last year. Families growing faster but short of stock are shown as excluded,
so the reason for the pick is visible. The card may cite only the facts built here.
"""
from core.inventory import RISK_WEEKS
from core.metrics import MEASURES

TARGET = 'First-time Gen Z customers'


def _target(d):
    return d[(d.CUST_AGE_GROUP == 'Gen Z') & (d.COHORT_STATUS == 'New')]


def find(win, inventory, fmt):
    ty, ly = _target(win['ptd']['ty']), _target(win['ptd']['ly'])
    sales, customers = MEASURES['net_sales']['fn'], MEASURES['customers']['fn']
    inv = {r['name']: r for r in inventory['rows']}
    total_growth = sales(win['ptd']['ty']) - sales(win['ptd']['ly'])

    fams = []
    for name in sorted(set(ty.STYLE_GROUP) | set(ly.STYLE_GROUP)):
        t, l = ty[ty.STYLE_GROUP == name], ly[ly.STYLE_GROUP == name]
        r = inv[name]
        fams.append(dict(name=name, diff=sales(t) - sales(l), cust_ty=customers(t), cust_ly=customers(l),
                         aov=sales(t) / len(t) if len(t) else None,
                         store_share=(t.CHANNEL_DETAIL == 'Retail Store').mean() if len(t) else None,
                         cover=r['ty']['cover'], cover_ly=r['ly']['cover'], stock=r['ty']['on_hand'], sales_yoy=r['sales']['yoy']))
    fams.sort(key=lambda f: -f['diff'])
    growing = [f for f in fams if f['diff'] > 0 and f['cust_ty'] > f['cust_ly']]
    eligible = [f for f in growing if f['cover'] is not None and f['cover'] >= RISK_WEEKS]
    excluded = [f for f in growing if f not in eligible and f['diff'] > (eligible[0]['diff'] if eligible else 0)]
    if not eligible:
        return None
    pick, others = eligible[0], eligible[1:3]

    facts = {}
    def fact(key, value, f, label):
        if value is not None:
            facts[key] = dict(value=value, fmt=f, label=label, source='Opportunity rule (core/opportunity.py)')

    fact('seg_customers_ty', customers(ty), 'int', f'{TARGET}, this year')
    fact('seg_customers_ly', customers(ly), 'int', f'{TARGET}, last year')
    fact('seg_growth_share', (sales(ty) - sales(ly)) / total_growth if total_growth > 0 else None, 'pct0', f'{TARGET}, share of total sales growth')
    fact('pick_name', pick['name'], 'text', 'Picked product family')
    fact('pick_customers_ty', pick['cust_ty'], 'int', f"{pick['name']}, first-time Gen Z customers this year")
    fact('pick_customers_ly', pick['cust_ly'], 'int', f"{pick['name']}, first-time Gen Z customers last year")
    fact('pick_diff', pick['diff'], 'money_signed', f"{pick['name']}, sales to first-time Gen Z customers, change vs last year")
    fact('pick_aov', pick['aov'], 'money', f"{pick['name']}, average first purchase by a Gen Z customer")
    fact('pick_store_share', pick['store_share'], 'pct0', f"{pick['name']}, share of those purchases made in stores")
    fact('pick_cover', pick['cover'], 'weeks', f"{pick['name']}, weeks of stock left")
    fact('pick_cover_ly', pick['cover_ly'], 'weeks', f"{pick['name']}, weeks of stock left last year")
    fact('pick_stock', pick['stock'], 'int', f"{pick['name']}, units in stock")
    fact('pick_sales_yoy', pick['sales_yoy'], 'pct_signed', f"{pick['name']}, total sales vs last year")
    for i, f in enumerate(excluded[:2], 1):
        k = 'lead' if i == 1 else 'lead2'
        fact(f'{k}_name', f['name'], 'text', f'Faster-growing family excluded for low stock #{i}')
        fact(f'{k}_diff', f['diff'], 'money_signed', f"{f['name']}, sales to first-time Gen Z customers, change vs last year")
        fact(f'{k}_cover', f['cover'], 'weeks', f"{f['name']}, weeks of stock left")
        fact(f'{k}_aov', f['aov'], 'money', f"{f['name']}, average first purchase by a Gen Z customer")
    for i, f in enumerate(others, 2):
        fact(f'cand{i}_name', f['name'], 'text', f'Candidate #{i}')
        fact(f'cand{i}_diff', f['diff'], 'money_signed', f"{f['name']}, sales to first-time Gen Z customers, change vs last year")

    w = lambda v: '–' if v is None else fmt(v, 'weeks')
    row = lambda f, status: [f['name'], f"{f['cust_ty']} / {f['cust_ly']}", fmt(f['diff'], 'money_signed'), w(f['cover']), status]
    rows = [row(f, f'Excluded: under {RISK_WEEKS} weeks of stock') for f in excluded]
    rows += [row(pick, 'Picked')] + [row(f, 'Runner-up') for f in others]
    return dict(id=pick['name'], target=TARGET, facts=facts,
                rule=f'Among product families with at least {RISK_WEEKS} weeks of stock left, the one whose sales to '
                     f'first-time Gen Z customers grew the most vs last year (since {win["ptd"]["ty_range"][0]:%b %-d}).',
                columns=['Product family', 'First-time Gen Z customers (this / last year)', 'Sales from them vs LY', 'Weeks of stock left', 'Result'],
                rows=rows)
