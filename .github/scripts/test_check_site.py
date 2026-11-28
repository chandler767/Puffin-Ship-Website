"""Tests for check_site.py. Run: python3 -m unittest discover -s .github/scripts"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import shutil  # noqa: E402
import tempfile  # noqa: E402
from check_site import SIGNUP_URL, TERMS_URL, check, check_site, contrast  # noqa: E402

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

    RESTRICT = f'<a href="{TERMS_URL}">Some restrictions apply.</a>'

    def test_approved_credit_amount_allowed(self):
        self.assertClean(page(body_extra=f"<p>New workspaces start with $25 in credit. {self.RESTRICT}</p>"),
                         llms=f"# P\n\nNew workspaces start with $25 in credit. Some restrictions apply: {TERMS_URL}\n")

    def test_other_dollar_amounts_still_flagged(self):
        for txt in ["New workspaces start with $50 in credit.", "Only $25 a month.",
                    "$25 in credit, then $9 per clip."]:
            self.assertFlags(page(body_extra=f"<p>{txt} {self.RESTRICT}</p>"), "dollar amount")

    def test_credit_amount_without_restrictions_link_flagged(self):
        self.assertFlags(page(body_extra="<p>Start with $25 in credit.</p>"), "restrictions")

    def test_restrictions_link_must_point_at_terms(self):
        self.assertFlags(page(body_extra='<p>Start with $25 in credit. '
                                         '<a href="#faq">Some restrictions apply.</a></p>'), "restrictions")

    def test_credit_amount_in_llms_needs_restrictions(self):
        self.assertFlags(page(), "restrictions", llms="# P\n\nStart with $25 in credit.\n")

    def test_free_standing_still_flagged(self):
        self.assertFlags(page(body_extra="<p>It is free to try.</p>"), "free")

    # aria-label on generic elements
    def test_aria_label_on_span_flagged(self):
        self.assertFlags(page(body_extra='<td><span aria-label="100 to 350">100&ndash;350</span></td>'),
                         "ignored by screen readers")

    def test_aria_label_on_div_flagged(self):
        self.assertFlags(page(body_extra='<div aria-label="Samples">x</div>'), "ignored by screen readers")

    def test_aria_label_on_div_with_role_allowed(self):
        self.assertClean(page(body_extra='<div role="img" aria-label="A diagram">x</div>'))

    def test_aria_label_on_nav_and_section_allowed(self):
        self.assertClean(page(body_extra='<nav aria-label="Main">x</nav><section aria-label="Examples">y</section>'))

    def test_sr_only_text_pattern_allowed(self):
        self.assertClean(page(body_extra='<span aria-hidden="true">1&ndash;2</span><span class="sr-only">1 to 2</span>'))

    # Label in Name
    def test_button_label_missing_visible_words_flagged(self):
        self.assertFlags(page(body_extra='<button type="button" aria-label="Play the product tour">'
                                         'Watch the tour <span>2:03</span></button>'), "must contain the visible words")

    def test_link_label_missing_visible_words_flagged(self):
        self.assertFlags(page(body_extra='<a href="#how" aria-label="Read more">Pricing</a>'),
                         "must contain the visible words")

    def test_label_containing_visible_words_allowed(self):
        self.assertClean(page(body_extra='<a href="#how" aria-label="Pricing, opens the plan">Pricing</a>'))

    def test_label_match_ignores_case_and_punctuation(self):
        self.assertClean(page(body_extra='<button type="button" aria-label="watch the tour (2:03)">'
                                         'Watch the tour, 2:03</button>'))

    def test_partial_word_does_not_count_as_match(self):
        self.assertFlags(page(body_extra='<a href="#how" aria-label="Watchful eyes">Watch</a>'),
                         "must contain the visible words")

    def test_symbol_only_button_with_label_allowed(self):
        self.assertClean(page(body_extra='<button type="button" aria-label="Next video">&#8250;</button>'))

    def test_icon_button_with_label_allowed(self):
        self.assertClean(page(body_extra='<button type="button" aria-label="Play full screen"><svg></svg></button>'))

    def test_button_without_label_allowed(self):
        self.assertClean(page(body_extra='<button type="button">Watch the tour 2:03</button>'))


GOOD_ROOT = """:root {
  --ink-800: #2E3338; --ink-600: #5C6268; --ink-50: #F6F7F9;
  --paper: #F7F9FB; --white: #FFFFFF;
  --orange-700: #0A6E97; --orange-500: #18A8E0;
  --ocean-600: #0E4E6E; --ocean-700: #0A3A52;
  --text-body: var(--ink-800); --text-muted: var(--ink-600); --text-faint: var(--ink-600);
  --accent: var(--orange-500); --accent-strong: var(--orange-700);
  --accent-hover: var(--ocean-600); --accent-press: var(--ocean-700);
}"""


def styled(css="", root=GOOD_ROOT):
    return page(head_extra=f"<style>{root}\n{css}</style>")


class ContrastTests(unittest.TestCase):
    def flags(self, html):
        return [p for p in check(html, "# P\n") if p.startswith("contrast")]

    def test_contrast_math(self):
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(contrast("#18a8e0", "#ffffff"), 2.72, places=2)
        self.assertAlmostEqual(contrast("#0a6e97", "#ffffff"), 5.69, places=2)

    def test_good_tokens_pass(self):
        self.assertEqual(self.flags(styled(".btn-primary { background: var(--accent-strong); color: #fff; }")), [])

    def test_page_without_tokens_not_checked(self):
        self.assertEqual(self.flags(page()), [])

    def test_faint_text_too_light_flagged(self):
        root = GOOD_ROOT.replace("--text-faint: var(--ink-600)", "--text-faint: #7C838A")
        self.assertTrue(any("--text-faint" in p for p in self.flags(styled(root=root))))

    def test_light_accent_strong_flagged(self):
        root = GOOD_ROOT.replace("--accent-strong: var(--orange-700)", "--accent-strong: var(--orange-500)")
        self.assertTrue(any("--accent-strong on --white" in p for p in self.flags(styled(root=root))))

    def test_light_hover_under_white_text_flagged(self):
        root = GOOD_ROOT.replace("--accent-hover: var(--ocean-600)", "--accent-hover: #1389C2")
        self.assertTrue(any("on --accent-hover" in p for p in self.flags(styled(root=root))))

    def test_missing_token_flagged(self):
        root = GOOD_ROOT.replace("--accent-strong: var(--orange-700);", "")
        self.assertTrue(any("cannot resolve --accent-strong" in p for p in self.flags(styled(root=root))))

    def test_white_on_bright_blue_button_flagged(self):
        self.assertTrue(any(".btn-primary" in p for p in
                            self.flags(styled(".btn-primary { background: var(--accent); color: #fff; }"))))

    def test_hex_pair_in_one_rule_flagged(self):
        self.assertTrue(self.flags(styled(".tag { color: #ffffff; background-color: #45BBE8; }")))

    def test_dark_on_dark_flagged(self):
        self.assertTrue(self.flags(styled(".x { color: #444; background: #222; }")))

    def test_bright_blue_as_text_flagged(self):
        for v in ("var(--accent)", "var(--orange-500)", "#18A8E0"):
            self.assertTrue(self.flags(styled(f".eyebrow {{ color: {v}; }}")), v)

    def test_bright_blue_as_fill_or_border_allowed(self):
        css = (".card { border: 2px solid var(--accent); } "
               ".bar { background: var(--accent); } "
               ".strike { text-decoration-color: var(--accent); }")
        self.assertEqual(self.flags(styled(css)), [])

    def test_rule_inside_media_query_checked(self):
        css = "@media (max-width: 600px) { .eyebrow { color: var(--accent); } }"
        self.assertTrue(self.flags(styled(css)))

    def test_commented_out_rule_ignored(self):
        self.assertEqual(self.flags(styled("/* .eyebrow { color: var(--accent); } */")), [])

    def test_unresolvable_background_skipped(self):
        css = ".hero { color: #fff; background: linear-gradient(#000, #333); }"
        self.assertEqual(self.flags(styled(css)), [])


class RetiredTermTests(unittest.TestCase):
    def flags(self, html, llms="# P\n"):
        return [p for p in check(html, llms) if "retired product word" in p]

    def test_template_in_visible_text_flagged(self):
        self.assertTrue(self.flags(page(body_extra="<p>Pick a ready-made template.</p>")))

    def test_plural_and_capitalised_flagged(self):
        self.assertTrue(self.flags(page(body_extra="<p>Templates are recipes.</p>")))

    def test_run_noun_flagged(self):
        self.assertTrue(self.flags(page(body_extra="<li>Every run shows its tokens</li>")))

    def test_runs_flagged(self):
        self.assertTrue(self.flags(page(body_extra="<p>Runs can start from the API.</p>")))

    def test_rerun_and_hyphenated_flagged(self):
        self.assertTrue(self.flags(page(body_extra="<p>Rerun it.</p>")))
        self.assertTrue(self.flags(page(body_extra="<p>A re-run is cheap.</p>")))

    def test_run_group_flagged(self):
        self.assertTrue(self.flags(page(body_extra="<p>Open the run group.</p>")))
        self.assertTrue(self.flags(page(body_extra="<p>Open the run-group.</p>")))

    def test_attribute_flagged(self):
        self.assertTrue(self.flags(page(body_extra='<img src="x.png" alt="A template gallery" />')))

    def test_meta_content_flagged(self):
        self.assertTrue(self.flags(page(head_extra='<meta name="x" content="Start runs anywhere." />')))

    def test_faq_jsonld_flagged(self):
        faq = [("Q?", "Write your templates for you.")]
        self.assertTrue(self.flags(page(faq=faq)))

    def test_llms_flagged(self):
        self.assertTrue(self.flags(page(), llms="# P\n\nRated runs help.\n"))

    def test_tour_video_jsonld_exempt(self):
        tour = json.dumps({"@context": "https://schema.org", "@type": "VideoObject",
                           "description": "two ways to start a template",
                           "hasPart": [{"@type": "Clip", "name": "Templates as recipes"}]})
        self.assertEqual(self.flags(page(head_extra=f'<script type="application/ld+json">{tour}</script>')), [])

    def test_other_jsonld_not_exempt(self):
        org = json.dumps({"@type": "Organization", "description": "It builds your template."})
        self.assertTrue(self.flags(page(head_extra=f'<script type="application/ld+json">{org}</script>')))

    def test_exemption_does_not_leak_into_visible_text(self):
        self.assertTrue(self.flags(page(body_extra="<p>Templates as recipes</p>")))

    def test_allowed_plain_english_phrases(self):
        body = ("<p>A steady run of shorts. The editing runs on its own. "
                "The team can run it for them. It keeps running.</p>")
        self.assertEqual(self.flags(page(body_extra=body)), [])

    def test_allowed_phrase_does_not_hide_a_second_use(self):
        self.assertTrue(self.flags(page(body_extra="<p>A steady run of shorts, and every run is logged.</p>")))

    def test_words_containing_run_not_flagged(self):
        body = "<p>A runaway project stops. A frontrunner. Brunch. Rerunning nothing.</p>"
        self.assertEqual(self.flags(page(body_extra=body)), [])

    def test_new_names_pass(self):
        body = ("<p>Pick what you want to make and Puffin Ship builds the project. "
                "Every version shows its tokens. Make a new version.</p>")
        self.assertEqual(self.flags(page(body_extra=body)), [])

    def test_css_and_script_not_checked(self):
        body = "<style>.g{grid-template-columns:1fr}</style><script>var run = 1;</script>"
        self.assertEqual(self.flags(page(body_extra=body)), [])


    def test_faq_with_h2_questions_matches(self):
        html = page().replace('<h3 class="faq-q">What is it?</h3>', '<h2 class="faq-q">What is it?</h2>')
        self.assertIn('<h2 class="faq-q">', html)
        self.assertEqual(check(html, GOOD_LLMS), [])


GA = ("<script async src=\"https://www.googletagmanager.com/gtag/js?id=G-RY63074N1P\"></script>"
      "<script>gtag('config', 'G-RY63074N1P', {});</script>")
HEADER = ('<header id="top"><a href="/">Home</a><a href="/pricing/"{cur}>Pricing</a>'
          f'<a href="{SIGNUP_URL}" data-signup>Get started</a></header>')
FOOTER = '<footer><a href="/pricing/">Pricing</a></footer>'
BANNER = '<div id="cookie-banner"><p>Cookies?</p><div><button>Accept</button></div></div>'


def site_page(url, title, body="", header=None, footer=FOOTER, canonical=None, og=None, ga=GA, head_extra=""):
    canonical = canonical if canonical is not None else "https://puffinship.com" + url
    og = og if og is not None else canonical
    header = header if header is not None else HEADER.format(cur=' aria-current="page"' if url == "/pricing/" else "")
    return f"""<!DOCTYPE html><html><head><title>{title}</title>
