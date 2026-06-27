from tools.vault.paths import normalize_vault_path


def test_normalize_strips_apps_data_prefix():
    assert normalize_vault_path("apps/data/preprod/infra/postgres") == "preprod/infra/postgres"


def test_normalize_strips_apps_prefix():
    assert normalize_vault_path("apps/preprod/infra/postgres") == "preprod/infra/postgres"


def test_normalize_strips_data_prefix():
    assert normalize_vault_path("data/preprod/infra/postgres") == "preprod/infra/postgres"
