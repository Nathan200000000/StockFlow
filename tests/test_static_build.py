"""The Vercel build (public/index.html) must stay in sync with the app and engine."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_public_index_is_up_to_date():
    spec = importlib.util.spec_from_file_location("build_static", ROOT / "scripts" / "build_static.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    built = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
    assert built == module.build(), "Run `python scripts/build_static.py` and commit public/index.html"
