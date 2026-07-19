import glob
import re

files = glob.glob("/Users/munishm/Desktop/AM/am-agents/tool-agent/tools/*/search/parse_rules.py")
for f in files:
    with open(f, "r") as fh:
        content = fh.read()
    
    # Replace single line signatures
    if "def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:" in content:
        content = content.replace(
            "def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:",
            "def parse_rules(query: str, *, tool_name: str, backend_hint: str | None = None) -> IntentDocument | None:"
        )
        with open(f, "w") as fh:
            fh.write(content)
        print(f"Updated {f}")
    elif "backend_hint" not in content:
        # Check multiline
        if "def parse_rules(" in content:
            # We'll just print it so we can manually fix it
            print(f"Needs manual fix: {f}")
