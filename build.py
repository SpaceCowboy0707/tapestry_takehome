"""Build the static dashboard: read the extract, compute measures, embed them in dist/index.html."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.metrics import compare, contribution, drill, DRILL_DIMS, SMALL_BASE
from core.periods import add_period_cols, as_of, windows

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data/raw/TYLY_data_sample.xlsx'


def fmt_range(r):
    a, b = r
    if a == b: return f'{a:%b %-d, %Y}'
    return f'{a:%b %-d}–{b:%-d, %Y}' if a.month == b.month else f'{a:%b %-d}–{b:%b %-d, %Y}'


def build():
    df = add_period_cols(pd.read_excel(SOURCE, sheet_name='Data'))
    ref = as_of(df)
    win = windows(df, ref)

    flash = {'yesterday': dict(label=win['yesterday']['label'], **compare(win['yesterday'], 'net_sales'),
                               transactions=compare(win['yesterday'], 'transactions')['ty'])}
    for k in ('wtd', 'ptd'):
        w = win[k]
        flash[k] = dict(label=w['label'], ty_range=fmt_range(w['ty_range']), ly_range=fmt_range(w['ly_range']),
                        contribution=contribution(w, 'net_sales'), **compare(w, 'net_sales'))

        # The segments partition the window, so their points must add back to the YoY exactly.
        parts = sum(c['pp'] for c in flash[k]['contribution'].values())
        assert abs(parts - flash[k]['yoy']) < 1e-9, f'{k}: contributions {parts} != yoy {flash[k]["yoy"]}'
        flash[k]['drill'] = drill(w, 'net_sales')
        for seg, d in flash[k]['drill'].items():
            for col, rows in d['dims'].items():
                s = sum(r['pp'] for r in rows)
                assert abs(s - d['pp']) < 1e-9, f'{k}/{seg}/{col}: members {s} != segment {d["pp"]}'
        assert abs(flash[k]['drill']['all']['pp'] - flash[k]['yoy']) < 1e-9

    customers = {}
    for key in ('gen_z_new', 'gen_z_share_of_new', 'repeat_share', 'repeat_customers'):
        customers[key] = {k: compare(win[k], key) for k in ('wtd', 'ptd')}

    data = dict(
        meta=dict(as_of=f"{ref['date']:%Y-%m-%d}", as_of_label=f"{ref['date']:%a %b %-d, %Y}",
                  fiscal=f"FY26 W{ref['wk']}", small_base=SMALL_BASE, drill_dims=DRILL_DIMS,
                  source=SOURCE.name, fingerprint=hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:8],
                  built_at=datetime.now().strftime('%Y-%m-%d %H:%M')),
        flash=flash, customers=customers)

    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    html = html.replace('/*__DATA__*/null', json.dumps(data, ensure_ascii=False))
    out = ROOT / 'dist/index.html'
    out.write_text(html, encoding='utf-8')
    return out, data


if __name__ == '__main__':
    out, data = build()
    print(json.dumps(data, indent=1, ensure_ascii=False))
    print('wrote', out)
