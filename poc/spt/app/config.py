from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "am-spt-poc"
    app_port: int = 8150
    log_level: str = "INFO"
    root_path: str = ""

    poc_target_url: str = "http://am-analysis.am-apps-dev.svc.cluster.local:8080"
    # Mounted ConfigMaps / local dir of service spt.yaml registrations
    catalog_external_dir: str = "/catalog-external"
    data_dir: str = "/data"
    # Persistence: json | dual | db (default db after cutover; use dual then json to rollback)
    spt_store: str = "db"
    # Empty → SQLite at {data_dir}/spt.db; set postgresql+psycopg://… for cluster
    spt_database_url: str | None = None
    # ACL: when True, mutating APIs require a valid API key (except local UI if key seeded open)
    spt_acl_required: bool = False
    # Bootstrap keys (plaintext, hashed on startup). Format role:name:secret
    # e.g. developer:local-dev:spt_sk_dev_localchange_me
    spt_bootstrap_keys: str = ""
    spt_max_concurrent_runs: int = 3
    spt_run_retention_days: int = 30
    k6_bin: str = "/usr/local/bin/k6"
    default_environment: str = "dev"
    spt_user_id: str = "ssd2658"
    spt_public_base_url: str = "https://am.asrax.in"
    spt_identity_url: str = "http://am-identity.am-apps-dev.svc.cluster.local:8080"
    spt_auth_username: str = "ssd2658@gmail.com"
    spt_auth_password: str | None = None

    # Safety caps (preprod)
    max_vus: int = 50
    max_duration_seconds: int = 600

    # Shared infra (reuse cluster services)
    grafana_public_url: str = "https://grafana.asrax.in"
    grafana_k6_dashboard_uid: str = "spt-load-testing"
    influxdb_url: str = "http://influxdb.infra.svc.cluster.local:8086"
    influxdb_org: str = "am-portfolio"
    influxdb_bucket: str = "load-testing-dev"
    influxdb_token: str | None = None
    minio_endpoint: str = "http://minio.infra.svc.cluster.local:9000"
    minio_bucket: str = "load-testing"
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_public_console_url: str = "https://minio-console.asrax.in"

    # Testkube (optional — falls back to local k6)
    testkube_enabled: bool = False
    testkube_api_url: str = "http://testkube-api-server.load-testing.svc.cluster.local:8088"
    testkube_namespace: str = "load-testing"

    smoke_vus: int = 5
    smoke_duration: str = "30s"

    trace_body_max_bytes: int = 8000
    # Cap full request/response samples stored per run (inspector list)
    trace_max_calls: int = 500
    default_run_profile: str = "load"


settings = Settings()
