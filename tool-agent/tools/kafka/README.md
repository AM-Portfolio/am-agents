# Kafka

Preprod cluster: **am-preprod** (`KAFKA_UI_CLUSTER`).

Canonical topic names live in `am-core-services/libraries/am-kafka-lib/.../KafkaTopics.java` and are cataloged in:

- `schema/preprod.yaml` — full topic list + entity aliases
- `prompts/intent.yaml` — NL parsing vocabulary for LLM fallback

## Quick reference (am-analysis / gateway streaming)

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `am-user-watching` | am-gateway | am-analysis orchestrator | Demand-driven stream trigger |
| `am-portfolio-stream` | am-analysis | am-gateway | Live portfolio snapshot to UI |
| `am-portfolio-update` | am-portfolio | am-analysis | Structural holdings ingest |
| `am-stock-price-update` | am-market-data | am-gateway, am-analysis | Live prices |
| `am-trade-update` | am-trade | am-gateway, am-analysis | Trade events |
| `dashboard-*-update` | am-analysis | am-gateway | Dashboard widget streams |

Use `list_topics` when unsure; wrong names like `am-portfolio-events` are aliased to `am-portfolio-update` in parse_rules.
