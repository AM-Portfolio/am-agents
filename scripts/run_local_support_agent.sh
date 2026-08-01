#!/usr/bin/env bash
set -e

export TEMPORAL_HOST=localhost:7233
export TEMPORAL_NAMESPACE=default
export TEMPORAL_TASK_QUEUE=support-agent-v2

echo "Starting local support-agent gateway on port 8091..."
export PYTHONPATH="src:${PYTHONPATH}"
export SUPPORT_AGENT_API_TOKEN=${SUPPORT_AGENT_API_TOKEN:-"dev-token"}
export TOOL_AGENT_BASE_URL=${TOOL_AGENT_BASE_URL:-"http://localhost:8141"}
export SUPPORT_AGENT_GATEWAY_PORT=${SUPPORT_AGENT_GATEWAY_PORT:-"8091"}
export SUPPORT_AGENT_RUNSTORE="memory"
export SUPPORT_AGENT_WORKFLOW_STORE="memory"
export SUPPORT_AGENT_TEMPORAL_ENABLED="true"

# Source root .env if it exists (picks up LiteLLM, Langfuse, LLM provider settings)
if [ -f "../.env" ]; then
    set -a
    source ../.env
    set +a
fi

# These are overridden after .env sourcing so local always wins
export TEMPORAL_HOST=localhost:7233
export TEMPORAL_NAMESPACE=default
export TEMPORAL_TASK_QUEUE=support-agent-v2

echo ""
echo "=== Local Support Agent Config ==="
echo "  LLM Provider:       ${SUPPORT_AGENT_LLM_PROVIDER:-NOT SET}"
echo "  LLM Model:          ${SUPPORT_AGENT_LLM_MODEL:-NOT SET}"
echo "  LLM Enabled:        ${SUPPORT_AGENT_LLM_ENABLED:-NOT SET}"
echo "  Incident Parity:    ${SUPPORT_AGENT_INCIDENT_PARITY:-NOT SET}"
echo "  LiteLLM URL:        ${LITELLM_BASE_URL:-NOT SET}"
echo "  Langfuse Host:      ${LANGFUSE_HOST:-NOT SET}"
echo "  Temporal Host:      ${TEMPORAL_HOST}"
echo "  Task Queue:         ${TEMPORAL_TASK_QUEUE}"
echo ""

# Start local Temporal worker in background
echo "Starting local support-agent Temporal worker..."
python -m am_support_agent.orchestrator.worker_main &
WORKER_PID=$!
trap "kill $WORKER_PID 2>/dev/null || true" EXIT

python -m uvicorn am_support_agent.gateway.app:create_app --factory --host 0.0.0.0 --port 8091 --reload
