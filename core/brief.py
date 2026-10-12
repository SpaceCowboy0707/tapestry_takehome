"""Check and render the AI-written weekly brief.

The model writes sentences with {fact_id} placeholders and no digits of its own. This module decides whether
a brief may be published: every placeholder must name a real fact, no number may be typed by hand, and a
negative value shown without its sign (|abs) must sit in a sentence that says the thing went down.
It cannot check that the reasoning between facts is right; inference and action sentences are labelled as such.
"""
import re

PLACEHOLDER = re.compile(r'\{([a-z0-9_]+)(\|abs)?\}')
DIGIT = re.compile(r'\d')
KINDS = {'fact', 'inference', 'hypothesis', 'action', 'limit'}
SIGNED = {'money_signed', 'pct_signed', 'int_signed', 'pts_signed'}
# Direction words, matched as whole words inside the clause that holds the number (not the whole sentence),
# so "Europe grew {a} while apparel fell {b|abs}" is read as two separate claims.
NEGATIVE = re.compile(r"\b(less|lower|down|fell|falls?|falling|lost|lose|losing|drop|drops|dropped|behind|declin\w*|shrank|shrink\w*|below|weaker)\b")
POSITIVE = re.compile(r"\b(grew|grow\w*|rose|rise|rising|up|ahead|gain\w*|added|adds?|adding|increas\w*|above|higher|stronger)\b")
CLAUSE_BREAK = re.compile(r"[,;:()]|\s(?:and|but|while|whereas|yet)\s")


FROM_TO = re.compile(r"from\s+\{([a-z0-9_]+)(?:\|abs)?\}\s+to\s+\{([a-z0-9_]+)(?:\|abs)?\}")


def clause_around(text, start, end):
    """The words of the clause that contains text[start:end], with placeholders removed."""
    left = max((m.end() for m in CLAUSE_BREAK.finditer(text, 0, start)), default=0)
    right = next((m.start() for m in CLAUSE_BREAK.finditer(text, end)), len(text))
    return PLACEHOLDER.sub(' ', text[left:right]).lower()


def fmt_value(value, fmt, absolute=False):
    if fmt == 'text':
        return str(value)
    v = abs(value) if absolute else value
    if fmt in ('money', 'money_signed'):
        a = abs(v)
        body = f'${a / 1e6:.2f}M' if a >= 1e6 else f'${a / 1000:.1f}K' if a >= 1000 else f'${a:,.0f}'
        sign = ('+' if v > 0 else '−' if v < 0 else '') if fmt == 'money_signed' and not absolute else ('−' if v < 0 else '')
        return sign + body
    if fmt == 'pct_signed':
        return (f'{abs(v) * 100:.1f}%' if absolute else f"{'+' if v > 0 else '−' if v < 0 else '±'}{abs(v) * 100:.1f}%")
    if fmt == 'int_signed':
        return f'{abs(int(round(v))):,}' if absolute else f"{'+' if v > 0 else '−' if v < 0 else '±'}{abs(int(round(v))):,}"
    if fmt == 'pts_signed':
        r = round(v * 100)
        body = f'{abs(r)} pts'
        return body if absolute else f"{'+' if r > 0 else '−' if r < 0 else '±'}{body}"
    if fmt == 'pct0':
        return f'{v * 100:.0f}%'
    if fmt in ('weeks', 'dec1'):
        return f'{v:.1f}'
    if fmt == 'int':
        return f'{int(round(v)):,}'
    raise ValueError(f'unknown format {fmt}')


def display_facts(facts):
    """Pre-format every fact once, so the page only inserts text and never formats numbers itself."""
    out = {}
    for fid, f in facts.items():
        d = dict(label=f['label'], source=f['source'], fmt=f['fmt'], text=fmt_value(f['value'], f['fmt']))
        if f['fmt'] in SIGNED and f['value'] < 0:
            d['abs_text'] = fmt_value(f['value'], f['fmt'], absolute=True)
        out[fid] = d
    return out


