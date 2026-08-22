#!/usr/bin/env python3
"""Generate 02-ai-gateway-mcp-design.drawio with clear vertical/horizontal flows."""

from pathlib import Path

OUT = Path(__file__).parent / "02-ai-gateway-mcp-design.drawio"

STYLE = {
    "title": "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=20;fontStyle=1;fontColor=#0F172A;",
    "lane": "swimlane;horizontal=1;startSize=30;fillColor={bg};strokeColor={stroke};fontColor={fg};fontStyle=1;rounded=1;",
    "box_blue": "rounded=1;whiteSpace=wrap;html=1;fillColor=#0284C7;fontColor=#FFFFFF;strokeColor=#0369A1;fontSize=12;",
    "box_indigo": "rounded=1;whiteSpace=wrap;html=1;fillColor=#4F46E5;fontColor=#FFFFFF;strokeColor=#312E81;fontSize=12;",
    "box_purple": "rounded=1;whiteSpace=wrap;html=1;fillColor=#7C3AED;fontColor=#FFFFFF;strokeColor=#6D28D9;fontSize=12;",
    "box_pink": "rounded=1;whiteSpace=wrap;html=1;fillColor=#DB2777;fontColor=#FFFFFF;strokeColor=#BE185D;fontSize=12;",
    "box_teal": "rounded=1;whiteSpace=wrap;html=1;fillColor=#0D9488;fontColor=#FFFFFF;strokeColor=#0F766E;fontSize=12;",
    "box_gray": "rounded=1;whiteSpace=wrap;html=1;fillColor=#64748B;fontColor=#FFFFFF;strokeColor=#475569;fontSize=12;",
    "box_sky": "rounded=1;whiteSpace=wrap;html=1;fillColor=#0EA5E9;fontColor=#FFFFFF;strokeColor=#0284C7;fontSize=12;",
    "box_orange": "rounded=1;whiteSpace=wrap;html=1;fillColor=#F59E0B;fontColor=#FFFFFF;strokeColor=#D97706;fontSize=12;",
    "box_green": "rounded=1;whiteSpace=wrap;html=1;fillColor=#059669;fontColor=#FFFFFF;strokeColor=#047857;fontSize=12;",
    "box_violet": "rounded=1;whiteSpace=wrap;html=1;fillColor=#6366F1;fontColor=#FFFFFF;strokeColor=#4F46E5;fontSize=12;",
    "box_planned": "rounded=1;whiteSpace=wrap;html=1;fillColor=#EDE9FE;fontColor=#5B21B6;strokeColor=#7C3AED;dashed=1;dashPattern=8 4;fontSize=11;",
    "note": "text;html=1;strokeColor=#CBD5E1;fillColor=#FFFFFF;align=left;verticalAlign=top;spacingLeft=10;spacingTop=8;fontColor=#0F172A;rounded=1;fontSize=11;",
    "arrow": "edgeStyle=orthogonalEdgeStyle;rounded=0;strokeColor=#334155;strokeWidth=2;endArrow=classic;html=1;",
    "arrow_blue": "edgeStyle=orthogonalEdgeStyle;rounded=0;strokeColor=#0284C7;strokeWidth=2;endArrow=classic;html=1;fontColor=#0369A1;",
    "arrow_dash": "edgeStyle=orthogonalEdgeStyle;rounded=0;strokeColor=#6366F1;strokeWidth=2;endArrow=classic;dashed=1;html=1;fontColor=#4338CA;",
    "arrow_down": "edgeStyle=orthogonalEdgeStyle;rounded=0;strokeColor=#334155;strokeWidth=3;endArrow=block;endFill=1;html=1;",
}


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "&#xa;")
    )


