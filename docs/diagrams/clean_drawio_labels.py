"""Convert Draw.io HTML labels to plain multiline text (no visible tags)."""
import html
import re
import xml.sax.saxutils as xu
from pathlib import Path

FILE = Path(__file__).parent / "enterprise-agent-ecosystem.drawio"


def to_plain(raw_attr: str) -> str:
    s = html.unescape(raw_attr)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</?(?:b|i|u|font)[^>]*>", "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    lines = [ln.strip() for ln in s.replace("\r", "").split("\n")]
    return "\n".join(lines).strip()


def to_attr(text: str) -> str:
    return xu.escape(text, entities={"\"": "&quot;"}).replace("\n", "&#10;")


def needs_clean(raw: str) -> bool:
    s = html.unescape(raw)
    return bool(re.search(r"<br\s*/?>|</?(?:b|i|u|font)\b|<[^>]+>", s, re.I) or "&lt;" in raw)


def fix_style(style: str, multiline: bool) -> str:
    style = style.replace("html=1", "html=0")
    style = re.sub(r";{2,}", ";", style).strip(";")
    if multiline and "whiteSpace=wrap" not in style:
        style = f"{style};whiteSpace=wrap" if style else "whiteSpace=wrap"
    if "html=0" not in style:
        style = f"{style};html=0" if style else "html=0"
    return style


def main() -> None:
    content = FILE.read_text(encoding="utf-8")
    count = 0

    def repl_value(m: re.Match) -> str:
        nonlocal count
        raw = m.group(1)
        if not needs_clean(raw):
            return m.group(0)
        count += 1
        return f'value="{to_attr(to_plain(raw))}"'

    out = re.sub(r'value="([^"]*)"', repl_value, content)

    def repl_style(m: re.Match) -> str:
        val, style = m.group(1), m.group(2)
        multiline = "&#10;" in val
        if "html=1" in style or (multiline and "whiteSpace=wrap" not in style):
            return f'value="{val}" style="{fix_style(style, multiline)}"'
        return m.group(0)

    out = re.sub(r'value="([^"]*)" style="([^"]*)"', repl_style, out)
    out = out.replace("html=1", "html=0")

    FILE.write_text(out, encoding="utf-8")
    left = len(re.findall(r"&lt;b&gt;|&lt;br&gt;|&lt;i&gt;", out))
    print(f"Cleaned {count} labels; remaining HTML fragments: {left}")


if __name__ == "__main__":
    main()
