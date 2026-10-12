# Build log: AI tools, prompts and checks

## Tools

- **Claude (Cowork)** for data profiling, code and page iterations. I set the questions, metric definitions and layout decisions; Claude wrote most of the code and I reviewed each change against screenshots and the build checks.
- **Claude** also wrote the weekly brief from `ai/prompt_input.txt` (recorded in `ai/recorded/`).

## Decisions I made along the way

- Static HTML instead of React or Streamlit: one file, no server, every number computed in Python.
- Last year matched on fiscal week and weekday, not calendar date; the week in progress only compared with the same weekdays.
- No day-level comparison: about 35 orders a day is too small a sample.
- "This week so far" compared with the same days last week, not last year: the overall comparison with last year is already on the page.
- Customer change shown as bars from a zero line rather than a waterfall: the changes are small next to the totals, so a waterfall either hides them or exaggerates the totals.
- Weeks of stock left read against last year and as a ranking, because sales in the extract look sampled.
- AI writes placeholders, never numbers; a checker decides what gets published.
- Toned the two briefs down to facts and findings. The first versions read like a chatbot ("thanks to", "few of them come back", "could stall within weeks") and claimed more than the data shows, notably about retention, which this extract can't measure. The prompts now ask for a neutral report tone with no causal wording; "Why it matters" became "Observations", which may only put cited facts side by side.

## Key prompt

See `ai/prompts/weekly_brief.md`. The rules that matter most: never type a digit; names come from facts; label every sentence as fact or limit; plain business English in a neutral report tone.

## How the AI output was checked

- `core/brief.py` rejects hand-typed numbers, unknown facts, wording that points the opposite way to a number's sign ("Sales fell +12.8%", "returning customers added −$6.3K"; checked per clause), "fell from {a} to {b}" when b is actually higher, fact sentences without a citation, and briefs written for a different data fingerprint.
- The page repeats the checks on every load and hides the brief if anything fails (tested by editing the brief in the browser to include "84%": it was rejected).
- `tests/test_brief.py` covers each rule. Writing these tests exposed a bug where a fact id containing "drop" counted as the word "drop"; fixed by checking only the words outside placeholders.
- `build.py` stops if any breakdown doesn't add back to its total (customer groups, generations, product families, weeks, stock).

## Chat prototype (Ask the data)

- Same rule as the brief, one layer added: the model chooses tool calls (`core/tools.py`: compare, breakdown, order_value, stock), code runs them, and the answer may cite only those results. Prompt: `ai/prompts/chat.md`.
- Tool calls are checked against a schema before they run; an unknown measure, dimension or value is rejected (`tests/test_tools.py`).
- Three runs are recorded (Insider and Gen Z retention, products bringing in Gen Z, order value by age group). Each answer shows an evidence trace: calls, results, the answer as written with placeholders, values filled in, checks passed.
- Tested by typing a number into one answer in the browser: that answer was hidden, the others stayed.


## Growth opportunity card

- A rule picks, the model explains: among product families with at least 4 weeks of stock, the one whose sales to first-time Gen Z grew most (`core/opportunity.py`). This week that is Brooklyn; Tabby and Pillow Tabby grew more but are excluded for low stock, and the card shows that.
- The card's explanation is labelled Hypothesis (a new sentence kind in the checker) and the action is written as a test. It may cite only the rule's facts, and it is rejected if it is about a different family than the rule picked.
- I considered weekly alerts too, but they repeated the brief; the opportunity card adds something new (where to push, not what went wrong).