class Diagram:
    def __init__(self, diagram_id: str, name: str, width: int = 1200, height: int = 900):
        self.diagram_id = diagram_id
        self.name = name
        self.width = width
        self.height = height
        self.cells: list[str] = []
        self._n = 0

    def uid(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def cell(self, cid: str, value: str, style: str, x: int, y: int, w: int, h: int, parent: str = "1") -> str:
        self.cells.append(
            f'                <mxCell id="{cid}" value="{esc(value)}" style="{style}" parent="{parent}" vertex="1">\n'
            f'                    <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>\n'
            f"                </mxCell>"
        )
        return cid

    def lane(self, cid: str, label: str, bg: str, stroke: str, fg: str, x: int, y: int, w: int, h: int) -> str:
        style = STYLE["lane"].format(bg=bg, stroke=stroke, fg=fg)
        return self.cell(cid, label, style, x, y, w, h)

    def edge(self, eid: str, source: str, target: str, label: str = "", style: str | None = None, parent: str = "1") -> None:
        style = style or STYLE["arrow"]
        label_attr = f' value="{esc(label)}"' if label else ""
        self.cells.append(
            f'                <mxCell id="{eid}"{label_attr} style="{style}" parent="{parent}" source="{source}" target="{target}" edge="1">\n'
            f'                    <mxGeometry relative="1" as="geometry"/>\n'
            f"                </mxCell>"
        )

    def edge_points(self, eid: str, source: str, target: str, points: list[tuple[int, int]], label: str = "", style: str | None = None) -> None:
        style = style or STYLE["arrow"]
        label_attr = f' value="{esc(label)}"' if label else ""
        pts = "\n".join(f'                            <mxPoint x="{x}" y="{y}"/>' for x, y in points)
        self.cells.append(
            f'                <mxCell id="{eid}"{label_attr} style="{style}" parent="1" source="{source}" target="{target}" edge="1">\n'
            f"                    <mxGeometry relative=\"1\" as=\"geometry\">\n"
            f"                        <Array as=\"points\">\n{pts}\n"
            f"                        </Array>\n"
            f"                    </mxGeometry>\n"
            f"                </mxCell>"
        )

    def render(self) -> str:
        body = "\n".join(self.cells)
        return f"""    <diagram id="{self.diagram_id}" name="{esc(self.name)}">
        <mxGraphModel dx="1100" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.width}" pageHeight="{self.height}" background="#ffffff" math="0" shadow="0">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
{body}
            </root>
        </mxGraphModel>
    </diagram>"""


def build_target_architecture() -> Diagram:
    d = Diagram("target-architecture", "1 - Target Architecture", 1200, 1300)

    d.cell("p1_title", "AI Gateway + MCP — Target Architecture", STYLE["title"], 150, 20, 900, 40)
    d.cell(
        "p1_sub",
        "Whiteboard vision implemented via am-platform/am-mcp-gateway (L2) routing am-agents (L3) to MCP core services (L4)",
        "text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=12;fontColor=#64748B;",
        80,
        55,
        1040,
        30,
    )

    # L1
    l1 = d.lane("p1_l1", "L1 — Client Surfaces (UI · IDE · Mobile)", "#EEF2FF", "#4F46E5", "#312E81", 40, 100, 1120, 110)
    ui = d.cell("p1_ui", "Web UI\nam-modern-ui\nAI Chat · Widgets", STYLE["box_indigo"], 60, 45, 180, 55, l1)
    ide = d.cell("p1_ide", "IDE\nCursor / VS Code\nMCP tools", STYLE["box_indigo"], 270, 45, 160, 55, l1)
    mob = d.cell("p1_mob", "Mobile\n(future)\nSame API", STYLE["box_planned"], 460, 45, 130, 55, l1)
    pb = d.cell("p1_pb", "Portal B\nai-bots React\nWorkspace", STYLE["box_green"], 620, 45, 160, 55, l1)
    pc = d.cell("p1_pc", "Portal C\nkagent UI\nSRE ops", "rounded=1;whiteSpace=wrap;html=1;fillColor=#EA580C;fontColor=#FFFFFF;strokeColor=#C2410C;fontSize=12;", 810, 45, 140, 55, l1)

    # Auth strip
    lauth = d.lane("p1_auth", "Auth & Security — Keycloak JWT · RBAC · Guardrails", "#F1F5F9", "#64748B", "#0F172A", 40, 230, 1120, 80)
    kc = d.cell("p1_kc", "Keycloak\nJWT + roles", STYLE["box_gray"], 420, 40, 140, 35, lauth)
    rbac = d.cell("p1_rbac", "RBAC\ntenant · agent allowlist", STYLE["box_gray"], 590, 40, 170, 35, lauth)

    # L2 Gateway - internal flow left to right
    l2 = d.lane("p1_l2", "L2 — AI Gateway  am-mcp-gateway :8120  (am-platform repo)", "#F0F9FF", "#0284C7", "#0C4A6E", 40, 330, 1120, 160)
    chat = d.cell("p1_chat", "POST\n/api/v1/chat/stream", STYLE["box_blue"], 40, 45, 130, 50, l2)
    preg = d.cell("p1_preg", "Prompt Registry\nagents.yaml", STYLE["box_sky"], 190, 45, 130, 50, l2)
    route = d.cell("p1_route", "Intent Router\nkeywords + LLM", STYLE["box_sky"], 340, 45, 130, 50, l2)
    sec = d.cell("p1_sec", "AI Security\ninput/output guard", STYLE["box_sky"], 490, 45, 130, 50, l2)
    sse = d.cell("p1_sse", "Unified SSE\nnormalize events", STYLE["box_sky"], 640, 45, 130, 50, l2)
    llm = d.cell("p1_llm", "LLM Proxy\n/agent/llm/completions", STYLE["box_sky"], 790, 45, 150, 50, l2)
    mcp = d.cell("p1_mcp", "MCP Proxy\ntool routes", STYLE["box_sky"], 960, 45, 130, 50, l2)
    d.edge("p1_e_l2_1", chat, preg, parent=l2)
    d.edge("p1_e_l2_2", preg, route, parent=l2)
    d.edge("p1_e_l2_3", route, sec, parent=l2)
    d.edge("p1_e_l2_4", sec, sse, parent=l2)
    d.edge("p1_e_l2_5", sse, llm, parent=l2)
    d.edge("p1_e_l2_6", llm, mcp, parent=l2)

    # L3 agents
    l3 = d.lane("p1_l3", "L3 — Domain Agents  (am-agents repo) — gateway routes by intent", "#F5F3FF", "#7C3AED", "#4C1D95", 40, 510, 1120, 110)
    fin = d.cell("p1_fin", "fin-agent :8100\nPortfolio · widgets", STYLE["box_pink"], 60, 45, 150, 55, l3)
    test = d.cell("p1_test", "ui-test-agent :8130\nPlaywright QA", STYLE["box_purple"], 240, 45, 150, 55, l3)
    tool = d.cell("p1_tool", "tool-agent :8141\nVault · K8s · Mongo", STYLE["box_purple"], 420, 45, 150, 55, l3)
    dev = d.cell("p1_dev", "ai-bots dev :5000\nCode · Jira · RAG", STYLE["box_green"], 600, 45, 150, 55, l3)
    scribe = d.cell("p1_scribe", "scribe-agent\n(planned)", STYLE["box_planned"], 780, 45, 130, 55, l3)
    sup = d.cell("p1_sup", "support-agent\n(planned)", STYLE["box_planned"], 930, 45, 130, 55, l3)

    # L4 MCP
    l4 = d.lane("p1_l4", "L4 — MCP Core Services (Whiteboard: Portfolio · Trade · Market · Stock Analysis)", "#F0FDFA", "#0D9488", "#134E4A", 40, 640, 1120, 110)
    port = d.cell("p1_port", "Portfolio SDK\nholdings · PnL", STYLE["box_teal"], 60, 45, 130, 55, l4)
    trade = d.cell("p1_trade", "Trade\norders", STYLE["box_teal"], 210, 45, 100, 55, l4)
    market = d.cell("p1_market", "Market Analysis\nETF · MF", STYLE["box_teal"], 330, 45, 130, 55, l4)
    stock = d.cell("p1_stock", "Stock Analysis", STYLE["box_teal"], 480, 45, 120, 55, l4)
    vault = d.cell("p1_vault", "Vault MCP\nsecrets", STYLE["box_teal"], 620, 45, 110, 55, l4)
    k8s = d.cell("p1_k8s", "K8s MCP\ndeploy", STYLE["box_teal"], 750, 45, 100, 55, l4)
    dbmcp = d.cell("p1_db", "DB MCP Toolbox\nPostgres · Mongo", STYLE["box_teal"], 870, 45, 150, 55, l4)

    # Platform
    lplat = d.lane("p1_plat", "Platform — LiteLLM · Langfuse · Vault · Usage/Billing", "#EEF2FF", "#6366F1", "#312E81", 40, 770, 1120, 90)
    lit = d.cell("p1_lit", "LiteLLM\nmodel routing", STYLE["box_violet"], 200, 40, 140, 45, lplat)
    lf = d.cell("p1_lf", "Langfuse\ntraces · cost", STYLE["box_violet"], 380, 40, 140, 45, lplat)
    hv = d.cell("p1_hv", "Vault\nsecrets", STYLE["box_violet"], 560, 40, 120, 45, lplat)

    # Vertical flow arrows between layers
    d.edge("p1_v1", ui, kc, "all clients", STYLE["arrow_down"])
    d.edge("p1_v2", kc, chat, "authenticated", STYLE["arrow_down"])
    d.edge("p1_v3", route, fin, "route: finance", STYLE["arrow_down"])
    d.edge("p1_v4", route, test, "route: test", STYLE["arrow_down"])
    d.edge("p1_v5", route, tool, "route: devops", STYLE["arrow_down"])
    d.edge("p1_v6", fin, port, "MCP tools", STYLE["arrow_down"])
    d.edge("p1_v7", tool, vault, "MCP tools", STYLE["arrow_down"])
    d.edge("p1_v8", llm, lit, "LLM calls", STYLE["arrow_dash"])
    d.edge("p1_v9", lit, lf, "trace", STYLE["arrow_dash"])

    d.cell(
        "p1_legend",
        "FLOW: Clients -> Auth -> am-mcp-gateway (route) -> Domain Agent -> MCP Service -> LiteLLM/Langfuse\n"
        "TODAY: fin-agent, ui-test-agent, tool-agent live.  PLANNED: agents.yaml registry, scribe, unified SSE schema.",
        STYLE["note"],
        40,
        880,
        1120,
        55,
    )
    d.cell(
        "p1_map",
        "Whiteboard mapping:\n"
        "AI Gateway = am-mcp-gateway | fin-agent = am-fin-agent | MCP server = tool-agent + fin MCP + LiteLLM registry | "
        "Prompt Registry = agents.yaml | Modern UI = am-modern-ui",
        "text;html=1;strokeColor=#F59E0B;fillColor=#FFFBEB;align=left;verticalAlign=top;spacingLeft=10;spacingTop=8;fontColor=#92400E;rounded=1;fontSize=11;",
        40,
        950,
        1120,
        70,
    )
    return d


def build_chat_flow() -> Diagram:
    d = Diagram("chat-flow", "2 - Chat Request Flow", 1200, 850)

    d.cell("p2_title", "Chat Request Flow — Example: Show my portfolio PnL", STYLE["title"], 200, 20, 800, 40)

    # Step pipeline
    lane = d.lane("p2_lane", "6-Step Execution Pipeline", "#FFF7ED", "#F59E0B", "#92400E", 40, 70, 1120, 80)
    steps = []
    labels = ["1 User msg", "2 Auth", "3 Route", "4 Agent", "5 MCP exec", "6 SSE back"]
    x = 30
    for i, lbl in enumerate(labels):
        cid = f"p2_s{i+1}"
        steps.append(d.cell(cid, lbl, STYLE["box_orange"], x, 40, 110, 35, lane))
        x += 130
    for i in range(len(steps) - 1):
        d.edge(f"p2_es{i+1}", steps[i], steps[i + 1], parent=lane)

    # Main horizontal sequence
    user = d.cell("p2_user", "User", "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fillColor=#4F46E5;strokeColor=#312E81;", 60, 200, 40, 70)
    ui = d.cell("p2_ui", "L1 UI\nam-modern-ui", STYLE["box_indigo"], 140, 210, 120, 55)
    gw = d.cell("p2_gw", "L2 Gateway\nam-mcp-gateway\n:8120", STYLE["box_blue"], 300, 200, 150, 70)
    agent = d.cell("p2_agent", "L3 fin-agent\n:8100", STYLE["box_pink"], 490, 210, 120, 55)
    mcp = d.cell("p2_mcp", "L4 Portfolio SDK", STYLE["box_teal"], 650, 210, 130, 55)
    lit = d.cell("p2_lit", "LiteLLM", STYLE["box_violet"], 820, 210, 100, 55)
    lf = d.cell("p2_lf", "Langfuse", STYLE["box_violet"], 960, 210, 100, 55)

    d.edge("p2_e1", user, ui, "1")
    d.edge("p2_e2", ui, gw, "2 POST /chat/stream\n+ JWT", STYLE["arrow_blue"])
    d.edge("p2_e3", gw, agent, "3 route: finance\nagent_selected", STYLE["arrow_blue"])
    d.edge("p2_e4", agent, mcp, "4 tool_call:\nget_holdings")
    d.edge("p2_e5", agent, lit, "5 LLM via\n/agent/llm/completions", STYLE["arrow_dash"])
    d.edge("p2_e6", lit, lf, "trace")
    d.edge_points("p2_e7", agent, ui, [(540, 340), (200, 340)], "6 SSE: token, artifact(widget), done", STYLE["arrow_blue"])

    d.cell(
        "p2_sse",
        "SSE Events (gateway normalizes all agents to one schema):\n"
        "agent_selected | stage | tool_call | token | artifact | memory_update | done",
        STYLE["note"],
        40,
        390,
        540,
        70,
    )
    d.cell(
        "p2_req",
        "Gateway -> Agent request body:\n"
        "message, sessionId, userId, traceId, agentContext { pinnedAgent, requirementIds }",
        STYLE["note"],
        600,
        390,
        540,
        70,
    )

    d.cell(
        "p2_modes",
        "No-agent mode: gateway answers via LiteLLM directly (simple queries).\n"
        "Multi-agent mode: router chains agents using agentContext.workingSummary.",
        "text;html=1;strokeColor=#CBD5E1;fillColor=#F8FAFC;align=left;verticalAlign=top;spacingLeft=10;spacingTop=8;fontColor=#475569;rounded=1;fontSize=11;",
        40,
        480,
        1100,
        50,
    )

    # agents.yaml
    d.cell(
        "p2_yaml",
        "agents.yaml registry (planned — replaces hardcoded routes):\n"
        "finance -> am-fin-agent:8100  keywords: [portfolio, pnl, trade]\n"
        "test -> am-ui-test-agent:8130  keywords: [playwright, ui, test]\n"
        "devops -> am-tool-agent:8141  keywords: [k8s, vault, deploy]",
        "text;html=1;strokeColor=#0284C7;fillColor=#F0F9FF;align=left;verticalAlign=top;spacingLeft=10;spacingTop=8;fontColor=#0C4A6E;rounded=1;fontSize=11;",
        40,
        550,
        1100,
        80,
    )
    return d


def build_llm_mcp_flow() -> Diagram:
    d = Diagram("llm-mcp-flow", "3 - LLM and MCP Paths", 1200, 900)

    d.cell("p3_title", "LLM & MCP Proxy Paths — How agents use the gateway today", STYLE["title"], 150, 20, 900, 40)

    # Path A
    la = d.lane("p3_la", "Path A — Agent LLM calls (MCP_GATEWAY_BASE_URL)", "#EEF2FF", "#6366F1", "#312E81", 40, 70, 1120, 130)
    agents = d.cell("p3_agents", "ui-test-agent\ntool-agent\ndb-agent\nfin-portfolio-agent", STYLE["box_purple"], 40, 45, 160, 70, la)
    gw = d.cell("p3_gw", "am-mcp-gateway\nPOST /api/v1/agent/llm/completions", STYLE["box_blue"], 250, 45, 220, 70, la)
    lit = d.cell("p3_lit", "LiteLLM\nOpenAI · Gemini · Together", STYLE["box_violet"], 520, 45, 180, 70, la)
    lf = d.cell("p3_lf", "Langfuse\ntraces · sessionId · cost", STYLE["box_violet"], 750, 45, 160, 70, la)
    env = d.cell("p3_env", "Env: MCP_GATEWAY_BASE_URL\nAuth: Keycloak client_credentials\nVault: LITELLM_MASTER_KEY", STYLE["note"], 940, 45, 150, 70, la)
    d.edge("p3_a1", agents, gw, "HTTP POST", parent=la)
    d.edge("p3_a2", gw, lit, "proxy", parent=la)
    d.edge("p3_a3", lit, lf, "observability", parent=la)

    # Path B
    lb = d.lane("p3_lb", "Path B — MCP tool registration & execution", "#F0FDFA", "#0D9488", "#134E4A", 40, 220, 1120, 150)
    sync = d.cell("p3_sync", "sync_litellm_mcp_tools\n(am-mcp-gateway)", STYLE["box_teal"], 40, 45, 170, 55, lb)
    reg = d.cell("p3_reg", "LiteLLM MCP Registry\nK8s ConfigMap", STYLE["box_violet"], 240, 45, 170, 55, lb)
    gw2 = d.cell("p3_gw2", "am-mcp-gateway\nMCP proxy routes", STYLE["box_blue"], 440, 45, 170, 55, lb)
    cursor = d.cell("p3_cursor", "Cursor / IDE\nMCP client", STYLE["box_indigo"], 640, 45, 130, 55, lb)
    finm = d.cell("p3_finm", "fin MCP\nportfolio tools", STYLE["box_teal"], 40, 105, 120, 40, lb)
    uim = d.cell("p3_uim", "ui-test MCP", STYLE["box_teal"], 180, 105, 110, 40, lb)
    toolm = d.cell("p3_toolm", "tool-agent MCP\nvault · k8s", STYLE["box_teal"], 310, 105, 130, 40, lb)
    dbm = d.cell("p3_dbm", "DB MCP Toolbox", STYLE["box_teal"], 460, 105, 130, 40, lb)
    d.edge("p3_b1", sync, reg, "register", parent=lb)
    d.edge("p3_b2", reg, gw2, "expose", parent=lb)
    d.edge("p3_b3", cursor, gw2, "MCP protocol", parent=lb)
    d.edge("p3_b4", finm, reg, parent=lb)
    d.edge("p3_b5", uim, reg, parent=lb)
    d.edge("p3_b6", toolm, reg, parent=lb)

    # Path C security
    lc = d.lane("p3_lc", "Path C — Security loop (every request wraps LiteLLM)", "#F1F5F9", "#64748B", "#0F172A", 40, 390, 1120, 100)
    boxes = []
    labels = ["Request", "JWT + RBAC", "SPT Guard", "Prompt filter", "LiteLLM", "Output guard", "Response"]
    x = 30
    for lbl in labels:
        style = STYLE["box_violet"] if lbl == "LiteLLM" else STYLE["box_gray"]
        if lbl == "Response":
            style = STYLE["box_blue"]
        boxes.append(d.cell(f"p3_c_{lbl.replace(' ', '_')}", lbl, style, x, 45, 110, 45, lc))
        x += 130
    for i in range(len(boxes) - 1):
        d.edge(f"p3_c_e{i+1}", boxes[i], boxes[i + 1], parent=lc)

    d.cell(
        "p3_note",
        "K8s service: am-mcp-gateway.am-apps-{env}.svc.cluster.local:8120\n"
        "All agents in am-agents set MCP_GATEWAY_BASE_URL in Helm values (dev/preprod/prod)",
        STYLE["note"],
        40,
        510,
        1100,
        50,
    )
    return d


def main() -> None:
    pages = [build_target_architecture(), build_chat_flow(), build_llm_mcp_flow()]
    content = "\n".join(p.render() for p in pages)
    xml = f"""<mxfile host="app.diagrams.net" modified="2026-08-22T06:20:00.000Z" agent="am-agents" version="22.1.0" type="device">
{content}
</mxfile>
"""
    OUT.write_text(xml, encoding="utf-8")
    print(f"Wrote {OUT} ({len(xml)} bytes, {len(pages)} pages)")


if __name__ == "__main__":
    main()
