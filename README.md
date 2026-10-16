# TYLY Weekly Flash

A sales dashboard built from the TYLY sample data, with a weekly summary written by AI. Python calculates every number, the page only displays them, and the AI never types a number itself.

By Max Xiang. I made the analysis decisions; Claude wrote most of the code, and I reviewed every change.

**Live page:** https://spacecowboy0707.github.io/tapestry_takehome/dist/

The same diagrams as PDFs: [Repository structure](docs/Repository_structure.pdf) · [Weekly brief workflow](docs/Weekly_brief_workflow.pdf) · [Chat workflow](docs/Chat_workflow.pdf)

## What is on the page

- **This week's brief** (top of the Overview tab). An AI-written summary in four parts: what happened, what changed since last week, observations, and week-by-week trends. Code checks every sentence before it is shown.
- **Growth opportunity** (under the brief). A fixed rule picks one product family to focus on; the AI only explains the choice.
- **Overview**. Weekly sales this year vs last year, with filters for product family, region, store vs online and full-price vs outlet. Below it: sales by customer group, by product family and by stock level. Click a row to see where its change came from.
- **All stock**. An AI-written stock brief, then every product family with its weeks of stock left.
- **Ask the data**. A chat prototype with three recorded questions. Each answer shows which calculations were run, their results and the checks the answer passed.

## Run it

```bash
pip install -r requirements.txt
# put the data file at data/raw/TYLY_data_sample.xlsx (it is not in the repository)
python build.py          # writes dist/index.html
python -m unittest discover -s tests
```

To view the page, open `dist/index.html` in a browser. No server is needed.

## Repository structure

The data flows from top to bottom, and `build.py` runs every step.

**Input:** `data/raw/TYLY_data_sample.xlsx` (not in the repository)

**1. Calculation** (`core/`)

| File | What it does |
|---|---|
| `periods.py` | Reporting date and time windows; last year matched on fiscal week and weekday |
| `metrics.py` | One definition per measure; breakdowns by group and the weekly trend |
| `inventory.py` | Weeks of stock left and stock status per product family |
| `headlines.py` | One-sentence summary per section, written by fixed rules |

**2. Evidence: what the AI can see**

| File | What it does |
|---|---|
| `core/facts.py` | 246 named values for the weekly and stock briefs |
| `core/scan.py` | Fixed rules that flag groups whose weekly sales trend stands out |
| `core/tools.py` | 4 calculations the chat can ask for, with input checks |
| `core/opportunity.py` | Fixed rule that picks the growth opportunity |

**3. AI** (`ai/`)

| File | What it does |
|---|---|
| `prompts/` | Defining rules for each AI output |
| `prompt_input*.txt` | Everything the model reads: the rules plus the values or the list of calculations (written by the build) |
| `recorded/` | What the model wrote, with named slots instead of numbers, saved per week |

**4. Checks**

| File | What it does |
|---|---|
| `core/brief.py` | Checks every AI sentence against the values before it is published |
| `build.py` | Stops if any breakdown does not add up to its total |
| `tests/` | 27 tests covering time windows, checks, chat calculations, trend rules and the opportunity rule |

**5. Display**

| File | What it does |
|---|---|
| `templates/index.html` | Page layout and charts; no data |
| `dist/index.html` | The built page with data included; hover a number to see where it comes from |

Other notes: `data/README.md` (data location and notes) and `docs/build-log.md` (decisions and AI checks).

## Weekly brief workflow

How the week's data becomes the brief on the page. The model never writes a number. The stock brief follows the same steps.

