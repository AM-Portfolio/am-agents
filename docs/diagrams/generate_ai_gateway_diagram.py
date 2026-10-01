#!/usr/bin/env python3
"""Generate draw.io using the exact format from the working repo diagram."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
import base64
import zlib

OUT = Path(__file__).parent / "02-ai-gateway-mcp-design.drawio"
TEMPLATE = Path(__file__).parent / "01-three-surfaces-overview.drawio"


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "&#10;")
    )


def cell(cid: str, value: str, style: str, x: int, y: int, w: int, h: int, parent: str = "1") -> str:
    return (
        f'                <mxCell id="{cid}" value="{esc(value)}" style="{style}" parent="{parent}" vertex="1">\n'
        f'                    <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>\n'
        f"                </mxCell>"
    )


def edge(eid: str, source: str, target: str, label: str = "", style: str | None = None, parent: str = "1") -> str:
    style = style or "strokeColor=#334155;strokeWidth=2;endArrow=classic;"
    label_attr = f' value="{esc(label)}"' if label else ""
    return (
        f'                <mxCell id="{eid}"{label_attr} style="{style}" parent="{parent}" source="{source}" target="{target}" edge="1">\n'
        f'                    <mxGeometry relative="1" as="geometry"/>\n'
        f"                </mxCell>"
    )


def build_page_architecture() -> str:
    s_lane = "swimlane;horizontal=1;startSize=28;fillColor={bg};strokeColor={stroke};fontColor={fg};fontStyle=1;rounded=1;"
    s_box = "rounded=1;whiteSpace=wrap;html=1;fillColor={bg};fontColor={fg};strokeColor={stroke};"
    s_text = "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=18;fontColor=#0F172A;"
    s_note = "text;html=1;strokeColor=#CBD5E1;fillColor=#FFFFFF;align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;fontColor=#0F172A;rounded=1;"

    lines: list[str] = []
    add = lines.append

    add(cell("ag_title", "AI Gateway + MCP Architecture (Target State)", s_text, 350, 20, 900, 40))
    add(cell("ag_sub", "am-platform/am-mcp-gateway is the L2 AI Gateway from the whiteboard", "text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=12;fontColor=#64748B;", 300, 55, 1000, 24))

    add(cell("ag_lane_exec", "Request flow (6 steps)", s_lane.format(bg="#FFF7ED", stroke="#F59E0B", fg="#92400E"), 40, 90, 1520, 90))
    steps = ["1 User message", "2 Auth + RBAC", "3 Route agent", "4 Agent run", "5 MCP execute", "6 SSE response"]
    xs = [20, 180, 340, 500, 660, 820]
    ids = []
    for i, (lbl, x) in enumerate(zip(steps, xs)):
        cid = f"ag_ex{i+1}"
        ids.append(cid)
        add(cell(cid, lbl, s_box.format(bg="#F59E0B", fg="#FFFFFF", stroke="#D97706"), x, 40, 130, 40, "ag_lane_exec"))
    for i in range(len(ids) - 1):
        add(edge(f"ag_exe{i+1}", ids[i], ids[i + 1], parent="ag_lane_exec"))

    add(cell("ag_lane_auth", "Ingress and Auth", s_lane.format(bg="#F1F5F9", stroke="#64748B", fg="#0F172A"), 40, 200, 1520, 80))
    add(cell("ag_traefik", "Traefik&#10;host routing", s_box.format(bg="#64748B", fg="#FFFFFF", stroke="#475569"), 400, 38, 140, 50, "ag_lane_auth"))
    add(cell("ag_keycloak", "Keycloak JWT&#10;RBAC roles tenant", s_box.format(bg="#64748B", fg="#FFFFFF", stroke="#475569"), 580, 38, 170, 50, "ag_lane_auth"))
    add(cell("ag_guard", "AI Guardrails&#10;SPT policy", s_box.format(bg="#64748B", fg="#FFFFFF", stroke="#475569"), 780, 38, 150, 50, "ag_lane_auth"))
    add(edge("ag_e_tr_kc", "ag_traefik", "ag_keycloak", parent="ag_lane_auth"))
    add(edge("ag_e_kc_gd", "ag_keycloak", "ag_guard", parent="ag_lane_auth"))

    add(cell("ag_lane_l1", "L1 UI - Web UI, IDE, Mobile", s_lane.format(bg="#EEF2FF", stroke="#4F46E5", fg="#312E81"), 40, 300, 1520, 110))
    add(cell("ag_ui", "Web UI&#10;am-modern-ui Flutter&#10;AI Chat Widgets", s_box.format(bg="#4F46E5", fg="#FFFFFF", stroke="#312E81"), 120, 40, 190, 65, "ag_lane_l1"))
    add(cell("ag_ide", "IDE&#10;Cursor VS Code&#10;MCP client", s_box.format(bg="#4F46E5", fg="#FFFFFF", stroke="#312E81"), 350, 40, 170, 65, "ag_lane_l1"))
    add(cell("ag_mobile", "Mobile&#10;future same API", s_box.format(bg="#818CF8", fg="#FFFFFF", stroke="#6366F1"), 560, 40, 150, 65, "ag_lane_l1"))
    add(cell("ag_pb", "Portal B&#10;ai-bots React", s_box.format(bg="#059669", fg="#FFFFFF", stroke="#047857"), 750, 40, 170, 65, "ag_lane_l1"))
    add(cell("ag_pc", "Portal C&#10;kagent SRE", s_box.format(bg="#EA580C", fg="#FFFFFF", stroke="#C2410C"), 960, 40, 150, 65, "ag_lane_l1"))

    add(cell("ag_lane_l2", "L2 AI Gateway - am-mcp-gateway :8120 (am-platform repo)", s_lane.format(bg="#F0F9FF", stroke="#0284C7", fg="#0C4A6E"), 40, 430, 1520, 130))
    add(cell("ag_gw", "am-mcp-gateway&#10;POST /api/v1/chat/stream&#10;POST /api/v1/agent/llm/completions", s_box.format(bg="#0284C7", fg="#FFFFFF", stroke="#0369A1"), 460, 38, 240, 55, "ag_lane_l2"))
    add(cell("ag_preg", "Prompt Registry&#10;agents.yaml", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 120, 95, 130, 40, "ag_lane_l2"))
    add(cell("ag_router", "Intent router", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 280, 95, 120, 40, "ag_lane_l2"))
    add(cell("ag_rbac", "RBAC check", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 430, 95, 120, 40, "ag_lane_l2"))
    add(cell("ag_sse", "Unified SSE", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 580, 95, 120, 40, "ag_lane_l2"))
    add(cell("ag_llm", "LLM proxy", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 730, 95, 120, 40, "ag_lane_l2"))
    add(cell("ag_mcp", "MCP proxy", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 880, 95, 120, 40, "ag_lane_l2"))
    add(edge("ag_e_gw_r", "ag_gw", "ag_router", parent="ag_lane_l2"))
    add(edge("ag_e_r_rb", "ag_router", "ag_rbac", parent="ag_lane_l2"))
    add(edge("ag_e_rb_s", "ag_rbac", "ag_sse", parent="ag_lane_l2"))
    add(edge("ag_e_s_l", "ag_sse", "ag_llm", parent="ag_lane_l2"))
    add(edge("ag_e_l_m", "ag_llm", "ag_mcp", parent="ag_lane_l2"))

    add(cell("ag_lane_l3", "L3 Domain Agents - am-agents repo", s_lane.format(bg="#F5F3FF", stroke="#7C3AED", fg="#4C1D95"), 40, 580, 1520, 90))
    add(cell("ag_fin", "fin-agent :8100", s_box.format(bg="#DB2777", fg="#FFFFFF", stroke="#BE185D"), 80, 40, 130, 40, "ag_lane_l3"))
    add(cell("ag_test", "ui-test-agent :8130", s_box.format(bg="#7C3AED", fg="#FFFFFF", stroke="#6D28D9"), 240, 40, 140, 40, "ag_lane_l3"))
    add(cell("ag_tool", "tool-agent :8141", s_box.format(bg="#7C3AED", fg="#FFFFFF", stroke="#6D28D9"), 410, 40, 130, 40, "ag_lane_l3"))
    add(cell("ag_dev", "ai-bots dev :5000", s_box.format(bg="#059669", fg="#FFFFFF", stroke="#047857"), 570, 40, 140, 40, "ag_lane_l3"))
    add(cell("ag_scribe", "scribe planned", s_box.format(bg="#EDE9FE", fg="#5B21B6", stroke="#7C3AED"), 740, 40, 120, 40, "ag_lane_l3"))
    add(cell("ag_support", "support planned", s_box.format(bg="#EDE9FE", fg="#5B21B6", stroke="#7C3AED"), 890, 40, 130, 40, "ag_lane_l3"))

    add(cell("ag_lane_l4", "L4 MCP Core Services", s_lane.format(bg="#F0FDFA", stroke="#0D9488", fg="#134E4A"), 40, 690, 1520, 90))
    add(cell("ag_port", "Portfolio SDK", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 80, 40, 130, 40, "ag_lane_l4"))
    add(cell("ag_trade", "Trade", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 240, 40, 100, 40, "ag_lane_l4"))
    add(cell("ag_market", "Market Analysis", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 370, 40, 140, 40, "ag_lane_l4"))
    add(cell("ag_vault", "Vault MCP", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 540, 40, 110, 40, "ag_lane_l4"))
    add(cell("ag_k8s", "K8s MCP", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 680, 40, 100, 40, "ag_lane_l4"))
    add(cell("ag_db", "DB MCP Toolbox", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 810, 40, 140, 40, "ag_lane_l4"))

    add(cell("ag_lane_obs", "Platform - LiteLLM Langfuse Vault", s_lane.format(bg="#EEF2FF", stroke="#6366F1", fg="#312E81"), 40, 800, 520, 80))
    add(cell("ag_lit", "LiteLLM", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 30, 38, 120, 40, "ag_lane_obs"))
    add(cell("ag_lf", "Langfuse", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 180, 38, 120, 40, "ag_lane_obs"))
    add(cell("ag_vlt", "Vault secrets", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 330, 38, 120, 40, "ag_lane_obs"))

    add(edge("ag_e_ui_gw", "ag_ui", "ag_gw", "chat/stream", "strokeColor=#4F46E5;strokeWidth=2;endArrow=classic;"))
    add(edge("ag_e_pb_gw", "ag_pb", "ag_gw", "all agents", "strokeColor=#059669;strokeWidth=2;endArrow=classic;"))
    add(edge("ag_e_kc_ui", "ag_keycloak", "ag_ui", parent="1"))
    add(edge("ag_e_gd_gw", "ag_guard", "ag_gw", parent="1"))
    add(edge("ag_e_sse_fin", "ag_sse", "ag_fin", parent="1"))
    add(edge("ag_e_sse_test", "ag_sse", "ag_test", parent="1"))
    add(edge("ag_e_fin_port", "ag_fin", "ag_port", parent="1"))
    add(edge("ag_e_tool_vault", "ag_tool", "ag_vault", parent="1"))
    add(edge("ag_e_llm_lit", "ag_llm", "ag_lit", "LLM calls", "strokeColor=#6366F1;strokeWidth=1;endArrow=classic;dashed=1;"))
    add(edge("ag_e_lit_lf", "ag_lit", "ag_lf", parent="1"))

    add(cell("ag_legend", "Legend: Blue=Gateway Purple=Agents Teal=MCP Indigo=UI Green=Portal B Orange=Portal C", s_note, 580, 800, 520, 60))

    body = "\n".join(lines)
    return f"""    <diagram id="ai-gateway-architecture" name="AI Gateway Architecture">
        <mxGraphModel dx="967" dy="790" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="1100" background="#ffffff" math="0" shadow="0">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
{body}
            </root>
        </mxGraphModel>
    </diagram>"""


def build_page_chat_flow() -> str:
    s_box = "rounded=1;whiteSpace=wrap;html=1;fillColor={bg};fontColor={fg};strokeColor={stroke};"
    lines = []
    add = lines.append

    add(cell("cf_t", "Chat Flow - Show my portfolio PnL", "text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=16;fontColor=#0F172A;", 300, 20, 500, 30))
    add(cell("cf_user", "User", s_box.format(bg="#64748B", fg="#FFFFFF", stroke="#475569"), 400, 60, 120, 40))
    add(cell("cf_ui", "L1 am-modern-ui", s_box.format(bg="#4F46E5", fg="#FFFFFF", stroke="#312E81"), 380, 130, 160, 45))
    add(cell("cf_gw", "L2 am-mcp-gateway&#10;POST /api/v1/chat/stream", s_box.format(bg="#0284C7", fg="#FFFFFF", stroke="#0369A1"), 360, 210, 200, 50))
    add(cell("cf_router", "Intent router picks finance", s_box.format(bg="#0EA5E9", fg="#FFFFFF", stroke="#0284C7"), 360, 290, 200, 45))
    add(cell("cf_agent", "L3 fin-agent :8100", s_box.format(bg="#DB2777", fg="#FFFFFF", stroke="#BE185D"), 380, 370, 160, 45))
    add(cell("cf_mcp", "L4 Portfolio SDK MCP", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 140, 370, 170, 45))
    add(cell("cf_lit", "LiteLLM via gateway", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 620, 370, 160, 45))
    add(cell("cf_sse", "SSE stream&#10;token artifact done", s_box.format(bg="#F59E0B", fg="#FFFFFF", stroke="#D97706"), 380, 460, 160, 50))
    add(cell("cf_note", "Agents call MCP_GATEWAY_BASE_URL for LLM at /api/v1/agent/llm/completions", "text;html=1;strokeColor=#CBD5E1;fillColor=#FFFFFF;align=left;spacingLeft=8;fontColor=#475569;rounded=1;", 120, 540, 720, 40))

    for i, (a, b) in enumerate([
        ("cf_user", "cf_ui"), ("cf_ui", "cf_gw"), ("cf_gw", "cf_router"), ("cf_router", "cf_agent"),
        ("cf_agent", "cf_mcp"), ("cf_agent", "cf_lit"), ("cf_agent", "cf_sse"), ("cf_sse", "cf_ui"),
    ]):
        add(edge(f"cf_e{i+1}", a, b))

    body = "\n".join(lines)
    return f"""    <diagram id="ai-gateway-chat-flow" name="AI Gateway Chat Flow">
        <mxGraphModel dx="677" dy="553" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="900" pageHeight="700" background="#ffffff" math="0" shadow="0">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
{body}
            </root>
        </mxGraphModel>
    </diagram>"""


def build_page_llm_mcp() -> str:
    s_box = "rounded=1;whiteSpace=wrap;html=1;fillColor={bg};fontColor={fg};strokeColor={stroke};"
    s_lane = "swimlane;horizontal=1;startSize=28;fillColor={bg};strokeColor={stroke};fontColor={fg};fontStyle=1;rounded=1;"
    lines = []
    add = lines.append

    add(cell("lm_t", "LLM and MCP Proxy Paths", "text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=16;fontColor=#0F172A;", 250, 20, 500, 30))

    add(cell("lm_lane_a", "Path A - Agent LLM calls", s_lane.format(bg="#EEF2FF", stroke="#6366F1", fg="#312E81"), 40, 70, 820, 100))
    add(cell("lm_agents", "ui-test tool db fin agents", s_box.format(bg="#7C3AED", fg="#FFFFFF", stroke="#6D28D9"), 30, 45, 170, 45, "lm_lane_a"))
    add(cell("lm_gw", "am-mcp-gateway&#10;/agent/llm/completions", s_box.format(bg="#0284C7", fg="#FFFFFF", stroke="#0369A1"), 230, 45, 190, 45, "lm_lane_a"))
    add(cell("lm_lit", "LiteLLM", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 450, 45, 120, 45, "lm_lane_a"))
    add(cell("lm_lf", "Langfuse", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 600, 45, 120, 45, "lm_lane_a"))
    add(edge("lm_a1", "lm_agents", "lm_gw", parent="lm_lane_a"))
    add(edge("lm_a2", "lm_gw", "lm_lit", parent="lm_lane_a"))
    add(edge("lm_a3", "lm_lit", "lm_lf", parent="lm_lane_a"))

    add(cell("lm_lane_b", "Path B - MCP tool registration", s_lane.format(bg="#F0FDFA", stroke="#0D9488", fg="#134E4A"), 40, 190, 820, 100))
    add(cell("lm_sync", "sync_litellm_mcp_tools", s_box.format(bg="#0D9488", fg="#FFFFFF", stroke="#0F766E"), 30, 45, 170, 45, "lm_lane_b"))
    add(cell("lm_reg", "LiteLLM MCP registry", s_box.format(bg="#6366F1", fg="#FFFFFF", stroke="#4F46E5"), 230, 45, 160, 45, "lm_lane_b"))
    add(cell("lm_gw2", "gateway MCP proxy", s_box.format(bg="#0284C7", fg="#FFFFFF", stroke="#0369A1"), 420, 45, 150, 45, "lm_lane_b"))
    add(cell("lm_ide", "Cursor IDE MCP client", s_box.format(bg="#4F46E5", fg="#FFFFFF", stroke="#312E81"), 600, 45, 150, 45, "lm_lane_b"))
    add(edge("lm_b1", "lm_sync", "lm_reg", parent="lm_lane_b"))
    add(edge("lm_b2", "lm_reg", "lm_gw2", parent="lm_lane_b"))
    add(edge("lm_b3", "lm_ide", "lm_gw2", parent="lm_lane_b"))

    body = "\n".join(lines)
    return f"""    <diagram id="ai-gateway-llm-mcp" name="AI Gateway LLM MCP">
        <mxGraphModel dx="677" dy="553" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="900" pageHeight="400" background="#ffffff" math="0" shadow="0">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
{body}
            </root>
        </mxGraphModel>
    </diagram>"""


def compress_drawio(xml: str) -> str:
    encoded = quote(xml, safe="")
    co = zlib.compressobj(level=9, wbits=-15)
    compressed = co.compress(encoded.encode("utf-8")) + co.flush()
    return base64.b64encode(compressed).decode("ascii")


def wrap_mxfile(pages: list[str], compressed: bool = False) -> str:
    if not compressed:
        return "<mxfile host=\"65bd71144e\">\n" + "\n".join(pages) + "\n</mxfile>\n"

    wrapped_pages = []
    for page in pages:
        # extract inner mxGraphModel xml
        start = page.index("<mxGraphModel")
        end = page.index("</mxGraphModel>") + len("</mxGraphModel>")
        inner = page[start:end]
        diagram_open = page[: page.index(">") + 1]
        diagram_close = "    </diagram>"
        encoded = compress_drawio(inner)
        wrapped_pages.append(f"{diagram_open}{encoded}{diagram_close}")
    return "<mxfile host=\"65bd71144e\">\n" + "\n".join(wrapped_pages) + "\n</mxfile>\n"


def append_to_enterprise(page_xml: str) -> None:
    ent = Path(__file__).parent / "enterprise-agent-ecosystem.drawio"
    text = ent.read_text(encoding="utf-8")
    if "ai-gateway-architecture" in text:
        return
    if text.rstrip().endswith("</mxfile>"):
        text = text.rstrip()[:-len("</mxfile>")] + page_xml + "\n</mxfile>\n"
        ent.write_text(text, encoding="utf-8")


def main() -> None:
    pages = [build_page_architecture(), build_page_chat_flow(), build_page_llm_mcp()]
    OUT.write_text(wrap_mxfile(pages, compressed=False), encoding="utf-8")

    compressed_out = OUT.with_name("02-ai-gateway-mcp-design-compressed.drawio")
    compressed_out.write_text(wrap_mxfile(pages, compressed=True), encoding="utf-8")

    append_to_enterprise(build_page_architecture())
    print(f"Wrote {OUT}")
    print(f"Wrote {compressed_out}")
    print("Appended architecture page to enterprise-agent-ecosystem.drawio")


if __name__ == "__main__":
    main()
