#!/usr/bin/env bash
set -e

# Change to support-agent directory
cd "$(dirname "$0")/../support-agent"

echo "Starting local support-agent gateway on port 8091..."
export PYTHONPATH="src:${PYTHONPATH}"
export SUPPORT_AGENT_API_TOKEN=${SUPPORT_AGENT_API_TOKEN:-"dev-token"}
export TOOL_AGENT_BASE_URL=${TOOL_AGENT_BASE_URL:-"http://localhost:8141"}
export SUPPORT_AGENT_GATEWAY_PORT=${SUPPORT_AGENT_GATEWAY_PORT:-"8091"}
export SUPPORT_AGENT_RUNSTORE="memory"
export SUPPORT_AGENT_WORKFLOW_STORE="memory"

# Source root .env if it exists
if [ -f "../.env" ]; then
    set -a
    source ../.env
    set +a
fi

python -m uvicorn am_support_agent.gateway.app:create_app --factory --host 0.0.0.0 --port 8091 --reload
