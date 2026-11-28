#!/usr/bin/env python3
"""Enforces the site's copy and link rules on every page and llms.txt.

Usage: python3 .github/scripts/check_site.py            (the whole site, from the repo root)
       python3 .github/scripts/check_site.py PAGE LLMS  (one page and llms.txt)
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
  plain-English uses in OLD_TERM_ALLOWED. "Video template" is allowed:
  "project" stays the main word, but calling a project a reusable video
  template is fine where it helps explain reuse (Chandler, 2026-11-28).

Across the whole site (check_site):
- Every link to a page on this site ("/pricing/", "/faq/#x") reaches a page
  that exists, and its #fragment is an id on that page. Every local file a
  page loads (images, video, posters, CSS, JS) exists. Links are root-relative.
- Every page has the same header, footer and cookie banner as the home page
  (aria-current, which marks the page you are on, is ignored).
- Every page has a unique <title>, a meta description, a canonical URL that
  matches where the page lives, a matching og:url, and the GA4 tag.
- sitemap.xml lists every indexable page and nothing else.
- Every puffinship.com link in llms.txt reaches a page (and id) that exists.
"""
import os
import html as htmllib
import json
import re
import sys
from html.parser import HTMLParser

SITE = "https://puffinship.com"
GA_ID = "G-RY63074N1P"
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
OLD_TERM_ALLOWED = ["steady run of", "runs on its own", "run it for them", "video template"]
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
        if self._faq_field and tag in ("h2", "h3", "h4", "p"):
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
    """One page and llms.txt: the rules that need no other file."""
    return check_page(html) + check_llms(llms)


def check_llms(llms):
    problems = []
    for i, line in enumerate(llms.splitlines(), 1):
        problems += _copy_rules(f"llms.txt:{i}", line)
        problems += _old_terms(f"llms.txt:{i}", line)
    if CREDIT_OFFER in llms and not (RESTRICTIONS_RE.search(llms) and TERMS_URL in llms):
        problems.append(f"llms.txt states {CREDIT_OFFER!r} without 'Some restrictions apply' and {TERMS_URL}")
    return problems


def check_page(html, linked_css=""):
    """One page. linked_css is the text of the stylesheets it links to, so the
    contrast rules see them as well as any <style> block."""
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

    problems += _old_terms("visible text", _norm(" ".join(p.text)))
    for tag, attr, val in p.attrs:
        problems += _old_terms(f"<{tag} {attr}>", val)
    for d in docs:
        for s in _strings_outside(d, OLD_TERM_EXEMPT_TYPES):
            if not s.startswith("http"):
                problems += _old_terms("JSON-LD", s)

    page_text = " ".join([_norm(" ".join(p.text))] + [v for _, _, v in p.attrs]
                         + [x for d in docs for x in _strings(d)])
    if CREDIT_OFFER in page_text and not any(
            RESTRICTIONS_RE.search(l["text"]) and l["href"] == TERMS_URL for l in p.links):
        problems.append(f"the page states {CREDIT_OFFER!r} but has no "
                        f"'Some restrictions apply' link to {TERMS_URL}")
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

    problems += _contrast_rules("\n".join(p.css + [linked_css]))

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


# ── Whole site ────────────────────────────────────────────────────────────

# Folders that hold no pages of this site. docs/ only forwards old links to
# the docs in the app.
SKIP_DIRS = {".git", ".github", ".githooks", ".claude", "assets", "docs", "node_modules"}
# Pages that exist but are not listed in the sitemap.
NOT_IN_SITEMAP = {"/404.html"}

_URL_ATTRS = {("a", "href"), ("link", "href"), ("img", "src"), ("script", "src"),
              ("source", "src"), ("video", "src"), ("video", "poster")}


class _Refs(HTMLParser):
    """Every URL a page links to or loads, plus its ids and head tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []      # (tag, attr, url)
        self.ids = set()
        self.title = None
        self.meta = {}      # name or property -> content
        self.canonical = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for k, v in attrs:
            if (tag, k) in _URL_ATTRS and v:
                self.refs.append((tag, k, v))
        if tag == "title":
            self._in_title, self.title = True, ""
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key] = a.get("content") or ""
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def site_pages(root):
    """{url path: file path} for every page of the site."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel != "." and rel.split(os.sep)[0] in SKIP_DIRS:
            dirnames[:] = []
            continue
        for fn in filenames:
            if not fn.endswith(".html"):
                continue
            rp = os.path.normpath(os.path.join(rel, fn)).replace(os.sep, "/")
            if rp == "index.html":
                url = "/"
            elif rp.endswith("/index.html"):
                url = "/" + rp[: -len("index.html")]
            else:
                url = "/" + rp
            out[url] = os.path.join(dirpath, fn)
    return out


def _page_target(root, pages, path):
    """A root-relative path to a page URL, a file on disk, or None."""
    if path in pages:
        return path
    if not path.endswith("/") and path + "/" in pages:
        return None  # "/pricing" works on GitHub Pages only via a redirect; link "/pricing/"
    f = os.path.join(root, path.lstrip("/"))
    if path != "/" and os.path.isfile(f):
        return f
    return None


