/* Puffin Ship site script. Shared by every page; loaded with defer.
   Google Analytics itself is set up inline in each page's <head> so consent
   defaults are in place before the tag loads. */

// Mobile menu: the Menu button opens the panel of nav links below 960px.
(function () {
  var btn = document.querySelector('.nav-menu-btn');
  var panel = document.getElementById('nav-panel');
  if (!btn || !panel) return;
  function set(open) {
    panel.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  btn.addEventListener('click', function () { set(btn.getAttribute('aria-expanded') !== 'true'); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && btn.getAttribute('aria-expanded') === 'true') { set(false); btn.focus(); }
  });
  window.addEventListener('resize', function () { if (window.innerWidth > 960) set(false); });
})();

// Copy buttons: copy the text of the element named in data-copy.
(function () {
  document.querySelectorAll('.copy-btn[data-copy]').forEach(function (btn) {
    if (!navigator.clipboard) return;
    btn.hidden = false;
    btn.addEventListener('click', function () {
      var el = document.getElementById(btn.getAttribute('data-copy'));
      if (!el) return;
      navigator.clipboard.writeText(el.textContent.trim()).then(function () {
        btn.textContent = 'Copied';
        setTimeout(function () { btn.textContent = 'Copy'; }, 1800);
      }, function () {});
    });
  });
})();

  (function () {
    var STORAGE_KEY = 'ps_cookie_consent_v1';

    var banner = document.getElementById('cookie-banner');
    var acceptBtn = document.getElementById('cookie-accept');
    var declineBtn = document.getElementById('cookie-decline');
    var settingsBtn = document.getElementById('cookie-settings');

    function showBanner() {
      if (banner) banner.hidden = false;
    }
    function hideBanner() {
      if (banner) banner.hidden = true;
    }

    // The tag is already loaded in <head> with analytics_storage denied by
    // default, so Accept/Decline only flips the consent state; it never
    // injects the tag.
    function grant() {
      localStorage.setItem(STORAGE_KEY, 'granted');
      gtag('consent', 'update', { analytics_storage: 'granted' });
      hideBanner();
    }

    function deny() {
      localStorage.setItem(STORAGE_KEY, 'denied');
      gtag('consent', 'update', { analytics_storage: 'denied' });
      hideBanner();
    }

    var stored;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      stored = null;
    }

    if (stored === 'granted') {
      gtag('consent', 'update', { analytics_storage: 'granted' });
    } else if (stored === 'denied') {
      gtag('consent', 'update', { analytics_storage: 'denied' });
    } else {
      showBanner();
    }

    if (acceptBtn) acceptBtn.addEventListener('click', grant);
    if (declineBtn) declineBtn.addEventListener('click', deny);
    if (settingsBtn) {
      settingsBtn.addEventListener('click', function () {
        try {
          localStorage.removeItem(STORAGE_KEY);
        } catch (e) {}
        gtag('consent', 'update', { analytics_storage: 'denied' });
        showBanner();
      });
    }
  })();

  (function () {
    var form = document.getElementById('lead-form');
    if (!form) return;
    var errEl = document.getElementById('lead-error');
    var btn = document.getElementById('lead-submit');
    var done = document.getElementById('lead-done');

    function fail(msg) {
      errEl.textContent = msg;
      errEl.hidden = false;
      btn.disabled = false;
      btn.textContent = 'Send';
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      errEl.hidden = true;

      var data = new FormData(form);
      var name = (data.get('name') || '').trim();
      var email = (data.get('email') || '').trim();
      var company = (data.get('company') || '').trim();
      var message = (data.get('message') || '').trim();

      if (!name || !message) {
        fail('Please fill in your name and what you would like help with.');
        return;
      }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        fail('Please enter a valid email address.');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Sending';

      fetch('https://app.puffinship.com/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          email: email,
          company: company,
          website_url: (data.get('website_url') || '').trim(),
          what_you_sell: (data.get('what_you_sell') || '').trim(),
          channels: data.getAll('channels'),
          message: message,
          page_url: window.location.href,
          website: data.get('website') || ''
        })
      }).then(function (res) {
        if (!res.ok) throw new Error('bad status');
        form.hidden = true;
        done.hidden = false;
      }).catch(function () {
        fail('Something went wrong sending that. Please try again, or email info@puffinship.com.');
      });
    });
  })();


