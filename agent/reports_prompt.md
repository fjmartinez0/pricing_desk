# Pricing Desk: classify and write up changes reported by PricingSaaS

Today is {{TODAY}} ({{WEEKDAY}}). Run id: `{{RUN}}`.

Our pipeline captures companies' pricing pages itself. It also reads PricingSaaS, a site that tracks
far more companies, and saves its "diff" pages: one company's before → after for one day or one week.
Your job: for **every** report in `{{INPUT_FILE}}`, say which company it is, what kind of change it is
and, if it is kept, write the record. Python code checks everything you write.

## Inputs (read them with the Read tool)
- `{{INPUT_FILE}}`: `reports[]`, each with `report_id`, `week`, `change_date`, `urls` (PricingSaaS diff pages),
  `files` (their saved text: **your evidence**), `article_files` (PricingSaaS articles about the same change),
  `registry_guess` / `registry_name` (our best match in the registry, may be null or wrong) and
  `existing_records` (records we already have for that company and week).
- `data/registry.json`: the companies we track (slug, name, domains, tier).
- `data/desk.json`: all records, if you need more context.

Work from the saved files only. Do not browse PricingSaaS. You may use WebSearch/WebFetch only to find a
**new** company's own pricing page (see `new_company`).

## Output: write `{{OUTPUT_FILE}}` early and update it as you go
```json
{"type": "reports", "run": "{{RUN}}", "items": [ ... one item per report_id ... ]}
```
Each item:
```json
{
  "report_id": "atlassian.bitbucket:2026-W43",
  "company": "atlassian",
  "new_company": null,
  "kind": "price_increase",
  "why": "one sentence: what changed, for the audit log",
  "detail": "card",
  "record": { ... },
  "promo": null
}
```

### company / new_company
- `company`: the registry slug this report is about. Product lines map to their company
  (`atlassian.bitbucket` → `atlassian`, `pagerduty.incident` → `pagerduty`). Check `registry_guess`; fix it if wrong.
- If the company is not in the registry, set `company` to null and fill `new_company`:
  `{"name": "Tailscale", "category": "<one of desk.json categories[].name>", "segment": "B2B"|"B2C"|"Both",
  "pricing_urls": ["https://tailscale.com/pricing"], "domains": ["tailscale.com"], "source_url": "<the PricingSaaS diff URL>",
  "why": "reported by PricingSaaS"}`. Find the pricing URL on the company's **own** site; if you can't, give
  `"pricing_urls": []` and `"domains": []` (the registry agent finds it later). The company is added to the
  registry either way, and from then on we capture its page ourselves.

### kind, detail, record, promo
Exactly as in `agent/changes_prompt.md` (read it once: the kinds, the keep rule, every record field and
allowed value). Differences for reports:
1. **Evidence = the saved PricingSaaS text** (`files` and `article_files`). Every number in `rows`, `delta`,
   `deltaSub`, `short` and `headline` must appear in that text. Percentages and ×-multipliers you calculate
   are fine. Code checks this: a card that fails becomes a one-line record, a line that fails is held back.
2. Describe **this** change only: the one in `change_date` / `week`. Ignore any history of older changes.
3. `stated` / `statedUrl`: only the company's own words on the company's own site, never PricingSaaS's
   words. Usually null.
4. `read`: our inference, as usual. Don't copy PricingSaaS's sentences; write your own.
5. **Duplicates:** if `existing_records` already cover this change, `kind` is `duplicate`.
   Two reports about the same change (a day page and a week page) → keep one, mark the other `duplicate`.
6. PricingSaaS calls many things "changes". Apply the keep rule strictly: prices shown for the first time are
   `price_reveal`, prices removed are `price_hidden`, a new model or product added to a price list without
   changing existing prices is `new_feature`, page copy is `wording`.
7. If PricingSaaS says the page looks like a test (A/B, experiment marker, prices that flip), say so in
   `headline`/`read` and add a `caveat`.
8. `detail`: `card` for tier 1–2 companies in the registry (and for new companies only when the change is
   clearly important), otherwise `line`.

Finish by checking that `{{OUTPUT_FILE}}` is valid JSON and has one item for every report_id.
