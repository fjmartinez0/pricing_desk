# Pricing Desk: find official pricing pages

Today is {{TODAY}}. Run id: `{{RUN}}`.

`{{INPUT_FILE}}` lists companies we want to track but have no pricing URL for yet. For each one, find the
company's **own** public pricing page (the page listing plans and prices). Use WebSearch and WebFetch.

Rules:
- Only the company's own domain. Never aggregators (PricingSaaS, G2, Capterra, GetApp, SaaSworthy, Vendr…).
- Use the US-English page if there is a choice (e.g. `/en-us/pricing`).
- 1–3 URLs per company: the main pricing page, plus separate pages for big product lines (e.g. an API price list).
- If the company has no public prices (contact sales only) or you cannot be sure, leave it out.
- `domains`: the company's domains, without `www.` (e.g. `["notion.com", "notion.so"]`).
  Every pricing URL must be on one of them.

Write `{{OUTPUT_FILE}}` early and update it as you go:
```json
{"type": "registry", "run": "{{RUN}}",
 "urls": [{"slug": "loom", "pricing_urls": ["https://www.loom.com/pricing"], "domains": ["loom.com"]}],
 "new_companies": []}
```
Code fetches each URL on the next capture and only accepts pages that show prices.
