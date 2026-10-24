# Pricing Desk: write the weekly edition for {{WEEK}}

Today is {{TODAY}}. Run id: `{{RUN}}`. The week {{WEEK}} ({{WEEK_LABEL}}) has closed.

## Inputs
- `data/desk.json`: all records. This week's changes are those with `"week": "{{WEEK}}"`.
  Records with `"reported": true` come from PricingSaaS reports at companies we don't capture yet; the rest
  from our own captures. When a pattern or stat leans on reported records, say so in its text.
  Look at last week's `news`, `patterns`, `stats_analysis`, `news_trends` for the style and length.
- `{{STATS_FILE}}`: counts for this week, computed by code. **Every number in a stats figure must come from this file.**
- `agent/sources.json`: the news sources to read this week.

## Tasks
1. **News (4–7 items).** Read this week's posts from the sources in `agent/sources.json` (published
   {{WEEK_LABEL}} or the days just after). Pick pieces about software pricing. Each item:
   `{"id": "kebab-case-id", "lead": true|false (exactly one lead), "src": "Growth Unhinged", "by": "author or null",
   "date": "7 Oct", "topic": "AI pricing", "rel": true|false (directly about pricing changes),
   "title": "…", "url": "https://… (the article itself)", "gist": "3–4 sentences in your own words",
   "nums": [["76% vs 49%", "what the number means"], …], "why": "1–2 sentences: why it matters to a buyer"}`.
   Every number in `nums` must be printed in the article (code checks the article online). Paraphrase;
   never copy sentences.
2. **Patterns (2–3).** `{"t": "short title", "p": "2–3 sentences", "ids": ["change ids from this week"]}`.
3. **Stats analysis (3–6).** `{"t": "finding", "fig": "8 of 13", "figNote": "what the figure counts",
   "p": "2–3 sentences", "ids": ["change ids from this week"]}`. Figures only from `{{STATS_FILE}}`.
4. **News trends (2–4).** `{"t": "…", "p": "…", "nums": [["value", "meaning"]], "news": ["news ids"],
   "changes": ["change ids, any week"]}`.
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
