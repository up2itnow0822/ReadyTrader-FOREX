"""docs/TOOLS.md is what the running server registers (regenerate with tools/generate_tool_docs.py)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("generate_tool_docs", ROOT / "tools" / "generate_tool_docs.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_tools_md_matches_the_registered_tools():
    assert (ROOT / "docs" / "TOOLS.md").read_text() == gen.render(), "run: python tools/generate_tool_docs.py"


def test_every_tool_the_readme_names_is_registered():
    import re

    registered = {t["name"] for t in gen._registered_tools()}
    readme = (ROOT / "README.md").read_text()
    named = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)\(", readme)) | set(re.findall(r"\| `([a-z]+(?:_[a-z]+)+)`", readme))
    code_names = {"on_candle"}
    assert named - registered - code_names == set()
