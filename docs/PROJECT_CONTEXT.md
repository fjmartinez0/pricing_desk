# Pricing Desk: project context, decisions and next steps

**Updated:** Wed 11 Nov 2026. **Supersedes** every earlier handoff (v1–v7).
**Owner:** fmz. **Language:** English.

> **Claude: read this first.**
> This file, `BUILD_GUIDE.md` and `pricing_desk.zip` (the code) are everything the project needs.
> 1. Read this file fully, then `BUILD_GUIDE.md`.
> 2. Go to **§10 Next steps** and start with the first step that isn't marked done.
> 3. Installation is done (§9). Use `pdpy` (python.org Python) for every project command, never `python3`.
> 4. Never weaken the rules in §5. They are what makes fully automatic publishing safe.

---

## 1. What the product is

A daily, phone-friendly "newspaper" of software price changes, so the reader never has to open
source links. Scope: software only, for education and personal use.

One self-contained HTML page with these tabs:
- **News**: the gist, key numbers and "why it matters" for each story.
- **Main Price Changes**: Ranked and Timeline views of the relevant changes.
- **All Price Changes**: Changes and Promotions views.
- **Statistics**: Analysis, and Models & patterns.
- **Market Trends from News**
- **Sources**

A week selector picks the current edition, all weeks, a month, or one week.

**Where it lives:**
- **Until the pipeline runs:** the claude.ai artifact https://claude.ai/artifact/XrojnVsyGGEqdpwdfpw9Yb
  ("SaaS Pricing Desk"), edited by hand in Claude conversations.
- **From installation on:** GitHub Pages at `https://<github-user>.github.io/pricing_desk/`, rebuilt on
  every push. Repo `pricing_desk` (public). The artifact is frozen as of 20 Oct 2026; its data is
  identical to `data/desk.json` in the zip.

---

## 2. How it works (architecture)

This follows the user's own blueprint ("scheduled AI-assisted data pipeline on a home Mac"),
adapted to this project. Parts of the blueprint that don't apply were left out: its design system,
the job-board notes, and the job-posting status words.

**Environment:**
- **Mac mini** that never sleeps, with the user logged in so the Keychain is unlocked.
- **launchd** job `com.fmz.pricing_desk`, running at **07:00 and 19:00** America/Toronto.
- **python.org Python 3.13** (`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`, alias **`pdpy`**
  on the Mac). Homebrew's `python3` comes first on the user's PATH and must not be used for this project.
  Standard library everywhere, except Playwright in one module.
- **Repo on the Mac:** `/Users/fernandomartinez/personal_projects/pricing_desk`.
- **git** pushing to GitHub over HTTPS, using the Keychain helper.
- **Claude Code** run headless on the user's Claude subscription. It can only write to `proposals/`.
- **GitHub Actions**, with two workflows:
  - `publish`: validate, run the unit tests, build the page, deploy to Pages;
  - `watchdog`: a daily check that alerts if no run has happened in 36 hours.
- **ntfy** on the iPhone, topic **`fmz_pricing_desk`**.

**One run** (`scripts/run_daily.sh`):
1. `git pull`, then keep a copy of `desk.json` to compare against at the end.
2. **capture.py:** fetch every tracked pricing page (static first, Playwright when the page needs
   JavaScript) and normalize it to text. A new page version must appear on **2 captures in a row**
   before it counts. A page that shows two different versions within one run is reported as a
   possible price test. Confirmed changes go into `data/backlog.json`.
2b. **pricingsaas_capture.py** (hybrid, D39): read PricingSaaS's daily briefings (clicking "Load more",
   about 9 days back) and this and last week's weekly review; fetch new articles and diff pages; queue them
   in `data/reports.json`.
3. **Claude**, up to four tasks:
   - classify and write up the backlog (`agent/changes_prompt.md`);
   - classify up to 40 PricingSaaS reports (`agent/reports_prompt.md`);
   - find pricing URLs for up to 30 companies that need one (`agent/registry_prompt.md`);
   - when an edition is due, write the weekly edition (`agent/edition_prompt.md`).
4. **coverage_check.py:** quiet alerts if the run did less than expected.
5. **apply_proposals.py:** the rules in §5 decide what enters the data.
6. **recheck.py:** check quotes and news numbers against the live pages.
7. **validate.py:** integrity rules. On failure the run's changes are stashed, nothing is published,
   and an alert is sent.
