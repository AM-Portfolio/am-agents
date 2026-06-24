# AM UI Test Agent — Documentation

Canonical specifications live in **am-platform**:

| Document | Path |
|----------|------|
| **Doc index** | [../../am-platform/docs/ui-agent-ai-testing/README.md](../../am-platform/docs/ui-agent-ai-testing/README.md) |
| Agent design | [../../am-platform/docs/ui-agent-ai-testing/AM_UI_TEST_AGENT_DESIGN.md](../../am-platform/docs/ui-agent-ai-testing/AM_UI_TEST_AGENT_DESIGN.md) |
| Hybrid design review | [../../am-platform/docs/ui-agent-ai-testing/DESIGN_REVIEW_HYBRID.md](../../am-platform/docs/ui-agent-ai-testing/DESIGN_REVIEW_HYBRID.md) |
| Weekly release ops | [../../am-platform/docs/ui-agent-ai-testing/OPERATIONS_WEEKLY_UI_RELEASE.md](../../am-platform/docs/ui-agent-ai-testing/OPERATIONS_WEEKLY_UI_RELEASE.md) |
| Implementation status | [../../am-platform/docs/ui-agent-ai-testing/IMPLEMENTATION_STATUS.md](../../am-platform/docs/ui-agent-ai-testing/IMPLEMENTATION_STATUS.md) |

## Quick start

```powershell
# Terminal 1
cd am-ui-test-agent && npm run preprod

# Terminal 2
cd am-modern-ui && npm run test:auth:preprod
```

Reports: `../../reports/ui-test/{testId}.html`
