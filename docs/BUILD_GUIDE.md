# Pricing Desk: build guide (dashboard and code)

How the page is generated, the data it needs, and how every script works, so a future Claude
conversation can maintain, extend or rebuild any part. Read `PROJECT_CONTEXT.md` first; its §10
says what to do next.

**Canonical sources, in order:**
1. **The repo** (GitHub `pricing_desk`, or `pricing_desk.zip`). Everything lives here.
2. **The claude.ai artifact** https://claude.ai/artifact/XrojnVsyGGEqdpwdfpw9Yb. It's the same page with
   the data frozen on 20 Oct 2026. Use it only if the repo is lost (§6).

---

## 1. Generating the dashboard

### 1.1 How the page is built
- `site/template.html` is the finished dashboard, about 72 kB: inline CSS and JS, no framework, no build
  tools. It's the exact page from the claude.ai artifact. The only difference is that its data block reads:
  ```html
  <script id="pd-data" type="application/json">__PD_DATA__</script>
  ```
- `scripts/build_site.py` replaces `__PD_DATA__` with `data/desk.json`, serialized compactly, with
  `</` escaped as `<\/` so the JSON can't close the script tag. It writes `_site/index.html`,
  `_site/meta.json` (time of the last data commit) and `_site/.nojekyll`.
- GitHub Actions (`.github/workflows/pages.yml`) runs validate → unit tests → build → deploy on every
  push to `main`. The built page is never committed.
- **Preview anywhere, offline:** `python3 scripts/build_site.py --out preview.html` writes one file with
  the data embedded. It opens from disk, needs no server, and can be published as a claude.ai artifact
  as is.

### 1.2 Rules for editing the template
- Keep exactly one `__PD_DATA__`. `build_site.py` refuses to build otherwise.
- The page reads only `DATA.*` fields (§3). New data fields are safe: the page ignores them.
- After any template change, run this headless check with Playwright:
  1. build a preview;
  2. block requests to `fonts.g*`;
  3. click `#t-main`, `#t-all`, `#t-stats`, `#t-news`, `#t-newstrends` and `#t-src`;
  4. pick weeks with `locator('select[data-f=week]:visible').select_option(...)`, trying the current
     week, an older week and all weeks;
  5. check that there are no `pageerror` events.

  The test used during the build is in this guide's appendix.
- Typography in visible text: curly apostrophes (’) and the → arrow. Straight quotes only in code and JSON.

### 1.3 Design system (as implemented in the template)
- **Fonts:** Bricolage Grotesque (display), IBM Plex Sans (body), IBM Plex Mono (labels), from Google
  Fonts with system fallbacks.
- **Light theme:** background `#F3F5F8`, ink `#141B2B`, accent `#2A4BD7`, up `#C0392B`, down `#17794A`,
  pack `#7A4CC2`.
- **Dark theme:** background `#0E1320`, ink `#E8ECF4`, accent `#8BA3FF`, up `#FF8A80`, down `#6FD9A2`,
  pack `#C3A3F5`. The theme follows `prefers-color-scheme`.
- **Layout:** one column, max width 760px, phone first.
- **Tabs:** News (`#t-news`), Main Price Changes (`#t-main`: Ranked and Timeline), All Price Changes
  (`#t-all`: Changes and Promotions), Statistics (`#t-stats`: Analysis, Models & patterns), Market Trends
  from News (`#t-newstrends`), Sources (`#t-src`).
- **Week selector:** current edition, all weeks, a month, or a single week. A single week shows its
  coverage note in a `.cov-note` box.
- **Cards (D6):** headline delta chip → one-line summary → Before/After table → Who it hits → They say
  (only if stated) → Why · our read.
- **Relevant changes:** `isMain = c.main ?? tier <= 2`. The front page shows the first 7 changes of the
  current week by rank.
- **Main render functions:** `renderFront`, `renderGroups`, `card`, `renderTimeline`, `renderPromos`,
  `renderAnalysis`, `renderModels`, `renderPatterns`, `renderCtx`, `renderNews`, `renderTrends`,
  `renderKeyNumbers`, `showTab`.

---

## 2. Repository layout