def _texts(brief):
    yield 'headline', brief['headline']
    for i, sec in enumerate(brief['sections']):
        yield f'sections[{i}].title', sec['title']
        for j, item in enumerate(sec['items']):
            yield f'sections[{i}].items[{j}]', item['text']


def validate(brief, facts):
    errors = []
    try:
        assert isinstance(brief.get('headline'), str), 'headline must be text'
        assert isinstance(brief.get('sections'), list) and brief['sections'], 'sections must be a non-empty list'
        for i, sec in enumerate(brief['sections']):
            assert isinstance(sec.get('title'), str) and isinstance(sec.get('items'), list), f'sections[{i}] needs title and items'
            for j, item in enumerate(sec['items']):
                assert isinstance(item.get('text'), str), f'sections[{i}].items[{j}] needs text'
                assert item.get('kind') in KINDS, f'sections[{i}].items[{j}] kind must be one of {sorted(KINDS)}'
    except AssertionError as e:
        return dict(passed=False, errors=[f'Structure: {e}'], numbers_checked=0)

    cited = 0
    for where, text in _texts(brief):
        stripped = PLACEHOLDER.sub('', text)
        if DIGIT.search(stripped):
            errors.append(f'{where}: contains a number typed by hand ("{DIGIT.search(stripped).group()}" in "{stripped.strip()[:60]}")')
        for m in PLACEHOLDER.finditer(text):
            fid, absolute = m.group(1), bool(m.group(2))
            if fid not in facts:
                errors.append(f'{where}: unknown fact {{{fid}}}')
                continue
            f = facts[fid]
            if f['fmt'] != 'text':
                cited += 1
            if f['fmt'] not in SIGNED:
                if absolute:
                    errors.append(f'{where}: |abs| used on {fid}, which has no sign')
                continue
            clause = clause_around(text, m.start(), m.end())
            if absolute and f['value'] >= 0:
                errors.append(f'{where}: |abs| used on {fid}, but its value is not negative')
            elif absolute and not NEGATIVE.search(clause):
                errors.append(f'{where}: {fid} is negative and shown without its sign, but its clause does not say it went down')
            elif f['value'] > 0 and NEGATIVE.search(clause):
                errors.append(f'{where}: {fid} is a gain ({f["value"]:+.4g}) but its clause describes a decline ("{NEGATIVE.search(clause).group()}")')
            elif f['value'] < 0 and POSITIVE.search(clause):
                errors.append(f'{where}: {fid} is a decline ({f["value"]:+.4g}) but its clause describes growth ("{POSITIVE.search(clause).group()}")')
        # "from {old} to {new}": the direction word in that clause must match which way the value moved.
        for m in FROM_TO.finditer(text):
            a, z = facts.get(m.group(1)), facts.get(m.group(2))
            if not a or not z or 'text' in (a['fmt'], z['fmt']):
                continue
            clause = clause_around(text, m.start(), m.end())
            if NEGATIVE.search(clause) and z['value'] > a['value']:
                errors.append(f'{where}: says "{NEGATIVE.search(clause).group()}" but {m.group(2)} is higher than {m.group(1)}')
            elif POSITIVE.search(clause) and z['value'] < a['value']:
                errors.append(f'{where}: says "{POSITIVE.search(clause).group()}" but {m.group(2)} is lower than {m.group(1)}')
    for i, sec in enumerate(brief['sections']):
        for j, item in enumerate(sec['items']):
            if item['kind'] == 'fact' and not PLACEHOLDER.search(item['text']):
                errors.append(f'sections[{i}].items[{j}]: a fact sentence must cite at least one fact')
    return dict(passed=not errors, errors=errors, numbers_checked=cited)


def render_text(text, facts):
    """Plain-text rendering (for tests and the build log); the page renders the same way from display_facts."""
    def sub(m):
        f = facts[m.group(1)]
        return fmt_value(f['value'], f['fmt'], absolute=bool(m.group(2)))
    return PLACEHOLDER.sub(sub, text)
