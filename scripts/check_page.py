"""Open the built page in a headless browser and click through it: every tab, every period and every
category. Any JavaScript error is a failure (exit 1). A record the page can't draw stops the rest of
the page from drawing, which validate.py can't see (D53: one short record emptied Statistics on 3 Nov).

Usage:
  python3 scripts/check_page.py            # builds the page from data/desk.json into .run/ and checks it
  python3 scripts/check_page.py page.html  # checks an already built page
"""
from __future__ import annotations

import sys
from pathlib import Path

from common import RUN, log, report_problem


def check(path: Path, seen: dict | None = None) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors: list[str] = []
    seen = {} if seen is None else seen
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.route("**/*", lambda r: r.abort() if not r.request.url.startswith("file:") else r.continue_())
        page.on("pageerror", lambda e: errors.append(f"{where[0]}: {e}"))
        where = ["load"]
        page.goto(path.resolve().as_uri())
        page.wait_for_timeout(300)
        tabs = page.locator("nav button")
        names = [t.strip() for t in tabs.all_inner_texts()]
        seen["tabs"] = len(names)
        for name in names:
            where[0] = f"tab {name}"
            tabs.get_by_text(name, exact=True).click()
            for sub in page.locator("[data-sub]:visible, [data-msub]:visible, [data-asub]:visible").all():
                try:
                    sub.click(timeout=1000)
                except Exception:
                    pass
        main = names[1] if len(names) > 1 else names[0]

        def to_main():
            tabs.get_by_text(main, exact=True).click()
            ranked = page.locator('[data-msub="ranked"]')
            if ranked.count():
                ranked.click()
            return page.locator("select[data-f=week]:visible").first

        week = to_main()
        periods = week.locator("option").evaluate_all("os => os.map(o => o.value)")
        seen["periods"] = len(periods)
        for value in periods:
            where[0] = f"period {value}"
            week.select_option(value)
            for name in names:                       # every tab and sub-view draws with this period
                tabs.get_by_text(name, exact=True).click()
                for sub in page.locator("[data-sub]:visible, [data-msub]:visible, [data-asub]:visible").all():
                    sub.click()
            week = to_main()
        cat = page.locator("select[data-f=cat]:visible").first
        if cat.count():
            week.select_option("ALL")
            cats = cat.locator("option").evaluate_all("os => os.map(o => o.value)")
            seen["categories"] = len(cats)
            for value in cats:
                where[0] = f"category {value}"
                cat.select_option(value)
        browser.close()
    return sorted(set(errors))


def main(argv: list[str]) -> int:
    if argv:
        path = Path(argv[0])
    else:
        import build_site
        RUN.mkdir(exist_ok=True)
        path = RUN / "page_check.html"
        path.write_text(build_site.render(), encoding="utf-8")
    seen: dict = {}
    try:
        errors = check(path, seen)
    except ImportError:
        log("page check skipped: Playwright is not installed")
        return 0
    for e in errors:
        log(f"  page error: {e}")
    if errors:
        report_problem(f"The page has {len(errors)} JavaScript error(s), so parts of it don't draw "
                       f"(first: {errors[0][:160]}). Details in the log.", "page")
        return 1
    log(f"page check: no errors ({seen.get('tabs', 0)} tabs, {seen.get('periods', 0)} periods, "
        f"{seen.get('categories', 0)} categories)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
