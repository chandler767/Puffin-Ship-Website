"""Tests for check_site.py. Run: python3 -m unittest discover -s .github/scripts"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from check_site import SIGNUP_URL, check  # noqa: E402

EM = "—"

GOOD_FAQ = [("What is it?", "It makes clips.")]


def jsonld(faq):
    return json.dumps({
        "@context": "https://schema.org",
        "@graph": [{
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq
            ],
        }],
    })


def page(body_extra="", head_extra="", faq=None, jsonld_faq=None, signup=None):
    faq = GOOD_FAQ if faq is None else faq
    jsonld_faq = faq if jsonld_faq is None else jsonld_faq
    signup = signup if signup is not None else (
        f'<a href="{SIGNUP_URL}" data-signup class="btn">Get started</a>')
    faq_html = "".join(
        f'<div class="faq-item"><h3 class="faq-q">{q}</h3><p class="faq-a">{a}</p></div>'
        for q, a in faq)
    return f"""<!DOCTYPE html><html><head>
<meta name="description" content="Clips from your recordings." />
<script type="application/ld+json">{jsonld(jsonld_faq)}</script>
{head_extra}
</head><body>
<a href="#how">How</a>
<section id="how"><h2>How it works</h2></section>
{signup}
<section id="faq">{faq_html}</section>
{body_extra}
</body></html>"""


GOOD_LLMS = "# Puffin Ship\n\nTurns recordings into clips.\n"


class CheckSiteTests(unittest.TestCase):
    def assertClean(self, html, llms=GOOD_LLMS):
        self.assertEqual(check(html, llms), [])

    def assertFlags(self, html, needle, llms=GOOD_LLMS):
        problems = check(html, llms)
        self.assertTrue(any(needle in p for p in problems),
                        f"expected a violation mentioning {needle!r}, got {problems}")

    def test_good_page_passes(self):
        self.assertClean(page())

    def test_em_dash_in_visible_text(self):
        self.assertFlags(page(body_extra=f"<p>Fast {EM} and good</p>"), "em dash")

    def test_em_dash_in_meta_content(self):
        self.assertFlags(page(head_extra=f'<meta property="og:title" content="A {EM} B" />'), "em dash")

    def test_em_dash_in_alt(self):
        self.assertFlags(page(body_extra=f'<img src="x.png" alt="Logo {EM} mark" />'), "em dash")

    def test_em_dash_in_comment_ignored(self):
        self.assertClean(page(body_extra=f"<!-- note {EM} for devs -->"))

    def test_em_dash_in_script_and_style_ignored(self):
        self.assertClean(page(body_extra=f"<script>// a {EM} b\n</script><style>/* {EM} */</style>"))

    def test_em_dash_in_jsonld_flagged(self):
        self.assertFlags(page(faq=[("Q?", f"A {EM} b")]), "em dash")

    def test_em_dash_in_llms_flagged(self):
        self.assertFlags(page(), "em dash", llms=f"# P\n\nA {EM} b\n")

    def test_banned_word_free(self):
        self.assertFlags(page(body_extra="<p>Start Free today</p>"), "free")

    def test_freelancer_not_flagged(self):
        self.assertClean(page(body_extra="<p>Better than a freelancer.</p>"))

    def test_banned_early_access_in_llms(self):
        self.assertFlags(page(), "early access", llms="# P\n\nJoin Early Access now.\n")

    def test_banned_word_in_attribute(self):
        self.assertFlags(page(head_extra='<meta name="x" content="Now in beta" />'), "beta")

    def test_dollar_amount_flagged(self):
        self.assertFlags(page(body_extra="<p>Includes $25 of credit</p>"), "dollar amount")

    def test_dollar_amount_in_llms_flagged(self):
        self.assertFlags(page(), "dollar amount", llms="# P\n\nGet $ 10 credit.\n")

    def test_broken_anchor(self):
        self.assertFlags(page(body_extra='<a href="#nope">x</a>'), "#nope")

    def test_top_anchor_needs_id_too(self):
        self.assertFlags(page(body_extra='<a href="#top">x</a>'), "#top")

    def test_get_started_wrong_href(self):
        self.assertFlags(page(signup='<a href="https://example.com" data-signup>Get started</a>'),
                         "Get started")

    def test_get_started_missing_data_signup(self):
        self.assertFlags(page(signup=f'<a href="{SIGNUP_URL}">Get started</a>'), "data-signup")

    def test_page_without_get_started_flagged(self):
        self.assertFlags(page(signup=""), "Get started")

    def test_faq_jsonld_mismatch(self):
        self.assertFlags(page(jsonld_faq=[("What is it?", "Something else.")]), "FAQ")

    def test_faq_jsonld_count_mismatch(self):
        self.assertFlags(page(jsonld_faq=GOOD_FAQ + [("Extra?", "Yes.")]), "FAQ")

    def test_faq_jsonld_match_passes_with_whitespace_and_entities(self):
        html = page(faq=[("Can I review?", "Yes &amp; it\n   waits for you.")],
                    jsonld_faq=[("Can I review?", "Yes & it waits for you.")])
        self.assertClean(html)

    def test_get_started_with_arrow_wrong_href(self):
        self.assertFlags(page(body_extra='<a href="https://example.com">Get started <span>&rarr;</span></a>'),
                         "Get started")

    def test_get_started_button_flagged(self):
        self.assertFlags(page(body_extra='<button>Get started</button>'), "Get started")

    def test_banned_phrase_with_hyphen_or_nbsp(self):
        self.assertFlags(page(body_extra="<p>Join early-access</p>"), "early")
        self.assertFlags(page(head_extra='<meta name="x" content="early&nbsp;access" />'), "early")

    def test_value_attribute_checked(self):
        self.assertFlags(page(body_extra='<input value="Try it free" />'), "free")

    def test_em_dash_entity_in_text(self):
        self.assertFlags(page(body_extra="<p>A &mdash; b &#8212; c</p>"), "em dash")

    def test_title_checked(self):
        self.assertFlags(page(head_extra="<title>Puffin Ship \u2014 clips</title>"), "em dash")

    def test_violation_quotes_the_offending_sentence_not_page_start(self):
        problems = check(page(body_extra="<p>Some long intro text here. Then we say Start free now.</p>"), GOOD_LLMS)
        hit = [p for p in problems if "free" in p]
        self.assertTrue(hit)
        self.assertIn("Start free now", hit[0])
        self.assertNotIn("How it works", hit[0])

    def test_free_form_and_hyphenated_free_not_flagged(self):
        self.assertClean(page(body_extra="<p>Write free-form notes.</p>"))

    def test_free_standing_still_flagged(self):
        self.assertFlags(page(body_extra="<p>It is free to try.</p>"), "free")


if __name__ == "__main__":
    unittest.main()
