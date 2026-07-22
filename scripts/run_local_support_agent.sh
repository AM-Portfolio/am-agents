#!/usr/bin/env bash
set -e

TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=support-agent-v2

echo "Starting local support-agent gateway on port 8091..."
export PYTHONPATH="src:${PYTHONPATH}"
export SUPPORT_AGENT_API_TOKEN=${SUPPORT_AGENT_API_TOKEN:-"dev-token"}
export TOOL_AGENT_BASE_URL=${TOOL_AGENT_BASE_URL:-"http://localhost:8141"}
export SUPPORT_AGENT_GATEWAY_PORT=${SUPPORT_AGENT_GATEWAY_PORT:-"8091"}
export SUPPORT_AGENT_RUNSTORE="memory"
export SUPPORT_AGENT_WORKFLOW_STORE="memory"
export SUPPORT_AGENT_TEMPORAL_ENABLED="true"

# Source root .env if it exists
if [ -f "../.env" ]; then
    set -a
    source ../.env
    set +a
fi

# Start local Temporal worker in background
echo "Starting local support-agent Temporal worker..."
python -m am_support_agent.orchestrator.worker_main &
WORKER_PID=$!
trap "kill $WORKER_PID 2>/dev/null || true" EXIT

python -m uvicorn am_support_agent.gateway.app:create_app --factory --host 0.0.0.0 --port 8091 --reload