```
pricing_desk/
  README.md  RUNBOOK.md  config.example.env (→ config.env, gitignored)  .gitignore
  docs/PROJECT_CONTEXT.md  docs/BUILD_GUIDE.md
  site/template.html            the dashboard (§1)
  data/desk.json                the page's data (§3)
  data/registry.json            companies we track (§3.6)
  data/capture_state.json       per-company capture state machine (§4.2)
  data/backlog.json             confirmed changes waiting for an agent decision
  data/snapshots/<slug>/<run>.txt   confirmed page texts = evidence
  data/checks.jsonl             append-only log of external checks
  data/meta.json                last run time (watchdog), registry counts
  proposals/<run>.input.json    backlog handed to the agent (audit)
  proposals/<run>.{changes,registry,edition}.json   agent outputs (audit)
  agent/changes_prompt.md  agent/registry_prompt.md  agent/edition_prompt.md  agent/sources.json
  scripts/*.py, *.sh            one script per step (§4)
  tests/test_pipeline.py  tests/fixtures/
  launchd/com.fmz.pricing_desk.plist   (template with __REPO__)
  .github/workflows/pages.yml  .github/workflows/watchdog.yml
  logs/  .run/  _site/          gitignored
```
**Run id:** `YYYY-MM-DDTHH` (e.g. `2026-11-02T19`). It's set by `run_daily.sh` as `PD_RUN_ID` and names
every per-run file.

---

## 3. Data contract

### 3.1 Top level of `desk.json` (= the page's `pd-data`)
| Key | Meaning | Set by |
|---|---|---|
| `current_week` | The edition shown by default, e.g. `"2026-W42"` | edition merge |
| `today`, `edition_date`, `period` | ISO dates; `period` like `"1–19 Oct"` | merge |
| `week_order` | Week labels, newest first | code (`desk.ensure_week`) |
| `weeks[]` | `{week, label "5–11 Oct", start ISO, source_week, coverage?, note?}` | code |
| `tiers`, `pattern_cats`, `categories` | Fixed reference lists | by hand |
| `changes[]` | Records (§3.2) | merge |
| `companies{}` | `slug → {name, tier, category, aiNative, ownership, hq, funding, employees}`; promo-only companies have `tier: null` | merge, from registry |
| `promos[]` | `{id, week, company, co, kind new/changed/ended, text, src}` | merge |
| `news[]` | `{id, lead, src, by, date, topic, rel, title, url, gist, nums [[value, meaning]], why}` | edition |
| `patterns[]` | `{t, p, ids[]}`, ids from the current week | edition |
| `stats_analysis[]` | `{t, fig, figNote, p, ids[]}`, fig numbers from code stats | edition |
| `news_trends[]` | `{t, p, nums, news[], changes[]}` | edition |
| `market_context` | `{source, total, increases, cuts, other, note}` | code |

### 3.2 Change records
**One-line record:**
- identity and placement: `id` (`<slug>-2026wNN`, with `-2` if taken), `week`, `rank`, `co`,
  `company`, `tier`
- the change: `group` (up/down/pack), `delta`, `short`, `pattern`, `seg`, `ai`, `planLevel`, `reach`
- `magnitude: null`
- dates and source: `seen` (week start), `seenLabel`, `when` ("27 Oct"), `src`, `url`
- `detail: "line"`, plus `evidence` on automated records

**Full card:** the line fields without `detail`, plus:
- `plan`, `deltaSub`, `headline`, `rows` (1–5 rows of `[label, before, after]`)
- `who`, `stated` (or null), `statedUrl`, `read`, `caveat?`
- `model`, `modelBefore`, `modelAfter`, `appliesTo`
- `magnitude {low, high, basis}`
- optional `announced` and `effective`

**Allowed values** (`scripts/common.py`):
- `group`: up, down, pack
- `seg`: B2B, B2C, Both
- `planLevel`: free, entry, mid, top, enterprise, all, add-on
- `appliesTo`: all, new, existing, unknown
- models: Seat, Usage, Flat, Hybrid (`model` may be written as "A → B")
- magnitude `basis`: list price, unit price, allowance, minimum
- `reach`: 1–3
- `pattern`: one of 16 patterns (Price increase, Price cut, Bundling, Unbundling, Tier consolidation,
  New tier, Rename & reposition, Limits tighten, Limits loosen, Minimums, Billing terms, New billing units,
  AI gets a meter, AI moves between tiers, AI costs pass through, Free plans as funnels)

**Records before automation** (`src` starting "PricingSaaS") were built by hand and have looser rules
in the validator: `url` may be null and rows may number up to 8. Automated records have
`src: "Pricing Desk capture"`.

### 3.3 Ranking (code, `desk.rerank`)
Full cards before one-line records. Then tier 1 → 3, then `reach` (high first), then the size of
`magnitude`, with previous order as the tie-break. This runs for every week that receives a record.

