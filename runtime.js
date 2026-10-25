/* quote-card runtime — shared by every template.
 *
 * A template is pure visual markup. It only has to provide these ids:
 *   #stage #bg #bgImg #scrim #mark #quote #speaker #title #kicker #bar
 * Everything else (text fitting, cue timing, pop-in motion) lives here, so a
 * new template never needs to touch animation logic.
 *
 * Two modes:
 *   static — renderAt() is never called; applyStatic() fills the card.
 *   video  — the driver calls renderAt(t) once per frame. Everything is a pure
 *            function of t, so seeking works and nothing drifts against audio.
 */
(function () {
  const CFG = window.QC_CONFIG;
  const $ = (id) => document.getElementById(id);

  const E = {
    stage: $('stage'),
    bg: $('bg'),
    bgImg: $('bgImg'),
    scrim: $('scrim'),
    mark: $('mark'),
    quote: $('quote'),
    speaker: $('speaker'),
    title: $('title'),
    kicker: $('kicker'),
    bar: $('bar'),
    body: $('body'),
    // the corner index ("01") is a class, not an id — every template spells it
    // the same way but none of them gives it an id.
    idx: document.querySelector('.idx'),
    // the big quote mark in the same corner — also a class, for the same
    // reason.
    qmark: document.querySelector('.qmark'),
    // the brand logo, top-left. Optional — the kicker text takes the same
    // slot when there is no logo.
    logo: document.querySelector('#logo'),
  };

  /* ------------------------------------------------------------ media urls */

  // A media path may already be a URL, an absolute path, or something
  // relative to the page. The builder resolves everything to an absolute
  // file:// URL before it gets here, so this only has to cover the
  // hand-written HTML case.
  function mediaSrc(value, baseDir) {
    if (!value) return null;
    const s = String(value);
    if (/^[a-z][a-z0-9+.-]*:/i.test(s) || s.startsWith('//')) return s;
    if (/^[a-z]:[\\/]/i.test(s)) return s;
    if (s.startsWith('/')) return s;
    return baseDir + '/' + s.replace(/^\.?\//, '');
  }

  /* ------------------------------------------------------------ text marks */

  // `highlight` in the job file lists the phrases worth stopping on. We wrap
  // them so templates can style a `.key` span instead of hand-editing HTML —
  // which is the one thing you would otherwise redo for every single card.
  function markKeys(host, text) {
    host.textContent = '';
    const keys = (CFG.highlight || []).filter(Boolean)
      .sort((a, b) => b.length - a.length);   // longest first, avoid nesting
    if (!keys.length || !text) {
      host.textContent = text || '';
      return;
    }
    let i = 0;
    while (i < text.length) {
      const k = keys.find((k) => text.startsWith(k, i));
      if (k) {
        const s = document.createElement('span');
        s.className = 'key';
        s.textContent = k;
        host.appendChild(s);
        i += k.length;
      } else {
        host.appendChild(document.createTextNode(text[i]));
        i += 1;
      }
    }
  }

  /* ---------------------------------------------------------------- tokens */

  function applyTokens(t) {
    const root = document.documentElement.style;
    // a bare family name needs quoting; a stack that already has commas does not
    const fam = (f) => (/[,"']/.test(f) ? f : '"' + f + '"');
    const scale = t.quoteScale == null ? 1 : t.quoteScale;
    const map = {
      '--bg': t.bg,
      '--bg2': t.bg2,
      '--ink': t.ink,
      '--ink-soft': t.inkSoft,
      '--accent': t.accent,
      '--accent2': t.accent2,
      '--rule': t.rule,
      // role colours: the field is the page ground, the plate is the
      // surface the quote sits on. Each carries its own ink so a bright
      // ground and a dark panel can coexist in one card.
      '--plate': t.plate,
      '--plate-pad': t.platePad,
      '--plate-radius': t.plateRadius,
      '--on-plate': t.onPlate,
      '--on-plate-soft': t.onPlateSoft,
      '--on-field': t.onField,
      '--on-accent2': t.onAccent2,
      '--mesh1': t.mesh1,
      '--mesh2': t.mesh2,
      // keyline + shadow around the quote glyphs
      '--quote-stroke': t.quoteStroke || 'transparent',
      '--quote-stroke-width': t.quoteStrokeWidth || '0px',
      '--quote-shadow': t.quoteShadow || '0 0 0 transparent',
      '--font-quote': fam(t.quoteFont),
      '--font-meta': fam(t.metaFont),
      '--weight-quote': String(t.quoteWeight),
      '--size-quote': Math.round(t.quoteSize * scale) + 'px',
      '--tracking-quote': (t.quoteTracking ?? 0) + 'em',
      '--line-quote': String(t.quoteLeading ?? 1.35),
      '--pad': t.pad + 'px',
      '--pane-quote': t.paneQuote || '80%',
      '--vignette': t.vignette,
      // the big quote mark
      '--qmark-size': t.qmarkSize + 'px',
      '--qmark-opacity': String(t.qmarkOpacity),
      '--qmark-inset': t.qmarkInset + 'px',
      '--qmark-font': fam(t.qmarkFont || 'Georgia, "Times New Roman", serif'),
      '--qmark-color': t.qmarkColor || 'var(--on-plate)',
      // the brand logo's box
      '--logo-w': t.logoWidth + 'px',
      '--logo-h': t.logoHeight + 'px',
    };
    for (const k in map) root.setProperty(k, map[k]);
    // A full-frame gradient is optional — only publish it when the theme
    // actually asks for one, so the flat fallback stays in charge otherwise.
    if (t.bgGrad) root.setProperty('--bg-grad', t.bgGrad);
    else root.removeProperty('--bg-grad');
    document.body.dataset.density = t.density || 'regular';
    document.body.dataset.lang = t.lang || 'zh-CN';
    document.documentElement.lang = t.lang || 'zh-CN';
  }

  function minSize(t) {
    const scale = t.quoteScale == null ? 1 : t.quoteScale;
    return Math.round((t.quoteMinSize || Math.round(t.quoteSize * 0.62)) * scale);
  }

  function applyBackground(t, baseDir) {
    if (!E.bgImg || !t.bgImage) {
      if (E.bg) E.bg.style.display = 'none';
      return;
    }
    const src = mediaSrc(t.bgImage, baseDir);
    if (!src) return;
    E.bgImg.style.backgroundImage = 'url("' + src + '")';
    E.bgImg.style.backgroundSize = t.bgFit || 'cover';
    E.bgImg.style.backgroundPosition = t.bgPos || 'center';
    E.bgImg.style.filter = t.bgFilter || 'none';
    // Blur/darken is what keeps an arbitrary user photo readable under text.
    E.scrim.style.background = t.bgScrim || 'transparent';
  }

  /* ------------------------------------------------------------ text fit */

  // The quote's box is whatever the pane gives it — but the pane may also
  // hold a mark above it, and that mark eats into the same column. Count the
  // space the siblings already took, or the text quietly overflows.
  function usedBySiblings(el) {
    const p = el.parentElement;
    if (!p) return 0;
    let used = 0;
    for (const sib of p.children) {
      if (sib === el) break;
      const cs = getComputedStyle(sib);
      if (cs.display === 'none' || cs.position === 'absolute' ||
          cs.position === 'fixed') continue;
      const b = sib.getBoundingClientRect();
      used += b.height + (parseFloat(cs.marginTop) || 0) +
              (parseFloat(cs.marginBottom) || 0);
    }
    return used;
  }

  // Chinese sentences vary in length a lot. Rather than let one long cue
  // overflow the card, shrink toward a floor. The ceiling is the element's OWN
  // computed size, so a template that scales the quote with
  // `calc(var(--size-quote) * 1.4)` still gets its scale — setting an inline
  // size from the theme instead would silently override every template.
  function fit(el, floor) {
    if (!el || !el.dataset.measure) return;
    el.style.fontSize = '';
    let size = parseFloat(getComputedStyle(el).fontSize) || 0;
    if (!size) return;
    // Remember the template's own size — the video pass needs it as the
    // starting point, and by then an inline size is already in place.
    el.dataset.base = String(size);
    el.style.fontSize = size + 'px';
    // The panel's padding lives on this element, and scrollHeight counts it —
    // so compare against the space that's actually left for text.
    const cs = getComputedStyle(el);
    const padV = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    const boxH = el.parentElement.clientHeight - padV - usedBySiblings(el);
    if (boxH <= 0) return;
    while (size > floor && el.scrollHeight - padV > boxH) {
      size -= Math.max(1, Math.round(size * 0.04));
      el.style.fontSize = size + 'px';
    }
  }

  // What the type settled on, so the tool can report it before spending
  // minutes rendering frames. Null until the first measurement.
  let fitInfo = null;

  // One font size for the whole clip. Fitting per frame makes the type
  // breathe as lines scroll in and out; instead, measure every window once
  // and take the smallest size that fits the tallest of them. The cost is a
  // one-off pass over the cue list at boot.
  function fitStack(keep, fill, floor) {
    const q = E.quote;
    if (!q || !spans.length) return;
    const base = parseFloat(q.dataset.base || '') || 0;
    if (!base) return;
    const saved = spans.map((s) => s.style.display);
    q.style.fontSize = base + 'px';
    const cs = getComputedStyle(q);
    const padV = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    let worst = 0;
    for (let cur = 0; cur < spans.length; cur++) {
      const lo = keep ? Math.max(0, cur - keep + 1) : 0;
      spans.forEach((s, i) => {
        const inWindow = i >= lo && i <= cur;
        const isFill = fill && i === cur + 1;
        s.style.display = (inWindow || isFill) ? '' : 'none';
      });
      worst = Math.max(worst, q.scrollHeight - padV);
    }
    const boxH = q.parentElement.clientHeight - padV - usedBySiblings(q);
    let size = base;
    if (boxH > 0 && worst > boxH) size = Math.max(floor, base * boxH / worst);
    q.style.fontSize = size.toFixed(2) + 'px';
    spans.forEach((s, i) => s.style.display = saved[i]);
    fitInfo = { mode: 'stack', size, base, worst, boxH, keep,
                fill: !!fill, floor, lines: spans.length };
  }

  // Measure the whole clip in one pass: the size the type will actually use,
  // the tallest window of lines, and the emptiest one. The emptiest one
  // matters as much as the tallest — a window that is a quarter full looks
  // broken, and no amount of "it fits" fixes that.
  function measure() {
    if (!E.quote) return null;
    if (!spans.length) buildSpans();
    const q = E.quote;
    const V = CFG.video || {};
    const acc = V.accumulate !== false;
    const keep = acc
      ? (V.keepLines ? Math.max(1, parseInt(V.keepLines, 10) || 0) : 0)
      : 1;
    const floor = minSize(CFG.theme);
    const base = parseFloat(q.dataset.base || '') || 0;

    // Settle the size exactly the way the renderer will.
    let size = base;
    if (keep) {
      if (!fitInfo) fitStack(keep, !!V.fillLast, floor);
      size = fitInfo ? fitInfo.size : base;
    } else {
      // Every line stays on screen, so the tightest moment is the full
      // stack — fit() shrinks the way the renderer does, step by step.
      const saved = spans.map((s) => s.style.display);
      spans.forEach((s) => { s.style.display = ''; });
      fit(q, floor);
      size = parseFloat(q.style.fontSize) || base;
      spans.forEach((s, i) => { s.style.display = saved[i]; });
    }

    // Now walk every window at the settled size and see how full it is.
    const saved = spans.map((s) => s.style.display);
    q.style.fontSize = size.toFixed(2) + 'px';
    const cs = getComputedStyle(q);
    const padV = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    const boxH = q.parentElement.clientHeight - padV - usedBySiblings(q);
    let minUsed = Infinity;
    let maxUsed = 0;
    let worstAt = 0;
    let firstUsed = 0;
    let minFull = Infinity;
    let sumFull = 0;
    let nFull = 0;
    for (let cur = 0; cur < spans.length; cur++) {
      const lo = keep ? Math.max(0, cur - keep + 1) : 0;
      const hi = (V.fillLast && cur + 1 < spans.length) ? cur + 1 : cur;
      spans.forEach((s, i) => {
        s.style.display = (i >= lo && i <= hi) ? '' : 'none';
      });
      const used = q.scrollHeight - padV;
      if (cur === 0) firstUsed = used;
      if (used < minUsed) minUsed = used;
      if (used > maxUsed) { maxUsed = used; worstAt = cur; }
      // A window that is not full yet says nothing about how empty the card
      // looks — the opening line is supposed to sit alone in a big field.
      // Only the full windows tell you whether the type fills the frame.
      if (hi - lo + 1 >= Math.min(keep, spans.length)) {
        if (used < minFull) minFull = used;
        sumFull += used;
        nFull += 1;
      }
    }
    spans.forEach((s, i) => { s.style.display = saved[i]; });

    return {
      mode: keep ? 'stack' : 'grow',
      keep, lines: spans.length,
      size, base, floor,
      boxH, minUsed: minUsed === Infinity ? 0 : minUsed, maxUsed, worstAt,
      firstUsed,
      minFull: minFull === Infinity ? minUsed : minFull,
      avgFull: nFull ? sumFull / nFull : 0,
      fits: boxH > 0 ? maxUsed <= boxH + 0.5 : true,
    };
  }

  /* -------------------------------------------------------------- easing */

  const easeOut = (x) => 1 - Math.pow(1 - x, 3);
  const easeBack = (x) => {
    const c = 1.70158 + 1;
    return 1 + c * Math.pow(x - 1, 3) + 1.70158 * Math.pow(x - 1, 2);
  };
  const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

  /* --------------------------------------------------------------- static */

  function applyStatic() {
    const t = CFG.theme;
    applyTokens(t);
    applyBackground(t, CFG.baseDir);
    if (E.quote) {
      markKeys(E.quote, CFG.quote || '');
      E.quote.dataset.measure = '1';
      fit(E.quote, minSize(t));
    }
    if (E.mark && !CFG.showMark) E.mark.style.display = 'none';
    if (E.idx && CFG.showIndex === false) E.idx.style.display = 'none';
    // The quote mark and the corner index want the same corner, so they are
    // mutually exclusive — one of them has to give way, and the mark is the
    // heavier element, so the index goes.
    if (E.qmark) {
      E.qmark.style.display = CFG.showQuoteMark ? '' : 'none';
      if (CFG.showQuoteMark && E.idx) E.idx.style.display = 'none';
    }
    if (E.speaker) E.speaker.textContent = CFG.speaker || '';
    if (E.title) E.title.textContent = CFG.title || '';
    if (E.kicker) E.kicker.textContent = CFG.kicker || '';
    // The logo replaces the kicker in the corner — the CSS hides the kicker
    // as soon as the body carries the flag, so the two never share the slot.
    //
    // A card can sit on a dark ground in one template and a light one in
    // another (the photoframe template always does), so the job may carry
    // two files: one for a light ground, one for a dark one. The ground was
    // resolved in Python — the template's own declaration for a photo
    // behind it, the theme's field colour otherwise.
    if (E.logo) {
      const ground = CFG.ground || document.documentElement.dataset.ground || 'light';
      const src = mediaSrc(
        (ground === 'dark' ? (CFG.logoOnDark || CFG.logo)
                           : (CFG.logo || CFG.logoOnDark)),
        CFG.baseDir);
      if (src) {
        E.logo.src = src;
        document.body.classList.add('has-logo');
        // How much room the logo takes above the quote. A wordmark's height
        // follows its width and its own aspect ratio, so it can only be
        // measured once the file has decoded — a template that has to clear
        // it (split) reads this instead of guessing from the box.
        const publish = () => document.body.style.setProperty(
          '--logo-real-h', Math.round(E.logo.offsetHeight) + 'px');
        if (E.logo.complete && E.logo.naturalWidth) publish();
        else E.logo.addEventListener('load', publish, { once: true });
      }
    }
    if (E.bar) E.bar.style.width = '100%';
  }

  /* ---------------------------------------------------------------- video */

  let spans = [];
  // True once fitStack() has settled on one size for the whole clip.
  let sized = false;

  function buildSpans() {
    if (!E.quote) return;
    E.quote.textContent = '';
    // A trimmed clip must not replay lines that were said before the trim.
    const clipStart = CFG.clipStart || 0;
    const list = (CFG.cues || []).filter((c) => c.end > clipStart - 1e-6);
    cueList = list;
    spans = list.map((c, i) => {
      const s = document.createElement('span');
      s.className = 'cue';
      s.dataset.i = String(i);
      markKeys(s, c.text);
      E.quote.appendChild(s);
      return s;
    });
    E.quote.dataset.measure = '1';
    // Size the type once for the whole clip: the tallest window of lines is
    // measured up front, so the quote never overflows and never resizes
    // mid-video. Only worth it when the window is bounded — with every line
    // on screen there is no single size to settle on, and the old per-cue
    // fit (which shrinks as the stack grows) is the lesser evil.
    const V = CFG.video || {};
    const acc = V.accumulate !== false;
    const keep = acc
      ? (V.keepLines ? Math.max(1, parseInt(V.keepLines, 10) || 0) : 0)
      : 1;
    if (keep) {
      fitStack(keep, !!V.fillLast, minSize(CFG.theme));
      sized = true;
    }
  }

  let cueList = [];

  // Called by the Python driver for every frame. t is seconds.
  function renderAt(t) {
    const V = CFG.video || {};
    if (!spans.length) buildSpans();

    const cues = cueList;
    const pop = V.popMs == null ? 260 : V.popMs;
    const popS = pop / 1000;
    const lead = V.lead == null ? 0.06 : V.lead;
    const accumulate = V.accumulate !== false;
    const fill = V.fillLast;
    // How many lines stay on screen at once when accumulating. 0 = all of them.
    const keep = accumulate && V.keepLines
      ? Math.max(1, parseInt(V.keepLines, 10) || 0)
      : 0;

    let cur = -1;
    for (let i = 0; i < cues.length; i++) {
      if (t >= cues[i].start - lead && t < cues[i].end) { cur = i; break; }
      if (t >= cues[i].end) cur = i; // keep the last one that finished
    }

    spans.forEach((s, i) => {
      const c = cues[i];
      s.className = 'cue';
      if (i > cur && !(fill && i === cur + 1)) return; // not spoken yet

      if (i === cur && t < c.start) {
        // inside the lead-in: still waiting, hold it hidden
        s.style.opacity = '0';
        return;
      }
      if (i === cur) {
        const p = clamp01((t - c.start) / popS);
        const e = easeOut(p);
        const isLead = t < c.start;
        s.style.opacity = String(isLead ? 0 : Math.min(1, e * 1.4));
        const sc = 0.955 + 0.045 * e;
        const ty = isLead ? 0 : (1 - e) * 14;
        s.style.transform = 'translateY(' + ty.toFixed(2) + 'px) scale(' + sc.toFixed(4) + ')';
        s.classList.add('is-current');
        if (isLead) s.classList.remove('is-current');
      } else {
        // already spoken — settle back to the muted style
        const age = t - c.end;
        const fade = clamp01(age / (popS * 0.8));
        s.style.opacity = String(accumulate ? 0.46 * fade : 0);
        s.style.transform = 'none';
        s.classList.toggle('is-spent', accumulate);
      }
    });

    if (E.bar) {
      // `t` is absolute audio time but `duration` is the clip length, so the
      // trim offset has to come off before dividing.
      const total = CFG.duration || 0;
      const p = total > 0 ? ((t - (CFG.clipStart || 0)) / total) : 0;
      E.bar.style.width = (Math.max(0, Math.min(1, p)) * 100).toFixed(2) + '%';
    }

    // Re-fit only when the visible text changes, not every frame — reflow is
    // the single most expensive thing we do here.
    if (cur !== renderAt._last) {
      renderAt._last = cur;
      // Without accumulate, only the current line is on screen. The spoken
      // lines have to leave the flow entirely (display:none) — fading them to
      // opacity 0 still reserves their height, which pushes the current line
      // off the bottom of the card.
      //
      // `keepLines` caps the accumulated window: the last N lines stay on
      // screen (the current one lit, the rest dimmed) and the older ones
      // scroll off. Keeping every line would squeeze the whole transcript
      // into one frame at an unreadable size; dropping every line but the
      // current one leaves the card half empty.
      const lo = accumulate
        ? (keep ? Math.max(0, cur - keep + 1) : 0)
        : cur;
      // `fillLast` shows one line ahead of the current one — it has to be
      // displayed too, or the fill never appears.
      const hi = (fill && cur + 1 < spans.length) ? cur + 1 : cur;
      spans.slice(lo, hi + 1).forEach((s) => s.style.display = '');
      for (let i = 0; i < lo; i++) spans[i].style.display = 'none';
      for (let i = hi + 1; i < spans.length; i++) spans[i].style.display = 'none';
      // With a bounded window the type was already sized once for the whole
      // clip — re-fitting per cue would make it breathe. With every line on
      // screen there is no such size, so keep shrinking as the stack grows.
      if (!sized) fit(E.quote, minSize(CFG.theme));
    }
  }

  /* ----------------------------------------------------------------- boot */

  applyStatic();

  window.QC = {
    applyTokens,
    applyStatic,
    renderAt,
    buildSpans,
    measure,
    ready: true,
  };
  document.documentElement.dataset.qcReady = '1';
})();