"""Render a Mermaid flow file to a PNG.

Mermaid's CLI needs its own Chromium; this machine already has Playwright's
Chromium, so the diagram is rendered inside that instead. Mermaid's JS is
cached next to the script and only fetched once.

    python diagram.py                        # docs/flow.html -> docs/flow.png
    python diagram.py docs/other.html
    python diagram.py docs/other.mmd         # mermaid source also works
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;background:#F7F9FB}
  #host{display:inline-block;padding:28px}
</style></head>
<body><div id="host"></div>
<!-- script content is raw text: <br/> survives as literal markup for
     mermaid, and entities like &lt; are not decoded on the way in. -->
<script type="text/plain" id="src">__SOURCE__</script>
<script>__MERMAID__</script>
<script>
  window.__err = null;
  mermaid.initialize({
    startOnLoad:false, theme:'base', securityLevel:'loose',
    themeVariables:{
      // Chinese first: Century Gothic has no CJK glyphs, so a Chinese-first
      // stack keeps the two scripts looking like one typeface instead of
      // a thin geometric Latin next to a mismatched CJK fallback.
      fontFamily:'"Microsoft YaHei","Segoe UI",system-ui,sans-serif',
      fontSize:'19px',
      primaryColor:'#EDF2F7', primaryTextColor:'#1A202C', primaryBorderColor:'#4A5568',
      secondaryColor:'#F7F9FB', tertiaryColor:'#FFFFFF',
      lineColor:'#4A5568', textColor:'#1A202C',
      clusterBkg:'#FFFFFF', clusterBorder:'#A0AEC0',
      lineWidth:2.5
    },
    flowchart:{ curve:'basis', nodeSpacing:52, rankSpacing:58, padding:20,
                useMaxWidth:false }
  });
  mermaid.render('g', document.getElementById('src').textContent)
    .then(r => {
      document.getElementById('host').innerHTML = r.svg;
      window.__ok = true;
    })
    .catch(e => { window.__err = String(e && e.message || e); window.__ok = true; });
</script></body></html>
"""


def mermaid_js() -> str:
    CACHE.mkdir(exist_ok=True)
    p = CACHE / "mermaid.min.js"
    if not p.exists():
        print("  fetching mermaid.js (once) ...")
        with urllib.request.urlopen(MERMAID_URL, timeout=60) as r:
            p.write_bytes(r.read())
    return p.read_text(encoding="utf-8")


def render(src: Path, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    if src.suffix.lower() in (".html", ".htm"):
        return render_html(src, out)

    source = src.read_text(encoding="utf-8")
    # .format() would choke on the CSS braces, so substitute by hand.
    html = PAGE.replace("__SOURCE__", source).replace("__MERMAID__", mermaid_js())
    tmp = out.parent / f".{out.stem}.html"
    tmp.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 2x so the text stays crisp after the image is scaled down to fit a
        # chat window or an editor pane.
        page = browser.new_page(device_scale_factor=2)
        page.goto(tmp.resolve().as_uri())
        page.wait_for_function("() => window.__ok === true", timeout=30000)
        err = page.evaluate("() => window.__err")
        if err:
            browser.close()
            raise SystemExit(f"mermaid failed: {err}")
        el = page.query_selector("#host svg")
        if el is None:
            browser.close()
            raise SystemExit("no svg produced")
        el.screenshot(path=str(out))
        browser.close()
    tmp.unlink(missing_ok=True)
    report(out)


def render_html(src: Path, out: Path) -> None:
    """Screenshot a hand-built HTML diagram. No mermaid, no layout engine —
    the page is the diagram."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto(src.resolve().as_uri())
        page.wait_for_timeout(300)
        el = page.query_selector(".wrap") or page.query_selector("body")
        el.screenshot(path=str(out))
        browser.close()
    report(out)


def report(out: Path) -> None:
    from PIL import Image
    w, h = Image.open(out).size
    print(f"  {out}  ({out.stat().st_size // 1024} KB, {w}x{h})")


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "docs" / "flow.html"
    dst = src.with_suffix(".png")
    print("quote-card diagram")
    render(src, dst)