_CHROME_RES = {
    "header": re.compile(r"<header\b.*?</header>", re.S),
    "footer": re.compile(r"<footer\b.*?</footer>", re.S),
    "cookie banner": re.compile(r'<div id="cookie-banner".*?</div>\s*</div>', re.S),
}


def _chrome(html):
    out = {}
    for name, rx in _CHROME_RES.items():
        m = rx.search(html)
        out[name] = re.sub(r'\s+aria-current="page"', "", m.group(0)) if m else None
    return out


def check_site(root="."):
    problems = []
    pages = site_pages(root)
    if "/" not in pages:
        return ["no index.html at the site root"]
    html_of, refs_of = {}, {}
    for url, f in pages.items():
        with open(f, encoding="utf-8") as fh:
            html_of[url] = fh.read()
        r = _Refs()
        r.feed(html_of[url])
        r.close()
        refs_of[url] = r

    home_chrome = _chrome(html_of["/"])
    titles = {}
    for url in sorted(pages):
        html, r = html_of[url], refs_of[url]
        css = []
        for tag, attr, ref in r.refs:
            if tag == "link" and ref.split("?")[0].endswith(".css") and ref.startswith("/"):
                f = os.path.join(root, ref.split("?")[0].lstrip("/"))
                if os.path.isfile(f):
                    with open(f, encoding="utf-8") as fh:
                        css.append(fh.read())
        problems += [f"{url}: {x}" for x in check_page(html, "\n".join(css))]

        # Links and files.
        for tag, attr, ref in r.refs:
            if ref.startswith(("http:", "https:", "mailto:", "tel:", "#", "data:")) or ref.startswith("//"):
                if ref.startswith(SITE + "/") and tag == "a":
                    ref = ref[len(SITE):]
                else:
                    continue
            if not ref.startswith("/"):
                problems.append(f"{url}: <{tag} {attr}={ref!r}> is relative; use a root-relative path like /{ref}")
                continue
            path, _, frag = ref.partition("#")
            path = path.split("?")[0]
            target = _page_target(root, pages, path)
            if target is None:
                problems.append(f"{url}: <{tag} {attr}> points at {ref!r}, which does not exist")
            elif frag and target in refs_of and frag not in refs_of[target].ids:
                problems.append(f"{url}: link to {ref!r}: no id {frag!r} on {target}")

        # Shared header, footer and cookie banner.
        if url != "/":
            for name, block in _chrome(html).items():
                if block is None:
                    problems.append(f"{url}: no {name}")
                elif block != home_chrome[name]:
                    problems.append(f"{url}: {name} differs from the home page's")

        # Head tags.
        if not (r.title or "").strip():
            problems.append(f"{url}: no <title>")
        else:
            titles.setdefault(_norm(r.title), []).append(url)
        if not r.meta.get("description", "").strip():
            problems.append(f"{url}: no meta description")
        want = SITE + url
        if r.canonical != want:
            problems.append(f"{url}: canonical is {r.canonical!r}, expected {want!r}")
        if r.meta.get("og:url") != r.canonical:
            problems.append(f"{url}: og:url {r.meta.get('og:url')!r} does not match the canonical URL")
        if f"gtag/js?id={GA_ID}" not in html or f"'config', '{GA_ID}'" not in html:
            problems.append(f"{url}: Google Analytics tag {GA_ID} is missing")
    for t, urls in titles.items():
        if len(urls) > 1:
            problems.append(f"title {t!r} is used by more than one page: {', '.join(urls)}")

    # Sitemap.
    sm_path = os.path.join(root, "sitemap.xml")
    if not os.path.isfile(sm_path):
        problems.append("no sitemap.xml")
    else:
        with open(sm_path, encoding="utf-8") as fh:
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", fh.read())
        listed = {l[len(SITE):] if l.startswith(SITE) else l for l in locs}
        want = {u for u in pages if u not in NOT_IN_SITEMAP}
        for u in sorted(want - listed):
            problems.append(f"sitemap.xml is missing {SITE}{u}")
        for u in sorted(listed - want):
            problems.append(f"sitemap.xml lists {SITE}{u}, which is not a page")

    # llms.txt.
    llms_path = os.path.join(root, "llms.txt")
    if not os.path.isfile(llms_path):
        problems.append("no llms.txt")
    else:
        with open(llms_path, encoding="utf-8") as fh:
            llms = fh.read()
        problems += check_llms(llms)
        for m in re.finditer(r"https://puffinship\.com(/[^\s)\]>,]*)?", llms):
            ref = (m.group(1) or "/").rstrip(".")
            path, _, frag = ref.partition("#")
            if path.endswith(".txt") or path.endswith(".xml"):
                continue
            target = _page_target(root, pages, path)
            if target is None:
                problems.append(f"llms.txt links to {m.group(0)!r}, which is not a page")
            elif frag and target in refs_of and frag not in refs_of[target].ids:
                problems.append(f"llms.txt links to {m.group(0)!r}: no id {frag!r} on that page")
    return problems


def main(argv):
    if len(argv) > 1:
        html_path = argv[1]
        llms_path = argv[2] if len(argv) > 2 else "llms.txt"
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
        with open(llms_path, encoding="utf-8") as f:
            llms = f.read()
        problems = check(html, llms)
    else:
        problems = check_site(".")
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