// Carousels: buttons step one slide at a time and disable at the ends.
(function () {
  document.querySelectorAll('.carousel').forEach(function (root) {
    var track = root.querySelector('.carousel-track');
    var prev = root.querySelector('.carousel-btn[data-dir="-1"]');
    var next = root.querySelector('.carousel-btn[data-dir="1"]');
    var nav = root.querySelector('.carousel-nav');
    var slides = Array.prototype.slice.call(track.querySelectorAll('.sample'));
    if (!slides.length) return;
    function update() {
      var max = track.scrollWidth - track.clientWidth - 2;
      nav.hidden = max <= 0;
      prev.disabled = track.scrollLeft <= 2;
      next.disabled = track.scrollLeft >= max;
    }
    // The stops the buttons move between: each slide's start, capped at
    // the end of the row. Stops closer together than a third of a slide
    // merge, so "back" from the end never moves a few pixels and stalls.
    var pending = null, settle;
    function stops() {
      var max = track.scrollWidth - track.clientWidth, first = slides[0].offsetLeft, out = [];
      var minGap = slides[0].offsetWidth / 3;
      slides.forEach(function (sl) {
        var p = Math.min(sl.offsetLeft - first, max);
        if (!out.length || p - out[out.length - 1] > minGap) out.push(p);
        else out[out.length - 1] = p;
      });
      return out;
    }
    function step(dir) {
      var ps = stops();
      var from = pending !== null ? pending : track.scrollLeft;
      var idx = 0;
      for (var i = 1; i < ps.length; i++) if (Math.abs(ps[i] - from) < Math.abs(ps[idx] - from)) idx = i;
      idx = Math.max(0, Math.min(ps.length - 1, idx + dir));
      pending = ps[idx];
      track.scrollTo({ left: pending });
      clearTimeout(settle);
      settle = setTimeout(function () { pending = null; update(); }, 700);
    }
    prev.addEventListener('click', function () { step(-1); });
    next.addEventListener('click', function () { step(1); });
    track.addEventListener('scroll', update, { passive: true });
    track.addEventListener('scrollend', function () { pending = null; update(); });
    window.addEventListener('resize', update);
    update();
  });
})();

// Sample videos: the full-screen button, one video playing at a time, and
// no "Save video as" on right-click.
(function () {
  document.querySelectorAll('.sample-fs').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var v = btn.parentNode.querySelector('video');
      var go = v.requestFullscreen || v.webkitRequestFullscreen;
      if (go) {
        var req = go.call(v);
        if (req && req.catch) req.catch(function () {}); // blocked: just play inline
        v.play();
      }
      else if (v.webkitEnterFullscreen) { v.play(); v.webkitEnterFullscreen(); } // iPhone
    });
  });
  document.addEventListener('play', function (e) {
    document.querySelectorAll('video').forEach(function (o) { if (o !== e.target) o.pause(); });
    var name = e.target.getAttribute('data-name');
    if (name && !e.target.dataset.tracked && typeof gtag === 'function') {
      e.target.dataset.tracked = '1';
      gtag('event', 'showcase_play', { video_name: name });
    }
  }, true);
  document.addEventListener('contextmenu', function (e) {
    if (e.target.tagName === 'VIDEO' && !e.target.closest('#tour')) e.preventDefault();
  });
})();

// Hero quickstart video: a big play button over the poster, then native controls.
(function () {
  var box = document.getElementById('tour');
  if (!box) return;
  var v = document.getElementById('tour-video');
  var tracked = false;
  box.querySelector('.tour-play').addEventListener('click', function () {
    box.classList.add('is-playing');
    v.controls = true;
    var p = v.play();
    if (p && p.catch) p.catch(function () {});
  });
  v.addEventListener('play', function () {
    box.classList.add('is-playing');
    v.controls = true;
    if (!tracked && typeof gtag === 'function') { tracked = true; gtag('event', 'tour_play'); }
  });
})();
