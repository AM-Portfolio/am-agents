"""Rebuild enterprise-agent-ecosystem.drawio with unique per-page IDs."""
import re
from collections import Counter
from pathlib import Path

FILE = Path(__file__).parent / "enterprise-agent-ecosystem.drawio"
ROOT = {"0", "1"}


def page_prefix(block: str) -> str:
    m = re.search(r'<diagram id="([^"]+)"', block)
    return re.sub(r"[^a-zA-Z0-9_]", "_", m.group(1)).strip("_") + "_" if m else "p_"


def strip_prefix(raw: str, prefix: str) -> str:
    while raw.startswith(prefix):
        raw = raw[len(prefix):]
    return raw


def normalize_diagram(block: str) -> str:
    prefix = page_prefix(block)

    # Strip existing page prefix from all ids so we only apply once
    raw_ids = []
    for m in re.finditer(r'<mxCell id="([^"]+)"', block):
        raw_ids.append(strip_prefix(m.group(1), prefix))

    # Master page: disambiguate lifecycle Test vs L4 layer before prefixing
    if prefix == "enterprise_master_":
        seen_l4 = 0
        fixed_raw = []
        for raw in raw_ids:
            if raw == "l4":
                seen_l4 += 1
                fixed_raw.append("ltest" if seen_l4 == 1 else "l4lane")
            else:
                fixed_raw.append(raw)
        raw_ids = fixed_raw

    counts = Counter(raw_ids)
    occ: dict[str, int] = {}
    new_ids: list[str] = []
    for raw in raw_ids:
        if raw in ROOT:
            new_ids.append(raw)
            continue
        n = occ.get(raw, 0)
        occ[raw] = n + 1
        new_ids.append(prefix + raw if n == 0 else f"{prefix}{raw}_{n + 1}")

    ref: dict[str, str] = {}
    occ2: dict[str, int] = {}
    for raw in raw_ids:
        if raw in ROOT:
            ref[raw] = raw
        elif raw not in ref:
            n = occ2.get(raw, 0)
            ref[raw] = prefix + raw if n == 0 else f"{prefix}{raw}_{n + 1}"
            occ2[raw] = occ2.get(raw, 0) + 1

    i = 0

    def repl_id(m: re.Match) -> str:
        nonlocal i
        out = f'<mxCell id="{new_ids[i]}"'
        i += 1
        return out

    out = re.sub(r'<mxCell id="([^"]+)"', repl_id, block)

    def remap(v: str) -> str:
        if v in ROOT:
            return v
        return ref.get(strip_prefix(v, prefix), prefix + strip_prefix(v, prefix))

    out = re.sub(r'parent="([^"]+)"', lambda m: f'parent="{remap(m.group(1))}"', out)
    out = re.sub(r'source="([^"]+)"', lambda m: f'source="{remap(m.group(1))}"', out)
    out = re.sub(r'target="([^"]+)"', lambda m: f'target="{remap(m.group(1))}"', out)
    return out


def audit(content: str) -> bool:
    ok = True
    all_ids: list[str] = []
    for d in re.findall(r"<diagram\b[^>]*>.*?</diagram>", content, re.DOTALL):
        name = re.search(r'name="([^"]+)"', d).group(1)
        ids = re.findall(r'<mxCell id="([^"]+)"', d)
        loc = {k: v for k, v in Counter(ids).items() if v > 1 and k not in ROOT}
        if loc:
            print(f"FAIL local {name}: {loc}")
            ok = False
        all_ids.extend(ids)
    g = {k: v for k, v in Counter(all_ids).items() if v > 1 and k not in ROOT}
    if g:
        print(f"FAIL global: {g}")
        ok = False
    if ok:
        print("OK: all IDs unique")
    return ok


def main() -> None:
    content = FILE.read_text(encoding="utf-8")
    header = re.match(r"<mxfile[^>]*>", content).group(0)
    diagrams = re.findall(r"<diagram\b[^>]*>.*?</diagram>", content, re.DOTALL)
    fixed = [normalize_diagram(d) for d in diagrams]
    out = header + "\n" + "\n".join(fixed) + "\n</mxfile>\n"
    audit(out)
    FILE.write_text(out, encoding="utf-8")
    print(f"Rebuilt {len(fixed)} pages -> {FILE.name}")


if __name__ == "__main__":
    main()
