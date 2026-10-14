"""Facts the AI brief may cite. Each fact is a value computed elsewhere in the build, with a format and a source.

The model never sees raw data and never writes a number: it writes {fact_id} placeholders, and the page fills
them in from this list. Text facts (product names, dates) are facts too, so names also come from the data.
"""
from core.metrics import MEASURES, OTHER_GENERATIONS


def _row(rows, name):
    return next(r for r in rows if r['name'] == name)


def build_facts(data, win, prev_cover):
    f = {}

    def add(fid, value, fmt, label, source):
        assert fid not in f, f'duplicate fact {fid}'
        f[fid] = dict(value=value, fmt=fmt, label=label, source=source)

    flash, inv, prods = data['flash'], data['inventory'], data['products']
    ptd, wtd, drill = flash['ptd'], flash['wtd'], flash['ptd']['drill']
    meta = data['meta']

    # How are we doing?
    add('period_start', meta['period_start'], 'text', 'First day of the data', 'Trend')
    add('sales_ptd', ptd['ty'], 'money', 'Sales since the start of the data', 'Trend')
    add('sales_ptd_ly', ptd['ly'], 'money', 'Same days last year', 'Trend')
    add('yoy_ptd', ptd['yoy'], 'pct_signed', 'Change vs last year, since the start of the data', 'Trend')
    add('growth_ptd', ptd['ty'] - ptd['ly'], 'money_signed', 'Dollar growth vs last year', 'Trend')
    add('sales_wtd', wtd['ty'], 'money', 'Sales this week so far', 'Trend')
    add('wow', wtd['vs_last_week']['yoy'], 'pct_signed', 'Change vs the same days last week', 'Trend')
    full = [r for r in data['trend'] if not r['partial']]
    add('weeks_ahead', sum(1 for r in data['trend'] if r['yoy'] and r['yoy'] > 0), 'int', 'Weeks ahead of last year', 'Trend → sales by week')
    add('weeks_total', len(data['trend']), 'int', 'Weeks in the data', 'Trend → sales by week')

    # Who is buying?
    g = drill['gen_z_new']
    growth = ptd['ty'] - ptd['ly']
    add('genz_new_diff', g['diff'], 'money_signed', 'Change from first-time Gen Z customers', 'By customer age group')
    add('genz_new_share', g['diff'] / growth, 'pct0', 'Share of growth from first-time Gen Z customers', 'By customer age group')
    store = _row(g['dims']['CHANNEL_DETAIL'], 'Retail Store')
    add('genz_new_store_share', store['diff'] / g['diff'], 'pct0', 'Share of that change made in stores', 'By customer age group → store vs online')
    add('genz_repeat_diff', drill['gen_z_repeat']['diff'], 'money_signed', 'Change from returning Gen Z customers', 'By customer age group')
    c = data['customers']
    add('genz_new_customers', c['gen_z_new']['ptd']['ty'], 'int', 'First-time Gen Z customers', 'By customer age group')
    add('genz_new_customers_ly', c['gen_z_new']['ptd']['ly'], 'int', 'First-time Gen Z customers last year', 'By customer age group')
    add('repeat_customers', c['repeat_customers']['ptd']['ty'], 'int', 'Returning customers', 'By customer age group')
    add('repeat_customers_ly', c['repeat_customers']['ptd']['ly'], 'int', 'Returning customers last year', 'By customer age group')
    t = win['ptd']['ty']
    gz_new = t[(t.CUST_AGE_GROUP == 'Gen Z') & (t.COHORT_STATUS == 'New')]
    add('genz_new_insider', MEASURES['insider_share']['fn'](gz_new), 'pct0', 'First-time Gen Z customers who joined Insider', 'Customers (Insider flag)')
    l = win['ptd']['ly']
    gz_new_ly = l[(l.CUST_AGE_GROUP == 'Gen Z') & (l.COHORT_STATUS == 'New')]
    add('genz_new_insider_ly', MEASURES['insider_share']['fn'](gz_new_ly), 'pct0', 'First-time Gen Z customers who joined Insider, last year', 'Customers (Insider flag)')
    gz_rep = lambda d: d[(d.CUST_AGE_GROUP == 'Gen Z') & (d.COHORT_STATUS != 'New')]
    add('genz_repeat_customers', MEASURES['customers']['fn'](gz_rep(t)), 'int', 'Returning Gen Z customers', 'By customer age group')
    add('genz_repeat_customers_ly', MEASURES['customers']['fn'](gz_rep(l)), 'int', 'Returning Gen Z customers last year', 'By customer age group')
    add('genz_repeat_sales_yoy', drill['gen_z_repeat']['yoy'], 'pct_signed', 'Returning Gen Z customers, sales change vs last year', 'By customer age group')
    add('repeat_insider', MEASURES['insider_share']['fn'](t[t.COHORT_STATUS != 'New']), 'pct0', 'Returning customers in Insider', 'Customers (Insider flag)')
    regions = drill['all']['dims']['GEO_REGION']
    add('europe_yoy', _row(regions, 'Europe')['yoy'], 'pct_signed', 'Europe, change vs last year', 'By customer age group → region')
    add('china_yoy', _row(regions, 'Greater China')['yoy'], 'pct_signed', 'Greater China, change vs last year', 'By customer age group → region')

    # What's selling?
    up = [r for r in prods if r['diff'] > 0]
    for i, r in enumerate(up[:2], 1):
        add(f'top{i}_name', r['name'], 'text', f'Product family with the {"largest" if i == 1 else "second-largest"} gain', 'By product family')
        add(f'top{i}_diff', r['diff'], 'money_signed', f'{r["name"]}, change vs last year', 'By product family')
        add(f'top{i}_sales', r['ty'], 'money', f'{r["name"]}, sales', 'By product family')
        add(f'top{i}_cover', r['cover'], 'weeks', f'{r["name"]}, weeks of stock left', 'Stock insight')
        add(f'top{i}_cover_ly', r['cover_ly'], 'weeks', f'{r["name"]}, weeks of stock left last year', 'Stock insight')
    apparel = _row(drill['all']['dims']['PROD_CATEGORY'], '4.Womens Apparel')
    add('apparel_yoy', apparel['yoy'], 'pct_signed', "Women's apparel, change vs last year", 'By customer age group → category')

    # Is stock in the right place?
    over = [r for r in inv['rows'] if r['status'] == 'overstock']
    add('overstock_names', ', '.join(r['name'] for r in over), 'text', 'Families with too much stock', 'Stock insight')
    add('overstock_threshold', inv['thresholds']['overstock'], 'int', 'Too-much-stock threshold, weeks', 'Stock insight')
    worst = max(over, key=lambda r: r['ty']['cover']) if over else None
    if worst:
        add('most_over_name', worst['name'], 'text', 'Family with the most weeks of stock', 'Stock insight')
        add('most_over_cover', worst['ty']['cover'], 'weeks', f'{worst["name"]}, weeks of stock left', 'Stock insight')
        add('most_over_sales_yoy', worst['sales']['yoy'], 'pct_signed', f'{worst["name"]}, sales change vs last year', 'By product family')

    # Observations: facts that link customers, channels, products and stock.
    top12 = up[0]['diff'] + up[1]['diff']
    add('top12_diff', top12, 'money_signed', f'{up[0]["name"]} and {up[1]["name"]}, change vs last year', 'By product family')
    add('top12_growth_share', top12 / growth, 'pct0', f'Share of growth from {up[0]["name"]} and {up[1]["name"]}', 'By product family')
    gz_fam = {r['name']: r for r in g['dims']['STYLE_GROUP']}
    gz_top12 = sum(gz_fam[r['name']]['diff'] for r in up[:2] if r['name'] in gz_fam)
    add('genz_new_top12_diff', gz_top12, 'money_signed', f'{up[0]["name"]} and {up[1]["name"]}, change from first-time Gen Z customers', 'By customer age group → product family')
    add('genz_new_top12_share', gz_top12 / g['diff'], 'pct0', f'Share of first-time Gen Z growth from {up[0]["name"]} and {up[1]["name"]}', 'By customer age group → product family')
    insider = MEASURES['insider_share']['fn']
    older = lambda d: d[d.CUST_AGE_GROUP.isin(list(OTHER_GENERATIONS.values())) & (d.COHORT_STATUS == 'New')]
    via = lambda d, ch: d[d.CHANNEL_DETAIL == ch]
    for ch, key in (('Retail Store', 'store'), ('eComm', 'online')):
        where = 'in stores' if key == 'store' else 'online'
        on = lambda d: via(d, ch)
        add(f'genz_new_insider_{key}', insider(on(gz_new)), 'pct0', f'First-time Gen Z customers {where} who joined Insider', 'Customers (Insider flag) → store vs online')
        add(f'genz_new_insider_{key}_ly', insider(on(gz_new_ly)), 'pct0', f'First-time Gen Z customers {where} who joined Insider, last year', 'Customers (Insider flag) → store vs online')
        add(f'other_new_insider_{key}', insider(on(older(t))), 'pct0', f'First-time customers of other generations {where} who joined Insider', 'Customers (Insider flag) → store vs online')
        add(f'other_new_insider_{key}_ly', insider(on(older(l))), 'pct0', f'First-time customers of other generations {where} who joined Insider, last year', 'Customers (Insider flag) → store vs online')
    add('genz_new_online_customers', MEASURES['customers']['fn'](via(gz_new, 'eComm')), 'int', 'First-time Gen Z customers online', 'By customer age group → store vs online')
    add('genz_new_online_customers_ly', MEASURES['customers']['fn'](via(gz_new_ly, 'eComm')), 'int', 'First-time Gen Z customers online, last year', 'By customer age group → store vs online')
    rep_store = _row(drill['gen_z_repeat']['dims']['CHANNEL_DETAIL'], 'Retail Store')
    add('genz_repeat_store_diff', rep_store['diff'], 'money_signed', 'Change from returning Gen Z customers in stores', 'By customer age group → store vs online')
    add('genz_repeat_insider_store', insider(via(gz_rep(t), 'Retail Store')), 'pct0', 'Returning Gen Z customers in stores who are in Insider', 'Customers (Insider flag) → store vs online')
    add('genz_repeat_insider_store_ly', insider(via(gz_rep(l), 'Retail Store')), 'pct0', 'Returning Gen Z customers in stores who are in Insider, last year', 'Customers (Insider flag) → store vs online')

    # Weekly scan (core/scan.py): slices that a fixed rule flagged, with their own values. Patterns are text facts.
    PATTERN = {'against': 'moving against the total', 'streak_up': 'above last year week after week',
               'streak_down': 'below last year week after week', 'speeding_up': 'speeding up', 'slowing': 'slowing down'}
    sc = data['scan']
    add('scan_early_first', sc['early_weeks'][0], 'int', 'Scan: first of the earlier weeks', 'Weekly scan')
    add('scan_early_last', sc['early_weeks'][-1], 'int', 'Scan: last of the earlier weeks', 'Weekly scan')
    add('scan_recent_first', sc['recent_weeks'][0], 'int', 'Scan: first of the latest complete weeks', 'Weekly scan')
    add('scan_recent_last', sc['recent_weeks'][-1], 'int', 'Scan: last of the latest complete weeks', 'Weekly scan')
    add('scan_min_customers', sc['rules']['min_customers'], 'int', 'Scan: fewest customers in either year for a group to count', 'Weekly scan')
    add('scan_small_count', sc['small_excluded'], 'int', 'Scan: groups with a sizeable change left out as too small', 'Weekly scan')
    for i, hit in enumerate(sc['top'], 1):
        k = f'scan{i}'
        add(f'{k}_name', hit['name'], 'text', f'Scan #{i}: group', 'Weekly scan')
        add(f'{k}_pattern', PATTERN[hit['pattern']], 'text', f'Scan #{i}: pattern found', 'Weekly scan')
        add(f'{k}_diff', hit['diff'], 'money_signed', f"{hit['name']}, change vs last year since the start of the data", 'Weekly scan')
        add(f'{k}_yoy', hit['yoy'], 'pct_signed', f"{hit['name']}, sales vs last year since the start of the data", 'Weekly scan')
        add(f'{k}_early_yoy', hit['early_yoy'], 'pct_signed', f"{hit['name']}, sales vs last year in the earlier weeks", 'Weekly scan')
        add(f'{k}_recent_yoy', hit['recent_yoy'], 'pct_signed', f"{hit['name']}, sales vs last year in the latest complete weeks", 'Weekly scan')
        add(f'{k}_streak', hit['streak'], 'int', f"{hit['name']}, latest complete weeks in a row on the same side of last year", 'Weekly scan')
        add(f'{k}_customers', hit['customers'], 'int', f"{hit['name']}, customers", 'Weekly scan')
        add(f'{k}_customers_ly', hit['customers_ly'], 'int', f"{hit['name']}, customers last year", 'Weekly scan')

    # Stock scan: families whose selling pace changed most between the two halves of the sell-rate window.
    ss = data['stock_scan']
    add('pace_prior_first', ss['prior_weeks'][0], 'int', 'Pace: first of the earlier weeks', 'Stock scan')
    add('pace_prior_last', ss['prior_weeks'][-1], 'int', 'Pace: last of the earlier weeks', 'Stock scan')
    add('pace_latest_first', ss['latest_weeks'][0], 'int', 'Pace: first of the latest weeks', 'Stock scan')
    add('pace_latest_last', ss['latest_weeks'][-1], 'int', 'Pace: last of the latest weeks', 'Stock scan')
    for side in ('up', 'down'):
        for i, r in enumerate(ss[side], 1):
            k = f'pace_{side}{i}'
            add(f'{k}_name', r['name'], 'text', f"Family whose selling pace {'rose' if side == 'up' else 'fell'} the most (#{i})", 'Stock scan')
            add(f'{k}_prior', r['rate_prior'], 'dec1', f"{r['name']}, units sold per week in the earlier weeks", 'Stock scan')
            add(f'{k}_latest', r['rate_latest'], 'dec1', f"{r['name']}, units sold per week in the latest weeks", 'Stock scan')
            add(f'{k}_change', r['change'], 'pct_signed', f"{r['name']}, change in units sold per week", 'Stock scan')
            add(f'{k}_prior_ly', r['rate_prior_ly'], 'dec1', f"{r['name']}, units sold per week in the earlier weeks, last year", 'Stock scan')
            add(f'{k}_latest_ly', r['rate_latest_ly'], 'dec1', f"{r['name']}, units sold per week in the latest weeks, last year", 'Stock scan')
            add(f'{k}_cover', r['cover'], 'weeks', f"{r['name']}, weeks of stock left", 'Stock scan')

    # What changed since last week. "Last week" is the previous complete week, or the same weekdays of it
    # when comparing with the week in progress; stock is compared with the previous snapshot.
    trend = {r['wk']: r for r in data['trend']}
    cur = max(trend)
    last_full = cur - 1 if trend[cur]['partial'] else cur
    add('wtd_yoy', wtd['yoy'], 'pct_signed', 'This week so far vs the same days last year', 'Trend → sales by week')
    add('last_week_no', last_full, 'int', 'Last complete fiscal week', 'Trend → sales by week')
    add('last_week_yoy', trend[last_full]['yoy'], 'pct_signed', f'Week {last_full} vs the same week last year', 'Trend → sales by week')
    add('prior_week_yoy', trend[last_full - 1]['yoy'], 'pct_signed', f'Week {last_full - 1} vs the same week last year', 'Trend → sales by week')
    count_gz = lambda d: MEASURES['gen_z_new']['fn'](d)
    add('genz_new_wtd', count_gz(win['wtd']['ty']), 'int', 'First-time Gen Z customers this week so far', 'By customer age group')
    add('genz_new_last_week', count_gz(win['last_week']['ty']), 'int', 'First-time Gen Z customers, same days last week', 'By customer age group')
    for i, r in enumerate(up[:2], 1):
        add(f'top{i}_cover_prev', prev_cover[r['name']]['cover'], 'weeks', f'{r["name"]}, weeks of stock left a week earlier', 'Stock insight')
    if worst:
        add('most_over_cover_prev', prev_cover[worst['name']]['cover'], 'weeks', f'{worst["name"]}, weeks of stock left a week earlier', 'Stock insight')
    now_status = {r['name']: r['status'] for r in inv['rows']}
    changed = [g for g in now_status if prev_cover[g]['status'] != now_status[g]]
    add('status_changes', len(changed), 'int', 'Product families whose stock status changed since last week', 'Stock insight')
    if changed:
        add('status_change_names', ', '.join(changed), 'text', 'Families whose stock status changed', 'Stock insight')

    # Stock detail, for the stock brief on the All stock page.
    tot, bt, th = inv['total'], inv['by_type'], inv['thresholds']
    add('snapshot_week', inv['snapshot_week'], 'int', 'Week of the latest stock count', 'Stock')
    add('rate_week_first', inv['rate_weeks'][0], 'int', 'First week of the sell-rate window', 'Stock')
    add('rate_week_last', inv['rate_weeks'][-1], 'int', 'Last week of the sell-rate window', 'Stock')
    add('risk_threshold', th['risk'], 'int', 'Could-run-out threshold, weeks', 'Stock')
    add('stock_total', tot['ty']['on_hand'], 'int', 'Units in stock, all families', 'Stock')
    add('stock_total_ly', tot['ly']['on_hand'], 'int', 'Units in stock, all families, last year', 'Stock')
    add('stock_total_change', tot['ty']['on_hand'] / tot['ly']['on_hand'] - 1, 'pct_signed', 'Units in stock vs last year', 'Stock')
    add('units_per_week_total', tot['ty']['rate'], 'dec1', 'Units sold per week, all families, in this extract', 'Stock')
    add('cover_total', tot['ty']['cover'], 'weeks', 'Weeks of stock left, all families', 'Stock')
    add('cover_total_ly', tot['ly']['cover'], 'weeks', 'Weeks of stock left, all families, last year', 'Stock')
    for t in ('Hero', 'Halo'):
        k = t.lower()
        add(f'{k}_cover', bt[t]['ty']['cover'], 'weeks', f'{t} families, weeks of stock left', 'Stock')
        add(f'{k}_cover_ly', bt[t]['ly']['cover'], 'weeks', f'{t} families, weeks of stock left last year', 'Stock')
    stock_rows = {r['name']: r for r in inv['rows']}
    for i, r in enumerate(up[:2], 1):
        sr = stock_rows[r['name']]
        add(f'top{i}_stock', sr['ty']['on_hand'], 'int', f'{r["name"]}, units in stock', 'Stock')
        add(f'top{i}_stock_ly', sr['ly']['on_hand'], 'int', f'{r["name"]}, units in stock last year', 'Stock')
        add(f'top{i}_rate', sr['ty']['rate'], 'dec1', f'{r["name"]}, units sold per week', 'Stock')
        add(f'top{i}_rate_ly', sr['ly']['rate'], 'dec1', f'{r["name"]}, units sold per week last year', 'Stock')
    for i, r in enumerate(sorted(over, key=lambda r: -r['ty']['cover']), 1):
        add(f'over{i}_name', r['name'], 'text', f'Too-much-stock family #{i} by weeks of stock', 'Stock')
        add(f'over{i}_cover', r['ty']['cover'], 'weeks', f'{r["name"]}, weeks of stock left', 'Stock')
        add(f'over{i}_cover_ly', r['ly']['cover'], 'weeks', f'{r["name"]}, weeks of stock left last year', 'Stock')
        add(f'over{i}_stock', r['ty']['on_hand'], 'int', f'{r["name"]}, units in stock', 'Stock')
        add(f'over{i}_stock_ly', r['ly']['on_hand'], 'int', f'{r["name"]}, units in stock last year', 'Stock')
        add(f'over{i}_sales_yoy', r['sales']['yoy'], 'pct_signed', f'{r["name"]}, sales change vs last year', 'By product family')
    # Not flagged yet, but heading the wrong way: OK status, more cover than last year, sales down sharply.
    watch = sorted([r for r in inv['rows'] if r['status'] == 'ok' and r['ty']['cover'] > r['ly']['cover']
                    and r['sales']['yoy'] is not None and r['sales']['yoy'] < -0.15], key=lambda r: r['sales']['yoy'])
    if watch:
        w = watch[0]
        add('watch_name', w['name'], 'text', 'Family not flagged yet but with falling sales and rising cover', 'Stock')
        add('watch_cover', w['ty']['cover'], 'weeks', f'{w["name"]}, weeks of stock left', 'Stock')
        add('watch_cover_ly', w['ly']['cover'], 'weeks', f'{w["name"]}, weeks of stock left last year', 'Stock')
        add('watch_sales_yoy', w['sales']['yoy'], 'pct_signed', f'{w["name"]}, sales change vs last year', 'By product family')

    # Facts for the preset questions.
    gzr = sorted(g['dims']['GEO_REGION'], key=lambda r: -r['diff'])
    for i, r in enumerate(gzr[:2], 1):
        add(f'genz_region{i}_name', r['name'], 'text', f'Region #{i} by first-time Gen Z growth', 'By customer age group → region')
        add(f'genz_region{i}_diff', r['diff'], 'money_signed', f'{r["name"]}, change from first-time Gen Z customers', 'By customer age group → region')
        add(f'genz_region{i}_share', r['diff'] / g['diff'], 'pct0', f'{r["name"]}, share of first-time Gen Z growth', 'By customer age group → region')
    gzp = sorted(g['dims']['STYLE_GROUP'], key=lambda r: -r['diff'])
    for i, r in enumerate(gzp[:2], 1):
        add(f'genz_family{i}_name', r['name'], 'text', f'Product family #{i} by first-time Gen Z growth', 'By customer age group → product family')
        add(f'genz_family{i}_diff', r['diff'], 'money_signed', f'{r["name"]}, change from first-time Gen Z customers', 'By customer age group → product family')
    add('genz_new_online_share', 1 - store['diff'] / g['diff'], 'pct0', 'Share of first-time Gen Z growth made online', 'By customer age group → store vs online')
    for reg, key in (('Europe', 'europe'), ('Greater China', 'china')):
        add(f'{key}_sales', _row(regions, reg)['ty'], 'money', f'{reg}, sales', 'By customer age group → region')
        add(f'{key}_diff', _row(regions, reg)['diff'], 'money_signed', f'{reg}, change vs last year', 'By customer age group → region')
        for seg, label in (('new', 'first-time'), ('repeat', 'returning')):
            r = _row(drill[seg]['dims']['GEO_REGION'], reg)
            add(f'{key}_{seg}_diff', r['diff'], 'money_signed', f'{reg}, change from {label} customers', 'By customer age group → region')
            add(f'{key}_{seg}_yoy', r['yoy'], 'pct_signed', f'{reg}, {label} customers, sales change vs last year', 'By customer age group → region')
    add('sales_last_week_same_days', wtd['vs_last_week']['ly'], 'money', 'Sales on the same days last week', 'Trend')
    return f
