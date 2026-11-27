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
- No dollar amounts, except the approved credit offer CREDIT_OFFER. Wherever
  it appears, "Some restrictions apply" must link to the Terms (TERMS_URL);
  in llms.txt the phrase and the Terms URL must both be present.
- Every in-page anchor points at an id that exists.
- Every "Get started" link carries data-signup and points at SIGNUP_URL, and
  at least one exists.
- The FAQPage JSON-LD matches the visible FAQ word for word.
- No aria-label on a generic element (span, div, p and the like) without a
  role: screen readers ignore it there, so the label silently never reads.
- A link or button with an aria-label contains its visible words in that
  label (WCAG 2.5.3 Label in Name), so voice users can say what they see.
- Colour contrast (WCAG 1.4.3 AA) in the page's CSS: every pair in
  CONTRAST_PAIRS meets its ratio once the :root tokens are resolved, any rule
  that sets both a text colour and a solid background meets 4.5:1, and the
  bright brand blue (LIGHT_ACCENT) is never used as a text colour.
- No retired product words: the app calls templates "projects", run groups
  "videos" and single runs "versions", so "template", "run group", "run" and
  "rerun" may not appear in copy. Exempt: the tour video's JSON-LD (it names
  what the recorded footage shows until the tour is re-recorded) and the
  plain-English uses in OLD_TERM_ALLOWED.
"""
import html as htmllib
import json
import re
import sys
from html.parser import HTMLParser

SIGNUP_URL = "https://app.puffinship.com/login"
TERMS_URL = "https://app.puffinship.com/terms"
# The one dollar figure the site may state. Change it here when the offer changes.
CREDIT_OFFER = "$25 in credit"
RESTRICTIONS_RE = re.compile(r"restrictions\s+apply", re.I)

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
# Retired product words. "running" is not matched: it is never the product noun.
OLD_TERM_RE = re.compile(r"\b(templates?|run[\W_]+groups?|re-?runs?|runs?)\b", re.I)
# Plain-English phrases that use "run" without meaning the product. Add a phrase
# here, not a looser pattern above, when new copy needs one.
OLD_TERM_ALLOWED = ["steady run of", "runs on its own", "run it for them"]
# JSON-LD nodes describing the recorded tour, which still shows the old UI.
OLD_TERM_EXEMPT_TYPES = {"VideoObject", "Clip"}
READABLE_ATTRS = {"content", "alt", "title", "aria-label", "placeholder", "value"}
# Elements whose implicit role does not allow a name, so aria-label is ignored.
GENERIC_TAGS = {"span", "div", "p", "em", "strong", "b", "i", "small", "code", "u", "s"}


# Text colour / background token pairs the page relies on, with the minimum
# ratio. Token names resolve through :root; plain hex values are used as is.
_LIGHT_BGS = ["--white", "--paper", "--ink-50"]
CONTRAST_PAIRS = (
    [(fg, bg, 4.5) for fg in ("--text-body", "--text-muted", "--text-faint", "--accent-strong")
     for bg in _LIGHT_BGS]
    + [("#FFFFFF", bg, 4.5) for bg in ("--accent-strong", "--accent-hover", "--accent-press")]
)
# The bright brand blue is 2.7:1 on white: fine for fills and art, never for text.
LIGHT_ACCENT = {"--accent", "--orange-500", "#18a8e0"}


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
        self.ignored_labels = []  # (tag, label) for aria-label on a generic element
        self.css = []           # contents of <style> blocks

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag in GENERIC_TAGS and a.get("aria-label") and not a.get("role"):
            self.ignored_labels.append((tag, a["aria-label"]))
        for k, v in attrs:
            if k in READABLE_ATTRS and v and tag != "script":
                self.attrs.append((tag, k, v))
        if tag in ("script", "style"):
            self._skip += 1
            self._script_type = a.get("type")
            self._buf = []
            return
        if tag == "button":
            self._link = {"href": None, "data_signup": "data-signup" in a, "text": [], "tag": "button",
                          "label": a.get("aria-label")}
        if tag == "a":
            href = a.get("href") or ""
            if href.startswith("#"):
                self.anchors.append(href)
            self._link = {"href": href, "data_signup": "data-signup" in a, "text": [], "tag": "a",
                          "label": a.get("aria-label")}
        cls = (a.get("class") or "").split()
        if "faq-q" in cls:
            self._faq_field, self._faq_buf = "q", []
        elif "faq-a" in cls:
            self._faq_field, self._faq_buf = "a", []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if tag == "script" and self._script_type == "application/ld+json":
                self.jsonld.append("".join(self._buf))
            if tag == "style":
                self.css.append("".join(self._buf))
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


def _words(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


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
    m = DOLLAR_RE.search(s.replace(CREDIT_OFFER, " " * len(CREDIT_OFFER)))
    if m:
        out.append(f"{where}: dollar amount in {_around(s, m.start(), m.end())!r}")
    return out


def _hex(v):
    v = v.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)
    if v in ("white", "#fff"):
        return "#ffffff"
    return None


def _css_tokens(css):
    """Custom properties from :root blocks, as name -> raw value."""
    tokens = {}
    for block in re.findall(r":root\s*\{([^{}]*)\}", css):
        for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block):
            tokens[name] = val.strip()
    return tokens


def _resolve(v, tokens, depth=0):
    """A token name, var(...) or hex value resolved to #rrggbb, or None."""
    v = v.strip()
    if depth > 10:
        return None
    m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)", v)
    name = m.group(1) if m else (v if v.startswith("--") else None)
    if name:
        return _resolve(tokens[name], tokens, depth + 1) if name in tokens else None
    return _hex(v)


