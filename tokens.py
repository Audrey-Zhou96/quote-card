"""Theme resolution + a couple of readability guards.

A brand palette is the thing the user swaps in later, so everything that could
reasonably be re-skinned lives in one dict and gets validated here rather than
at render time.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

# Token -> what it drives. Anything absent falls back to these.
DEFAULTS = {
    "bg": "#0E0E12",
    "bg2": "#1A1A22",
    "ink": "#F6F4F0",
    "inkSoft": "#9A9AA5",
    "accent": "#FF4D2E",
    "accent2": "#FFC53D",
    "rule": "#2A2A33",
    "quoteFont": "Microsoft YaHei",
    "metaFont": "Microsoft YaHei",
    "quoteWeight": 700,
    "quoteSize": 68,
    "quoteScale": 1,
    "quoteMinSize": 40,
    "quoteTracking": 0,
    "quoteLeading": 1.35,
    "pad": 96,
    # How much of the frame the main colour takes in the split template.
    # A CSS percentage, because the two panes have to add up to the whole card.
    # The main visual colour is the point of the template, so it gets the
    # lion's share; the lower pane only has to carry the attribution.
    "paneQuote": "80%",
    "density": "regular",
    "lang": "zh-CN",
    # --- role colours -------------------------------------------------------
    # "field"  the page ground. "plate" the surface the quote sits on.
    # "onField" ink for text lying directly on the field, "onPlate" ink for
    # text on the plate. Splitting them is what lets one palette serve both
    # a bright ground and a dark panel without the quote going invisible.
    "plate": "transparent",
    "platePad": "0px",
    "plateRadius": "0px",
    "onPlate": None,
    "onPlateSoft": None,
    "onField": None,
    # What the text actually lands on, for templates that paint their own
    # surfaces (boldblock's full-bleed block, split's two panes). Only the
    # contrast check reads these.
    "quoteGround": None,
    "fieldGround": None,
    "inkGround": None,
    # true for templates whose ground is a photo — ground ratios are moot
    "photoGround": False,
    # ink for text sitting on an accent2 wash (the marker template's
    # highlighter). Default: the field colour, which is what a bright
    # highlighter wants.
    "onAccent2": None,
    # gradient template's mesh blobs. Separate from accent/accent2 because
    # those have to stay legible as small marks, while a mesh blob is pure
    # decoration and can be any colour in the family.
    "mesh1": None,
    "mesh2": None,
    # The big quote mark in the top-right corner. Opt-in per job
    # ("showQuoteMark") — the short accent rule is the house style, and the
    # mark is the louder alternative for cards that want to announce
    # themselves.
    "qmarkSize": 150,
    "qmarkOpacity": 0.13,
    "qmarkInset": 70,
    "qmarkFont": 'Georgia,"Times New Roman",serif',
    "qmarkColor": None,
    # The brand logo's box in the top-left corner. The width is the one that
    # matters — a horizontal wordmark is set by its width, and the height cap
    # only stops a tall mark from taking over the corner. Still smaller than
    # the quote, but big enough to read as a brand mark rather than a smudge.
    "logoWidth": 240,
    "logoHeight": 84,
    # One number scales the whole box. Without it, doubling the width alone
    # would run into the height cap and quietly do almost nothing.
    "logoScale": 1,
    # A keyline drawn around the quote glyphs. This is what lets white type
    # sit straight on a bright ground without a panel under it — the outline
    # does the separating, the ground stays one flat colour.
    "quoteStroke": None,
    "quoteStrokeWidth": "0px",
    # A soft shadow under the quote — the cheaper alternative to a keyline.
    "quoteShadow": None,
    # A full-frame background gradient. When set it replaces bg/bg2 as the
    # ground, which is how a card can be one continuous surface instead of a
    # flat colour with a block dropped on it.
    "bgGrad": None,
    # background-image handling
    "bgImage": None,
    "bgFit": "cover",
    "bgPos": "center",
    "bgFilter": "none",
    "bgScrim": "transparent",
    # gradient template's mesh veil. Must lighten on light themes or dark text
    # ends up sitting on a darkened blob.
    "vignette": ("radial-gradient(125% 85% at 50% 42%, rgba(0,0,0,0) 38%, "
                 "rgba(0,0,0,.34) 74%, rgba(0,0,0,.66) 100%)"),
}

NUMERIC = {"quoteWeight", "quoteSize", "quoteMinSize",
           "quoteTracking", "quoteLeading", "pad",
           "qmarkSize", "qmarkInset", "logoWidth", "logoHeight"}
# quoteScale is a multiplier, not a pixel value — int() would collapse
# 0.75 to 0 and 1.3 to 1, silently discarding the whole adjustment.
FLOATS = {"quoteScale", "qmarkOpacity", "logoScale"}


def load_theme(theme: str | None, overrides: dict | None = None,
               template: str | None = None) -> dict:
    """Merge order: defaults < themes/<name>.json < theme's per-template block
    < job's theme block.

    The per-template block exists because the same palette has to work in
    templates that paint the ground differently (boldblock's full-bleed
    block, editorial's flat page). It is a flat dict of token overrides.
    """
    t = dict(DEFAULTS)
    tpl_over: dict = {}
    if theme:
        p = HERE / "themes" / f"{theme}.json"
        if not p.exists():
            raise SystemExit(f"theme not found: {p}")
        raw = json.loads(p.read_text(encoding="utf-8"))
        tpl_over = raw.pop("overrides", {}) or {}
        t.update(raw)
    if template and template in tpl_over:
        t.update(tpl_over[template])
    if overrides:
        t.update(overrides)

    for k in NUMERIC:
        if k in t:
            t[k] = int(t[k])
    for k in FLOATS:
        if k in t:
            t[k] = float(t[k])

    # The logo scale multiplies the box, so one number moves both edges.
    if t.get("logoScale", 1) != 1:
        t["logoWidth"] = round(t["logoWidth"] * t["logoScale"])
        t["logoHeight"] = round(t["logoHeight"] * t["logoScale"])

    # Resolve the role inks now, so runtime.js never sees a null. The plate
    # ink defaults to the body ink; the field ink likewise.
    t["onPlate"] = t["onPlate"] or t["ink"]
    t["onPlateSoft"] = t["onPlateSoft"] or t["inkSoft"]
    t["onField"] = t["onField"] or t["ink"]
    t["onAccent2"] = t["onAccent2"] or t["bg"]
    t["mesh1"] = t["mesh1"] or t["accent"]
    t["mesh2"] = t["mesh2"] or t["accent2"]
    return t


# --------------------------------------------------------------- colour maths

def _hex(c: str) -> tuple[int, int, int]:
    c = (c or "").strip()
    if c.lower().startswith("rgba"):
        # alpha doesn't change the hue, and contrast maths wants a solid
        # colour — a translucent plate is judged by the colour under it.
        nums = c[c.index("(") + 1:c.index(")")].split(",")
        return tuple(int(float(n)) for n in nums[:3])
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lin(v: float) -> float:
    v /= 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(c: str) -> float:
    r, g, b = _hex(c)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def perceptual_luma(c: str) -> float:
    """Gamma-encoded luminance, 0..1.

    The linearised `luminance` is the right number for a contrast ratio.
    This one is the right number for "is this thing light or dark" — the
    same scale you get by averaging the pixels of a logo, so a wordmark
    and the card behind it can be compared without converting either.
    """
    r, g, b = _hex(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def is_dark_ground(col: str) -> bool:
    """Is this ground dark enough to want a light logo on it?

    A plain brightness test gets saturated colours wrong: a bright orange
    (#FF4D2E) looks bright but still reads far better under a dark logo
    than a white one. So the test is the one that actually matters —
    which ink has more contrast against the ground.
    """
    try:
        return contrast(col, "#FFFFFF") > contrast(col, "#000000")
    except Exception:
        return True


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _opaque(color: str) -> bool:
    """True when the colour will actually cover what's behind it."""
    c = (color or "").strip().lower()
    return c not in ("", "transparent", "none", "inherit")


def audit(theme: dict) -> list[str]:
    """Cheap legibility check. Brand palettes break these rules more often
    than you'd think, and the failure is unreadable cards, not an error.

    The trick is knowing what the text actually lands on. Most templates put
    the quote straight on the page ground, but boldblock paints a full-bleed
    block and split splits the page in two — so a template can declare its
    own grounds and the check follows the paint instead of guessing.

    The accent is deliberately not checked: its job differs per template
    (stage fill, progress bar, kicker text, underline), and no single ground
    is right for all of them.
    """
    out = []
    plate = theme.get("plate", "transparent")
    has_plate = _opaque(plate)

    quote_ground = theme.get("quoteGround")
    field_ground = theme.get("fieldGround")
    ink_ground = theme.get("inkGround") or field_ground
    quote_on = plate if has_plate else (quote_ground or theme["bg"])
    field_on = field_ground or theme["bg"]

    # Over a photo the scrim and the text shadow do the work, so ground
    # ratios say nothing useful.
    on_photo = bool(theme.get("bgImage")) or bool(theme.get("photoGround"))

    pairs = []
    if not on_photo:
        # Over a photo the scrim and the text shadow do the work, so ground
        # ratios say nothing useful — there is no ground to measure against.
        pairs.append(("quote text", theme["onPlate"], quote_on, 4.5))
        pairs += [
            ("field text", theme["onField"], field_on, 4.5),
            ("muted meta text", theme["inkSoft"], field_on, 3.0),
        ]
        if ink_ground:
            # `ink` is the generic body ink. Only worth checking where a
            # template actually puts it on something — if it merely repeats
            # the plate or field ink it is never painted on its own.
            if theme["ink"] not in (theme["onPlate"], theme["onField"]):
                pairs.append(("body text", theme["ink"], ink_ground, 4.5))
        if not has_plate and not quote_ground:
            # The quote lands on the page ground, so the alt ground matters too.
            pairs.append(("quote text / alt bg", theme["onPlate"], theme["bg2"], 4.5))
    pairs.append(("highlighter text", theme["onAccent2"], theme["accent2"], 4.5))

    # A dark vignette on a light ground is the same failure as dark text on
    # a bright block: the corners go muddy. Light grounds want a light veil.
    vig = (theme.get("vignette") or "").lower()
    dark_vig = "rgba(0,0,0" in vig or "#000" in vig
    if dark_vig and luminance(theme["bg"]) > 0.35:
        out.append("vignette: darkens a light ground - use a white veil "
                   "instead (rgba(255,255,255,..))")

    # A keyline or a shadow under the glyphs is what separates white type from
    # a bright ground, so the plain colour ratio stops being the whole story.
    # Report it, but don't shout about it the way a real failure deserves.
    assisted = bool(theme.get("quoteStroke")) or bool(theme.get("quoteShadow"))

    for name, fg, bgc, minr in pairs:
        try:
            r = contrast(fg, bgc)
        except Exception:
            out.append(f"{name}: could not parse {fg} / {bgc}")
            continue
        if r >= minr:
            continue
        if assisted and name.startswith("quote text"):
            out.append(f"note: {name}: contrast {r:.2f} on {fg} over {bgc} "
                       f"- separated by the keyline/shadow, not by colour")
        else:
            out.append(f"{name}: contrast {r:.2f} on {fg} over {bgc} - below {minr}")
    return out


def scrim_for(bg_image: str | None, theme: dict) -> str:
    """A gradient veil that keeps text readable over an arbitrary photo.

    The veil has to be the colour the text ISN'T. A bright brand ground
    (a lime, a cyan) makes a terrible veil — it tints the whole photo into
    its own hue and hides the picture the user chose. So the veil is the
    darker of the ground and the body ink, and a neutral black if even
    that is too bright to carry white type.
    """
    if not bg_image:
        return theme["bgScrim"]
    dark = theme["bg"] if luminance(theme["bg"]) < luminance(theme["ink"]) else theme["ink"]
    if luminance(dark) > 0.35:
        dark = "#101014"
    return f"linear-gradient(180deg, {dark}00 0%, {dark}CC 55%, {dark}F2 100%)"