8. Stamp the run time, commit, push. GitHub Actions validates again and deploys.
9. **notify.py:** alerts to the iPhone.

---

## 3. Decisions log

### Content decisions (D1–D20, still valid)
| # | Decision |
|---|---|
| D1 | Use feeds and public pages first; scrape only where nothing else exists. *(Now: our own captures of public pricing pages are the primary source.)* |
| D2 | Keep the news source list small (about 5); much 2026 pricing content is recycled. |
| D3 | Tag changes B2B / B2C / Both instead of splitting tabs. |
| D4 | News cards are The gist / Key numbers / Why it matters. |
| D5 | Off-topic news posts collapse to one line. |
| D6 | Price-change cards follow this order: headline delta → one-line summary → Before/After table → Who it hits → They say (only if stated) → Why · our read. |
| D7 | Keep the company's stated reason separate from our read (inference), and label the inference. |
| D8 | Show "They say" only when a reason exists. |
| D9 | Rank by market weight, then by how many customers the change reaches, never by % size. |
| D10 | Three tiers: Market leaders, Notable, Smaller. |
| D11 | Track packaging, limits, minimums and model access, not just list price. |
| D12 | Colour and the delta chip carry the change type: up = pay more, down = pay less, pack = restructured. |
| D13 | The only filter on change lists is segment. |
| D14 | `≈` marks values back-calculated from a reported %. *(Automated cards never use ≈: numbers must be on the page.)* |
| D15 | Own watchlist of 20 pricing pages: Notion, Canva, Slack, HubSpot, Figma, 1Password, Duolingo, Zoom, Atlassian, Microsoft 365, Adobe, ChatGPT/OpenAI, Linear, Airtable, Calendly, Dropbox, Salesforce, Intercom, Zapier, Grammarly. |
| D16 | Watchlist companies always rank as market leaders (tier 1). Intercom is therefore tier 1 from now on, although hand-built weeks show it as tier 2. |
| D17 | Every kept change gets at least a one-line record (`detail: "line"`). Tier 1–2 changes get full cards and count as **Relevant** (`isMain = c.main ?? tier<=2`). |
| D18 | Keep rule (§6). |
| D19 | Promotions are separate (`promos`): limited-time discounts added, changed or ended. They aren't changes. |
| D20 | Week coverage notes: `coverage` (`partial`, `subset`, or `tracked` for automated weeks) plus `note` in `weeks[]`. Picking a single week shows its note; multi-week views list only partial weeks. |

