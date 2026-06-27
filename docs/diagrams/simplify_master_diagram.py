"""Replace enterprise-master page with a simplified layer-stack (no arrow spaghetti)."""
import re
from pathlib import Path

FILE = Path(__file__).parent / "enterprise-agent-ecosystem.drawio"

SIMPLE_MASTER = '''    <diagram id="enterprise-master" name="Enterprise Master - Agents Features Integrations">
        <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" page="1" pageScale="1" pageWidth="1800" pageHeight="1150" background="#ffffff">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>

                <mxCell id="em_title" value="Enterprise Agent Platform — Overview&#10;Layers stack top → bottom · Details on other pages (Chat Flow, Portal B, Phases)" style="text;html=0;strokeColor=none;fillColor=none;fontSize=18;fontColor=#0F172A;align=center;whiteSpace=wrap;html=0" parent="1" vertex="1">
                    <mxGeometry x="200" y="15" width="1400" height="45" as="geometry"/>
                </mxCell>

                <mxCell id="em_life" value="Lifecycle (REQ status)" style="swimlane;startSize=24;fillColor=#FFFBEB;strokeColor=#F59E0B;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="70" width="1720" height="58" as="geometry"/>
                </mxCell>
                <mxCell id="em_ls1" value="Discovery" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="15" y="32" width="95" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls2" value="Requirements" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="120" y="32" width="105" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls3" value="Development" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="235" y="32" width="105" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls4" value="Test" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="350" y="32" width="70" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls5" value="Release" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="430" y="32" width="80" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls6" value="Marketing" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="520" y="32" width="95" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls7" value="Support" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="625" y="32" width="80" height="22" as="geometry"/></mxCell>
                <mxCell id="em_ls8" value="Admin" style="rounded=1;fillColor=#FDE68A;strokeColor=#D97706;" parent="em_life" vertex="1"><mxGeometry x="715" y="32" width="70" height="22" as="geometry"/></mxCell>
                <mxCell id="em_lstat" value="draft → approved → in_progress → tested → released → supported" style="text;html=0;fillColor=none;strokeColor=none;fontColor=#92400E;fontStyle=2;fontSize=11;" parent="em_life" vertex="1"><mxGeometry x="820" y="34" width="420" height="18" as="geometry"/></mxCell>

                <mxCell id="em_ui" value="L1 UI + L2 Gateway (all chat goes through gateway)" style="swimlane;startSize=24;fillColor=#EEF2FF;strokeColor=#4F46E5;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="145" width="1720" height="95" as="geometry"/>
                </mxCell>
                <mxCell id="em_pa" value="Portal A&#10;am-modern-ui&#10;Finance · end users" style="rounded=1;fillColor=#4F46E5;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="20" y="35" width="130" height="52" as="geometry"/></mxCell>
                <mxCell id="em_pb" value="Portal B — main workspace&#10;ai-bots React&#10;All business agents" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="170" y="32" width="160" height="58" as="geometry"/></mxCell>
                <mxCell id="em_pc" value="Portal C&#10;kagent UI&#10;SRE only" style="rounded=1;fillColor=#EA580C;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="350" y="35" width="120" height="52" as="geometry"/></mxCell>
                <mxCell id="em_gw" value="am-mcp-gateway :8120&#10;Router · RBAC · SSE" style="rounded=1;fillColor=#0284C7;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="500" y="35" width="160" height="52" as="geometry"/></mxCell>
                <mxCell id="em_aib" value="ai-bots API :5000&#10;Integrations + dev agent" style="rounded=1;fillColor=#047857;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="680" y="35" width="160" height="52" as="geometry"/></mxCell>
                <mxCell id="em_kc" value="Keycloak + Traefik" style="rounded=1;fillColor=#64748B;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="860" y="40" width="130" height="42" as="geometry"/></mxCell>
                <mxCell id="em_uinote" value="Portal B tabs: Chat · Integrations · Requirements · Meetings · Profile · Company profile" style="text;html=0;fillColor=#ECFDF5;strokeColor=#059669;fontColor=#065F46;rounded=1;whiteSpace=wrap;html=0;fontSize=11;" parent="em_ui" vertex="1"><mxGeometry x="1010" y="38" width="690" height="44" as="geometry"/></mxCell>

                <mxCell id="em_agents" value="L3 Domain agents (routed by gateway — no lines on this page; see Chat Flow page)" style="swimlane;startSize=24;fillColor=#F5F3FF;strokeColor=#7C3AED;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="255" width="1720" height="130" as="geometry"/>
                </mxCell>
                <mxCell id="em_scribe" value="scribe :8150&#10;Meetings · MOM · REQ" style="rounded=1;fillColor=#7C3AED;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="15" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_dev" value="dev :8152&#10;Code · PR · RAG" style="rounded=1;fillColor=#7C3AED;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="140" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_test" value="test :8130&#10;Playwright QA" style="rounded=1;fillColor=#7C3AED;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="265" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_devops" value="devops :8151&#10;K8s · deploy" style="rounded=1;fillColor=#DB2777;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="390" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_fin" value="fin :8100&#10;Finance widgets" style="rounded=1;fillColor=#DB2777;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="515" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_mkt" value="marketing :8153&#10;Campaigns · video" style="rounded=1;fillColor=#7C3AED;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="640" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_sup" value="support :8154&#10;Tickets · FAQ" style="rounded=1;fillColor=#7C3AED;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="765" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_adm" value="admin :8155&#10;Compliance" style="rounded=1;fillColor=#7C3AED;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="890" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_kagent" value="kagent / infra-ops&#10;SRE · Portal C" style="rounded=1;fillColor=#EA580C;fontColor=#FFFFFF;whiteSpace=wrap;html=0;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="1015" y="35" width="115" height="48" as="geometry"/></mxCell>
                <mxCell id="em_agentnote" value="Ph 1: gateway + fin/test/devops/dev · Ph 2: scribe + memory · Ph 4: marketing/support/admin" style="text;html=0;fillColor=none;strokeColor=none;fontColor=#6D28D9;fontStyle=2;fontSize=11;whiteSpace=wrap;html=0;" parent="em_agents" vertex="1"><mxGeometry x="1150" y="42" width="550" height="36" as="geometry"/></mxCell>
                <mxCell id="em_agentnote2" value="LIVE today: fin · test · ai-bots dev" style="text;html=0;fillColor=none;strokeColor=none;fontColor=#6D28D9;fontSize=11;" parent="em_agents" vertex="1"><mxGeometry x="1150" y="78" width="280" height="18" as="geometry"/></mxCell>

                <mxCell id="em_integ" value="Integrations (Portal B IntegrationsHub → ai-bots API)" style="swimlane;startSize=24;fillColor=#F0FDF4;strokeColor=#059669;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="400" width="1120" height="72" as="geometry"/>
                </mxCell>
                <mxCell id="em_jira" value="Jira" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="15" y="34" width="70" height="30" as="geometry"/></mxCell>
                <mxCell id="em_gh" value="GitHub" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="95" y="34" width="70" height="30" as="geometry"/></mxCell>
                <mxCell id="em_conf" value="Confluence" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="175" y="34" width="85" height="30" as="geometry"/></mxCell>
                <mxCell id="em_graf" value="Grafana" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="270" y="34" width="75" height="30" as="geometry"/></mxCell>
                <mxCell id="em_meet" value="Meet / Teams" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="355" y="34" width="90" height="30" as="geometry"/></mxCell>
                <mxCell id="em_crm" value="CRM" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="455" y="34" width="60" height="30" as="geometry"/></mxCell>
                <mxCell id="em_recall" value="Recall.ai" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="525" y="34" width="75" height="30" as="geometry"/></mxCell>
                <mxCell id="em_slack" value="Slack" style="rounded=1;fillColor=#059669;fontColor=#FFFFFF;fontSize=11;" parent="em_integ" vertex="1"><mxGeometry x="610" y="34" width="65" height="30" as="geometry"/></mxCell>

                <mxCell id="em_mem" value="company-memory :8157 — Postgres + Qdrant" style="swimlane;startSize=24;fillColor=#ECFEFF;strokeColor=#0891B2;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="487" width="1120" height="68" as="geometry"/>
                </mxCell>
                <mxCell id="em_m1" value="meetings" style="rounded=1;fillColor=#0891B2;fontColor=#FFFFFF;fontSize=11;" parent="em_mem" vertex="1"><mxGeometry x="15" y="32" width="90" height="28" as="geometry"/></mxCell>
                <mxCell id="em_m2" value="requirements" style="rounded=1;fillColor=#0891B2;fontColor=#FFFFFF;fontSize=11;" parent="em_mem" vertex="1"><mxGeometry x="115" y="32" width="100" height="28" as="geometry"/></mxCell>
                <mxCell id="em_m3" value="tasks" style="rounded=1;fillColor=#0891B2;fontColor=#FFFFFF;fontSize=11;" parent="em_mem" vertex="1"><mxGeometry x="225" y="32" width="70" height="28" as="geometry"/></mxCell>
                <mxCell id="em_m4" value="decisions" style="rounded=1;fillColor=#0891B2;fontColor=#FFFFFF;fontSize=11;" parent="em_mem" vertex="1"><mxGeometry x="305" y="32" width="85" height="28" as="geometry"/></mxCell>
                <mxCell id="em_m5" value="lifecycle events" style="rounded=1;fillColor=#0891B2;fontColor=#FFFFFF;fontSize=11;" parent="em_mem" vertex="1"><mxGeometry x="400" y="32" width="110" height="28" as="geometry"/></mxCell>
                <mxCell id="em_m6" value="company profile" style="rounded=1;fillColor=#0891B2;fontColor=#FFFFFF;fontSize=11;" parent="em_mem" vertex="1"><mxGeometry x="520" y="32" width="115" height="28" as="geometry"/></mxCell>

                <mxCell id="em_l4" value="L4 Capabilities (MCP / REST — used by agents, not drawn here)" style="swimlane;startSize=24;fillColor=#F0FDFA;strokeColor=#0D9488;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="570" width="1120" height="68" as="geometry"/>
                </mxCell>
                <mxCell id="em_ta" value="tool-agent" style="rounded=1;fillColor=#0D9488;fontColor=#FFFFFF;fontSize=11;" parent="em_l4" vertex="1"><mxGeometry x="15" y="32" width="95" height="28" as="geometry"/></mxCell>
                <mxCell id="em_va" value="video-agent" style="rounded=1;fillColor=#0D9488;fontColor=#FFFFFF;fontSize=11;" parent="em_l4" vertex="1"><mxGeometry x="120" y="32" width="95" height="28" as="geometry"/></mxCell>
                <mxCell id="em_k8s" value="k8s MCP" style="rounded=1;fillColor=#0D9488;fontColor=#FFFFFF;fontSize=11;" parent="em_l4" vertex="1"><mxGeometry x="225" y="32" width="80" height="28" as="geometry"/></mxCell>
                <mxCell id="em_llm" value="LiteLLM" style="rounded=1;fillColor=#0D9488;fontColor=#FFFFFF;fontSize=11;" parent="em_l4" vertex="1"><mxGeometry x="315" y="32" width="75" height="28" as="geometry"/></mxCell>
                <mxCell id="em_lf" value="Langfuse" style="rounded=1;fillColor=#6366F1;fontColor=#FFFFFF;fontSize=11;" parent="em_l4" vertex="1"><mxGeometry x="400" y="32" width="80" height="28" as="geometry"/></mxCell>

                <mxCell id="em_flows" value="Main workflows (text only — see Chat Flow / Integration Flow pages for sequences)" style="swimlane;startSize=24;fillColor=#FFF7ED;strokeColor=#EA580C;fontStyle=1;" parent="1" vertex="1">
                    <mxGeometry x="40" y="655" width="1720" height="115" as="geometry"/>
                </mxCell>
                <mxCell id="em_f1" value="Meeting → scribe → REQ → dev" style="rounded=1;fillColor=#FFEDD5;strokeColor=#EA580C;fontSize=11;whiteSpace=wrap;html=0;" parent="em_flows" vertex="1"><mxGeometry x="15" y="32" width="200" height="36" as="geometry"/></mxCell>
                <mxCell id="em_f2" value="dev → test → devops release" style="rounded=1;fillColor=#FFEDD5;strokeColor=#EA580C;fontSize=11;whiteSpace=wrap;html=0;" parent="em_flows" vertex="1"><mxGeometry x="225" y="32" width="200" height="36" as="geometry"/></mxCell>
                <mxCell id="em_f3" value="Release → marketing" style="rounded=1;fillColor=#FFEDD5;strokeColor=#EA580C;fontSize=11;whiteSpace=wrap;html=0;" parent="em_flows" vertex="1"><mxGeometry x="435" y="32" width="160" height="36" as="geometry"/></mxCell>
                <mxCell id="em_f4" value="support → new REQ → dev" style="rounded=1;fillColor=#FFEDD5;strokeColor=#EA580C;fontSize=11;whiteSpace=wrap;html=0;" parent="em_flows" vertex="1"><mxGeometry x="605" y="32" width="180" height="36" as="geometry"/></mxCell>
                <mxCell id="em_f5" value="IntegrationsHub connect" style="rounded=1;fillColor=#FFEDD5;strokeColor=#EA580C;fontSize=11;whiteSpace=wrap;html=0;" parent="em_flows" vertex="1"><mxGeometry x="795" y="32" width="170" height="36" as="geometry"/></mxCell>
                <mxCell id="em_f6" value="B2B white-label Portal B" style="rounded=1;fillColor=#FFEDD5;strokeColor=#EA580C;fontSize=11;whiteSpace=wrap;html=0;" parent="em_flows" vertex="1"><mxGeometry x="975" y="32" width="170" height="36" as="geometry"/></mxCell>
                <mxCell id="em_fnote" value="↓ read top to bottom = request path · use page tabs for detail diagrams" style="text;html=0;fillColor=none;strokeColor=none;fontColor=#9A3412;fontStyle=2;fontSize=11;" parent="em_flows" vertex="1"><mxGeometry x="15" y="72" width="500" height="18" as="geometry"/></mxCell>

                <mxCell id="em_legend" value="Legend&#10;Blue = Portal A · Green = Portal B / integrations&#10;Orange = Portal C / SRE · Purple = agents · Teal = memory + L4" style="rounded=1;fillColor=#F8FAFC;strokeColor=#CBD5E1;fontColor=#334155;align=left;spacingLeft=8;whiteSpace=wrap;html=0;fontSize=11;" parent="1" vertex="1">
                    <mxGeometry x="1180" y="400" width="580" height="238" as="geometry"/>
                </mxCell>

            </root>
        </mxGraphModel>
    </diagram>'''


def main() -> None:
    content = FILE.read_text(encoding="utf-8")
    new_content, n = re.subn(
        r'<diagram id="enterprise-master" name="Enterprise Master - Agents Features Integrations">.*?</diagram>',
        SIMPLE_MASTER.strip(),
        content,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        raise SystemExit(f"Replace failed ({n})")
    FILE.write_text(new_content, encoding="utf-8")
    edges = len(re.findall(r'edge="1"', SIMPLE_MASTER))
    print(f"Master page simplified; arrows on master page: {edges}")


if __name__ == "__main__":
    main()