<meta name="description" content="About {title}." />
<link rel="canonical" href="{canonical}" />
<meta property="og:url" content="{og}" />
{ga}{head_extra}</head><body>{header}<main>{body}</main>{footer}{BANNER}</body></html>"""


class CheckWholeSiteTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.write("index.html", site_page("/", "Home", '<p id="hello">Hi</p>'))
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", '<p id="plan">One plan</p>'))
        self.write("404.html", site_page("/404.html", "Not found"))
        self.write("docs/index.html", "<p>moved</p>")  # a redirect page, not part of the site
        self.write("assets/a.png", "x")
        self.write("sitemap.xml", "<urlset><url><loc>https://puffinship.com/</loc></url>"
                                  "<url><loc>https://puffinship.com/pricing/</loc></url></urlset>")
        self.write("llms.txt", "# P\n\nPricing: https://puffinship.com/pricing/#plan\n")

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def flags(self, needle):
        problems = check_site(self.root)
        self.assertTrue(any(needle in p for p in problems), f"expected {needle!r} in {problems}")

    def test_good_site_passes(self):
        self.assertEqual(check_site(self.root), [])

    def test_link_to_missing_page(self):
        self.write("index.html", site_page("/", "Home", '<a href="/nope/">x</a>'))
        self.flags("/nope/")

    def test_link_without_trailing_slash(self):
        self.write("index.html", site_page("/", "Home", '<a href="/pricing">x</a>'))
        self.flags("/pricing")

    def test_cross_page_fragment_must_exist(self):
        self.write("index.html", site_page("/", "Home", '<a href="/pricing/#plan">ok</a><a href="/pricing/#gone">x</a>'))
        problems = check_site(self.root)
        self.assertTrue(any("#gone" in p for p in problems), problems)
        self.assertFalse(any("#plan" in p for p in problems), problems)

    def test_missing_asset(self):
        self.write("index.html", site_page("/", "Home", '<img src="/assets/a.png" alt="" /><video poster="/assets/b.jpg?v=2"></video>'))
        self.flags("/assets/b.jpg")

    def test_relative_link_flagged(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", '<img src="assets/a.png" alt="" />'))
        self.flags("relative")

    def test_absolute_site_url_checked_like_a_path(self):
        self.write("index.html", site_page("/", "Home", '<a href="https://puffinship.com/gone/">x</a>'))
        self.flags("/gone/")

    def test_header_drift(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", header="<header id=\"top\">Other</header>"))
        self.flags("header differs")

    def test_aria_current_ignored_in_header(self):
        self.assertEqual(check_site(self.root), [])

    def test_footer_drift(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", footer="<footer>Other</footer>"))
        self.flags("footer differs")

    def test_wrong_canonical(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", canonical="https://puffinship.com/"))
        self.flags("canonical")

    def test_og_url_must_match_canonical(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", og="https://puffinship.com/"))
        self.flags("og:url")

    def test_duplicate_title(self):
        self.write("pricing/index.html", site_page("/pricing/", "Home"))
        self.flags("more than one page")

    def test_missing_ga(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", ga=""))
        self.flags("Google Analytics")

    def test_page_copy_rules_apply_to_every_page(self):
        self.write("pricing/index.html", site_page("/pricing/", "Pricing", "<p>Start free today</p>"))
        self.flags("/pricing/: visible text: banned word")

    def test_sitemap_missing_page(self):
        self.write("about/index.html", site_page("/about/", "About"))
        self.flags("sitemap.xml is missing https://puffinship.com/about/")

    def test_sitemap_lists_non_page(self):
        self.write("sitemap.xml", "<urlset><url><loc>https://puffinship.com/</loc></url>"
                                  "<url><loc>https://puffinship.com/pricing/</loc></url>"
                                  "<url><loc>https://puffinship.com/old/</loc></url></urlset>")
        self.flags("not a page")

    def test_404_not_required_in_sitemap(self):
        problems = check_site(self.root)
        self.assertFalse(any("404" in p for p in problems), problems)

    def test_llms_link_to_old_anchor_flagged(self):
        self.write("llms.txt", "# P\n\nAsk at https://puffinship.com/#contact.\n")
        self.flags("#contact")

    def test_llms_copy_rules(self):
        self.write("llms.txt", "# P\n\nTry it free.\n")
        self.flags("banned word")


if __name__ == "__main__":
    unittest.main()