### Automation decisions (D21–D38, decided 19–20 Oct 2026)
| # | Decision |
|---|---|
| D21 | **Own company registry** (`data/registry.json`) is the core asset, so PricingSaaS can be dropped. Seeded with the 263 companies in the data plus the watchlist. It grows from the news and from PricingSaaS's weekly review, but those only add companies to watch, never records. |
| D22 | **Architecture from the user's blueprint** (§2): Mac mini + launchd + headless Claude Code + git + GitHub Pages + ntfy. "The AI proposes; code decides." |
| D23 | **Names:** project and repo `pricing_desk` (underscore); launchd label `com.fmz.pricing_desk`; **one ntfy topic `fmz_pricing_desk`**, no random suffix. Problems go to the same topic with high priority and a ⚠️ tag. The topic name can be guessed, which is fine because only public price data is sent. |
| D24 | **Playwright is allowed only for pages that need JavaScript**, isolated in `scripts/browser_capture.py`. A company switches to browser capture automatically when its static page shows no prices. |
| D25 | **Publishing is fully automatic.** The checks in code (§5) replace a human review. |
| D26 | **The dashboard stays exactly as designed.** `site/template.html` is the page with its data block replaced by `__PD_DATA__`. At publish time GitHub Actions injects `data/desk.json`, so the built page is never committed. The page stays one self-contained file that also works offline (`build_site.py --out`). |
| D27 | **Capture twice a day (07:00, 19:00).** A change needs 2 consecutive captures; a page that flips within one run 3 times is reported as a possible A/B price test (`unstable`). |
| D28 | **Week attribution:** a change belongs to the week of the last capture that still showed the old page. **Week numbering keeps PricingSaaS's convention, one ahead of ISO** (week 42 = 5–11 Oct 2026), because existing data uses it. Note: the last days of December fall into next year's W01. |
| D29 | **Edition:** closes the Monday–Sunday week on Monday at 19:00 (18 hours after the week ends, so Sunday changes are confirmed). If the agent fails, nothing is published and every following run retries. **The first automatic edition is week 44 (19–25 Oct), published Tue 27 Oct 19:00 (D49)** (moved from W45 on 25 Oct so the default view stops showing week 42). Weeks before W44 are hand-built or PricingSaaS reports (`FIRST_AUTO_EDITION`). |
| D30 | **Nothing is invented:** the rules in §5 are enforced in Python, not just asked of the agent. |
| D31 | **Keep rule in code:** the agent assigns each change one `kind`; a fixed table in `common.py` keeps, drops or makes it a promo. |
| D32 | **Append-only:** records are never deleted. Undecided changes stay in the backlog and are retried, then given up after 4 runs with an alert. Suggested URLs are verified by the first capture. |
| D33 | `market_context` is computed from our own counts (total, up, down, pack), no longer from PricingSaaS totals. |
| D34 | **Polite capture:** robots.txt is respected (a blocked company gets status `blocked`), the user agent identifies itself, there is a 2-second delay between companies, and aggregator domains are never used as a pricing page or as proof. |
| D35 | **Watchdog:** GitHub Actions alerts the phone if `data/meta.json` shows no run for 36 hours, since the Mac can't report its own death. |
| D36 | **Currency risk:** the Mac is in Quebec, so some sites may show CAD. Values are copied as shown, with a caveat. If a site does it, set a US URL with `add_company.py`. |
| D37 | **Code must stay maintainable:** one script per step, every rule in `common.py`, standard library except Playwright, unit tests on known cases, README + RUNBOOK. |
| D38 | ~~Backfill is closed at weeks 38–43.~~ Superseded by D42. |

### Decisions of 24 Oct 2026 (D39–D44)
| # | Decision |
|---|---|
| D39 | **Hybrid: our captures + PricingSaaS reports.** Every run reads PricingSaaS's daily briefings (`/news`, "Load more" to the end, about 9 days) and weekly reviews (`/news/week/2026Wnn`), follows them to the per-company **diff pages** (`/companies/<slug>/diffs/2026Dnnn` or `2026Wnn`), saves their text in `data/pricingsaas/pages/` and queues them in `data/reports.json`. Companies they name are added to the registry, so from then on we capture them ourselves. Educational, non-commercial use (user's decision); robots.txt is still respected. Amends D21 and D34. |
| D40 | **Reported records:** a kept change found only through PricingSaaS becomes a record with `src: "PricingSaaS report"`, `reported: true`, `url` = the PricingSaaS diff page and `evidence.files` = the saved texts. Every number must appear in that saved text, after cutting the page's history, peer and FAQ sections. The page labels them "Reported by PricingSaaS" / "via PricingSaaS". |
| D41 | **Our own capture wins.** If we captured the company before the change date, the report waits up to 4 runs for our own record of that company and week. If ours arrives, the report only corroborates it (logged in `checks.jsonl`); if not, the report is published and a problem alert says our capture missed it. Hand-built weeks (38–43) never get a second record for a company they already have. At most 3 reported records per company per week. |
| D42 | **Backfill reopened** (supersedes D38): weekly reviews from week 35 on can be read with `pricingsaas_capture.py --review …`. Weeks created this way (35–37, and 44) are marked partial with a note. Weekly reviews itemize only about 20 of the 150–280 changes PricingSaaS counts per week. |
| D43 | **Page tweaks:** one coverage box per week view (`weekNoteHTML`), News newest first, masthead "Weekly edition", edition `period` = the week range. |
| D44 | **Weekly edition stays** (Monday 19:00, captures twice a day). Decide on a daily "this week so far" panel after two weeks of data (around 8 Nov), based on how many Relevant changes arrive per day. |

