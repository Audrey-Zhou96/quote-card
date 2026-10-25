"""quote-card builder.

One job file describes the card; this produces a static image and/or a short
vertical video. Everything is local — Playwright renders, ffmpeg encodes,
faster-whisper supplies timings — so there is nothing to install or host.

    python build.py transcribe assets/speech.m4a -o assets/cues.json
    python build.py static jobs/cto.json
    python build.py video   jobs/cto.json
    python build.py both    jobs/cto.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

# Windows consoles default to GBK here, which mangles the Chinese the tool
# prints (template descriptions, verdicts). UTF-8 keeps them readable.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import tokens as T  # noqa: E402

RUNTIME = (HERE / "runtime.js").read_text(encoding="utf-8")
BASE_CSS = (HERE / "base.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------- job loading

def load_job(path: Path) -> dict:
    job = json.loads(path.read_text(encoding="utf-8"))
    job["_dir"] = path.parent
    job["_base"] = path.resolve().parent
    return job


def resolve(job: dict, key: str, default: str | None = None) -> Path | None:
    v = job.get(key, default)
    if not v:
        return None
    p = Path(v)
    return p if p.is_absolute() else (job["_base"] / p)


# ------------------------------------------------------------------- checks

def highlight_report(job: dict, cues: list | None = None) -> tuple[list[str], list[str]]:
    """Which of the job's highlight phrases actually appear in the copy.

    A phrase that is not in the text is a silent no-op: the card renders
    perfectly, with no highlighter on it, and nothing anywhere says why.
    Splitting the phrases into hit and miss is the whole point.
    """
    keys = [k for k in (job.get("highlight") or []) if k]
    if not keys:
        return [], []
    texts = [job.get("quote", "")] + [c.get("text", "") for c in (cues or [])]
    hit, miss = [], []
    for k in keys:
        (hit if any(k in t for t in texts) else miss).append(k)
    return hit, miss


def logo_ink(path: Path) -> float | None:
    """How light the logo's own ink is, 0..1.

    A wordmark carries its colour in its pixels, so the only way to know
    whether it will survive the card is to look at them. A white logo on a
    white card is invisible, and the theme knows nothing about the file.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    w, h = im.size
    step = max(1, min(w, h) // 100)
    px = im.load()
    tot = 0.0
    n = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            tot += 0.2126 * r + 0.7152 * g + 0.0722 * b
            n += 1
    return (tot / n / 255) if n else None


def template_ground(job: dict) -> str:
    """Is this template sitting on a light ground or a dark one?

    The template knows one thing — the photoframe template always has a
    photo under it, and a photo is dark more often than not. Everything
    else the theme decides.
    """
    tpl = HERE / "templates" / f"{job.get('template', 'editorial')}.html"
    if tpl.exists():
        m = re.search(r'data-ground="(\w+)"', tpl.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return "light"


def effective_ground(job: dict, theme: dict) -> str:
    """Light or dark — the ground the logo has to sit on.

    Two things decide it. A template that puts a photo behind the card
    is dark whatever the theme says. Otherwise the theme's own field
    colour decides: a dark theme wants a light logo, a light theme a
    dark one. Getting this wrong is how a white logo ends up on a white
    card — invisible, and no error message.
    """
    if template_ground(job) == "dark":
        return "dark"
    ground_col = theme.get("fieldGround") or theme.get("bg") or "#000000"
    return "dark" if T.is_dark_ground(ground_col) else "light"


def logo_file(job: dict, ground: str) -> str | None:
    """The logo file that belongs on this ground."""
    main, alt = job.get("logo"), job.get("logoOnDark")
    if ground == "dark":
        return alt or main
    return main or alt


def logo_note(job: dict, theme: dict, ground: str = "light") -> str | None:
    """Does the logo's ink survive the card's ground? None means it does."""
    src = logo_file(job, ground)
    if not src:
        return None
    p = Path(src)
    if not p.is_absolute():
        p = next((b / src for b in (job["_base"], HERE) if (b / src).exists()),
                 job["_base"] / src)
    if not p.exists():
        return f"logo 找不到：{src}"
    ink = logo_ink(p)
    if ink is None:
        return None
    if ground == "dark":
        if ink < 0.55:
            return (f"深底配深色 logo（logo 亮度 {ink:.2f}）"
                    f" —— 换成白色或浅色 logo")
        return None
    try:
        bg = T.perceptual_luma(theme.get("fieldGround") or theme.get("bg")
                               or "#000000")
    except Exception:
        return None
    if ink > 0.6 and bg > 0.45:
        return (f"浅底配浅色 logo（logo {ink:.2f} / 底色 {bg:.2f}）"
                f" —— 换成黑色或深色 logo")
    return None


# ------------------------------------------------------------------- media

# The photo the photoframe template falls back to when the job does not
# bring one. A template called "put your own image here" that renders an
# empty frame is not a template, it is a bug.
DEFAULT_PHOTO = "assets/demo-photo.jpg"

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def media_url(job: dict, value: str | None) -> str | None:
    """Turn a media path from a job or a theme into a URL the browser loads.

    Relative paths are looked for in the job's own folder first and in the
    tool's root second, so a job can point at its own photo while a theme
    can point at a bundled one without either having to know about the
    other. Anything already absolute (a URL, a drive path) is passed on.
    """
    if not value:
        return None
    s = str(value)
    if _SCHEME.match(s) or s.startswith("//"):
        return s
    p = Path(s)
    if p.is_absolute():
        return p.as_uri() if p.exists() else None
    for base in (job["_base"], HERE):
        cand = base / s
        if cand.exists():
            return cand.as_uri()
    return None


def out_root(job: dict) -> Path:
    """Where a job's files live: <outDir>/<job name>/.

    One folder per job is the difference between a folder you can look at
    and a folder you have to grep. Everything a job produces — stills,
    videos, the template overviews — goes under that one name.
    """
    d = job.get("outDir", "out")
    base = Path(d) if Path(d).is_absolute() else (job["_base"] / d)
    return base / job.get("name", "card")


def out_dir_for(job: dict, kind: str) -> Path:
    """The folder a render writes into, plus the file stem it uses.

    A gallery renders six templates into one job's folder, so it has to
    override both. The override keys are private to the builder — they are
    stripped before a job is written back to disk.
    """
    if job.get("_outDir"):
        out = Path(job["_outDir"])
    else:
        out = out_root(job) / kind
    out.mkdir(parents=True, exist_ok=True)
    return out


def file_stem(job: dict) -> str:
    return job.get("_fileStem") or job.get("name", "card")


def theme_of(job: dict, ratio: str | None = None) -> dict:
    # The theme carries a per-template block, so it has to be resolved with
    # the template in hand — otherwise every card gets the base palette and
    # the block templates lose their inverted look.
    t = T.load_theme(job.get("theme"), job.get("tokens"),
                      template=job.get("template"))
    # A square card has ~25% less vertical room than 3:4 at the same width, so
    # the fixed padding has to give a little or the quote has nowhere to sit.
    if (ratio or (job.get("ratio") if isinstance(job.get("ratio"), str) else "3:4")) == "1:1":
        t["pad"] = round(t["pad"] * 0.86)

    # The photo behind the card. The photoframe template always has one —
    # the bundled placeholder when the job does not bring its own.
    if not t.get("bgImage") and job.get("template") == "photoframe":
        t["bgImage"] = DEFAULT_PHOTO
    if t.get("bgImage"):
        url = media_url(job, t["bgImage"])
        if url:
            t["bgImage"] = url
        else:
            print(f"  ! photo not found: {t['bgImage']}", file=sys.stderr)
            t["bgImage"] = None
    return t


# ------------------------------------------------------------------ ratios

RATIOS = {
    "3:4": (1080, 1440),
    "1:1": (1080, 1080),
    "9:16": (1080, 1920),
}


def ratio_dims(ratio: str) -> tuple[int, int]:
    if ratio not in RATIOS:
        raise SystemExit(f"unknown ratio '{ratio}'. known: {', '.join(RATIOS)}")
    return RATIOS[ratio]


def ratio_slug(ratio: str) -> str:
    return ratio.replace(":", "x")


def ratios_of(job: dict, args=None) -> list[str]:
    """`ratio` may be one size or several — "give me both a square and a
    vertical to pick from" is the common request."""
    r = job.get("ratio", "3:4")
    if isinstance(r, str):
        r = [r]
    r = list(r)
    if args is not None and getattr(args, "ratios", None):
        r = list(args.ratios)
    for x in r:
        if x not in RATIOS:
            raise SystemExit(f"unknown ratio '{x}'. known: {', '.join(RATIOS)}")
    return r


# ------------------------------------------------------------------- webfonts

FONT_DIR = HERE / "fonts"
FONT_FMT = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
FONT_WEIGHT = {"thin": 100, "extralight": 200, "light": 300, "regular": 400,
               "medium": 500, "semibold": 600, "bold": 700, "extrabold": 800,
               "black": 900}
_FONT_STEM = re.compile(
    r"^(.*?)[-_ ]?(Thin|ExtraLight|Light|Regular|Medium|SemiBold|Bold|ExtraBold|Black)$",
    re.I)


def font_face_css() -> str:
    """Turn whatever is sitting in fonts/ into @font-face rules. Drop
    `MyBrand-Bold.woff2` in there and the theme's "MyBrand" starts resolving —
    no template or theme edit needed."""
    if not FONT_DIR.exists():
        return ""
    faces = []
    for f in sorted(FONT_DIR.iterdir()):
        fmt = FONT_FMT.get(f.suffix.lower())
        if not fmt:
            continue
        m = _FONT_STEM.match(f.stem)
        family, style = (m.group(1), m.group(2)) if m else (f.stem, "Regular")
        weight = FONT_WEIGHT.get(style.lower().replace(" ", ""), 400)
        faces.append(
            f"@font-face{{font-family:'{family}';font-style:normal;"
            f"font-weight:{weight};src:url('{f.as_uri()}') format('{fmt}');"
            f"font-display:block;}}")
    return "\n".join(faces)


# ------------------------------------------------------------------- html glue

# ------------------------------------------------------------------- preflight

_VAR_USE = re.compile(r"var\(\s*(--[a-zA-Z0-9-]+)")
# runtime.js declares them quoted ('--bg': …), so allow an optional quote
_VAR_DEF = re.compile(r"['\"]?(--[a-zA-Z0-9-]+)['\"]?\s*:")
# some are published one at a time instead of through the token map
_VAR_PROP = re.compile(r"(?:set|remove)Property\(\s*['\"](--[a-zA-Z0-9-]+)['\"]")


def lint_template(tpl: Path) -> str | None:
    """A CSS custom property that is never defined does not error — the
    declaration using it just silently drops at computed-value time. That's
    how a highlight wash turns into invisible text. So check names up front."""
    src = tpl.read_text(encoding="utf-8")
    runtime_defs = set(_VAR_DEF.findall(RUNTIME)) | set(_VAR_PROP.findall(RUNTIME))
    local_defs = set(_VAR_DEF.findall(src)) | set(_VAR_DEF.findall(BASE_CSS))
    missing = set(_VAR_USE.findall(src)) - runtime_defs - local_defs
    if missing:
        return (f"{tpl.stem}: uses CSS vars that are never defined "
                f"({', '.join(sorted(missing))}) — those declarations will "
                f"be dropped silently")
    return None


def build_html(job: dict, theme: dict, cues: list | None, duration: float | None) -> str:
    tpl_name = job.get("template", "editorial")
    tpl = HERE / "templates" / f"{tpl_name}.html"
    if not tpl.exists():
        avail = ", ".join(sorted(p.stem for p in (HERE / "templates").glob("*.html")))
        raise SystemExit(f"template '{tpl_name}' not found. available: {avail}")
    warn = lint_template(tpl)
    if warn:
        print(f"  ! {warn}", file=sys.stderr)
    html = tpl.read_text(encoding="utf-8")

    fonts = font_face_css()
    if fonts:
        html = html.replace("</head>", "<style>" + fonts + "</style>\n</head>")

    cfg = {
        "quote": job.get("quote", ""),
        "speaker": job.get("speaker", ""),
        "title": job.get("title", ""),
        "kicker": job.get("kicker", ""),
        "logo": media_url(job, job.get("logo")),
        "logoOnDark": media_url(job, job.get("logoOnDark")),
        "ground": effective_ground(job, theme),
        "showMark": job.get("showMark", True),
        "showIndex": job.get("showIndex", True),
        "showQuoteMark": job.get("showQuoteMark", False),
        "highlight": job.get("highlight", []),
        "theme": theme,
        "baseDir": job["_base"].as_uri(),
        "video": job.get("video", {}),
        "clipStart": (job.get("video") or {}).get("start", 0) or 0,
        "cues": cues or [],
        "duration": duration or 0,
    }
    payload = "<script>window.QC_CONFIG=" + json.dumps(cfg, ensure_ascii=False) + ";</script>"

    # runtime last so it can boot against a fully parsed DOM
    html = html.replace("<!--QC_CONFIG-->", payload)
    html = html.replace("<!--QC_BASE-->", "<style>" + BASE_CSS + "</style>")
    html = html.replace("<!--QC_RUNTIME-->", "<script>" + RUNTIME + "</script>")
    return html


def open_page(playwright, job: dict, theme: dict, cues, duration,
              width: int, height: int, scale: int):
    html = build_html(job, theme, cues, duration)
    tmp = Path(tempfile.mkdtemp(prefix="qc_"))
    f = tmp / "card.html"
    f.write_text(html, encoding="utf-8")
    browser = playwright.chromium.launch(args=["--force-color-profile=srgb",
                                              "--font-render-hinting=none"])
    ctx = browser.new_context(viewport={"width": width, "height": height},
                              device_scale_factor=scale)
    page = ctx.new_page()
    page.goto(f.as_uri())
    page.wait_for_selector('html[data-qc-ready="1"]')
    # A dropped-in webfont resolves after first paint, so screenshotting without
    # this silently captures the fallback face instead.
    page.evaluate("() => document.fonts.ready.then(() => true)")
    # A dropped-in logo is an <img>, and a screenshot taken before it
    # decodes shows the corner empty.
    page.evaluate("() => Promise.all([...document.images].map(i => "
                  "i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r; })))")
    page.wait_for_timeout(250)  # let the background image decode
    return browser, ctx, page, tmp


def cmd_demo(job_path: Path, args) -> None:
    """Render every template with the same copy, for side-by-side picking."""
    base = load_job(job_path)
    tpls = sorted(p.stem for p in (HERE / "templates").glob("*.html"))
    if args.only:
        tpls = [t for t in tpls if t in args.only]
    out = out_root(base)
    out.mkdir(parents=True, exist_ok=True)
    for t in tpls:
        job = dict(base)
        job["template"] = t
        job["_outDir"] = str(out / "stills")
        job["_fileStem"] = t
        job.pop("_dir", None)
        job.pop("_base", None)   # Path objects, not part of the on-disk job
        # temp job must sit beside the original, or its relative asset paths break
        tmp = job_path.parent / f"_tmp_{t}.json"
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            cmd_static(tmp, args)
        finally:
            tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------- static

def cmd_static(job_path: Path, args) -> None:
    from playwright.sync_api import sync_playwright

    job = load_job(job_path)
    ratios = ratios_of(job, args)
    out = out_dir_for(job, "stills")
    stem = file_stem(job)
    # One size keeps the plain name; several get a suffix so they don't
    # overwrite each other in the same folder.
    multi = len(ratios) > 1
    scale = int(job.get("scale", 2))  # supersample, then downscale for crisp text

    for ratio in ratios:
        theme = theme_of(job, ratio)
        for w in T.audit(theme):
            print(f"  ! contrast: {w}", file=sys.stderr)
        note = logo_note(job, theme, effective_ground(job, theme))
        if note:
            print(f"  ! {note}", file=sys.stderr)
        if theme.get("bgImage"):
            theme["bgScrim"] = T.scrim_for(theme["bgImage"], theme)

        W, H = ratio_dims(ratio)
        with sync_playwright() as p:
            browser, ctx, page, tmp = open_page(p, job, theme, None, None, W, H, scale)
            png = out / f"{stem}{'--' + ratio_slug(ratio) if multi else ''}.png"
            page.locator("#stage").screenshot(path=str(png))
            browser.close()
            shutil.rmtree(tmp, ignore_errors=True)

        # Rendered at scale x, delivered at nominal — supersampling is what keeps
        # small CJK glyph edges clean instead of jaggy.
        if scale != 1:
            from PIL import Image
            Image.open(png).convert("RGB").resize((W, H), Image.LANCZOS).save(png)

        print(f"  {png}  ({png.stat().st_size // 1024} KB, {W}x{H})")

        if getattr(args, "preview", False):
            # A self-contained page: open it in a browser, tweak the theme and
            # re-render without touching the pipeline.
            hp = out / f"{stem}{'--' + ratio_slug(ratio) if multi else ''}.html"
            hp.write_text(build_html(job, theme, None, None), encoding="utf-8")
            print(f"  {hp}  (open in a browser)")

        if getattr(args, "jpg", False):
            from PIL import Image
            jpg = png.with_suffix(".jpg")
            Image.open(png).convert("RGB").save(jpg, "JPEG", quality=95, optimize=True)
            print(f"  {jpg}  ({jpg.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------------- video

def cmd_video(job_path: Path, args) -> None:
    job = load_job(job_path)

    audio = resolve(job, "audio")
    if not audio or not audio.exists():
        raise SystemExit("job needs an 'audio' path for video mode")
    cues_path = resolve(job, "cues")
    if not cues_path or not cues_path.exists():
        raise SystemExit("job needs a 'cues' path — run `transcribe` first")
    cues = json.loads(cues_path.read_text(encoding="utf-8"))
    if isinstance(cues, dict):
        cues = cues.get("cues", [])
    # A cue with no text is a line the user chose to drop — it should not
    # take up a slot on screen.
    cues = [c for c in cues if (c.get("text") or "").strip()]

    V = job.get("video", {}) or {}
    # Which frames to render. An explicit --ratios wins; then video.ratios;
    # then explicit width/height; otherwise the still card's ratio decides,
    # so "give me both sizes" is one line in the job file.
    if args is not None and getattr(args, "ratios", None):
        sizes = [(r, ratio_dims(r), ratio_slug(r)) for r in args.ratios]
    elif V.get("ratios"):
        sizes = [(r, ratio_dims(r), ratio_slug(r)) for r in V["ratios"]]
    elif V.get("width") and V.get("height"):
        sizes = [(None, (int(V["width"]), int(V["height"])), None)]
    else:
        sizes = [(r, ratio_dims(r), ratio_slug(r)) for r in ratios_of(job, args)]

    multi = len(sizes) > 1
    for ratio, (W, H), slug in sizes:
        render_video(job, args, audio, cues, V, W, H, slug, multi, ratio)


def render_video(job: dict, args, audio: Path, cues: list, V: dict,
                 W: int, H: int, slug: str | None, multi: bool,
                 ratio: str | None = None, preview: bool = True) -> None:
    from playwright.sync_api import sync_playwright

    # The ratio decides the padding — a 1:1 frame has less vertical room than
    # a 3:4 one, and the still card already gives its padding back there.
    # The video has to make the same call, or the two drift apart.
    theme = theme_of(job, ratio)
    for w in T.audit(theme):
        print(f"  ! contrast: {w}", file=sys.stderr)
    note = logo_note(job, theme, effective_ground(job, theme))
    if note:
        print(f"  ! {note}", file=sys.stderr)
    if theme.get("bgImage"):
        theme["bgScrim"] = T.scrim_for(theme["bgImage"], theme)
    # a vertical frame carries more lines at once, so video usually wants the
    # tighter leading even when the still card is set to regular
    if V.get("density"):
        theme["density"] = V["density"]
    dur = float(V.get("duration") or ffprobe_duration(audio))
    start = float(V.get("start", 0))
    end = V.get("end")
    dur = float(end) - start if end else dur - start

    fps = int(V.get("fps", 30))
    fmt = V.get("frameFormat", "jpeg")

    out_dir = job.get("outDir", "out")
    out = out_dir_for(job, "videos")
    stem = file_stem(job)
    mp4 = out / f"{stem}{'--' + slug if multi and slug else ''}.mp4"

    frames = Path(tempfile.mkdtemp(prefix="qc_frames_"))
    ext = "jpg" if fmt == "jpeg" else "png"
    total = int(dur * fps)

    try:
        with sync_playwright() as p:
            browser, ctx, page, tmp = open_page(p, job, theme, cues, dur, W, H, 1)
            stage = page.locator("#stage")
            try:
                for i in range(total):
                    t = start + i / fps
                    page.evaluate("t => window.QC.renderAt(t)", t)
                    shot = stage.screenshot(type=fmt, quality=92) if fmt == "jpeg" \
                        else stage.screenshot(type="png")
                    (frames / f"f{i:06d}.{ext}").write_bytes(shot)
                    if i % 60 == 0:
                        print(f"    frame {i}/{total}", end="\r", flush=True)
            finally:
                browser.close()
                shutil.rmtree(tmp, ignore_errors=True)
        print(f"    frame {total}/{total} done      ")

        # ffmpeg's image2 probe fails on a pattern that starts with '%'; keep
        # the literal "f" prefix on both the writer and the reader.
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(fps), "-start_number", "0",
            "-f", "image2", "-i", str(frames / f"f%06d.{ext}"),
            "-ss", str(start), "-i", str(audio), "-t", str(dur),
            "-c:v", "libx264", "-preset", "medium", "-crf", str(V.get("crf", 19)),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ]
        music = resolve(job, "music")
        if music:
            cmd += ["-stream_loop", "-1", "-i", str(music),
                    "-filter_complex",
                    f"[1:a]volume=1[a0];[2:a]volume={V.get('musicGain',0.12)}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first[a]",
                    "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k"]
        cmd += [str(mp4)]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"ffmpeg failed:\n{r.stderr.strip()}")

        # a browser-openable preview, so timing can be checked without a re-encode
        if preview:
            (out / f"{stem}{'--' + slug if multi and slug else ''}_preview.html").write_text(
                build_html(job, theme, cues, dur), encoding="utf-8")
        print(f"  {mp4}  ({mp4.stat().st_size // 1024} KB, "
              f"{W}x{H}, {dur:.1f}s @ {fps}fps)")
    finally:
        shutil.rmtree(frames, ignore_errors=True)


# ---------------------------------------------------------------- transcribe

def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


_PUNCT = str.maketrans({",": "，", "?": "？", "!": "！", ";": "；",
                        ":": "：", "(": "（", ")": "）"})

HARD_STOP = "。！？!?"
SOFT_STOP = "，,、；;：:"


def normalize_zh(s: str) -> str:
    """Whisper emits halfwidth ASCII punctuation for Chinese. Fullwidth reads
    correctly at display sizes and matches how the sentence was spoken."""
    return s.translate(_PUNCT)


def cmd_transcribe(audio: Path, out: Path, model: str, max_chars: int,
                   language: str, max_gap: float) -> None:
    from faster_whisper import WhisperModel

    print(f"  loading whisper '{model}' (first run downloads it)...")
    wm = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=0)
    segs, info = wm.transcribe(
        str(audio), language=language, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
        # This bias is what keeps `language="zh"` from drifting into Traditional
        # output (們/聰/定義 instead of 们/聪/定义). Cheap and very effective.
        initial_prompt="以下是普通话内容，请用简体中文输出。" if language == "zh" else None,
    )

    cues, buf = [], []
    last_end = None

    def flush():
        nonlocal last_end
        if not buf:
            return
        text = normalize_zh("".join(w for w, _, _ in buf)).strip()
        if text:
            cues.append({"start": round(buf[0][1], 3),
                         "end": round(buf[-1][2], 3),
                         "text": text})
        buf.clear()
        last_end = None

    for seg in segs:
        words = seg.words or []
        if not words:
            continue
        for w in words:
            # A pause is a sentence boundary as surely as punctuation is — this
            # is the "break on semantic pauses" rule, and it catches the gaps
            # whisper's own segmentation happily runs across.
            if last_end is not None and w.start - last_end > max_gap:
                flush()
            tok = w.word
            buf.append((tok, w.start, w.end))
            last_end = w.end
            acc = "".join(x[0] for x in buf)
            if any(c in tok for c in HARD_STOP):
                flush()
            elif len(acc) >= max_chars * 0.7:
                # Treat max_chars as a target, not a ceiling: break at the comma
                # once we're near it. Hard-breaking at exactly the cap splits
                # words like 重新/設計 in half, which reads badly on screen.
                if any(c in tok for c in SOFT_STOP) or len(acc) >= max_chars * 1.8:
                    flush()
        flush()
    flush()

    out.write_text(json.dumps(
        {"duration": round(info.duration or 0, 3), "cues": cues},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {out}  ({len(cues)} cues, {info.duration:.1f}s)")


# ------------------------------------------------------------------ templates

TPL_DESC = {
    "editorial":  "杂志排版 · 细线、小标签、破折号署名",
    "boldblock":  "整块主色 · 引文反白出来",
    "split":      "上色块引文 / 下素底署名",
    "marker":     "关键词荧光笔 + 手写下划线，右对齐",
    "gradient":   "柔和网格渐变 · 实色字",
    "photoframe": "上传自己的图 + 遮罩压字",
}


# ---------------------------------------------------------------------- doctor

def cmd_doctor(args) -> None:
    """Check the machine before promising anything.

    The video branch needs whisper and ffmpeg; the still branch only needs a
    browser. Finding that out after the user has already written their copy
    is a waste of their time, so this runs first.
    """
    print("quote-card doctor\n")

    for exe in ("ffmpeg", "ffprobe"):
        p = shutil.which(exe)
        print(f"  {'ok      ' if p else 'MISSING'}  {exe}"
              + (f"   {p}" if p else "   (needed for video)"))

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ver = b.version
            b.close()
        print(f"  ok        playwright chromium {ver}   (needed for every render)")
    except Exception as e:
        print(f"  MISSING   playwright chromium   ({e})")

    try:
        import faster_whisper
        print(f"  ok        faster-whisper {getattr(faster_whisper, '__version__', '?')}"
              "   (needed for video)")
    except Exception as e:
        print(f"  MISSING   faster-whisper   ({e})")

    # Pillow is not optional: the render supersamples at 2x and downsamples
    # back, and the logo check reads the wordmark's pixels.
    try:
        import PIL
        print(f"  ok        pillow {getattr(PIL, '__version__', '?')}"
              "   (needed for every render)")
    except Exception as e:
        print(f"  MISSING   pillow   ({e})")

    # Only real font files count. A README sitting in fonts/ must not make
    # it look like a brand font is installed.
    files = sorted(f for f in (FONT_DIR.glob("*") if FONT_DIR.exists() else [])
                   if f.suffix.lower() in FONT_FMT)
    if files:
        print(f"  ok        fonts/  {len(files)} file(s): "
              + ", ".join(f.name for f in files[:6]))
    else:
        print(f"  WARN      fonts/ has no font file   "
              f"(themes fall back to the next family in the stack)")

    print("\n  static cards need only the browser. videos need ffmpeg + whisper.")


# --------------------------------------------------------------------- gallery

def cmd_gallery(job_path: Path, args) -> None:
    """Every template, one page, so the style can be picked before the copy
    is written. Renders all six and writes a browsable index next to them."""
    base = load_job(job_path)
    out = out_root(base)
    out.mkdir(parents=True, exist_ok=True)
    ratios = ratios_of(base, args)
    stem = base.get("name", "card")
    # An overview is about the templates, not the sizes — one size, so the
    # folder holds six files instead of six times however many sizes.
    one = _first_ratio(args, ratios[0])

    rendered = []
    for tpl in TPL_DESC:
        job = dict(base)
        job["template"] = tpl
        job["_outDir"] = str(out / "stills")
        job["_fileStem"] = tpl
        job.pop("_dir", None)
        job.pop("_base", None)
        tmp = job_path.parent / f"_tmp_gallery_{tpl}.json"
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            cmd_static(tmp, one)
            rendered.append(tpl)
        finally:
            tmp.unlink(missing_ok=True)

    page = out / "gallery.html"
    page.write_text(_gallery_html(stem, rendered, ratios[0]), encoding="utf-8")
    print(f"\n  {page}  (open it in a browser)")


def _first_ratio(args, ratio: str):
    """A copy of the args pinned to one size."""
    a = argparse.Namespace(**vars(args))
    a.ratios = [ratio]
    return a


def _gallery_html(stem: str, tpls: list[str], ratio: str) -> str:
    cells = []
    for t in tpls:
        img = f"stills/{t}.png"
        cells.append(
            f'<figure><a href="{img}" target="_blank"><img src="{img}" loading="lazy"></a>'
            f'<figcaption><b>{t}</b><span>{TPL_DESC.get(t, "")}</span></figcaption></figure>')
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{stem} · 模板总览</title>
<style>
 body{{margin:0;background:#161616;color:#eee;padding:32px;
   font:14px/1.6 "Microsoft YaHei",system-ui,sans-serif}}
 h1{{font-size:19px;margin:0 0 4px}}
 p.sub{{margin:0 0 26px;color:#8f8f8f}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:22px}}
 figure{{margin:0;background:#000;border:1px solid #2e2e2e}}
 figure img{{width:100%;display:block}}
 figcaption{{padding:11px 13px;display:flex;flex-direction:column;gap:3px}}
 figcaption b{{font-size:14px}}
 figcaption span{{color:#8f8f8f;font-size:12px}}
</style></head><body>
<h1>{stem} · 模板总览</h1>
<p class="sub">{ratio} &nbsp;·&nbsp; 点击图片看原图 &nbsp;·&nbsp; 选中一个，把 job 里的
&quot;template&quot; 改成它的名字即可</p>
<div class="grid">{''.join(cells)}</div>
</body></html>"""


# ----------------------------------------------------------------------- check

def _weight(s: str) -> int:
    """A language-neutral length measure.

    A CJK glyph is roughly twice the width of a Latin letter, so counting
    raw characters makes a Chinese quote look four times shorter than an
    English one of the same visual length. Counting a CJK glyph as two
    units puts both on one scale.
    """
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _verdict(lines: int) -> str:
    if lines <= 3:
        return "好 —— 短句，最抓眼"
    if lines <= 5:
        return "可以 —— 中等长度"
    if lines <= 7:
        return "偏长 —— 建议砍到 5 行以内"
    return "太长 —— 这已经是一段话，不是金句卡了"


def cmd_check(job_path: Path, args) -> None:
    """Say out loud whether the copy fits, before a render is waited on.

    The theme picks a starting size and the renderer then shrinks the quote
    if it will not fit. That shrink is invisible until you look at the
    output — this measures it, and says whether the line count reads like a
    quote card or like a paragraph.
    """
    from playwright.sync_api import sync_playwright

    job = load_job(job_path)
    quote = job.get("quote", "")
    print(f"  quote: {len(quote)} chars, {_weight(quote)} units")

    # The logo and the highlighter are the two things a job can ask for and
    # silently not get. Both are checked here, before a render is waited on.
    theme0 = theme_of(job, ratios_of(job, args)[0])
    ground = effective_ground(job, theme0)
    if job.get("logo") or job.get("logoOnDark"):
        note = logo_note(job, theme0, ground)
        which = ("深底用 " + job["logoOnDark"]) if (ground == "dark" and job.get("logoOnDark")) \
            else ("浅底用 " + job["logo"]) if job.get("logo") else ""
        print(f"  logo: {which}"
              + (f"   ! {note}" if note else "   颜色对得上底色"))
        if job.get("logo") and job.get("logoOnDark"):
            other = job["logo"] if ground == "dark" else job["logoOnDark"]
            print(f"         另一版（{'浅底' if ground == 'dark' else '深底'}用）：{other}")
    hit, miss = highlight_report(job)
    if hit or miss:
        print(f"  荧光笔  命中 {len(hit)}/{len(hit) + len(miss)}"
              + (f"：{' · '.join(hit)}" if hit else ""))
        if miss:
            print(f"          没命中（荧光笔不会出现在卡上）：{' · '.join(miss)}")

    for ratio in ratios_of(job, args):
        theme = theme_of(job, ratio)
        W, H = ratio_dims(ratio)
        with sync_playwright() as p:
            browser, ctx, page, tmp = open_page(p, job, theme, None, None, W, H, 1)
            m = page.evaluate(
                "() => {const q=document.getElementById('quote');"
                "if(!q) return null;"
                "const cs=getComputedStyle(q);const size=parseFloat(cs.fontSize);"
                "const lh=parseFloat(cs.lineHeight)||size*1.3;"
                "return {size:size,lines:Math.max(1,Math.round("
                "q.getBoundingClientRect().height/lh))};}")
            browser.close()
            shutil.rmtree(tmp, ignore_errors=True)
        if not m:
            continue
        base = theme["quoteSize"] * theme["quoteScale"]
        shrink = ("" if m["size"] >= base - 0.5
                  else f"  SHRUNK from {base:.0f}px")
        print(f"  {ratio:>5}  {m['size']:.0f}px, {m['lines']} lines"
              f"   {_verdict(m['lines'])}{shrink}")


# -------------------------------------------------------------- video gallery

def cmd_videogallery(job_path: Path, args) -> None:
    """Every template, as a short clip, so the motion can be picked too.

    There are not six stills and six separate video templates — the same
    six templates play back as video, because the motion lives in
    runtime.js and a template only draws. So "which one works as video?"
    is answered by rendering all six over the same seconds of the same
    audio and looking at them side by side.
    """
    base = load_job(job_path)
    audio = resolve(base, "audio")
    if not audio or not audio.exists():
        raise SystemExit("job needs an 'audio' path for video mode")
    cues_path = resolve(base, "cues")
    if not cues_path or not cues_path.exists():
        raise SystemExit("job needs a 'cues' path — run `transcribe` first")
    data = json.loads(cues_path.read_text(encoding="utf-8"))
    cues = data.get("cues", []) if isinstance(data, dict) else data
    cues = [c for c in cues if (c.get("text") or "").strip()]

    V = base.get("video", {}) or {}
    # 3:4 is the default vertical: 9:16 is a very tall frame for a card that
    # is mostly one quote, and the empty space above and below is dead air.
    ratios = getattr(args, "ratios", None) or ["3:4"]
    clip = float(args.clip)
    start = float(V.get("start", 0)) if args.start is None else float(args.start)
    stem = base.get("name", "card")
    out = out_root(base)
    out.mkdir(parents=True, exist_ok=True)
    # One size per overview, same as the still gallery — the point of this
    # page is the motion, not the crop.
    ratio = ratios[0]
    W, H = ratio_dims(ratio)

    for tpl in TPL_DESC:
        job = dict(base)
        job["template"] = tpl
        job["_outDir"] = str(out / "videos")
        job["_fileStem"] = tpl
        V2 = dict(V)
        V2["start"] = start
        V2["end"] = start + clip
        # the runtime reads its own trim offset from job["video"]
        job["video"] = V2
        render_video(job, args, audio, cues, V2, W, H, None, False,
                     ratio, preview=False)

    page = out / "videogallery.html"
    page.write_text(
        _videogallery_html(stem, list(TPL_DESC), ratio, start, clip),
        encoding="utf-8")
    print(f"\n  {page}  (open it in a browser)")


def _videogallery_html(stem: str, tpls: list[str], ratio: str,
                       start: float, clip: float) -> str:
    cells = []
    for t in tpls:
        src = f"videos/{t}.mp4"
        cells.append(
            f'<figure><video src="{src}" controls muted loop playsinline '
            f'preload="metadata"></video>'
            f'<figcaption><b>{t}</b><span>{TPL_DESC.get(t, "")}</span></figcaption></figure>')
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{stem} · 视频模板总览</title>
<style>
 body{{margin:0;background:#161616;color:#eee;padding:32px;
   font:14px/1.6 "Microsoft YaHei",system-ui,sans-serif}}
 h1{{font-size:19px;margin:0 0 4px}}
 p.sub{{margin:0 0 26px;color:#8f8f8f}}
 .bar{{margin:0 0 22px}}
 button{{background:#2b2b33;color:#eee;border:1px solid #3a3a44;
   padding:8px 15px;font:inherit;cursor:pointer}}
 button:hover{{background:#35353f}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:22px}}
 figure{{margin:0;background:#000;border:1px solid #2e2e2e}}
 figure video{{width:100%;display:block;background:#000}}
 figcaption{{padding:11px 13px;display:flex;flex-direction:column;gap:3px}}
 figcaption b{{font-size:14px}}
 figcaption span{{color:#8f8f8f;font-size:12px}}
</style></head><body>
<h1>{stem} · 视频模板总览</h1>
<p class="sub">{ratio} &nbsp;·&nbsp; {start:.1f}s 起 {clip:.0f}s 片段 &nbsp;·&nbsp;
同一段音频的六次渲染，按播放键即可对照 &nbsp;·&nbsp;
选中一个，把 job 里的 &quot;template&quot; 改成它的名字即可</p>
<div class="bar"><button id="all">▶ 同时播放 / 暂停</button></div>
<div class="grid">{''.join(cells)}</div>
<script>
 const vs=[...document.querySelectorAll('video')];
 document.getElementById('all').onclick=()=>{{
   const playing=vs.some(v=>!v.paused);
   vs.forEach((v,i)=>{{
     if(playing){{v.pause();}}
     else{{v.currentTime=0;v.muted=(i>0);v.play();}}
   }});
 }};
</script>
</body></html>"""


# ----------------------------------------------------------------------- fit

def cmd_fit(job_path: Path, args) -> None:
    """Measure the clip's typography before a minute of frames get rendered.

    A quote that will not fit does not error — the type just shrinks, or the
    text spills out of the colour block. This walks every window of lines
    once and says what the renderer will actually do: the size it settles
    on, the tightest window, and the emptiest one.
    """
    from playwright.sync_api import sync_playwright

    job = load_job(job_path)
    audio = resolve(job, "audio")
    if not audio or not audio.exists():
        raise SystemExit("job needs an 'audio' path for video mode")
    cues_path = resolve(job, "cues")
    if not cues_path or not cues_path.exists():
        raise SystemExit("job needs a 'cues' path — run `transcribe` first")
    data = json.loads(cues_path.read_text(encoding="utf-8"))
    cues = data.get("cues", []) if isinstance(data, dict) else data
    cues = [c for c in cues if (c.get("text") or "").strip()]

    V = job.get("video", {}) or {}
    # On video the highlighter has to find the phrase in a spoken line, not
    # in the job's still-card quote.
    hit, miss = highlight_report(job, cues)
    if hit or miss:
        print(f"  荧光笔  命中 {len(hit)}/{len(hit) + len(miss)}"
              + (f"：{' · '.join(hit)}" if hit else ""))
        if miss:
            print(f"          没命中（荧光笔不会出现在屏上）：{' · '.join(miss)}")
    ratios = (getattr(args, "ratios", None) or V.get("ratios")
              or ratios_of(job, args))
    dur = float(V.get("duration") or ffprobe_duration(audio))

    for ratio in ratios:
        W, H = ratio_dims(ratio)
        theme = theme_of(job, ratio)
        if V.get("density"):
            theme["density"] = V["density"]
        if theme.get("bgImage"):
            theme["bgScrim"] = T.scrim_for(theme["bgImage"], theme)

        with sync_playwright() as p:
            browser, ctx, page, tmp = open_page(p, job, theme, cues, dur, W, H, 1)
            m = page.evaluate("() => window.QC.measure()")
            browser.close()
            shutil.rmtree(tmp, ignore_errors=True)
        if not m:
            raise SystemExit("this template has no #quote to measure")

        box = m["boxH"]
        room = box - m["maxUsed"]
        lo_fill = (m["minFull"] / box * 100) if box > 0 else 0
        avg_fill = (m["avgFull"] / box * 100) if box > 0 else 0
        hi_fill = (m["maxUsed"] / box * 100) if box > 0 else 0
        print(f"  {ratio} ({W}×{H})   模板 {job.get('template')}   主题 {job.get('theme')}")
        print(f"  字号   基准 {m['base']:.0f}px → 实际 {m['size']:.1f}px"
              + ("（整支视频一次定死）" if m["mode"] == "stack" else "（句子越多越小）"))
        print(f"  窗口   屏上最多 {m['keep']} 句 / 全片 {m['lines']} 句")
        print(f"  最挤   高 {m['maxUsed']:.0f}px   引文区 {box:.0f}px   余量 {room:.0f}px")
        print(f"  满窗   占引文区 {lo_fill:.0f}% ~ {hi_fill:.0f}%，平均 {avg_fill:.0f}%")
        print(f"  开屏   第一句 {m['firstUsed']:.0f}px（字幕本来就要一句一句堆）")

        if room < 0:
            print("  结论   装不下 —— 已经压到字号下限了，砍文案或调小 keepLines")
        elif m["size"] < m["base"] * 0.85:
            print(f"  结论   装得下，但字号被压过（基准 {m['base']:.0f}px → "
                  f"{m['size']:.0f}px）—— 砍文案能拿回字号")
        elif m["size"] < m["base"] - 0.5:
            print(f"  结论   装得下，字号按画幅定死在 {m['size']:.0f}px，画面填得满 —— 可以开渲")
        elif avg_fill < 45:
            print(f"  结论   装得下，但满屏之后平均只用了 {avg_fill:.0f}% —— "
                  "字号偏小，加大 quoteScale 或让 keepLines 多留几句")
        else:
            print("  结论   装得下，字号全程不变，画面填得满 —— 可以开渲")
        print()


# ----------------------------------------------------------------------- cues

def cmd_cues(job_path: Path, args) -> None:
    """Print the transcript for review.

    Whisper gets口误、语气词 and the like wrong, and those words then sit on
    screen. The cue file is plain JSON — read it, fix it, delete a cue's
    text and it disappears from the subtitles.
    """
    job = load_job(job_path)
    cues_path = resolve(job, "cues")
    if not cues_path or not cues_path.exists():
        raise SystemExit("job needs a 'cues' path — run `transcribe` first")
    data = json.loads(cues_path.read_text(encoding="utf-8"))
    cues = data.get("cues", []) if isinstance(data, dict) else data

    blank = 0
    for i, c in enumerate(cues, 1):
        text = (c.get("text") or "").strip()
        if not text:
            blank += 1
        print(f"  {i:>3}  {c.get('start', 0):>6.2f}  {text}")
    print(f"\n  {cues_path}  ({len(cues)} cues"
          + (f", {blank} empty" if blank else "") + ")")
    if blank:
        print("  empty cues are skipped when rendering — delete them if unwanted")
    print("  edit this file directly, then re-run `video`; no re-transcribe needed")


# ----------------------------------------------------------------------- cli

def main() -> None:
    ap = argparse.ArgumentParser(prog="quote-card", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    dr = sub.add_parser("doctor", help="check ffmpeg / playwright / whisper / fonts")
    dr.set_defaults(_none=True)

    s = sub.add_parser("static", help="render a still card")
    s.add_argument("job")
    s.add_argument("--jpg", action="store_true", help="also write a .jpg")
    s.add_argument("--preview", action="store_true",
                   help="also write a standalone .html you can open in a browser")
    s.add_argument("--ratios", nargs="*", choices=sorted(RATIOS),
                   help="override the job's size(s): 1:1 9:16 ...")

    v = sub.add_parser("video", help="render a synced vertical video")
    v.add_argument("job")
    v.add_argument("--ratios", nargs="*", choices=sorted(RATIOS),
                   help="override the job's size(s): 1:1 9:16 ...")

    b = sub.add_parser("both", help="static + video")
    b.add_argument("job")
    b.add_argument("--jpg", action="store_true")
    b.add_argument("--preview", action="store_true")
    b.add_argument("--ratios", nargs="*", choices=sorted(RATIOS))

    d = sub.add_parser("demo", help="render every template with the same copy")
    d.add_argument("job")
    d.add_argument("--jpg", action="store_true")
    d.add_argument("--only", nargs="*", help="limit to these template names")
    d.add_argument("--ratios", nargs="*", choices=sorted(RATIOS))

    g = sub.add_parser("gallery", help="render every template + a browsable index")
    g.add_argument("job")
    g.add_argument("--jpg", action="store_true")
    g.add_argument("--ratios", nargs="*", choices=sorted(RATIOS))

    vg = sub.add_parser("videogallery",
                        help="render every template as a short clip + a browsable index")
    vg.add_argument("job")
    vg.add_argument("--clip", type=float, default=12.0,
                    help="how many seconds of the clip to show (default 12)")
    vg.add_argument("--start", type=float, default=None,
                    help="where the clip starts (default: the job's video.start)")
    vg.add_argument("--ratios", nargs="*", choices=sorted(RATIOS),
                    help="default 3:4 — the vertical that is not too tall")

    fit = sub.add_parser("fit", help="measure the video's typography before rendering")
    fit.add_argument("job")
    fit.add_argument("--ratios", nargs="*", choices=sorted(RATIOS))

    ck = sub.add_parser("check", help="does the quote fit the card?")
    ck.add_argument("job")
    ck.add_argument("--ratios", nargs="*", choices=sorted(RATIOS))

    cu = sub.add_parser("cues", help="print the transcript for review")
    cu.add_argument("job")

    t = sub.add_parser("transcribe", help="audio -> timed cues")
    t.add_argument("audio")
    t.add_argument("-o", "--out", required=True)
    t.add_argument("--model", default="small",
                   help="tiny|base|small|medium  (default small)")
    t.add_argument("--max-chars", type=int, default=18,
                   help="soft cap per on-screen line (default 18)")
    t.add_argument("--language", default="zh", help="default zh")
    t.add_argument("--max-gap", type=float, default=0.55,
                   help="silence (s) that counts as a sentence break (default 0.55)")

    a = ap.parse_args()
    if a.cmd == "transcribe":
        cmd_transcribe(Path(a.audio), Path(a.out), a.model, a.max_chars, a.language, a.max_gap)
        return
    if a.cmd == "doctor":
        cmd_doctor(a)
        return
    if a.cmd == "cues":
        cmd_cues(Path(a.job), a)
        return
    if a.cmd == "check":
        cmd_check(Path(a.job), a)
        return
    if a.cmd == "gallery":
        cmd_gallery(Path(a.job), a)
        return
    if a.cmd == "videogallery":
        cmd_videogallery(Path(a.job), a)
        return
    if a.cmd == "fit":
        cmd_fit(Path(a.job), a)
        return

    jp = Path(a.job)
    if a.cmd == "demo":
        cmd_demo(jp, a)
        return
    if a.cmd in ("static", "both"):
        cmd_static(jp, a)
    if a.cmd in ("video", "both"):
        cmd_video(jp, a)


if __name__ == "__main__":
    main()