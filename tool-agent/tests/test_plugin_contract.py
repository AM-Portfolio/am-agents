from app.config import TOOLS_DIR
from tools._loader import discover_tools


def test_template_not_discovered():
    names = [p.name for p in TOOLS_DIR.iterdir() if p.is_dir()]
    assert "_template" in names
    tools = discover_tools()
    assert all(t.name != "_template" for t in tools)
