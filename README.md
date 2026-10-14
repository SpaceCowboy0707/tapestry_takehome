# TYLY Weekly Flash

A static sales dashboard built from the TYLY sample extract. Python computes every number; the HTML only displays them.

## Run

```bash
pip install -r requirements.txt
# put the extract at data/raw/TYLY_data_sample.xlsx
python build.py          # writes dist/index.html
```

Open `dist/index.html` in a browser. No server is needed.

## What is on the page

**This week's brief** (top of Overview) is written by an AI model and fact-checked by code; see "AI brief" below.

**Ask the data** (third tab) is a small chat prototype. Type a question or pick one of three: whether Insider membership helps keep Gen Z customers, which products are bringing in Gen Z, and which age group spends more per order. Each answer has an **Evidence trace**: the tool calls Claude chose, their results, the answer exactly as written (placeholders, no numbers), the values filled in, and the checks it passed. Three answers are recorded; any other question gets an honest "not recorded" reply.

**Growth opportunity** (under the brief): click "Show this week's growth opportunity" for a card with the target customers, related products, evidence, why it could work (labelled Hypothesis), a suggested test and the missing data. A rule in `core/opportunity.py` picks the opportunity (among families with at least 4 weeks of stock, the one whose sales to first-time Gen Z grew most); the model only explains it from the rule's own facts (`ai/prompts/opportunity.md`, recorded in `ai/recorded/opportunity_<week>.json`), and the card is rejected if it names a different family than the rule picked. "How it was picked" shows the rule, the candidates and the families excluded for low stock.

**Overview** covers the four areas in the brief: trend, customer segments, product families and stock.

1. **Trend** Sales since Jun 28 (the first week in the extract), this week so far, and yesterday; a trailing weekly chart of this year vs last year with the change under each week, for all customers or one customer group (the same four groups as the breakdown below), in sales or in customers, filtered by product family, region, store vs online and full-price vs outlet in any combination (four separate filters; the product filter marks families that could run out or have too much stock, and for a family the note under the title gives its weeks of stock left). Every combination is computed at build time, with customers counted distinct within it. The unfinished week shows the same weekdays in both years. Everything after the chart is labelled as a year-over-year comparison.
2. **By customer age group** The change in sales vs last year for each customer group (first-time vs returning, Gen Z vs other generations, or every generation), drawn from a zero line: right sold more, left sold less. The groups don't overlap, so their changes add up to the total. Click a step to see where its change came from by region, channel, category, product type or product family.
3. **By product family** Product families ranked by dollar change, each with its weeks of stock left. Click a family to see where its change came from by region, store vs online, retail vs outlet or customer group (the same four groups as above); the rows add up to the family's change.
4. **Stock insight** Families that could run out and families with too much stock.

**All stock** opens with an AI-written stock brief (what the data shows, what changed since last week, what it could mean, and the limits of the analysis), then lists every product family by weeks of stock left, with stock trend vs last year.

Conventions (also under "How these numbers are calculated" on the page):

- The reporting date is the last date with sales data, never the system clock.
- Last year is matched on fiscal week and weekday (Wed of week 30 vs Wed of week 30), not calendar date.
- "This week so far" is compared with the same weekdays last week (Sun–Wed vs Sun–Wed). In the weekly chart and the customer breakdown the unfinished week is compared with the same days last year, and it is left out of sell rates.
- Yesterday has no comparison: with about 35 orders a day, a single-day change is mostly noise.
- Weeks of stock left = units in stock at the latest count ÷ average units sold per week over the last four complete weeks. Sales look sampled, so read it against last year and as a ranking. The 4- and 12-week thresholds are placeholders.
- Customer groups and every breakdown add back exactly to their totals; the build stops if they don't.

## Structure

```
core/
  periods.py     fiscal calendar: as-of date, WTD and PTD windows aligned to LY
  metrics.py     measures (one function per metric), YoY comparison, contribution, drill-down, weekly trend
  inventory.py   weeks of stock left per product family and status thresholds
  headlines.py   one-sentence answers per section, written from the numbers by fixed rules
  facts.py       the facts the AI brief may cite
  brief.py       checks and renders the AI brief
  tools.py       chat tools: schema check, run on the data, results as named values
  opportunity.py growth opportunity rule and its facts
  scan.py        weekly scan: groups flagged by fixed rules, for the briefs
build.py         reads the extract, computes everything, checks it, writes dist/index.html
ai/              prompts, prompt inputs (facts or tool list), recorded model output (briefs and chat runs)
tests/           period alignment, brief checker, chat tool and opportunity tests
templates/       HTML template; data is injected at build time
dist/            built dashboard
data/            see data/README.md
```

