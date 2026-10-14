"""Build the static dashboard: read the extract, compute measures, embed them in dist/index.html."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.metrics import compare, contribution, drill, family_drill, weekly, trend_cube as cube, DRILL_DIMS, FAMILY_DRILL_DIMS, OTHER_GENERATIONS, SMALL_BASE
from core.brief import display_facts, validate
from core.facts import build_facts
from core.headlines import SEGMENT_NAMES, headlines, products
from core.inventory import add_inventory_cols, cover_at, inventory_view
from core.periods import add_period_cols, as_of, windows

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data/raw/TYLY_data_sample.xlsx'


def fmt_range(r):
    a, b = r
    if a == b: return f'{a:%b %-d, %Y}'
    return f'{a:%b %-d}–{b:%-d, %Y}' if a.month == b.month else f'{a:%b %-d}–{b:%b %-d, %Y}'


# Line chart filter: one of these at a time, crossed with the customer group buttons.
TREND_SLICE_DIMS = {'STYLE_GROUP': 'Product family', 'GEO_REGION': 'Region',
                    'CHANNEL_DETAIL': 'Store vs online', 'SALES_CHANNEL': 'Retail vs outlet'}

BRIEF_DIR = ROOT / 'ai'


BRIEFS = {'brief': 'weekly_brief.md', 'stock_brief': 'stock_brief.md'}


def write_prompt_input(name, facts, meta):
    """Prompt + facts as one text to paste into a chat model; the reply goes in ai/recorded/<name>_<week>.json."""
    from core.brief import fmt_value
    lines = [(BRIEF_DIR / 'prompts' / BRIEFS[name]).read_text(encoding='utf-8').strip(), '',
             f"Facts (data as of {meta['as_of_label']}, {meta['fiscal']}, fingerprint {meta['fingerprint']}):", '']
    for fid, f in facts.items():
        lines.append(f"- {fid} = {fmt_value(f['value'], f['fmt'])}  ({f['label']}; {f['source']})")
    suffix = '' if name == 'brief' else '_' + name.split('_')[0]
    (BRIEF_DIR / f'prompt_input{suffix}.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def load_brief(name, facts, meta):
    path = BRIEF_DIR / 'recorded' / f"{name}_{meta['fiscal'].replace(' ', '')}.json"
    out = dict(facts=display_facts(facts), file=str(path.relative_to(ROOT)))
    if not path.exists():
        out.update(status='missing')
        print(f'{name}: missing ({out["file"]})')
        return out
    rec = json.loads(path.read_text(encoding='utf-8'))
    verdict = validate(rec['brief'], facts)
    if rec.get('fingerprint') != meta['fingerprint']:
        verdict['passed'] = False
        verdict['errors'].insert(0, f"Brief was written for data {rec.get('fingerprint')}, but the data is now {meta['fingerprint']}")
    out.update(status='ok' if verdict['passed'] else 'rejected', verdict=verdict, prompt_file=rec.get('prompt_file'),
               brief=rec['brief'], model=rec.get('model'), generated_at=rec.get('generated_at'))
    print(f"{name}: {out['status']}, {verdict['numbers_checked']} numbers cited" + ''.join('\n  - ' + e for e in verdict['errors']))
    return out


def load_chat(win, inventory, meta):
    """Chat prototype: recorded tool calls are re-run on the data at build time, their results become the only
    facts the answer may cite, and each answer is checked like the briefs. One failed answer hides only itself."""
    from core.brief import DIGIT, fmt_value
    from core.tools import Toolbox, ToolError
    tb = Toolbox(win, inventory, fmt_value)
    (BRIEF_DIR / 'prompt_input_chat.txt').write_text(
        (BRIEF_DIR / 'prompts/chat.md').read_text(encoding='utf-8').strip() + '\n\n' + tb.catalog() +
        f"\n\nData as of {meta['as_of_label']}, {meta['fiscal']}, fingerprint {meta['fingerprint']}.\n", encoding='utf-8')

    path = BRIEF_DIR / 'recorded' / f"chat_{meta['fiscal'].replace(' ', '')}.json"
    out = dict(file=str(path.relative_to(ROOT)), runs=[])
    if not path.exists():
        print(f'chat: missing ({out["file"]})')
        return out
    rec = json.loads(path.read_text(encoding='utf-8'))
    out.update(model=rec.get('model'), generated_at=rec.get('generated_at'), prompt_file=rec.get('prompt_file'))
    for r in rec['runs']:
        errors, trace, facts = [], [], {}
        for call in r['calls']:
            if DIGIT.search(call.get('purpose', '')):
                errors.append(f"{call['id']}: the purpose contains a number typed by hand")
            try:
                res = tb.run(call)
            except ToolError as e:
                errors.append(f"{call.get('id')}: tool call rejected: {e}")
                continue
            facts.update(res['facts'])
            shown = display_facts(res['facts'])
            trace.append(dict(id=res['id'], tool=res['tool'], purpose=res['purpose'], signature=res['signature'],
                              columns=res['columns'], rows=res['rows'],
                              facts={k: dict(text=v['text'], label=v['label']) for k, v in shown.items()}))
        verdict = validate(r['answer'], facts)
        verdict['errors'] = errors + verdict['errors']
        if rec.get('fingerprint') != meta['fingerprint']:
            verdict['errors'].insert(0, f"Answer was written for data {rec.get('fingerprint')}, but the data is now {meta['fingerprint']}")
        verdict['passed'] = not verdict['errors']
        verdict['calls'] = len(r['calls'])
        out['runs'].append(dict(id=r['id'], question=r['question'], keywords=r.get('keywords', []),
                                status='ok' if verdict['passed'] else 'rejected', verdict=verdict,
                                answer=r['answer'], facts=display_facts(facts), trace=trace))
        print(f"chat/{r['id']}: {out['runs'][-1]['status']}, {len(r['calls'])} tool calls, {verdict['numbers_checked']} numbers"
              + ''.join('\n  - ' + e for e in verdict['errors']))
    return out


def load_opportunity(win, inventory, meta):
    """A rule picks the opportunity; the recorded card may cite only its facts and must be about the family the rule picks."""
    from core.brief import fmt_value
    from core.opportunity import find
    opp = find(win, inventory, fmt_value)
    if opp is None:
        print('opportunity: none this week')
        return dict(status='none')
    lines = [(BRIEF_DIR / 'prompts/opportunity.md').read_text(encoding='utf-8').strip(), '',
             f"Rule: {opp['rule']}", f"Picked: {opp['id']}", '',
             f"Facts (data as of {meta['as_of_label']}, {meta['fiscal']}, fingerprint {meta['fingerprint']}):", '']
    lines += [f"- {k} = {fmt_value(f['value'], f['fmt'])}  ({f['label']})" for k, f in opp['facts'].items()]
    (BRIEF_DIR / 'prompt_input_opportunity.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    path = BRIEF_DIR / 'recorded' / f"opportunity_{meta['fiscal'].replace(' ', '')}.json"
    out = dict(file=str(path.relative_to(ROOT)), target=opp['target'], rule=opp['rule'], columns=opp['columns'],
               rows=opp['rows'], facts=display_facts(opp['facts']))
    if not path.exists():
        print(f'opportunity: missing ({out["file"]})')
        out['status'] = 'missing'
        return out
    rec = json.loads(path.read_text(encoding='utf-8'))
    verdict = validate(rec['card'], opp['facts'])
    if rec.get('picked') != opp['id']:
        verdict['errors'].insert(0, f"Card was written about {rec.get('picked')}, but the rule now picks {opp['id']}")
    if rec.get('fingerprint') != meta['fingerprint']:
        verdict['errors'].insert(0, f"Card was written for data {rec.get('fingerprint')}, but the data is now {meta['fingerprint']}")
    verdict['passed'] = not verdict['errors']
    out.update(status='ok' if verdict['passed'] else 'rejected', verdict=verdict, card=rec['card'],
               model=rec.get('model'), generated_at=rec.get('generated_at'))
    print(f"opportunity: {out['status']}, {opp['id']}, {verdict['numbers_checked']} numbers" + ''.join('\n  - ' + e for e in verdict['errors']))
    return out


def build():
    df = add_period_cols(pd.read_excel(SOURCE, sheet_name='Data'))
    inv = add_inventory_cols(pd.read_excel(SOURCE, sheet_name='Inventory'))
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
        # The expanded generations must add back to the collapsed Other row, cell by cell.
        dr = flash[k]['drill']
        for suffix in ('', '_new', '_repeat'):
            parts = sum(dr[g + suffix]['pp'] for g in OTHER_GENERATIONS)
            assert abs(parts - dr['other' + suffix]['pp']) < 1e-9, f'{k}: generations{suffix} != other{suffix}'

    lw = win['last_week']['ty']
    flash['wtd']['vs_last_week'] = compare(dict(ty=win['wtd']['ty'], ly=lw), 'net_sales')
    flash['wtd']['last_week_range'] = fmt_range((lw.TXN_DT.min(), lw.TXN_DT.max()))

    # Weekly trend: the weeks must add back to period to date, on both sides of the comparison.
    trend = weekly(df, ref, 'net_sales')
    assert abs(sum(r['ty'] for r in trend) - flash['ptd']['ty']) < 0.01, 'weekly TY != PTD'
    assert abs(sum(r['ly_same_days'] for r in trend) - flash['ptd']['ly']) < 0.01, 'weekly LY != PTD LY'

    # The same weekly view per customer group, in sales and in customers. Groups don't overlap,
    # so their weekly sales must add back to the total line.
    from core.metrics import SEGMENTS
    weeks = [r['wk'] for r in trend]

    def by_segment(frame):
        out = {'all': {m: weekly(frame, ref, m, weeks) for m in ('net_sales', 'customers')}}
        for (age, cohort), mask in SEGMENTS.items():
            out[f'{age}_{cohort}'] = {m: weekly(frame[mask(frame)], ref, m, weeks) for m in ('net_sales', 'customers')}
        for seg in out.values():
            for m, rows in seg.items():
                base = 1000 if m == 'net_sales' else SMALL_BASE
                for r in rows:
                    r['small'] = r['ly_same_days'] < base
        return out

    def adds_up(parts, total, what):
        for i, r in enumerate(total):
            for side in ('ty', 'ly'):
                s = sum(p[i][side] for p in parts)
                assert abs(s - r[side]) < 0.01, f"W{r['wk']} {side}: {what} {s} != total {r[side]}"

    trend_segments = by_segment(df)
    adds_up([v['net_sales'] for k, v in trend_segments.items() if k != 'all'], trend, 'groups')
    # The same view for each product family, region, store vs online and retail vs outlet, one at a time in the
    # line chart's filter; within each, the members add back to the total too.
    trend_slices = {}
    for col in TREND_SLICE_DIMS:
        trend_slices[col] = {v: by_segment(df[df[col] == v]) for v in sorted(df[col].unique())}
        adds_up([v['all']['net_sales'] for v in trend_slices[col].values()], trend, TREND_SLICE_DIMS[col])

    # The page combines the filters freely (product x region x channel x store type x customer group), so every
    # combination is computed here. Where a combination is also computed above, one filter at a time, both must agree.
    trend_cube = cube(df, ref, weeks, list(TREND_SLICE_DIMS))
    stars = ['*'] * len(TREND_SLICE_DIMS)

    def same(key, seg_rows):
        e = trend_cube.get(key)
        for m, short in (('net_sales', 's'), ('customers', 'c')):
            for i, r in enumerate(seg_rows[m]):
                got = e[short][i] if e else [0, 0, 0]
                want = [r['ty'], r['ly'], r['ly_same_days']]
                assert all(abs(a - b) < 0.011 for a, b in zip(got, want)), f'cube {key} {m} W{r["wk"]}: {got} != {want}'

    for seg, rows in trend_segments.items():
        same('|'.join(stars + ['*' if seg == 'all' else seg]), rows)
    for j, col in enumerate(TREND_SLICE_DIMS):
        for v, segs in trend_slices[col].items():
            for seg, rows in segs.items():
                k = list(stars); k[j] = v
                same('|'.join(k + ['*' if seg == 'all' else seg]), rows)

    inventory = inventory_view(df, inv, ref, win['ptd'])
    # Families must add back to the totals.
    for fy in ('ty', 'ly'):
        assert sum(r[fy]['on_hand'] for r in inventory['rows']) == inventory['total'][fy]['on_hand'], f'{fy} on hand'

    customers = {k: {p: compare(win[p], k) for p in ('wtd', 'ptd')}
                 for k in ('gen_z_new', 'new_customers', 'repeat_customers')}
    product_rows = products(flash['ptd']['drill'], inventory)
    assert abs(sum(r['diff'] for r in product_rows) - (flash['ptd']['ty'] - flash['ptd']['ly'])) < 0.05, 'products != growth'
    # Each family's drill rows must add back to that family's change.
    product_drill = family_drill(win['ptd'], 'net_sales')
    for r in product_rows:
        for col, rows in product_drill[r['name']].items():
            assert abs(sum(x['diff'] for x in rows) - r['diff']) < 0.05, f"{r['name']}/{col}: rows != family change"
    start_label = f"{win['ptd']['ty_range'][0]:%b %-d}"
    heads = headlines(flash, trend, product_rows, inventory, start_label)

    data = dict(
        meta=dict(as_of=f"{ref['date']:%Y-%m-%d}", as_of_label=f"{ref['date']:%a %b %-d, %Y}",
                  fiscal=f"FY26 W{ref['wk']}", small_base=SMALL_BASE, small_sales_base=1000, drill_dims=DRILL_DIMS, family_drill_dims=FAMILY_DRILL_DIMS, trend_slice_dims=TREND_SLICE_DIMS, other_generations=OTHER_GENERATIONS, segment_names=SEGMENT_NAMES,
                  period_start=f"{win['ptd']['ty_range'][0]:%b %-d}", wtd_start=f"{win['wtd']['ty_range'][0]:%b %-d}",
                  source=SOURCE.name, fingerprint=hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:8],
                  built_at=datetime.now().strftime('%Y-%m-%d %H:%M')),
        flash=flash, trend=trend, trend_cube=trend_cube, inventory=inventory,
        customers=customers, products=product_rows, product_drill=product_drill, headlines=heads)

    # AI brief: the facts it may cite, the prompt input for whoever generates it, and the recorded model output.
    snap = inventory['snapshot_week']
    prev_cover = cover_at(df, inv, snap - 1, inventory['rate_weeks'][-1] - 1)
    facts = build_facts(data, win, prev_cover)
    for name in BRIEFS:
        write_prompt_input(name, facts, data['meta'])
        data[name] = load_brief(name, facts, data['meta'])
    data['chat'] = load_chat(win, inventory, data['meta'])
    data['opportunity'] = load_opportunity(win, inventory, data['meta'])

    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    html = html.replace('/*__DATA__*/null', json.dumps(data, ensure_ascii=False))
    out = ROOT / 'dist/index.html'
    out.write_text(html, encoding='utf-8')
    return out, data


if __name__ == '__main__':
    out, data = build()
    print(json.dumps(data, indent=1, ensure_ascii=False))
    print('wrote', out)