### 3.4 Weeks (code, `common.week_label`)
Label = ISO week of (date + 7 days), so weeks run Monday–Sunday and are numbered one ahead of ISO.
This is the PricingSaaS convention that existing data uses. A change belongs to the week of the last
capture that still showed the old page.

### 3.5 Edition timing (code, `close_week.due_week`)
The previous week is due once 18 hours have passed after it ends (Monday 19:00 run). It must be later
than `current_week` and not earlier than `FIRST_AUTO_EDITION` (`2026-W45`). The edition is retried every
run until it's accepted.

### 3.6 Registry (`data/registry.json` → `companies.<slug>`)
Fields:
- identity: `name`, `tier`, `category`, `segment`, `watch`
- capture: `pricing_urls[]` (1–3), `domains[]`, `capture` (static or browser), `status`,
  `ignore_patterns[]` (regexes for volatile text)
- history: `added`, `source`, `source_url`, `url_attempts`, `notes`
- page fields: `aiNative`, `ownership`, `hq`, `funding`, `employees`

Status flow:
- `needs_url` → (agent suggests a URL) → `candidate` → (first capture shows prices) → `active`
- a candidate whose page shows no prices, or fails for 2 days, goes back to `needs_url`; after 3
  failed suggestions it becomes `dead`
- `active` → `paused` after 7 days of failed captures
- `blocked` when robots.txt forbids access

---

## 4. Code: what each script does

| Script | Step | Reads → writes | Notes |
|---|---|---|---|
| `common.py` | — | — | Paths, time zone, **all rules and thresholds**, enums, keep-rule table, watchlist, week helpers, JSON I/O, checks log, problem queue, number extraction |
| `normalize.py` | — | — | HTML → stable text (drops script/style/nav/footer, volatile lines); `looks_like_pricing`; `comparable` for quote matching |
| `fetch.py` | — | — | Static fetch with robots.txt, gzip, identifiable user agent; raises `Blocked` / `FetchError` |
| `browser_capture.py` | — | — | The only Playwright module: one Chromium per run, `networkidle` + 1.5 s |
| `seed_registry.py` | setup | desk.json → registry.json | Idempotent; adds missing companies + watchlist URLs |
| `capture.py` | 2 | registry, capture_state → snapshots, backlog, `proposals/<run>.input.json`, `.run/diffs/` | State machine (§4.2) |
| `prepare_registry.py` | 3 | registry → `.run/registry_todo_<run>.json` | Exit 10 = nothing to do |
| `close_week.py` | 3 | desk → `.run/edition_due_<run>.json`, `.run/week_stats_<run>.json` | Exit 10 = not due; `--force-week` for tests |
| `run_agent.sh` | 3 | prompt template → proposal | Fills `{{TODAY}} {{WEEKDAY}} {{RUN}} {{INPUT_FILE}} {{OUTPUT_FILE}} {{WEEK}} {{WEEK_LABEL}} {{STATS_FILE}}`; agent may write only `./proposals/**` |
| `coverage_check.py` | 4 | run files → problems | Never blocks |
| `apply_proposals.py` | 5 | proposals → desk, registry, backlog, `.run/merge_<run>.json` | **The rules** (PROJECT_CONTEXT §5) |
| `desk.py` | 5 | — | `ensure_week`, `rerank`, `sync_company`, `week_stats`, `stats_numbers` |
| `recheck.py` | 6 | merge result → desk, checks.jsonl | Quotes and news numbers online |
| `validate.py` | 7 + CI | desk, registry | Integrity; exit 1 lists problems |
| `stamp_meta.py` | 8 | → meta.json | Last run time for the watchdog |
| `notify.py` | 9 | desk before/after, problems → ntfy | `--test`, `--problem "…"` |
| `build_site.py` | CI | template + desk → `_site/` | `--out preview.html` |
| `add_company.py` | manual | registry | Add or fix companies, force browser, change status |
| `run_daily.sh` | all | — | Lock file, steps, stash on failed validation, commit and push, failure alerts |
| `install_mac.sh` | setup | plist → `~/Library/LaunchAgents` | `--run-now` kicks a run |

