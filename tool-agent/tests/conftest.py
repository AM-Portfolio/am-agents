import pytest


@pytest.fixture(autouse=True)
def _reset_singletons():
    from app.registry import reset_registry
    from app.schema.loader import reset_schema_catalog
    from tools._loader import clear_tool_cache

    clear_tool_cache()
    reset_registry()
    reset_schema_catalog()
    yield
    clear_tool_cache()
    reset_registry()
    reset_schema_catalog()