### Decisions of 24 Oct – 11 Nov 2026 (D45–D56)
| # | Decision |
|---|---|
| D45 | **"Updated …" line** under the title: the last run time from `data/meta.json`, injected by `build_site.py` as `updated_at` (not stored in desk.json), shown in the reader's time zone, orange with "no update for …" after 36 hours. |
| D46 | **Claude usage limits** (hit on 24 Oct after the backfill runs): classification tasks (changes, reports, registry) run on **Sonnet**, the weekly edition on **Opus** (`CLAUDE_MODEL_<TASK>` in config.env overrides). When Claude answers with a usage limit, the run skips the remaining agent tasks and sends one "usage limit, nothing lost" alert. Backlog changes and reports count an attempt only when the agent wrote a proposal and left them out, so a limit never makes the pipeline give items up. |
| D47 | **Run ids are per hour** (`YYYY-MM-DDTHH`), so a manual run in the same hour as a scheduled one shares its id: it overwrites that run's proposal files (harmless) and used to re-send its problem alerts. Since 24 Oct a run clears `.run/problems_<run>.jsonl` and `.run/agent_limited_<run>` after taking the lock. |
| D48 | **Move explorer (/feed) read every run.** The page embeds every row of PricingSaaS's latest weekly batch (about 200–280, one per company) even though its table shows 50; rows leave the free view after 7 days. Each run reads the embedded rows, keeps the list in `data/pricingsaas/feed/<period>.json` and follows each row's weekly diff page into the normal report queue. A saved copy of the page can be imported with `pricingsaas_capture.py --feed-file` (used for week 43 on 25 Oct). Reports go to the agent in up to `REPORTS_PARTS` (3) calls of `REPORTS_BATCH` (40) per run; a part the agent doesn't answer costs no attempt. |
| D49 | **Edition moves to Tuesday 19:00** (`EDITION_READY_AFTER` 18 h → 42 h). PricingSaaS posts its weekly batch on Monday over several hours (week 44: from 06:00 Toronto), and the edition step reads the data before its own run merges new decisions. Tuesday 19:00 is the first run that sees the batch decided (two runs × 120 reports, newest week first). Amends D29. |
| D50 | **Merge bug of 26–28 Oct fixed; merges are restorable.** The reported-records cap summed `None` when one of our own records (no `reported` key) shared a company and week with a PricingSaaS report, which first happened on 26 Oct; four runs (26T19, 27T07, 28T07, 28T19) stopped at merge. Because `update_backlog` had already saved, their decided page changes were lost from the backlog. Now a failed merge puts `backlog.json` and `reports.json` back, re-applied proposals skip what is already published, and `apply_proposals.py --run <id> --recover` re-applies an earlier run's changes and report decisions (not its edition or registry). |
| D51 | **Backfill progress on the page; wider desktop layout.** `build_site.py` injects `backfill` (PricingSaaS reports still waiting per week, from `reports.json`, and how many changes PricingSaaS listed per week, from `data/pricingsaas/feed/`). The page shows a "Still filling weeks …" pill under the title while reports wait, and each week's note says how many remain; hand-built weeks completed from the full list get an accurate note instead of the stale "free 7-day view" text. From 1,000 px wide the page is 1,180 px (was 760) and change and news cards go two per row; running text keeps its 65ch measure. Missing news authors are no longer shown as "null". |
| D52 | **Bot protection: browser fallback on refusal.** A static fetch answered with HTTP 401/403/429/503 now gets one browser try; if the browser page shows prices, the company switches to browser capture (OpenAI was refused from 25 Oct and paused on 31 Oct). The browser also accepts a page whose network never goes idle: after the 45 s wait it uses the loaded document (openai.com timed out on "networkidle"). A run that fails at a step now also sends the problems it had already raised (the "4 failed captures" alert for OpenAI was lost in the failed merges of 26 Oct). |
| D53 | **Page crash of 3–6 Nov fixed; one entry per company and week; page check every run.** A short "line" record of a tier-1/2 company (SugarCRM, our own capture, week 45) was drawn as a full card, which needs before/after rows; the JavaScript error stopped the rest of the page from drawing (empty Statistics and Timeline, Period menu not redrawing). Cards now draw records with or without rows. Main Price Changes and the front page show one entry per company and week: a company with several changes that week gets one card with a section per change ("+ N more changes" on the front page). The multi-week coverage note says which weeks come from PricingSaaS's full list, which only from its weekly review, and which include our captures. `scripts/check_page.py` opens the built page in Chromium and goes through every tab, sub-view, period and category; any JavaScript error is a problem alert (step 7 of `run_daily.sh`, after validate; the data is still published). |
| D54 | **Ranking by importance, the same across weeks.** Within a tier (market leaders, notable, others), changes are ordered by `desk.importance()`: company weight (1.5 for `HEADLINE_COMPANIES` in `common.py`: OpenAI, Anthropic, Microsoft 365, Google Workspace, Salesforce, Adobe, Shopify, Atlassian, GitHub) × who it hits (reach, or 3 for all/free plans, 2 entry/mid, 1 top/enterprise/add-on) × size (10 + % change, capped at 100; 15 when no %) × 1.5 for a list or unit price; one-line records count half. Stored as `score`; `rank` is the order within a week. A month or "all weeks" view ranks on `score` (before, it took each week’s #1, then each #2, so the month front page was one item per week, whatever its size). Every merge reranks every week. |
| D55 | **Agent errors say what went wrong.** From 7 Nov 19:00 to 10 Nov the Claude Code login on the Mac had expired ("OAuth session expired and could not be refreshed"); every agent call failed on its first request, and the alerts only said "Agent wrote no decision". `run_agent.sh` now classifies a failed call: usage limit (as before), expired login (skips the run's remaining agent tasks and sends "Claude login on the Mac mini has expired… run `claude`, then /login"), or any other error (sent with Claude's own message). |
| D56 | **Edition archive, catch-up editions, bulleted write-ups, 90-day Market Trends.** Every edition is kept in `desk.json` under `editions[<week>]` (the top-level `news`, `patterns`, `stats_analysis`, `news_trends` stay the current edition's copy); editions published before this were restored from git with `restore_editions.py` (42, 44, 45, 46). On the page, the Period selector is also on **News** (a past week shows its edition; a month or all weeks stacks the editions, newest first), and **Main → What connects them** shows a past week's own written patterns. **Market Trends** is written from the stories of the last 90 days (up to 13 earlier editions), and its Stats library shows this edition's numbers first, earlier ones folded. **Statistics** stays per edition (Models & patterns is already cumulative). Format 2 (`EDITION_FORMAT`): a story has a one-sentence `gist` plus 2–4 `points`; a pattern has a 1–2 sentence `p` plus `points` `[{id, text}]`, one per change, and the page prints the company and "via PricingSaaS". A pattern bullet may only quote numbers its record shows (merge); story bullets' numbers must be in the article (recheck). Runs with no edition due write one **catch-up edition** from `EDITION_BACKFILL` (46 rewrite, then 43, 41, 40, 39, 38, 45, 44); a catch-up for an earlier week is archived only and never moves `current_week`; one rejected twice is skipped with an alert. Story ids are unique across editions; a rewrite unlinks its replaced stories from other editions' trends. Wide screens: lead story spans the row (text left, numbers right), patterns and themes in two balanced columns, Stats library in two columns. |

---

## 4. Sources

- **Primary:** the companies' own pricing pages, captured twice a day (registry).
- **Secondary (hybrid, D39):** PricingSaaS daily briefings and weekly reviews, read every run; their diff pages
  back "reported" records and point to companies to add.
- **News for the edition** (`agent/sources.json`): Growth Unhinged, PricingSaaS newsletter (Good Better
  Best), AgentDeals digest, Ibbaka, and the PricingSaaS Pulse weekly review. The review is used only to
  find companies we miss.
- **PricingSaaS** (`pricingsaas.com/feed`, `/news/week/2026Wnn`) was the source for weeks 38–43, built by
  hand. Its free unfiltered feed shows only the last 7 days, about 50 rows. Weekly review pages exist from
  week 35 (checked 24 Oct 2026).
- **In a claude.ai conversation**, `web_fetch` only opens URLs that came from a search result or from the
  user's message. Headless Claude Code on the Mac doesn't have that limit.

---

## 5. Rules the code enforces (never weaken these)

Rules 1–10 apply to our own captures. **Rule 11** covers PricingSaaS reports (D40–D41).

1. **Cards are never invented.** Every number in a card's rows must appear in the captured page text:
   before-cells in the old page, after-cells in the new one. Numbers in `delta`, `deltaSub`, `short`
   and `headline` must be on either page. Percentages and ×-multipliers we calculate are exempt.
   - A card that fails is **downgraded to a one-line record**.
   - A one-line record that fails is **held back**.
2. **"They say" (`stated`)** is kept only with a `statedUrl` on the company's own domain, and
   `recheck.py` must then find the exact words on that page. Otherwise it's removed and the card stays.
3. **News "Key numbers"** must appear in the article itself (checked online). Numbers that fail are
   removed; an article that doesn't load is removed.
4. **Stats figures** (`stats_analysis.fig`) may only use numbers from the stats code computes for the
   week. `market_context` is computed in code.
5. **The keep rule** (§6) is applied from the agent's `kind`, by code. Price reveals are caught in code
   too: a price change with no before-price is dropped.
6. **Tier, IDs, week, dates, rank, company fields and `src`** are assigned by code. The registry tier
   wins, and watchlist companies are always tier 1.
7. **Enums, lengths and links:** fixed lists for pattern, group, segment, plan level, model, applies-to
   and magnitude basis. No URLs inside text fields.
8. **Duplicates** (same company, same summary or same rows) are dropped.
9. **Two validation gates** (Mac and GitHub Actions). A failing run publishes nothing.
10. **Evidence is kept:** every automated record carries `evidence` (before/after snapshot files and
    the diff id). Snapshots and every proposal are committed, and every external check is logged in
    `data/checks.jsonl`.
11. **PricingSaaS reports:** numbers must appear in the saved PricingSaaS diff page or article text (history,
    peer and FAQ sections cut); "They say" still needs the company's own site; a company we already capture
    waits for our own capture (D41); reported records must link a pricingsaas.com diff page and carry
    `reported: true` (validator); a report never overwrites or duplicates an existing record.

---

## 6. Keep rule (D18)

**Keep** (kinds):
- `price_increase`, `price_cut`
- `limit_change`: limits, allowances and caps going up or down
- `plan_change`: a plan added (with a price), removed or merged
- `feature_move`: a feature moving between tiers or being removed
- `metering`: new metering or billing units
- `free_plan`: free-plan changes
- `became_paid`: an included feature becoming paid

**Drop:**
- `new_feature`: new features or products, including new priced add-ons for new capabilities
- `wording`: wording, positioning and renames with no price change
- `price_reveal`, `price_hidden`
- `trial`: trial-length changes
- `support`: support and services
- `non_software`: devices, shipping, interest rates
- `duplicate`: a change already recorded in an earlier week
- `noise`: layout, cookie text, rendering differences

**Promotions:** `promo` (temporary discounts, added, changed or ended) go in `promos`.

**Open question for the user:** should trials and new priced AI add-ons count? (Examples: TradingView
removing free trials, Dynatrace's $0.10-per-AI-unit add-on.) Today they're dropped.

---

## 7. Data model (summary; full detail in BUILD_GUIDE.md §3)

`data/desk.json` is exactly the page's `pd-data` object. Its top-level keys:
- `current_week`, `today`, `edition_date`, `period`
- `week_order`, `weeks[]`
- `tiers`, `pattern_cats`, `categories`
- `changes[]`, `companies{}`, `promos[]`
- `news`, `patterns`, `stats_analysis`, `news_trends`, `market_context` (the current edition)
- `editions{}`: every edition by week (D56)

New fields on automated records (the page ignores them): `reach` (1–3), `statedUrl`, and `evidence`.

`data/registry.json` holds one entry per company: `name`, `tier`, `category`, `segment`, `watch`,
`pricing_urls[]`, `domains[]`, `capture` (`static` or `browser`), `status`, `ignore_patterns[]`, `added`,
`source`, `source_url`, `url_attempts`, `notes`, and the page's company fields. The statuses are:
- `needs_url`: no pricing URL yet;
- `candidate`: URL suggested, verified on the next capture;
- `active`;
- `paused`: after 7 days of failed captures;
- `blocked`: robots.txt forbids access;
- `dead`: three suggested URLs failed.

---

## 8. Current state (11 Nov 2026)

**Running on the Mac mini since 24 Oct 2026**, twice a day (07:00, 19:00 Toronto), hybrid since 25 Oct.
- **Registry:** 1,345 companies (29 tier 1, 40 tier 2, 1,276 tier 3): 410 active, 927 `needs_url`
  (mostly added from PricingSaaS reports), 1 candidate, 4 blocked, 2 paused (OpenAI: bot check, D52; Explorium:
  pricing page 404 since 3 Nov), 1 dead (Adobe, watchlist, since 24 Oct). Duolingo still has no URL.
- **PricingSaaS:** 2,412 reports, 2,405 done, 7 of week 46 waiting for our own capture (D41); `/feed` read every
  run (D48). Weeks 38–43 have PricingSaaS's full list (imported 25 Oct from a signed-in save); weeks 35–37 only
  the weekly review's handful. Nothing before week 35.
- **Catch-up after the login outage (D55) is done:** the user's manual run of 10 Nov (`2026-11-10T19`, +60) and
  the runs of 11 Nov (+44, +6) emptied the backlog and the report queue.
- **Editions:** 44 (Tue 27 Oct), 45 (Tue 3 Nov) and 46 (written by the manual run of 10 Nov, which read week 46
  before that run's merge: 35 of its now 130 changes, 8 of 9 Relevant). 46 is the first catch-up rewrite (D56).
  Week 42's hand-written edition (1–19 Oct) is kept as is. Week 47's edition is due Tue 17 Nov 19:00.
- **Repo size:** `data/` 44 MB (2,457 PricingSaaS diff pages).

| Week | Dates | Changes | Relevant | Promos | Coverage |
|---|---|---|---|---|---|
| 47 | 9–15 Nov | 15 so far | 4 | 6 | Our captures + PricingSaaS, in progress |
| 46 | 2–8 Nov | 130 | 9 | 49 | Our captures + PricingSaaS, **current edition** (to be rewritten, D56) |
| 45 | 26 Oct–1 Nov | 136 | 20 | 52 | Our captures + PricingSaaS, edition Tue 3 Nov |
| 44 | 19–25 Oct | 123 | 11 | 25 | Our captures (from 24 Oct) + PricingSaaS, edition Tue 27 Oct |
| 43 | 12–18 Oct | 103 | 11 | 22 | Hand-built + PricingSaaS full list (263 rows) |
| 42 | 5–11 Oct | 108 | 23 | 20 | Hand-built + full list (231), last hand-written edition |
| 41 | 28 Sep–4 Oct | 107 | 21 | 34 | Hand-built + full list (280) |
| 40 | 21–27 Sep | 107 | 16 | 35 | Hand-built + full list (277) |
| 39 | 14–20 Sep | 95 | 10 | 24 | Hand-built + full list (223) |
| 38 | 7–13 Sep | 88 | 8 | 17 | Hand-built + full list (176, may be cut where the user stopped scrolling) |
| 35–37 | 17 Aug–6 Sep | 3–4 each | | | Weekly review only |

## 9. Install and first run (done 24 Oct 2026; kept for a reinstall)

On the user's Mac, use `pdpy` wherever this section says `python3`.

Assumed already in place: python.org Python 3.13, git configured with GitHub (Keychain helper, token
with the **workflow** scope), Playwright for Python. The GitHub repo **doesn't exist yet**.

1. **Unzip the project into your home folder**, not Desktop, Documents or Downloads: macOS blocks
   launchd jobs from those folders.
   ```bash
   cd ~ && unzip ~/Downloads/pricing_desk.zip && cd ~/pricing_desk
   ```
2. **Check the tools:**
   ```bash
   python3 --version                       # 3.13.x
   python3 -c "import playwright; print('playwright ok')"
   python3 -m playwright install chromium  # downloads the browser if it isn't there yet
   claude --version                        # 2.1.259 or later
   claude auth status || claude auth login # signed in with your Claude subscription
   ```
   If you see HTTPS certificate errors later, run `/Applications/Python\ 3.13/Install\ Certificates.command` once.
3. **Run the tests:** `python3 -m unittest discover -s tests -v`. All 15 should end with `OK`.
4. **Create the GitHub repo:** on github.com → New repository → name `pricing_desk` → **Public** →
   no README, .gitignore or license → Create. Then open Settings → Pages → Build and deployment →
   Source: **GitHub Actions**.
5. **Push the code** (replace `<user>`):
   ```bash
   git init -b main
   git add -A
   git commit -m "Pricing Desk: initial pipeline"
   git remote add origin https://github.com/<user>/pricing_desk.git
   git push -u origin main
   ```
   On GitHub, open Actions: the **publish** run should go green, and the page appears at
   `https://<user>.github.io/pricing_desk/`, showing the same content as the claude.ai artifact.
6. **Configure:**
   ```bash
   cp config.example.env config.env
   open -e config.env    # set DASHBOARD_URL=https://<user>.github.io/pricing_desk/
   ```
7. **Phone:** install **ntfy** from the App Store, tap + and subscribe to `fmz_pricing_desk` (server
   ntfy.sh). Then run `python3 scripts/notify.py --test`; a test notification should arrive, and
   tapping it opens the page.
8. **Try one capture without saving:** `python3 scripts/capture.py --company slack --dry-run`. You
   should see Slack's plan names and prices as text.
9. **Mac settings:**
   - System Settings → Energy: **Prevent automatic sleeping** on, **Start up automatically after a
     power failure** on.
   - Users & Groups: **Automatic login** for your user, which needs FileVault off. If FileVault must
     stay on, accept that a power cut needs a manual login; the watchdog will tell you.
10. **Install the schedule and run once now:**
    ```bash
    bash scripts/install_mac.sh --run-now
    tail -f logs/$(date +%Y-%m-%d).log      # Ctrl-C to stop watching
    ```
    The first run captures the watchlist pages as a **baseline** (no changes yet) and asks Claude for
    pricing URLs for the first 30 companies. It takes about 5–15 minutes.
11. **Confirm three things:**
    - a new commit `run …` on GitHub;
    - the **publish** Action is green;
    - `data/meta.json` on GitHub shows `last_run_at`.

    From now on, runs happen at 07:00 and 19:00 by themselves.

If a step fails, the user pastes the error and Claude helps fix it before going on.

---

## 10. Next steps, in order

1. **Edition archive (D56).** After applying the patch: `pdpy scripts/restore_editions.py` once, then validate,
   commit, push. Then watch the catch-up, one edition per run without an edition due (about four days):
   week 46 rewritten in bullets first, then 43, 41, 40, 39, 38, 45, 44. Check each on the page (News with that
   week picked; Main → What connects them). Old weeks may have fewer stories if the news feeds don't reach
   back that far; an edition with fewer than 3 is rejected and, after 2 tries, skipped with an alert.
2. **OpenAI:** paused; PricingSaaS covers it. The browser gets OpenAI's bot check ("Verification successful.
   Waiting for openai.com…"). Don't try to get around the check. Also: ChatGPT plan amounts didn't appear in
   the browser text ("/ month" with no number); look at that only if OpenAI is captured again.
3. **Explorium:** its pricing URL returns 404 since 3 Nov; it's tier 3 and paused. Find the new URL or leave it.
   **Adobe** (watchlist) is still `dead`: `pdpy scripts/add_company.py --slug adobe --url
   https://www.adobe.com/creativecloud/plans.html --browser`. Duolingo still needs a URL.
4. **Weeks 35–37 and earlier:** only reachable from the signed-in PricingSaaS explorer. If the user wants them,
   they scroll further back, save the page ("Web Page, Complete") and run
   `pricingsaas_capture.py --feed-file <file> --max-fetches <n>` (only new rows are fetched; check with
   `--dry-run` first). The user accepted that this list comes from their signed-in account (D39 note).
5. **Ranking (D54):** check with the user that `HEADLINE_COMPANIES` is right; tune weights from mis-ranked examples.
6. **Watch:** "PricingSaaS reported … that our capture didn't record" alerts (capture misses: fix URL,
   `--browser` or ignore_patterns), repo growth, and the page check alert (D53).
7. **Ideas, not decided:** a cumulative Statistics → Analysis over several weeks (new stats code + agent task;
   the archived per-week findings could feed it); hold a due edition while its week's backlog or reports are
   still undecided (it bit once, after the D55 outage: built and tested on 10 Nov, not applied).
8. **Older open items (from 24 Oct):** a curated list of about 50 widely used products to add; the daily
   "this week so far" panel (D44); trials and priced AI add-ons in the keep rule; keep or drop the Sources tab;
   alert before a watchlist company goes `dead`.
