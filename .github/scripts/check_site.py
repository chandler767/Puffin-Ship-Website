#!/usr/bin/env python3
"""Enforces the site's copy and link rules on index.html and llms.txt.

Usage: python3 .github/scripts/check_site.py [index.html] [llms.txt]
Exits 1 and lists every violation if any rule is broken.

Rules (see CLAUDE.md and the repositioning design):
- No em dash in anything a visitor or crawler reads: visible text, readable
  attributes, JSON-LD strings, llms.txt. Comments, CSS and JS are exempt.
- No "early access", "waitlist", "launching soon", "beta" or "free" (the
  product is not free; new accounts get starting credit). Hyphenated forms
  like "free-form" are allowed.
- No dollar amounts (the starting credit amount may change).
- Every in-page anchor points at an id that exists.
- Every "Get started" link carries data-signup and points at SIGNUP_URL, and
  at least one exists.
- The FAQPage JSON-LD matches the visible FAQ word for word.
"""
import html as htmllib
import json
import re
import sys
from html.parser import HTMLParser

SIGNUP_URL = "https://app.puffinship.com/login"

EM_DASH = "—"
BANNED = ["early access", "waitlist", "launching soon", "beta", "free"]
# Words inside a phrase may be joined by any spacing or punctuation, so
# "early-access" and "early&nbsp;access" are caught too.
# "free" only as a standalone word: "free-form", "hands-free" and the like say
# nothing about price.
_PATTERNS = [r"(?<!-)free(?!-)" if w == "free" else r"[\W_]+".join(map(re.escape, w.split()))
             for w in BANNED]
BANNED_RE = re.compile(r"\b(" + "|".join(_PATTERNS) + r")\b", re.I)
DOLLAR_RE = re.compile(r"\$\s?\d")
READABLE_ATTRS = {"content", "alt", "title", "aria-label", "placeholder", "value"}


def _norm(s):
    return " ".join(htmllib.unescape(s).split())


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []          # visible text chunks
        self.attrs = []         # (tag, attr, value) for readable attributes
        self.ids = set()
        self.anchors = []       # in-page href targets
        self.links = []         # dicts: href, data_signup, text
        self.jsonld = []
        self._skip = 0          # depth inside script/style
        self._script_type = None
        self._buf = []
        self._link = None
        self._faq_field = None  # "q" or "a" while inside one
        self._faq_buf = []
        self.faq = []           # list of [q, a]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for k, v in attrs:
            if k in READABLE_ATTRS and v and tag != "script":
                self.attrs.append((tag, k, v))
        if tag in ("script", "style"):
            self._skip += 1
            self._script_type = a.get("type")
            self._buf = []
            return
        if tag == "button":
            self._link = {"href": None, "data_signup": "data-signup" in a, "text": [], "tag": "button"}
        if tag == "a":
            href = a.get("href") or ""
            if href.startswith("#"):
                self.anchors.append(href)
            self._link = {"href": href, "data_signup": "data-signup" in a, "text": [], "tag": "a"}
        cls = (a.get("class") or "").split()
        if "faq-q" in cls:
            self._faq_field, self._faq_buf = "q", []
        elif "faq-a" in cls:
            self._faq_field, self._faq_buf = "a", []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if tag == "script" and self._script_type == "application/ld+json":
                self.jsonld.append("".join(self._buf))
            self._skip = max(0, self._skip - 1)
            self._script_type = None
            return
        if tag in ("a", "button") and self._link is not None:
            self._link["text"] = _norm("".join(self._link["text"]))
            self.links.append(self._link)
            self._link = None
        if self._faq_field and tag in ("h3", "p"):
            val = _norm("".join(self._faq_buf))
            if self._faq_field == "q":
                self.faq.append([val, None])
            elif self.faq and self.faq[-1][1] is None:
                self.faq[-1][1] = val
            self._faq_field = None

    def handle_data(self, data):
        if self._skip:
            self._buf.append(data)
            return
        self.text.append(data)
        if self._link is not None:
            self._link["text"].append(data)
        if self._faq_field:
            self._faq_buf.append(data)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _around(s, start, end, pad=50):
    """The text around a match, so a report points at the offending sentence."""
    lo, hi = max(0, start - pad), min(len(s), end + pad)
    return ("..." if lo else "") + s[lo:hi].strip() + ("..." if hi < len(s) else "")


def _copy_rules(where, s):
    out = []
    i = s.find(EM_DASH)
    if i >= 0:
        out.append(f"{where}: em dash in {_around(s, i, i + 1)!r}")
    for m in BANNED_RE.finditer(s):
        out.append(f"{where}: banned word {m.group(0).lower()!r} in {_around(s, m.start(), m.end())!r}")
    m = DOLLAR_RE.search(s)
    if m:
        out.append(f"{where}: dollar amount in {_around(s, m.start(), m.end())!r}")
    return out


def _jsonld_faq(docs):
    pairs = []
    for d in docs:
        nodes = d.get("@graph", [d]) if isinstance(d, dict) else []
        for n in nodes:
            if isinstance(n, dict) and n.get("@type") == "FAQPage":
                for q in n.get("mainEntity", []):
                    pairs.append([_norm(q.get("name", "")),
                                  _norm(q.get("acceptedAnswer", {}).get("text", ""))])
    return pairs


def check(html, llms):
    p = _Collector()
    p.feed(html)
    p.close()
    problems = []

    problems += _copy_rules("visible text", _norm(" ".join(p.text)))
    for tag, attr, val in p.attrs:
        problems += _copy_rules(f"<{tag} {attr}>", val)

    docs = []
    for raw in p.jsonld:
        try:
            docs.append(json.loads(raw))
        except ValueError as e:
            problems.append(f"JSON-LD does not parse: {e}")
    for d in docs:
        for s in _strings(d):
            if not s.startswith("http"):
                problems += _copy_rules("JSON-LD", s)

    for i, line in enumerate(llms.splitlines(), 1):
        problems += _copy_rules(f"llms.txt:{i}", line)

    for href in p.anchors:
        if href != "#" and href[1:] not in p.ids:
            problems.append(f"broken in-page link {href}")

    starts = [l for l in p.links if re.match(r"get started\b", l["text"], re.I)]
    if not starts:
        problems.append("no Get started link on the page")
    for l in starts:
        if l["tag"] == "button":
            problems.append("Get started is a button; it must be a link to the signup URL")
            continue
        if l["href"] != SIGNUP_URL:
            problems.append(f"Get started link points at {l['href']!r}, not {SIGNUP_URL}")
        if not l["data_signup"]:
            problems.append("Get started link is missing data-signup")

    visible_faq = [[q, a or ""] for q, a in p.faq]
    ld_faq = _jsonld_faq(docs)
    if visible_faq != ld_faq:
        problems.append(f"FAQ JSON-LD does not match the visible FAQ "
                        f"({len(ld_faq)} structured vs {len(visible_faq)} visible)")
        for v, s in zip(visible_faq, ld_faq):
            if v != s:
                problems.append(f"  FAQ differs: visible {v!r} vs structured {s!r}")
    return problems


def main(argv):
    html_path = argv[1] if len(argv) > 1 else "index.html"
    llms_path = argv[2] if len(argv) > 2 else "llms.txt"
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    with open(llms_path, encoding="utf-8") as f:
        llms = f.read()
    problems = check(html, llms)
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
