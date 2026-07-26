#!/usr/bin/env bash
# run_local_with_llm.sh — starts all port-forwards and the support-agent worker
# with real LLM + Langfuse tracing enabled.
#
# Usage: bash scripts/run_local_with_llm.sh
# From:  am-agents/ root directory
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KUBECONFIG="$AGENTS_DIR/kubeconfig.bin"

echo "=== Cleaning up stale port-forwards ==="
pkill -f "kubectl.*port-forward" 2>/dev/null || true
sleep 2

echo "=== Finding Temporal frontend pod ==="
TEMPORAL_POD=$(kubectl --kubeconfig="$KUBECONFIG" get pods -n temporal \
  -l app.kubernetes.io/component=frontend \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
echo "  Temporal pod: $TEMPORAL_POD"

echo "=== Starting port-forwards ==="
# Use pod-level forward for Temporal gRPC stability (service-level drops on connection reset)
kubectl --kubeconfig="$KUBECONFIG" port-forward -n temporal pod/$TEMPORAL_POD 7233:7233 &
PF_TEMPORAL=$!
kubectl --kubeconfig="$KUBECONFIG" port-forward -n am-ai svc/litellm 4000:4000 &
PF_LITELLM=$!
kubectl --kubeconfig="$KUBECONFIG" port-forward -n am-ai svc/langfuse-web 3001:3000 &
PF_LANGFUSE=$!

trap "echo 'Shutting down...'; kill $PF_TEMPORAL $PF_LITELLM $PF_LANGFUSE $WORKER_PID 2>/dev/null || true" EXIT

sleep 5

echo ""
echo "=== Port health ==="
echo -n "  LiteLLM  4000: "; curl -s -o /dev/null -w '%{http_code}' http://localhost:4000/health; echo ""
echo -n "  Langfuse 3001: "; curl -s -o /dev/null -w '%{http_code}' http://localhost:3001; echo ""
echo "  Temporal 7233: gRPC (tested via Python SDK)"

echo ""
echo "=== Loading env from $AGENTS_DIR/.env ==="
set -a
source "$AGENTS_DIR/.env"
set +a

# Local overrides always win
export TEMPORAL_HOST=localhost:7233
export TEMPORAL_NAMESPACE=default
export TEMPORAL_TASK_QUEUE=support-agent-v2
export PYTHONPATH="$AGENTS_DIR/support-agent/src:${PYTHONPATH}"
export SUPPORT_AGENT_RUNSTORE=memory
export SUPPORT_AGENT_WORKFLOW_STORE=memory
export SUPPORT_AGENT_TEMPORAL_ENABLED=true
export SUPPORT_AGENT_RUNTIME_MODE=dev
export SUPPORT_AGENT_API_TOKEN=${SUPPORT_AGENT_API_TOKEN:-"dev-token"}
export SUPPORT_AGENT_GATEWAY_PORT=8091

echo ""
echo "=== Support Agent LLM Config ==="
echo "  LLM Provider:    ${SUPPORT_AGENT_LLM_PROVIDER}"
echo "  LLM Model:       ${SUPPORT_AGENT_LLM_MODEL}"
echo "  LLM Enabled:     ${SUPPORT_AGENT_LLM_ENABLED}"
echo "  Incident Parity: ${SUPPORT_AGENT_INCIDENT_PARITY}"
echo "  LiteLLM URL:     ${LITELLM_BASE_URL}"
echo "  Langfuse Host:   ${LANGFUSE_HOST}"
echo "  Langfuse Key:    ${LANGFUSE_PUBLIC_KEY:0:20}..."
echo ""

cd "$AGENTS_DIR/support-agent"

echo "=== Starting Temporal worker (background) ==="
python -m am_support_agent.orchestrator.worker_main &
WORKER_PID=$!
sleep 4

if kill -0 $WORKER_PID 2>/dev/null; then
  echo "  Worker PID $WORKER_PID — RUNNING ✅"
else
  echo "  Worker FAILED to start ❌ - check logs above"
  exit 1
fi

echo ""
echo "=== All ready! ==="
echo "  • Temporal:  localhost:7233 (gRPC)"
echo "  • LiteLLM:   http://localhost:4000"
echo "  • Langfuse:  http://localhost:3001  ← see LLM traces here!"
echo "  • Gateway:   http://localhost:8091  (starting now)"
echo ""

python -m uvicorn am_support_agent.gateway.app:create_app --factory --host 0.0.0.0 --port 8091 --reload
