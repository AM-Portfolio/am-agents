#!/usr/bin/env bash
set -e

# Change to tool-agent directory
cd "$(dirname "$0")/.."

echo "Fetching credentials from Kubernetes (infra namespace)..."
KUBECONFIG=${KUBECONFIG:-"/Users/munishm/Desktop/AM/kubeconfig.bin"}
export KUBECONFIG

PG_PASS=$(kubectl get secret postgresql-secret -n infra -o jsonpath='{.data.password}' | base64 -d)
MONGO_PASS=$(kubectl get secret mongodb-secret -n infra -o jsonpath='{.data.password}' | base64 -d)
REDIS_PASS=$(kubectl get secret redis-secret -n infra -o jsonpath='{.data.password}' | base64 -d)
KAFKA_PASS=$(kubectl get secret kafka-secret -n infra -o jsonpath='{.data.password}' | base64 -d)

echo "Starting port-forwards in the background..."

# Arrays to keep track of background PIDs
PIDS=()

cleanup() {
    echo "Stopping port-forwards..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo "Done."
}

trap cleanup EXIT

kubectl port-forward -n infra svc/postgresql 5433:5432 &
PIDS+=($!)
kubectl port-forward -n infra svc/mongo 27017:27017 &
PIDS+=($!)
kubectl port-forward -n infra svc/redis 6379:6379 &
PIDS+=($!)
kubectl port-forward -n infra svc/kafka 9092:9092 &
PIDS+=($!)
kubectl port-forward -n am-ai svc/qdrant 6333:6333 &
PIDS+=($!)
kubectl port-forward -n kagent svc/kagent-grafana-mcp 8000:8000 &
PIDS+=($!)
kubectl port-forward -n kagent svc/kagent-vault-mcp 8180:8080 &
PIDS+=($!)
kubectl port-forward -n am-apps-dev svc/am-mcp-gateway 8120:8120 &
PIDS+=($!)

echo "Waiting for port-forwards to initialize (5s)..."
sleep 5

export POSTGRES_URL="postgresql://postgres:${PG_PASS}@localhost:5433/postgres"
export MONGODB_URI="mongodb://admin:${MONGO_PASS}@localhost:27017/"
export REDIS_URL="redis://:${REDIS_PASS}@localhost:6379/"
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export KAFKA_USERNAME="kafkaUser"
export KAFKA_PASSWORD="${KAFKA_PASS}"
export KAFKA_SECURITY_PROTOCOL="SASL_PLAINTEXT"
export KAFKA_SASL_MECHANISM="SCRAM-SHA-256"
export QDRANT_URL="http://localhost:6333"
export GRAFANA_MCP_URL="http://localhost:8000/mcp"
export VAULT_MCP_URL="http://localhost:8180/mcp"
export MCP_GATEWAY_BASE_URL="http://localhost:8120"
export APP_ENV="local"

# Source the root .env file to get any required API keys (Together, OpenRouter, OpenProject, etc)
if [ -f "../.env" ]; then
    set -a
    source ../.env
    set +a
fi
export LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY:-$TOGETHER_API_KEY}
export LITELLM_BASE_URL=${LITELLM_BASE_URL:-"https://api.together.xyz/v1"}
export LLM_PLANNER_MODEL=${LLM_PLANNER_MODEL:-"Prism-ML/Ternary-Bonsai-27B"}
# Force local tool agent settings
export LLM_ROUTING="direct"

echo "Starting local tool-agent server on port 8141..."
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8141 --reload
