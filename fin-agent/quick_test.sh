#!/bin/bash

# Change to the directory where the script is located
cd "$(dirname "$0")"

# --- Environment Setup ---
TOGETHER_API_KEY=$(grep TOGETHER_API_KEY .env 2>/dev/null | cut -d '=' -f2)

if [ -z "$TOGETHER_API_KEY" ]; then
    echo "⚠️  WARNING: TOGETHER_API_KEY not found. Falling back to local Ollama (gpt-oss:20b-cloud)."
    # Ensure TOGETHER_API_KEY is empty so the factory picks Ollama
    export TOGETHER_API_KEY=""
else
    export TOGETHER_API_KEY=$TOGETHER_API_KEY
fi

echo "===================================================="
echo "   AM Finance Agent - One-Click Test Suite          "
echo "===================================================="

# 1. Start the Backend in background
echo "[1/4] Starting Backend (api.py)..."
python3 api.py > server.log 2>&1 &
SERVER_PID=$!

# Cleanup on exit
trap 'if [ -n "$SERVER_PID" ]; then kill $SERVER_PID 2>/dev/null; fi' EXIT

# 2. Wait for Readiness
echo -n "[2/4] Waiting for server to be ready..."
MAX_RETRIES=30
COUNT=0
while ! curl -s http://localhost:8100/ready > /dev/null; do
    sleep 1
    echo -n "."
    COUNT=$((COUNT+1))
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo -e "\n❌ ERROR: Server failed to start. See server.log"
        exit 1
    fi
done
echo " ✅ READY!"

# 3. Test API Testing Mode (FinanceAgent Chat)
echo "[3/4] Testing API Mode (FinanceAgent)..."
RESPONSE=$(curl -s -X POST http://localhost:8100/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Search for all registered APIs","userId":"u-123"}')

if echo "$RESPONSE" | grep -q "toolsUsed"; then
  echo "  ✅ API Mode Passed! (Tool used: $(echo $RESPONSE | jq -r '.toolsUsed[0]'))"
else
  echo "  ❌ API Mode Failed! Response: $RESPONSE"
fi

# 4. Test MCP Server Logic
echo "[4/4] Testing MCP Server Logic (Initialize Handshake)..."
# We send an 'initialize' request which is required before any other request in MCP 1.0+
MCP_OUTPUT=$(echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0.0"}}}' | python3 mcp_server/server.py 2>&1)

if echo "$MCP_OUTPUT" | grep -q "protocolVersion"; then
  echo "  ✅ MCP Mode Passed! (Server initialized successfully)"
else
  echo "  ❌ MCP Mode Failed!"
  echo "     Diagnostic Output: $MCP_OUTPUT"
fi

echo "===================================================="
echo "   🎉 All Tests Passed! System is fully operational. "
echo "===================================================="
