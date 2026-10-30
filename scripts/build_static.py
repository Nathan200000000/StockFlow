"""Build public/index.html: the floor app with the in-browser engine, for static hosting (Vercel).

Usage:  python scripts/build_static.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "static" / "dashboard.html"
ENGINE = ROOT / "web" / "floor-engine.js"
OUT = ROOT / "public" / "index.html"
MARKER = "<script>\n/* ====================================================================="


def build() -> str:
    html = APP.read_text(encoding="utf-8")
    if MARKER not in html:
        raise SystemExit("Could not find the app script marker in dashboard.html")
    engine = ENGINE.read_text(encoding="utf-8")
    return html.replace(MARKER, "<script>\n" + engine + "\n</script>\n" + MARKER, 1)


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