### 4.1 Agent tasks and proposal formats
The exact formats are in the prompts. These are the shapes the merge expects:
- **changes:** `{"type": "changes", "items": [{"diff_id", "kind", "why", "detail": "card"|"line", "record": {…}, "promo": {kind, text}|null}]}`
- **registry:** `{"type": "registry", "urls": [{"slug", "pricing_urls", "domains"}], "new_companies": [{"name", "category", "segment", "pricing_urls", "domains", "source_url", "why"}]}`
- **edition:** `{"type": "edition", "week", "news", "patterns", "stats_analysis", "news_trends", "missed": [new-company shape]}`

A proposal file that's missing or isn't valid JSON is reported and ignored. The backlog keeps the
changes for the next run.

### 4.2 Capture state machine (`capture.step_company`)
Per company the state holds:
- `confirmed_hash`, `confirmed_file`, `last_old_at`
- `pending_hash`, `pending_count`, `pending_first_at`
- `unstable_runs`, `fail_runs`

What a capture does:
- **First capture:** baseline snapshot, no change.
- **Same as confirmed:** reset pending; `last_old_at` = now.
- **Different:** fetch again 3 seconds later.
  - If the two fetches differ, it counts as an unstable run; on the 3rd unstable run the page is
    reported once as `unstable` (a possible A/B test), with both versions saved.
  - Otherwise it counts toward pending. At `DEBOUNCE_CAPTURES` (2) the new version is saved as a
    snapshot, a diff is written, and the event joins the backlog with `week = week_label(last_old_at)`.
- **Static page without prices:** try the browser; if that shows prices, switch the company to browser
  mode.

### 4.3 Thresholds (all in `common.py`)
- `DEBOUNCE_CAPTURES` 2
- `UNSTABLE_RUNS_TO_REPORT` 3
- `FAIL_RUNS_TO_ALERT` 4
- `FAIL_RUNS_TO_PAUSE` 14
- `URL_ATTEMPTS_MAX` 3
- `REGISTRY_BATCH` 30
- `MIN_CAPTURE_OK_RATIO` 0.9
- `BACKLOG_MAX_ATTEMPTS` 4
- `EDITION_READY_AFTER` 18 h
- `FIRST_AUTO_EDITION` 2026-W45
- `DELAY_BETWEEN_COMPANIES_SEC` 2

---

## 5. Extending safely
- **New rule:** add it to `common.py` (constant or enum) and use it in `apply_proposals.py` or
  `validate.py`. Add a test in `tests/test_pipeline.py` with a fixture showing the case, then run
  `python3 -m unittest discover -s tests -v`.
- **New data field:** add it in the merge. The page ignores unknown fields; to display it, edit
  `site/template.html` (§1.2).
- **New step:** a new script with a docstring, called from `run_daily.sh` between the existing steps.
  It must never fail the run unless it protects published data.
- **Agent behaviour:** edit `agent/*.md`. Keep the output format in step with `apply_proposals.py`.
- **Tests that must keep passing:**
  - week labels match the existing data;
  - edition timing;
  - text normalization and number extraction;
  - debounce, glitch and flip detection;
  - merge cases: traceable card accepted, invented number downgraded or held, off-site quote removed,
    drop and promo kinds, price reveal dropped, bad enum rejected;
  - the template builds and the data validates.

---

## 6. If the repo is ever lost
1. In a claude.ai conversation, read the artifact (`Artifact action: "read"` on the URL above).
2. Extract the data with `re.search(r'<script[^>]*id="pd-data"[^>]*>(.*?)</script>', html, re.S)`, then
   `json.loads(match.replace('<\\/', '</'))`. Save it as `data/desk.json`.
3. Save the page with that block's content replaced by `__PD_DATA__` as `site/template.html`.
4. Rebuild the scripts from §4 and the rules in `PROJECT_CONTEXT.md` §5. The tests in §5 describe the
   expected behaviour.

---

## Appendix: the headless page test
```python
import asyncio, sys
from playwright.async_api import async_playwright

async def main(path):
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 400, "height": 900})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.route("**/*", lambda r: r.abort() if "fonts.g" in r.request.url else r.continue_())
        await pg.goto("file://" + path)
        for t in ["#t-all", "#t-main", "#t-stats", "#t-news", "#t-newstrends", "#t-src", "#t-main"]:
            await pg.click(t); await pg.wait_for_timeout(150)
        for wk in ["2026-W42", "2026-W40", "ALL"]:
            await pg.locator("select[data-f=week]:visible").select_option(wk); await pg.wait_for_timeout(150)
        print("errors", errs); await b.close()

asyncio.run(main(sys.argv[1]))   # python3 test_page.py "$PWD/preview.html"
```
