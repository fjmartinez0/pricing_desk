# Pricing Desk: write the weekly edition for {{WEEK}}

Today is {{TODAY}}. Run id: `{{RUN}}`. The week {{WEEK}} ({{WEEK_LABEL}}) has closed. It may be the week that just
ended or an earlier week the archive is catching up on: either way, write about {{WEEK}} only.

## Inputs
- `data/desk.json`: all records. This week's changes are those with `"week": "{{WEEK}}"`.
  Records with `"reported": true` come from PricingSaaS reports at companies we don't capture yet; the rest
  from our own captures. When a pattern or stat leans on reported records, say so in its text.
  Earlier editions are in `editions` (older ones are written as paragraphs; write the bulleted format below).
- `{{STATS_FILE}}`: counts for this week, computed by code. **Every number in a stats figure must come from this file.**
- `agent/sources.json`: the news sources to read this week.
- `.run/news_window_{{RUN}}.json`: the stories of the editions before this one (about 90 days), for task 4.

## Tasks
1. **News (4–7 items).** Read this week's posts from the sources in `agent/sources.json` (published
   {{WEEK_LABEL}} or the days just after). Pick pieces about software pricing. Each item:
   `{"id": "kebab-case-id", "lead": true|false (exactly one lead), "src": "Growth Unhinged", "by": "author or null",
   "date": "7 Oct", "topic": "AI pricing", "rel": true|false (directly about pricing changes),
   "title": "…", "url": "https://… (the article itself)",
   "gist": "ONE sentence, at most 300 characters: the article’s point",
   "points": ["2–4 bullets, each one fact or argument, at most 200 characters, no trailing period"],
   "nums": [["76% vs 49%", "what the number means"], …], "why": "ONE sentence: why it matters to a buyer"}`.
   Bullets carry the detail the gist leaves out; don't repeat the gist or the key numbers in them. Every number
   in `nums` must be printed in the article (code checks the article online). Paraphrase; never copy sentences.
2. **Patterns (2–3).** What connects several of this week's changes:
   `{"t": "short title", "p": "1–2 sentences, at most 300 characters: the connection and why it matters",
     "points": [{"id": "a change id from this week", "text": "what that change did"}, …]}`, 2–8 points.
   The page prints the company name before each bullet and marks reported records, so `text` starts with the
   verb ("raised Qwen3.7-Max token prices by about two thirds"), never with the company, and doesn't say where
   the record came from. A bullet may only quote numbers shown on its record (code drops the bullet otherwise).
3. **Stats analysis (3–6).** `{"t": "finding", "fig": "8 of 13", "figNote": "what the figure counts",
   "p": "2–3 sentences", "ids": ["change ids from this week"]}`. Figures only from `{{STATS_FILE}}`.
4. **News trends (2–4).** Themes across this week's stories **and** the earlier ones in
   `.run/news_window_{{RUN}}.json` (the tab covers about 90 days): `{"t": "…", "p": "2–3 sentences",
   "nums": [["value", "meaning"]], "news": ["story ids: this edition's or the window's"],
   "changes": ["change ids, any week"]}`. Prefer themes that several weeks' stories support.
5. **Missed companies.** Read PricingSaaS's weekly review for this week if you can find it
   (search "PricingSaaS Pulse Weekly week N") and the news. List software companies with real price changes
   that are **not** in `data/registry.json`:
   `{"name": "…", "category": "one of desk.json categories", "segment": "B2B|B2C|Both",
     "pricing_urls": ["their own pricing page, if you found it"], "domains": ["…"], "source_url": "…", "why": "…"}`.
   These only grow the list of companies we track; they never become records directly.

Write `{{OUTPUT_FILE}}` early and update it as you go:
```json
{"type": "edition", "run": "{{RUN}}", "week": "{{WEEK}}",
 "news": [], "patterns": [], "stats_analysis": [], "news_trends": [], "missed": []}
```
Rules: no invented numbers or quotes; links only in `url`/`source_url` fields; curly apostrophes (’).