def _luminance(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _contrast_rules(css):
    out = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    tokens = _css_tokens(css)
    if not tokens:
        return out
    for fg, bg, need in CONTRAST_PAIRS:
        f, b = _resolve(fg, tokens), _resolve(bg, tokens)
        if f is None or b is None:
            out.append(f"contrast: cannot resolve {fg if f is None else bg} in the :root tokens")
            continue
        r = contrast(f, b)
        if r < need:
            out.append(f"contrast: {fg} on {bg} is {r:.2f}:1, needs {need}:1")
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sel = " ".join(sel.split())
        decls = dict((k.strip().lower(), v.strip())
                     for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body))
        color = decls.get("color")
        if color:
            raw = color.strip().lower()
            m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", raw)
            if (m and m.group(1) in LIGHT_ACCENT) or _hex(raw) in LIGHT_ACCENT:
                out.append(f"contrast: {sel} uses the bright brand blue ({color}) as text; "
                           f"use var(--accent-strong)")
        bg = decls.get("background-color") or decls.get("background")
        if color and bg:
            f, b = _resolve(color, tokens), _resolve(bg, tokens)
            if f and b and contrast(f, b) < 4.5:
                out.append(f"contrast: {sel} sets {color} on {bg}, "
                           f"{contrast(f, b):.2f}:1, needs 4.5:1")
    return out


def _old_terms(where, s):
    masked = s
    for phrase in OLD_TERM_ALLOWED:
        masked = re.sub(re.escape(phrase), lambda m: " " * len(m.group(0)), masked, flags=re.I)
    return [f"{where}: retired product word {m.group(0).lower()!r} in {_around(s, m.start(), m.end())!r}"
            for m in OLD_TERM_RE.finditer(masked)]


def _strings_outside(obj, skip_types):
    """Like _strings, but skips any node whose @type is in skip_types."""
    if isinstance(obj, dict):
        t = obj.get("@type")
        if (t in skip_types) if isinstance(t, str) else any(x in skip_types for x in (t or [])):
            return
        for v in obj.values():
            yield from _strings_outside(v, skip_types)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings_outside(v, skip_types)
    elif isinstance(obj, str):
        yield obj


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

    problems += _old_terms("visible text", _norm(" ".join(p.text)))
    for tag, attr, val in p.attrs:
        problems += _old_terms(f"<{tag} {attr}>", val)
    for d in docs:
        for s in _strings_outside(d, OLD_TERM_EXEMPT_TYPES):
            if not s.startswith("http"):
                problems += _old_terms("JSON-LD", s)
    for i, line in enumerate(llms.splitlines(), 1):
        problems += _old_terms(f"llms.txt:{i}", line)

    page_text = " ".join([_norm(" ".join(p.text))] + [v for _, _, v in p.attrs]
                         + [x for d in docs for x in _strings(d)])
    if CREDIT_OFFER in page_text and not any(
            RESTRICTIONS_RE.search(l["text"]) and l["href"] == TERMS_URL for l in p.links):
        problems.append(f"the page states {CREDIT_OFFER!r} but has no "
                        f"'Some restrictions apply' link to {TERMS_URL}")
    if CREDIT_OFFER in llms and not (RESTRICTIONS_RE.search(llms) and TERMS_URL in llms):
        problems.append(f"llms.txt states {CREDIT_OFFER!r} without 'Some restrictions apply' and {TERMS_URL}")

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

    problems += _contrast_rules("\n".join(p.css))

    for tag, label in p.ignored_labels:
        problems.append(f"aria-label {label!r} on <{tag}> without a role is ignored by "
                        f"screen readers; use visible or sr-only text instead")
    for l in p.links:
        label, text = l.get("label"), l["text"]
        if label and re.search(r"[A-Za-z]", text):
            if f" {_words(text)} " not in f" {_words(label)} ":
                problems.append(f"<{l['tag']}> shows {text!r} but its aria-label is {label!r}; "
                                f"the label must contain the visible words")

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