| # | Step | Done by | What happens | Files |
|---|---|---|---|---|
| 1 | Load the data | Input | Sales for this year and last year, and weekly stock by product family | `data/raw/TYLY_data_sample.xlsx` |
| 2 | Calculate the measures | Code | Sales, customers and stock, compared with the same fiscal weeks and weekdays last year. Every breakdown must add up to its total. **If not, the build stops and no page is made.** | `core/periods.py`, `core/metrics.py`, `core/inventory.py` |
| 3 | Look for trends | Code | Fixed rules check every region, product family, store vs online, full-price vs outlet and customer group, alone and in pairs. They flag groups that stay above or below last year week after week, speed up or slow down, or move against the total. Groups under 30 customers are left out. | `core/scan.py` |
| 4 | Pick the facts | Code | Named values the brief may use, each with a format, a label and a source, e.g. `genz_new_insider = 17%` | `core/facts.py` |
| 5 | Write the brief | Model | Reads the writing rules and the facts. Writes the headline and four sections using named slots such as `{genz_new_insider}`, never digits. Marks each sentence as a fact or a limit. | `ai/prompts/weekly_brief.md`, `ai/prompt_input.txt` |
| 6 | Check the brief | Code | No typed numbers; every slot is a known fact; words like "rose" or "fell" match the direction; "from A to B" moves the stated way; every fact sentence cites a value; written for this week's data. **If not, the brief is hidden with the reasons and the rest of the dashboard is still shown.** | `core/brief.py` |
| 7 | Fill in the values | Code | Each slot is replaced with its value from the data. The brief is saved with its facts and how many values were checked. | `build.py` |
| 8 | Show the brief | Page | Headline and sections at the top of the dashboard. Hover a number to see its label and source. | `dist/index.html` |

To update for a new week: run `python build.py`, give `ai/prompt_input.txt` to a chat model, save its reply as `ai/recorded/brief_<week>.json`, and run the build again.

## Chat workflow: Ask the data

How a question becomes an answer on the page. The model never writes a number.

| # | Step | Done by | What happens | Files |
|---|---|---|---|---|
| 1 | Question | User | Typed, or picked from the suggested questions | |
| 2 | Choose the calculations | Model | Reads the question, the rules and the list of calculations, measures and values. Picks which calculations to run, each with a one-line purpose. | `ai/prompts/chat.md`, `ai/prompt_input_chat.txt` |
| 3 | Check each request | Code | Only known calculations, measures, groups and values; nothing required is missing; no numbers typed in the purpose. **If not, it is not run, and the answer is not shown.** | `core/tools.py` |
| 4 | Run the calculations | Code | Uses the same measures as the dashboard. Results become named values, e.g. `c5_online_ty = 13%`. | `core/tools.py`, `core/metrics.py` |
| 5 | Write the answer | Model | Reads the named values. Writes a headline and sections using slots such as `{c5_online_ty}`, never digits. Marks each sentence as fact, interpretation, suggestion or limit. | |
| 6 | Check the answer | Code | Same checks as the brief, against this answer's own results only. **If not, this answer is hidden with the reasons; other answers are not affected.** | `core/brief.py` |
| 7 | Fill in the values | Code | Each slot is replaced with its value. The calculations, results and checks are kept as the evidence trail. | `build.py` |
| 8 | Show the answer | Page | The answer, plus the evidence trail: calculations run, results, the answer as written, values filled in, checks passed. | `dist/index.html` |

The three answers are recorded, so any other question gets a "not recorded" reply. Going live means sending steps 2 and 5 to a model directly; the calculations, checks and page stay the same.

## How the numbers are calculated

- The reporting date is the last date in the data (Wed Aug 19, 2026), not today's date.
- Last year is matched on fiscal week and weekday, not calendar date.
- Week 30 only runs Sunday to Wednesday, so it is compared with the same four days last year. "This week so far" is compared with the same days last week.
- Yesterday has no comparison. With about 35 orders a day, a one-day change is mostly noise.
- Weeks of stock left = units in stock at the latest count ÷ average units sold per week over the last four complete weeks. The 4- and 12-week thresholds are placeholders to be set with the business.
- Customer groups and every breakdown add up exactly to their totals. If they don't, the build stops.
