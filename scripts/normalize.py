"""Turn a pricing page's HTML into stable plain text.

The text is what we hash (to notice changes), diff (for the agent) and search
(to check that every number on a card is really on the page). Standard library only.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# Content inside these tags is never pricing information.
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe", "head", "nav", "footer"}
# These tags start a new line in the output.
BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "ul", "ol", "tr", "td", "th", "table", "h1", "h2",
    "h3", "h4", "h5", "h6", "br", "header", "main", "aside", "dt", "dd", "button", "label", "option",
}
VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "col", "embed"}

# Text that changes without any pricing change. Extend per company in registry "ignore_patterns".
VOLATILE_PATTERNS = [
    r"©\s*\d{4}.*",                       # copyright lines
    r"\b\d+\s+(?:people|users|teams) (?:are )?viewing\b.*",
    r"\b(?:offer|sale) ends in\b.*",       # countdown timers
]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS and tag not in VOID_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html: str, ignore_patterns: list[str] | None = None) -> str:
    """Visible text, one block per line, whitespace collapsed, volatile lines removed."""
    parser = _TextExtractor()
    parser.feed(html or "")
    parser.close()
    patterns = [re.compile(p, re.I) for p in VOLATILE_PATTERNS + list(ignore_patterns or [])]
    lines, last = [], None
    for raw in "".join(parser.parts).split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        for p in patterns:
            line = p.sub("", line).strip()
        if line and line != last:
            lines.append(line)
            last = line
    return "\n".join(lines)


_PRICE = re.compile(
    r"([$€£¥]\s?\d)|(\d\s?(usd|eur|gbp|cad)\b)|(/\s?(mo|month|yr|year|user|seat)\b)|(per (month|user|seat|year))",
    re.I,
)


def looks_like_pricing(text: str) -> bool:
    """True if the text shows at least two price-like tokens."""
    return len(_PRICE.findall(text or "")) >= 2


def comparable(text: str) -> str:
    """Lowercase, straight quotes, single spaces: for checking that a quote appears in a page."""
    text = (text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()
