from pathlib import Path

from app.prompts.provider import FilePromptProvider, compile_prompt


def test_file_prompt_provider_base():
    provider = FilePromptProvider()
    base_path = Path(__file__).resolve().parents[1] / "app" / "prompts" / "base.yaml"
    template = provider.get("tool-agent/intent/base", label="latest", fallback_path=base_path)
    assert "JSON" in template.content
    assert template.source == "file"


def test_compile_prompt_variables():
    out = compile_prompt("Hello {{name}} ops={{operations_list}}", {"name": "world", "operations_list": "mongo"})
    assert "Hello world" in out
    assert "mongo" in out
