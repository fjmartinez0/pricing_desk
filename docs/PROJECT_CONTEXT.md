# Pricing Desk: project context, decisions and next steps

**Updated:** Sat 24 Oct 2026. **Supersedes** every earlier handoff (v1–v7).
**Owner:** fmz. **Language:** English.

> **Claude: read this first.**
> This file, `BUILD_GUIDE.md` and `pricing_desk.zip` (the code) are everything the project needs.
> 1. Read this file fully, then `BUILD_GUIDE.md`.
> 2. Go to **§10 Next steps** and start with the first step that isn't marked done.
> 3. Installation is done (§8). Use `pdpy` (python.org Python) for every project command, never `python3`.
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
| D29 | **Edition:** closes the Monday–Sunday week on Monday at 19:00 (18 hours after the week ends, so Sunday changes are confirmed). If the agent fails, nothing is published and every following run retries. **The first automatic edition is week 45 (26 Oct–1 Nov), published Mon 2 Nov.** Weeks before W45 are hand-built (`FIRST_AUTO_EDITION`). |
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
- `news`, `patterns`, `stats_analysis`, `news_trends`, `market_context`

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

## 8. Current state (24 Oct 2026)

**Installed and running** on the Mac mini since Sat 24 Oct 2026, 13:18 (first run). Runs at 07:00 and 19:00.
- Install issues met and fixed: the repo wasn't a git repo at first (step 5 redone); Playwright was installed
  in Homebrew's Python, not python.org's (fixed; use `pdpy`); zsh doesn't treat `#` as a comment when typing.
- First run: 13 of 19 watchlist pages captured (the other 6 needed Playwright, since fixed); 26 pricing URLs
  accepted from the registry agent.
- Page fixes applied (D43). Week 43 note rewritten.
- 8 companies added by hand from PricingSaaS's week 43 review: Shopify (tier 1), Tailscale, Remote, Buildkite,
  GorillaDesk, ApprovalMax (candidates), Precog, fileAI (needs_url).
- Registry balance checked: 127 companies A–K, 136 L–Z. The A–K gap was only in week 43's hand-built records.
- **Hybrid (D39–D42): built and tested, waiting to be applied** (`pricing_desk_hybrid.patch`), then backfill
  weeks 35–43 from the weekly reviews.

| Week | Dates | Changes | Relevant | Promos | Coverage |
|---|---|---|---|---|---|
| 43 | 12–18 Oct | 23 | 4 | 0 | Partial: free 7-day feed, companies A–K only; PricingSaaS counted 204 that week |
| 42 | 5–11 Oct | 58 | 21 | 5 | Subset (AI-moves view), **current edition** |
| 41 | 28 Sep–4 Oct | 55 | 18 | 10 | Subset + weekly review |
| 40 | 21–27 Sep | 44 | 11 | 10 | Subset |
| 39 | 14–20 Sep | 41 | 7 | 7 | Subset |
| 38 | 7–13 Sep | 29 | 5 | 4 | Partial |

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

1. **Apply the hybrid** (`pricing_desk_hybrid.patch`) and **backfill weeks 35–43** from PricingSaaS's weekly
   reviews: `pdpy scripts/pricingsaas_capture.py --review 2026-W35 … 2026-W43 --max-fetches 400`. The agent
   then works through the queue at 40 reports per run (a few runs). *Not done.*
2. **Watch the first days** (through about Wed 28 Oct):
   - companies captured grow (`data/meta.json` → `tracked_active`, or the status counter in RUNBOOK.md);
   - `data/reports.json`: reports move from `todo` to `done`; read the `outcome`s;
   - problem alerts, especially "PricingSaaS reported … that our capture didn't record" (a capture miss to fix
     with `scripts/add_company.py`: URL, `--browser`, ignore_patterns);
   - spot-check 2–3 snapshots in `data/snapshots/` for cookie banners or rotating text.
   - Duolingo has no URL yet; ask the user for one or pause it.
3. **Week 44 (19–25 Oct)** no longer needs building by hand: the briefings reach back about 9 days, so the
   hybrid reads week 44 automatically. Check on Mon 26 Oct that week 44 has records and a partial-week note.
4. **First automatic edition: Mon 2 Nov, 19:00** (week 45). Check: every card's numbers match its source page;
   "They say" only with real quotes; reported records labeled; news links work. Tune `agent/*.md` if the
   writing needs it; tune rules only in `common.py`, with a test.
5. **Weeks 45–48:** the hybrid now does most of the side-by-side automatically (corroborations and capture
   misses). Each Monday, skim the reports' outcomes and fix capture misses.
6. **Coverage by design:** draft a list of about 50 widely used software products across the 12 categories
   that aren't in the registry; the user reviews it once; add the chosen ones. (Offered 24 Oct, pending.)
7. **Decide on daily** (D44), around Sun 8 Nov: count Relevant changes per day; if most days have one, add a
   "this week so far" panel to the front page.
8. **Open questions to ask the user when relevant:**
   - should trials and new priced AI add-ons count (§6)?
   - keep or drop the Sources tab?
   - check the Cursor / X Subscription terms against xAI's own announcement.