Measures live in `core/metrics.py` as plain functions that take a filtered DataFrame and return one number. The dashboard, the brief's facts and the chat tools all call the same functions, so they share one definition of each metric.

`build.py` fails if the parts of any split don't add back to their total.

## AI brief

The brief at the top of the page is the AI feature: a Monday-morning summary a merchant or regional lead can read in under a minute. It has four parts: what happened over the period, what changed since last week (compared with the previous week and the previous stock count, which the dashboard itself doesn't show), five observations that go a level deeper, each putting two areas side by side (customers, store vs online, Insider, products, stock, regions), and week-by-week trends by region, product, channel and customer group, found by the weekly scan. It states facts and findings in a neutral tone; it doesn't interpret, speculate or make recommendations.

How it is kept accurate:

1. `core/facts.py` picks the numbers the brief may use (sales, growth, customer groups, top products, stock) from the values the dashboard already computed. Each fact has an id, a format and the section it comes from.
   `core/scan.py` adds facts nobody had to think of in advance: it checks every region, product family, store vs online, full-price vs outlet and customer group, alone and in pairs, and flags groups whose sales are above or below last year week after week, speeding up or slowing down, or moving against the total. Groups with fewer than 30 customers in either year are left out; the rest are ranked by how far they sit from their parent's trend (a pair must differ from both its parents), and the top four single groups and top four pairs become facts. For the stock brief it adds the families whose selling pace changed most within the sell-rate window.
2. `build.py` writes `ai/prompt_input.txt` (weekly brief) and `ai/prompt_input_stock.txt` (stock brief): each prompt in `ai/prompts/` plus the same list of facts. That text is given to a chat model (no API needed); its JSON reply is saved in `ai/recorded/brief_<week>.json` with the model name, time and data fingerprint.
3. The model is not allowed to type a digit. Every number, and every product name that exists as a fact, is a placeholder such as `{top1_cover}`.
4. `core/brief.py` checks the reply before it is published: valid structure, every placeholder names a real fact, no number typed by hand, the words around every change point the same way as its sign (a gain can't be described as "fell", a decline can't be described as "grew"; checked clause by clause), "from {old} to {new}" comparisons must move the way their verb says, every fact sentence cites a fact, and the data fingerprint matches.
5. The page fills each placeholder from the data and repeats the number checks (no typed digits, every placeholder a real fact, signs) in the browser on every load. If anything fails, the brief is hidden and the errors are shown. Hover a number to see its fact and source.
6. Brief sentences are labelled fact or limit (the stock brief spells out what the data can't show). The checker verifies the numbers, not the reasoning between them, so the briefs carry no interpretation; the chat answers and the opportunity card label theirs.

The chat adds one layer to the same framework: **tools**. `core/tools.py` exposes the dashboard's measures as four tools (`compare`, `breakdown`, `order_value`, `stock`) over plain-language dimensions (age group, first-time vs returning, Insider, region, channel, store type, product family...).

1. The model gets `ai/prompt_input_chat.txt` (`ai/prompts/chat.md` plus the tool and value list) and replies with tool calls in JSON, each with a one-line purpose.
2. `build.py` checks every call against the schema (unknown tool, measure, dimension or value is rejected), runs it on the data, and turns the results into named values such as `c1_member_ty`. `python -m core.tools ai/recorded/chat_<week>.json` prints them to paste back to the model.
3. The model writes the answer with those placeholders only. The same validator checks it, against that answer's own tool results and nothing else.
4. The page re-checks each answer when it is shown and hides it if anything fails, without hiding the others.

The recorded runs are in `ai/recorded/chat_<week>.json`. Connecting a live model means replacing the recorded file with real calls to steps 1 and 3; the tools and checks stay the same.

`tests/test_brief.py` covers each rejection rule; one of those tests caught a real bug in the checker (fact ids were being read as words).

To regenerate for new data: run `python build.py`, paste `ai/prompt_input.txt` into a chat model, save the JSON reply as `ai/recorded/brief_<week>.json` with the new fingerprint, and rebuild. In production this would run on a schedule after each weekly data refresh.

## Tests

```bash
python -m unittest discover -s tests
```
