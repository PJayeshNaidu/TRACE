"""TRACE Static Code Analysis Evaluation Observatory (Streamlit Dashboard).

This dashboard provides an evaluation interface to trigger, observe, and inspect
TRACE Phase 2 (F02) repository code analysis runs via REST API endpoints.
Completely decoupled from backend internal domain and database models.
"""

import html
import json
import os
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:
    st = None  # type: ignore[assignment]
    components = None  # type: ignore[assignment]


def make_api_request(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any] | None]:
    """Execute a HTTP JSON request using standard library urllib."""
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            return status_code, json.loads(body) if body else None
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            return err.code, json.loads(body) if body else None
        except Exception:
            return err.code, {"error": body}
    except Exception as exc:
        return 0, {"error": str(exc)}


def render_graph_canvas(nodes: list[dict[str, Any]], rels: list[dict[str, Any]]) -> None:
    """Render a state-of-the-art interactive dark-mode graph canvas with HUD inspector."""
    if not nodes:
        st.info("No nodes available to visualize.")
        return

    # Modern Cyber-Neon Palette
    color_map = {
        "Module": {"bg": "#9333ea", "border": "#c084fc", "glow": "rgba(147, 51, 234, 0.45)"},
        "Class": {"bg": "#2563eb", "border": "#60a5fa", "glow": "rgba(37, 99, 235, 0.45)"},
        "Function": {"bg": "#059669", "border": "#34d399", "glow": "rgba(5, 150, 105, 0.45)"},
        "Endpoint": {"bg": "#ea580c", "border": "#fb923c", "glow": "rgba(234, 88, 12, 0.45)"},
        "DatabaseEntity": {"bg": "#dc2626", "border": "#f87171", "glow": "rgba(220, 38, 38, 0.45)"},
        "Service": {"bg": "#0891b2", "border": "#22d3ee", "glow": "rgba(8, 145, 178, 0.45)"},
        "ExternalPackage": {"bg": "#d97706", "border": "#fbbf24", "glow": "rgba(217, 119, 6, 0.45)"},
        "TestUnit": {"bg": "#475569", "border": "#94a3b8", "glow": "rgba(71, 85, 105, 0.45)"},
        "DocArtifact": {"bg": "#6b7280", "border": "#cbd5e1", "glow": "rgba(107, 114, 128, 0.45)"},
    }

    # Count node types for filter badges
    counts: dict[str, int] = {}
    for n in nodes:
        lbl = n.get("label") or n.get("type", "Unknown")
        counts[lbl] = counts.get(lbl, 0) + 1

    # Degree map for sizing
    deg_map: dict[str, int] = {}
    for r in rels:
        s = r.get("source_id") or r.get("source")
        t = r.get("target_id") or r.get("target")
        if s: deg_map[s] = deg_map.get(s, 0) + 1
        if t: deg_map[t] = deg_map.get(t, 0) + 1

    vis_nodes = []
    node_ids = set()
    for n in nodes:
        nid = n.get("id") or str(n.get("qualified_name"))
        node_ids.add(nid)
        label_type = n.get("label") or n.get("type", "Unknown")
        qual_name = n.get("qualified_name") or n.get("name") or nid
        
        # Clean display name
        if "::" in qual_name:
            short_name = qual_name.split("::")[1]
        elif "." in qual_name:
            short_name = qual_name.split(".")[-1]
        else:
            short_name = qual_name

        c_info = color_map.get(label_type, {"bg": "#64748b", "border": "#94a3b8", "glow": "rgba(100, 116, 139, 0.3)"})
        props = n.get("properties", {})
        file_path = props.get("file_path", "")
        start_line = props.get("start_line", "")
        degree = deg_map.get(nid, 0)
        
        base_size = 22 if label_type in ("Module", "Class", "Endpoint") else 14
        size = min(36, base_size + min(degree * 2, 12))

        vis_nodes.append({
            "id": nid,
            "label": str(short_name)[:22],
            "group": label_type,
            "qual_name": qual_name,
            "file_path": file_path,
            "start_line": start_line,
            "degree": degree,
            "properties": props,
            "shape": "dot",
            "size": size,
            "color": {
                "background": c_info["bg"],
                "border": c_info["border"],
                "highlight": {"background": "#38bdf8", "border": "#f0f9ff"},
                "hover": {"background": c_info["border"], "border": "#ffffff"}
            },
            "borderWidth": 2,
            "shadow": {"enabled": True, "color": c_info["glow"], "size": 8, "x": 0, "y": 0},
            "font": {
                "size": 11,
                "color": "#f8fafc",
                "face": "Inter, system-ui, -apple-system, sans-serif",
                "strokeWidth": 2,
                "strokeColor": "#0f172a"
            }
        })

    vis_edges = []
    for r in rels:
        src = r.get("source_id") or r.get("source")
        tgt = r.get("target_id") or r.get("target")
        rel_type = r.get("relationship_type") or r.get("type", "")
        if src in node_ids and tgt in node_ids:
            vis_edges.append({
                "from": src,
                "to": tgt,
                "label": rel_type,
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.65}},
                "color": {
                    "color": "rgba(148, 163, 184, 0.35)",
                    "highlight": "#38bdf8",
                    "hover": "rgba(248, 250, 252, 0.8)"
                },
                "font": {
                    "size": 9,
                    "color": "#94a3b8",
                    "face": "JetBrains Mono, monospace",
                    "strokeWidth": 2,
                    "strokeColor": "#0b0f19",
                    "align": "middle"
                },
                "smooth": {"type": "continuous", "roundness": 0.2},
                "selectionWidth": 2.5
            })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)
    counts_json = json.dumps(counts)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
      <style>
        * {{
          box-sizing: border-box;
          margin: 0;
          padding: 0;
          user-select: none;
        }}
        body {{
          background: #090d16;
          color: #f1f5f9;
          font-family: 'Inter', -apple-system, sans-serif;
          overflow: hidden;
        }}
        .graph-container {{
          position: relative;
          width: 100%;
          height: 680px;
          background: radial-gradient(circle at 50% 30%, #111827 0%, #06090f 100%);
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
          overflow: hidden;
        }}
        #network {{
          width: 100%;
          height: 100%;
        }}
        /* Floating Glassmorphism Toolbar */
        .glass-toolbar {{
          position: absolute;
          top: 14px;
          left: 14px;
          right: 14px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 14px;
          background: rgba(15, 23, 42, 0.75);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          z-index: 10;
          gap: 10px;
          flex-wrap: wrap;
        }}
        .search-box {{
          display: flex;
          align-items: center;
          background: rgba(30, 41, 59, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 6px;
          padding: 5px 10px;
          width: 220px;
          transition: all 0.2s;
        }}
        .search-box:focus-within {{
          border-color: #38bdf8;
          box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
          width: 260px;
        }}
        .search-box input {{
          background: transparent;
          border: none;
          outline: none;
          color: #f8fafc;
          font-size: 12px;
          width: 100%;
          margin-left: 6px;
          font-family: inherit;
        }}
        .search-box input::placeholder {{
          color: #64748b;
        }}
        /* Filter Pills */
        .filter-pills {{
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          align-items: center;
        }}
        .pill {{
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 3px 9px;
          border-radius: 14px;
          font-size: 11px;
          font-weight: 500;
          cursor: pointer;
          background: rgba(30, 41, 59, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #cbd5e1;
          transition: all 0.2s;
        }}
        .pill:hover {{
          transform: translateY(-1px);
          border-color: rgba(255, 255, 255, 0.25);
          color: #ffffff;
        }}
        .pill.active {{
          background: rgba(56, 189, 248, 0.15);
          border-color: #38bdf8;
          color: #38bdf8;
        }}
        .pill-dot {{
          width: 7px;
          height: 7px;
          border-radius: 50%;
        }}
        /* Controls Group */
        .controls-group {{
          display: flex;
          gap: 5px;
        }}
        .btn-ctrl {{
          background: rgba(30, 41, 59, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #94a3b8;
          border-radius: 6px;
          width: 30px;
          height: 30px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          font-size: 14px;
          transition: all 0.2s;
        }}
        .btn-ctrl:hover {{
          background: #1e293b;
          color: #f8fafc;
          border-color: #38bdf8;
        }}
        /* Modern Side HUD Inspector */
        .hud-panel {{
          position: absolute;
          bottom: 16px;
          right: 16px;
          width: 310px;
          background: rgba(15, 23, 42, 0.88);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(56, 189, 248, 0.25);
          border-radius: 12px;
          padding: 14px;
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.7);
          display: none;
          z-index: 15;
          animation: slideIn 0.25s ease-out;
        }}
        @keyframes slideIn {{
          from {{ opacity: 0; transform: translateY(12px); }}
          to {{ opacity: 1; transform: translateY(0); }}
        }}
        .hud-header {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 8px;
          margin-bottom: 10px;
        }}
        .hud-badge {{
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          padding: 2px 7px;
          border-radius: 4px;
        }}
        .hud-title {{
          font-size: 14px;
          font-weight: 700;
          color: #f8fafc;
          margin-bottom: 4px;
          word-break: break-word;
        }}
        .hud-sub {{
          font-size: 11px;
          color: #94a3b8;
          font-family: 'JetBrains Mono', monospace;
          margin-bottom: 8px;
          word-break: break-all;
        }}
        .hud-stats {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          margin-top: 8px;
        }}
        .stat-card {{
          background: rgba(30, 41, 59, 0.6);
          padding: 6px 8px;
          border-radius: 6px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .stat-card .lbl {{
          font-size: 9px;
          color: #64748b;
          text-transform: uppercase;
        }}
        .stat-card .val {{
          font-size: 12px;
          font-weight: 600;
          color: #e2e8f0;
        }}
        .hud-close {{
          cursor: pointer;
          color: #64748b;
          font-size: 16px;
          line-height: 1;
        }}
        .hud-close:hover {{
          color: #f8fafc;
        }}
        .status-pill {{
          position: absolute;
          bottom: 14px;
          left: 14px;
          font-size: 11px;
          color: #64748b;
          background: rgba(15, 23, 42, 0.7);
          padding: 4px 10px;
          border-radius: 20px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }}
      </style>
    </head>
    <body>
      <div class="graph-container">
        <!-- Floating Glass Toolbar -->
        <div class="glass-toolbar">
          <div class="search-box">
            <span style="color:#64748b; font-size:12px;">🔍</span>
            <input type="text" id="symbol-search" placeholder="Search function, class, module..." oninput="searchSymbol(this.value)"/>
          </div>

          <div class="filter-pills" id="pills-bar">
            <!-- Dynamically populated -->
          </div>

          <div class="controls-group">
            <button class="btn-ctrl" title="Zoom In" onclick="network.moveTo({{scale: network.getScale() * 1.3}})">＋</button>
            <button class="btn-ctrl" title="Zoom Out" onclick="network.moveTo({{scale: network.getScale() * 0.7}})">－</button>
            <button class="btn-ctrl" title="Fit to Screen" onclick="network.fit({{animation: {{duration: 500}}}})">🎯</button>
            <button class="btn-ctrl" id="btn-physics" title="Pause/Resume Simulation" onclick="togglePhysics()">⏸️</button>
          </div>
        </div>

        <!-- Vis Canvas -->
        <div id="network"></div>

        <!-- Node Details HUD -->
        <div class="hud-panel" id="node-hud">
          <div class="hud-header">
            <span class="hud-badge" id="hud-badge">MODULE</span>
            <span class="hud-close" onclick="closeHud()">✕</span>
          </div>
          <div class="hud-title" id="hud-title">Symbol Name</div>
          <div class="hud-sub" id="hud-path">src/module/file.py:42</div>
          <div class="hud-stats">
            <div class="stat-card">
              <div class="lbl">Connections</div>
              <div class="val" id="hud-conns">0 edges</div>
            </div>
            <div class="stat-card">
              <div class="lbl">Category</div>
              <div class="val" id="hud-group">Function</div>
            </div>
          </div>
        </div>

        <div class="status-pill" id="graph-stats">
          {len(vis_nodes)} Nodes &bull; {len(vis_edges)} Relationships
        </div>
      </div>

      <script type="text/javascript">
        var allNodes = {nodes_json};
        var allEdges = {edges_json};
        var nodeCounts = {counts_json};
        var activeGroup = null;
        var physicsEnabled = true;

        var colorPalette = {{
          "Module": {{ "bg": "#9333ea", "border": "#c084fc" }},
          "Class": {{ "bg": "#2563eb", "border": "#60a5fa" }},
          "Function": {{ "bg": "#059669", "border": "#34d399" }},
          "Endpoint": {{ "bg": "#ea580c", "border": "#fb923c" }},
          "DatabaseEntity": {{ "bg": "#dc2626", "border": "#f87171" }},
          "Service": {{ "bg": "#0891b2", "border": "#22d3ee" }},
          "ExternalPackage": {{ "bg": "#d97706", "border": "#fbbf24" }},
          "TestUnit": {{ "bg": "#475569", "border": "#94a3b8" }},
          "DocArtifact": {{ "bg": "#6b7280", "border": "#cbd5e1" }}
        }};

        // Build filter pills
        var pillsBar = document.getElementById('pills-bar');
        pillsBar.innerHTML = '<div class="pill active" id="pill-all" onclick="filterGroup(null)"><span class="pill-dot" style="background:#38bdf8"></span> All (' + allNodes.length + ')</div>';
        
        for (var grp in nodeCounts) {{
          var c = colorPalette[grp] || {{ bg: "#64748b" }};
          var p = document.createElement('div');
          p.className = 'pill';
          p.id = 'pill-' + grp;
          p.innerHTML = '<span class="pill-dot" style="background:' + c.bg + '"></span> ' + grp + ' (' + nodeCounts[grp] + ')';
          p.onclick = (function(g) {{ return function() {{ filterGroup(g); }}; }})(grp);
          pillsBar.appendChild(p);
        }}

        var nodesDataSet = new vis.DataSet(allNodes);
        var edgesDataSet = new vis.DataSet(allEdges);

        var container = document.getElementById('network');
        var data = {{ nodes: nodesDataSet, edges: edgesDataSet }};

        var options = {{
          nodes: {{
            shape: 'dot',
            scaling: {{ min: 10, max: 36 }}
          }},
          edges: {{
            arrows: {{ to: {{ enabled: true, scaleFactor: 0.65 }} }},
            smooth: {{ type: 'continuous', roundness: 0.2 }}
          }},
          physics: {{
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {{
              gravitationalConstant: -40,
              centralGravity: 0.006,
              springLength: 85,
              springConstant: 0.15,
              damping: 0.85
            }},
            maxVelocity: 45,
            stabilization: {{ iterations: 140 }}
          }},
          interaction: {{
            hover: true,
            tooltipDelay: 100,
            navigationButtons: false,
            keyboard: true,
            zoomView: true
          }}
        }};

        var network = new vis.Network(container, data, options);

        // Click Inspector
        network.on("click", function(params) {{
          if (params.nodes.length > 0) {{
            var nodeId = params.nodes[0];
            var nodeData = nodesDataSet.get(nodeId);
            if (nodeData) {{
              showHud(nodeData);
            }}
          }} else {{
            closeHud();
          }}
        }});

        function showHud(node) {{
          var hud = document.getElementById('node-hud');
          var badge = document.getElementById('hud-badge');
          var title = document.getElementById('hud-title');
          var path = document.getElementById('hud-path');
          var conns = document.getElementById('hud-conns');
          var group = document.getElementById('hud-group');

          var c = colorPalette[node.group] || {{ bg: "#38bdf8", border: "#f0f9ff" }};
          badge.style.background = c.bg;
          badge.style.color = "#ffffff";
          badge.innerText = node.group;

          title.innerText = node.qual_name || node.label;
          path.innerText = (node.file_path || "in-memory") + (node.start_line ? ":" + node.start_line : "");
          conns.innerText = (node.degree || 0) + " edges";
          group.innerText = node.group;

          hud.style.display = "block";
        }}

        function closeHud() {{
          document.getElementById('node-hud').style.display = "none";
        }}

        function togglePhysics() {{
          physicsEnabled = !physicsEnabled;
          network.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
          var btn = document.getElementById('btn-physics');
          btn.innerText = physicsEnabled ? '⏸️' : '▶️';
        }}

        function searchSymbol(query) {{
          if (!query || query.trim() === '') {{
            network.fit({{ animation: {{ duration: 300 }} }});
            return;
          }}
          var q = query.toLowerCase().trim();
          var matched = allNodes.filter(function(n) {{
            return (n.qual_name && n.qual_name.toLowerCase().indexOf(q) !== -1) ||
                   (n.label && n.label.toLowerCase().indexOf(q) !== -1);
          }});

          if (matched.length > 0) {{
            var targetId = matched[0].id;
            network.focus(targetId, {{
              scale: 1.4,
              animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }}
            }});
            network.selectNodes([targetId]);
            showHud(matched[0]);
          }}
        }}

        function filterGroup(groupName) {{
          activeGroup = groupName;
          
          // Update active pill styling
          var pills = document.querySelectorAll('.pill');
          pills.forEach(function(p) {{ p.classList.remove('active'); }});
          if (!groupName) {{
            document.getElementById('pill-all').classList.add('active');
          }} else {{
            var activePill = document.getElementById('pill-' + groupName);
            if (activePill) activePill.classList.add('active');
          }}

          if (!groupName) {{
            nodesDataSet.clear();
            nodesDataSet.add(allNodes);
            edgesDataSet.clear();
            edgesDataSet.add(allEdges);
          }} else {{
            var groupNodes = allNodes.filter(function(n) {{ return n.group === groupName; }});
            var groupNodeIds = new Set(groupNodes.map(function(n) {{ return n.id; }}));
            
            // Edges connected to this group
            var connectedEdges = allEdges.filter(function(e) {{
              return groupNodeIds.has(e.from) || groupNodeIds.has(e.to);
            }});
            
            // Ensure both endpoints exist in nodesDataSet so vis-network can draw all edges!
            var visibleNodeIds = new Set(groupNodeIds);
            connectedEdges.forEach(function(e) {{
              visibleNodeIds.add(e.from);
              visibleNodeIds.add(e.to);
            }});
            
            var visibleNodes = allNodes.filter(function(n) {{ return visibleNodeIds.has(n.id); }});

            nodesDataSet.clear();
            nodesDataSet.add(visibleNodes);
            edgesDataSet.clear();
            edgesDataSet.add(connectedEdges);
          }}
          network.fit({{ animation: {{ duration: 400 }} }});
        }}
      </script>
    </body>
    </html>
    """
    if components is not None:
        components.html(html_code, height=710)
    else:
        st.warning("Streamlit HTML components not available.")


def render_html(html_str: str) -> None:
    """Render HTML safely in Streamlit by dedenting to column 0, preventing CommonMark code block leaks."""
    if not html_str:
        return
    cleaned = textwrap.dedent(html_str).strip()
    if st is not None:
        st.markdown(cleaned, unsafe_allow_html=True)


def inject_neo_brutalist_css(theme_mode: str = "light") -> None:
    """Inject high-contrast Neo-Brutalist design system CSS into the Streamlit app."""
    is_dark = theme_mode.lower() == "dark"

    if is_dark:
        theme_vars = """
        :root {
          --nb-bg: #09090B;
          --nb-surface: #18181B;
          --nb-surface-card: #18181B;
          --nb-surface-alt: #27272A;
          --nb-tab-bg: #18181B;
          --nb-tab-hover-bg: #27272A;
          --nb-tab-active-bg: #CCFF00;
          --nb-tab-active-text: #000000;
          --nb-text: #FAFAFA;
          --nb-text-muted: #D4D4D8;
          --nb-text-subtle: #A1A1AA;
          --nb-border: #FFFFFF;
          --nb-border-interactive: #FFFFFF;
          --nb-shadow: 3px 3px 0px #FFFFFF;
          --nb-shadow-lg: 4px 4px 0px #FFFFFF;
          --nb-shadow-sm: 2px 2px 0px #FFFFFF;
          --nb-shadow-hover: 2px 2px 0px #FFFFFF;
          --nb-shadow-active: 0px 0px 0px #FFFFFF;
          --nb-accent-yellow: #FACC15;
          --nb-accent-lime: #CCFF00;
          --nb-accent-blue: #3B82F6;
          --nb-accent-red: #EF4444;
          --nb-accent-green: #22C55E;
          --nb-code-bg: #27272A;
          --nb-code-text: #F8FAFC;
          --bg-canvas: #09090B;
          --card-bg: #18181B;
          --border-color: #FFFFFF;
          --shadow-color: #FFFFFF;
          --text-primary: #FAFAFA;
          --text-secondary: #D4D4D8;
        }
        """
    else:
        theme_vars = """
        :root {
          --nb-bg: #FAF9F5;
          --nb-surface: #FFFFFF;
          --nb-surface-card: #FFFFFF;
          --nb-surface-alt: #F4F4F5;
          --nb-tab-bg: #FFFFFF;
          --nb-tab-hover-bg: #F4F4F5;
          --nb-tab-active-bg: #CCFF00;
          --nb-tab-active-text: #000000;
          --nb-text: #000000;
          --nb-text-muted: #27272A;
          --nb-text-subtle: #52525B;
          --nb-border: #000000;
          --nb-border-interactive: #000000;
          --nb-shadow: 3px 3px 0px #000000;
          --nb-shadow-lg: 4px 4px 0px #000000;
          --nb-shadow-sm: 2px 2px 0px #000000;
          --nb-shadow-hover: 2px 2px 0px #000000;
          --nb-shadow-active: 0px 0px 0px #000000;
          --nb-accent-yellow: #FACC15;
          --nb-accent-lime: #CCFF00;
          --nb-accent-blue: #2563EB;
          --nb-accent-red: #DC2626;
          --nb-accent-green: #16A34A;
          --nb-code-bg: #F1F5F9;
          --nb-code-text: #000000;
          --bg-canvas: #FAF9F5;
          --card-bg: #FFFFFF;
          --border-color: #000000;
          --shadow-color: #000000;
          --text-primary: #09090B;
          --text-secondary: #27272A;
        }
        """

    css_code = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700;800&display=swap');

    {theme_vars}

    /* Enforce 90-degree Sharp Corners across ALL UI elements */
    *, *::before, *::after {{
      border-radius: 0px !important;
    }}

    /* Core Application Canvas */
    .stApp {{
      background-color: var(--nb-bg) !important;
      color: var(--nb-text) !important;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }}

    [data-testid="stAppViewContainer"] {{
      background-color: var(--nb-bg) !important;
    }}

    [data-testid="stHeader"] {{
      background-color: var(--nb-bg) !important;
    }}

    /* Sidebar - Neo-Brutalist Frame */
    [data-testid="stSidebar"] {{
      background-color: var(--nb-surface) !important;
      border-right: 2px solid var(--nb-border) !important;
    }}

    [data-testid="stSidebar"] hr {{
      border-color: var(--nb-border) !important;
    }}

    /* Typography - Strict Headings */
    h1, h2, h3, h4, h5, h6 {{
      font-family: 'Inter', -apple-system, sans-serif !important;
      font-weight: 800 !important;
      color: var(--nb-text) !important;
      letter-spacing: -0.4px !important;
    }}

    /* Protect Streamlit Material Symbols & Icon Ligatures */
    [data-testid="stIconMaterial"],
    [data-testid="stExpander"] summary svg,
    button svg,
    [data-testid="stExpander"] summary span[data-testid="stIconMaterial"],
    [data-testid="stExpander"] summary span:has(svg),
    button [data-testid="stIconMaterial"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons,
    [data-testid="stIconMaterial"] * {{
      font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
    }}

    /* Widget Labels & Captions (Explicit High Contrast) */
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] div[role="radiogroup"] label,
    [data-testid="stCaptionContainer"] p,
    .stCaption {{
      color: var(--nb-text) !important;
      font-weight: 700 !important;
      font-family: 'Inter', sans-serif !important;
      font-size: 0.88rem !important;
      letter-spacing: 0.2px !important;
    }}

    [data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {{
      border: 2px solid var(--nb-border) !important;
      background-color: var(--nb-surface) !important;
      border-radius: 0px !important;
    }}

    /* Monospace elements */
    code, pre, kbd, samp {{
      font-family: 'JetBrains Mono', Consolas, 'Courier New', monospace !important;
    }}

    code {{
      background-color: var(--nb-code-bg) !important;
      color: var(--nb-code-text) !important;
      border: 1.5px solid var(--nb-border) !important;
      border-radius: 0px !important;
      padding: 1px 5px !important;
      font-size: 0.88em !important;
      font-weight: 700 !important;
    }}

    /* Buttons - Solid crisp borders, hard offset shadows, zero diffuse blur */
    .stButton > button,
    [data-testid="stDownloadButton"] > button,
    .stFormSubmitButton > button {{
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      font-weight: 800 !important;
      font-family: 'Inter', sans-serif !important;
      letter-spacing: 0.3px !important;
      text-transform: uppercase !important;
      box-shadow: var(--nb-shadow) !important;
      transition: transform 0.08s ease, box-shadow 0.08s ease !important;
    }}

    .stButton > button:hover,
    [data-testid="stDownloadButton"] > button:hover,
    .stFormSubmitButton > button:hover {{
      transform: translate(1px, 1px) !important;
      box-shadow: var(--nb-shadow-hover) !important;
    }}

    .stButton > button:active,
    [data-testid="stDownloadButton"] > button:active,
    .stFormSubmitButton > button:active {{
      transform: translate(3px, 3px) !important;
      box-shadow: var(--nb-shadow-active) !important;
    }}

    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {{
      background-color: #2563EB !important;
      color: #FFFFFF !important;
      border: 2px solid var(--nb-border) !important;
      box-shadow: var(--nb-shadow) !important;
      border-radius: 0px !important;
    }}

    .stButton > button[kind="secondary"] {{
      background-color: var(--nb-surface) !important;
      color: var(--nb-text) !important;
      border-color: var(--nb-border) !important;
    }}

    /* Form Controls & Inputs */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] > div > div {{
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      background-color: var(--nb-surface) !important;
      color: var(--nb-text) !important;
      box-shadow: var(--nb-shadow-sm) !important;
      font-family: 'JetBrains Mono', Consolas, monospace !important;
      font-size: 0.88rem !important;
      font-weight: 600 !important;
    }}

    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {{
      border-color: var(--nb-accent-blue) !important;
      box-shadow: 2px 2px 0px var(--nb-accent-blue) !important;
    }}

    /* Disabled Text Inputs (Explicit High Contrast) */
    [data-testid="stTextInput"] input:disabled {{
      background-color: var(--nb-code-bg) !important;
      color: var(--nb-text-muted) !important;
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      opacity: 1 !important;
      cursor: not-allowed;
    }}

    /* Targeted Streamlit BaseWeb Tab CSS - Authentic Neo-Brutalist Rectangular Button Tiles */
    [data-testid="stTabs"] {{
      border: none !important;
    }}

    [data-testid="stTabs"] [data-baseweb="tab-list"],
    [data-testid="stTabs"] div[data-baseweb="tab-list"],
    div[data-baseweb="tab-list"],
    [data-testid="stTabs"] [role="tablist"] {{
      background-color: transparent !important;
      border-bottom: none !important;
      border: none !important;
      box-shadow: none !important;
      gap: 14px !important;
      padding: 8px 0px 20px 0px !important;
      display: flex !important;
      flex-wrap: wrap !important;
    }}

    /* Hide default tab highlight bar and border line */
    [data-testid="stTabs"] [data-baseweb="tab-highlight"],
    [data-testid="stTabs"] div[data-baseweb="tab-highlight"],
    div[data-baseweb="tab-highlight"],
    [data-testid="stTabs"] [data-baseweb="tab-border"],
    [data-testid="stTabs"] div[data-baseweb="tab-border"],
    div[data-baseweb="tab-border"] {{
      display: none !important;
      background-color: transparent !important;
      height: 0px !important;
      width: 0px !important;
      border: none !important;
    }}

    /* Inactive Tab: Crisp White Box with 2px Border and Hard Shadow */
    [data-testid="stTabs"] button[data-baseweb="tab"],
    button[data-baseweb="tab"],
    [data-testid="stTabs"] [role="tab"],
    [data-testid="stTabs"] button[role="tab"] {{
      background-color: var(--nb-tab-bg) !important;
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      box-shadow: var(--nb-shadow) !important;
      color: var(--nb-text) !important;
      font-weight: 700 !important;
      font-family: 'Inter', -apple-system, sans-serif !important;
      font-size: 0.92rem !important;
      letter-spacing: 0.3px !important;
      padding: 10px 22px !important;
      height: auto !important;
      margin: 0px !important;
      transition: transform 0.08s ease, box-shadow 0.08s ease !important;
      text-align: center !important;
    }}

    [data-testid="stTabs"] button[data-baseweb="tab"]:hover,
    button[data-baseweb="tab"]:hover,
    [data-testid="stTabs"] [role="tab"]:hover,
    [data-testid="stTabs"] button[role="tab"]:hover:not([aria-selected="true"]) {{
      background-color: var(--nb-tab-hover-bg) !important;
      color: var(--nb-text) !important;
      transform: translate(1px, 1px) !important;
      box-shadow: var(--nb-shadow-hover) !important;
    }}

    /* Active Selected Tab: Bright Neo-Brutalist Highlight Tile (Lime/Volt) */
    [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
    button[data-baseweb="tab"][aria-selected="true"],
    [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
      background-color: #CCFF00 !important; /* Vivid Neo-brutalist Lime */
      color: #000000 !important;
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      box-shadow: 1px 1px 0px var(--nb-border) !important;
      transform: translate(2px, 2px) !important;
      font-weight: 800 !important;
    }}

    /* Ensure inner tab text inherits color and removes red accent */
    [data-testid="stTabs"] [role="tab"] p,
    [data-testid="stTabs"] [role="tab"] span,
    [data-testid="stTabs"] button[data-baseweb="tab"] p,
    [data-testid="stTabs"] button[data-baseweb="tab"] span {{
      color: inherit !important;
      font-weight: inherit !important;
    }}

    /* Expanders */
    [data-testid="stExpander"] {{
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      background-color: var(--nb-surface) !important;
      box-shadow: var(--nb-shadow) !important;
      margin-bottom: 14px !important;
    }}

    [data-testid="stExpander"] details summary p {{
      font-weight: 800 !important;
      font-family: 'Inter', sans-serif !important;
      color: var(--nb-text) !important;
      font-size: 0.92rem !important;
    }}

    [data-testid="stExpander"] details summary svg {{
      fill: var(--nb-text) !important;
    }}

    /* Metrics */
    [data-testid="stMetric"] {{
      background-color: var(--nb-surface) !important;
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      box-shadow: var(--nb-shadow) !important;
      padding: 10px 14px !important;
    }}

    [data-testid="stMetricValue"] {{
      font-family: 'JetBrains Mono', Consolas, monospace !important;
      font-weight: 800 !important;
      color: var(--nb-text) !important;
      font-size: 1.5rem !important;
    }}

    [data-testid="stMetricLabel"] {{
      font-family: 'Inter', sans-serif !important;
      font-weight: 800 !important;
      text-transform: uppercase !important;
      font-size: 0.72rem !important;
      letter-spacing: 0.5px !important;
      color: var(--nb-text-muted) !important;
    }}

    /* Alerts */
    [data-testid="stAlert"] {{
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      box-shadow: var(--nb-shadow) !important;
      color: var(--nb-text) !important;
      font-weight: 700 !important;
    }}

    /* Dataframe containers */
    [data-testid="stDataFrame"] {{
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      box-shadow: var(--nb-shadow) !important;
      background: var(--nb-surface) !important;
    }}

    /* Progress bar */
    [data-testid="stProgress"] > div {{
      border: 2px solid var(--nb-border) !important;
      border-radius: 0px !important;
      background-color: var(--nb-surface) !important;
      height: 16px !important;
    }}

    [data-testid="stProgress"] > div > div {{
      background-color: var(--nb-accent-blue) !important;
      border-radius: 0px !important;
    }}

    /* Framed Vertical Block Containers */
    [data-testid="stVerticalBlockBorderWrapper"] > div {{
      background-color: var(--nb-surface) !important;
      border: 2px solid var(--nb-border) !important;
      box-shadow: var(--nb-shadow-lg) !important;
      border-radius: 0px !important;
      padding: 16px 20px !important;
      margin-bottom: 20px !important;
    }}

    /* Dividers */
    hr {{
      border-color: var(--nb-border) !important;
      border-width: 1.5px !important;
      opacity: 1 !important;
    }}
    </style>
    """
    render_html(css_code)


def render_colored_diff(file_diff: dict[str, Any]) -> str:
    """Render a clean neo-brutalist unified diff with crisp borders, green additions, and red deletions."""
    hunks = file_diff.get("hunks", [])
    if not hunks:
        return (
            '<div style="color: var(--nb-text-muted); font-style: italic; padding: 12px; '
            'border: 1.5px solid var(--nb-border); border-radius: 0px; background: var(--nb-surface);">'
            'No line hunks available for this file.</div>'
        )

    html_parts = [
        '<div style="font-family: \'JetBrains Mono\', Consolas, monospace; font-size: 12px; '
        'background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 0px; '
        'overflow-x: auto; margin: 8px 0 16px 0; box-shadow: var(--nb-shadow);">'
    ]

    for h_idx, h in enumerate(hunks, 1):
        old_start = h.get("old_start", 0)
        old_lines = h.get("old_lines", 0)
        new_start = h.get("new_start", 0)
        new_lines = h.get("new_lines", 0)
        header_text = h.get("header", "").strip()

        context_str = f" &bull; <span style='font-weight: 700;'>{html.escape(header_text)}</span>" if header_text else ""
        top_border = "1.5px solid var(--nb-border)" if h_idx > 1 else "none"

        html_parts.append(
            f'<div style="background: var(--nb-code-bg); color: var(--nb-text); padding: 8px 12px; '
            f'font-weight: 700; font-size: 11px; border-bottom: 1.5px solid var(--nb-border); '
            f'border-top: {top_border}; '
            f'display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">'
            f'<div><span>Hunk #{h_idx}: Lines {new_start}–{new_start + max(0, new_lines - 1)}</span>{context_str}</div>'
            f'<div style="font-size: 11px; font-weight: 700; font-family: monospace;">'
            f'<span style="color: #dc2626;">-{old_start},{old_lines}</span> / '
            f'<span style="color: #16a34a;">+{new_start},{new_lines}</span>'
            f'</div>'
            f'</div>'
        )

        content = h.get("content", "")
        if not content:
            continue

        old_ptr = old_start
        new_ptr = new_start

        html_parts.append('<table style="width: 100%; border-collapse: collapse; table-layout: fixed;">')

        for raw_line in content.splitlines():
            line_str = html.escape(raw_line)
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                bg = "rgba(22, 163, 74, 0.12)"
                text_color = "#15803d"
                border_style = "border-left: 4px solid #16a34a;"
                old_num = ""
                new_num = str(new_ptr)
                new_ptr += 1
                sym = "+"
                code_text = line_str[1:] if len(line_str) > 1 else ""
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                bg = "rgba(220, 38, 38, 0.12)"
                text_color = "#b91c1c"
                border_style = "border-left: 4px solid #dc2626;"
                old_num = str(old_ptr)
                new_num = ""
                old_ptr += 1
                sym = "-"
                code_text = line_str[1:] if len(line_str) > 1 else ""
            else:
                bg = "transparent"
                text_color = "var(--nb-text)"
                border_style = "border-left: 4px solid transparent;"
                old_num = str(old_ptr)
                new_num = str(new_ptr)
                old_ptr += 1
                new_ptr += 1
                sym = " "
                code_text = line_str[1:] if (len(line_str) > 1 and raw_line.startswith(" ")) else line_str

            html_parts.append(
                f'<tr style="background: {bg}; {border_style}; line-height: 20px;">'
                f'<td style="width: 42px; text-align: right; padding: 0 6px; color: var(--nb-text-muted); user-select: none; font-size: 11px; border-right: 1px solid var(--nb-border); font-family: monospace;">{old_num}</td>'
                f'<td style="width: 42px; text-align: right; padding: 0 6px; color: var(--nb-text-muted); user-select: none; font-size: 11px; border-right: 1px solid var(--nb-border); font-family: monospace;">{new_num}</td>'
                f'<td style="width: 20px; text-align: center; color: {text_color}; font-weight: 700; user-select: none; font-family: monospace;">{sym}</td>'
                f'<td style="padding: 2px 8px; color: {text_color}; white-space: pre-wrap; word-break: break-all; font-family: \'JetBrains Mono\', monospace; font-size: 12px;">{code_text}</td>'
                f'</tr>'
            )

        html_parts.append('</table>')

    html_parts.append('</div>')
    return "".join(html_parts)


def build_impact_graph_json(d_detail: dict[str, Any]) -> dict[str, Any]:
    """Construct a complete, deduplicated structured JSON graph representing code changes and blast radius."""
    sym_diffs = d_detail.get("symbol_diffs", [])
    blast_items = d_detail.get("blast_radius", [])
    summ = d_detail.get("summary", {})

    nodes_dict: dict[str, dict[str, Any]] = {}
    name_to_node_id: dict[str, str] = {}
    edges_list: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    # Helper to clean qualified names from Neo4j identifiers
    def _clean_qual_name(raw_name: str) -> str:
        if not raw_name:
            return ""
        # Handle format: Function::main.calculate_total::uuid
        if "::" in raw_name:
            parts = [p for p in raw_name.split("::") if p and not (len(p) == 36 and "-" in p)]
            if len(parts) >= 2:
                return parts[1]
            return parts[0]
        return raw_name.removeprefix("sym:").removeprefix("func:").removeprefix("class:")

    # 1. Add changed & breaking symbol nodes (highest priority)
    for s in sym_diffs:
        qual_name = _clean_qual_name(s.get("qualified_name") or "")
        sid = s.get("symbol_id") or f"func:{qual_name}"
        is_breaking = s.get("is_breaking", False)
        ch_kind = s.get("change_kind", "MODIFIED")

        category = "Breaking Change" if is_breaking else "Changed Symbol"
        status = "BREAKING" if is_breaking else ch_kind

        short_name = qual_name.split(".")[-1] if "." in qual_name else qual_name

        nodes_dict[sid] = {
            "id": sid,
            "label": str(short_name)[:24],
            "qualified_name": qual_name or s.get("qualified_name"),
            "kind": s.get("kind", "symbol"),
            "category": category,
            "status": status,
            "file_path": s.get("file_path", ""),
            "is_breaking": is_breaking,
            "breaking_reason": s.get("breaking_reason"),
            "old_signature": s.get("old_signature"),
            "new_signature": s.get("new_signature"),
        }
        if qual_name:
            name_to_node_id[qual_name] = sid
            name_to_node_id[qual_name.lower()] = sid
            name_to_node_id[short_name] = sid

    # 2. Add affected blast radius nodes (only if not already present) & connect edges
    for b in blast_items:
        raw_aff_name = b.get("affected_qualified_name") or b.get("affected_symbol_id", "")
        aff_name = _clean_qual_name(raw_aff_name)
        short_aff = aff_name.split(".")[-1] if "." in aff_name else aff_name
        rel_kind = b.get("relationship_kind", "DEPENDS_ON")

        # Skip non-code relationships
        if rel_kind in ("DOCUMENTED_BY", "DEFINED_IN"):
            continue

        # Check if node already exists as a changed/breaking symbol or previously registered dependent
        if aff_name in name_to_node_id:
            src_id = name_to_node_id[aff_name]
        elif aff_name.lower() in name_to_node_id:
            src_id = name_to_node_id[aff_name.lower()]
        elif short_aff in name_to_node_id:
            src_id = name_to_node_id[short_aff]
        else:
            # Create new Impacted Dependent node
            aff_kind = (b.get("affected_kind") or "symbol").lower()
            prefix = "func" if "function" in aff_kind else ("class" if "class" in aff_kind else "sym")
            src_id = f"{prefix}:{aff_name}" if not aff_name.startswith(f"{prefix}:") else aff_name

            nodes_dict[src_id] = {
                "id": src_id,
                "label": str(short_aff)[:24],
                "qualified_name": aff_name,
                "kind": b.get("affected_kind", "Component"),
                "category": "Impacted Dependent",
                "status": "AFFECTED",
                "file_path": b.get("affected_file_path", ""),
                "is_breaking": False,
                "breaking_reason": None,
                "old_signature": None,
                "new_signature": None,
            }
            name_to_node_id[aff_name] = src_id
            name_to_node_id[aff_name.lower()] = src_id

        # Resolve target node ID
        raw_t_id = b.get("target_symbol_id", "")
        clean_t_name = _clean_qual_name(raw_t_id)
        if raw_t_id in nodes_dict:
            tgt_id = raw_t_id
        elif clean_t_name in name_to_node_id:
            tgt_id = name_to_node_id[clean_t_name]
        elif clean_t_name.split(".")[-1] in name_to_node_id:
            tgt_id = name_to_node_id[clean_t_name.split(".")[-1]]
        else:
            tgt_id = raw_t_id

        # Skip self-loops or duplicate edges
        if src_id and tgt_id and src_id != tgt_id:
            edge_key = (src_id, tgt_id, rel_kind)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges_list.append({
                    "from": src_id,
                    "to": tgt_id,
                    "relationship": rel_kind,
                    "depth": b.get("depth", 1),
                })

    return {
        "comparison_metadata": {
            "comparison_id": d_detail.get("comparison_id"),
            "repository_id": d_detail.get("repository_id"),
            "base_ref": d_detail.get("base_ref"),
            "target_ref": d_detail.get("target_ref"),
            "base_commit_hash": d_detail.get("base_commit_hash"),
            "target_commit_hash": d_detail.get("target_commit_hash"),
            "risk_level": d_detail.get("risk_level", "LOW"),
            "created_at": d_detail.get("created_at"),
        },
        "summary": {
            "total_files_changed": summ.get("total_files_changed", 0),
            "total_insertions": summ.get("total_insertions", 0),
            "total_deletions": summ.get("total_deletions", 0),
            "total_symbols_changed": summ.get("total_symbols_changed", 0),
            "total_breaking_changes": summ.get("total_breaking_changes", 0),
            "total_blast_radius_impacted": len(blast_items),
        },
        "graph": {
            "nodes_count": len(nodes_dict),
            "edges_count": len(edges_list),
            "nodes": list(nodes_dict.values()),
            "edges": edges_list,
        },
    }


def render_impact_graph_canvas(d_detail: dict[str, Any]) -> None:
    """Render interactive change impact & blast radius graph canvas with visual risk indicators."""
    graph_data = build_impact_graph_json(d_detail)
    raw_nodes = graph_data["graph"]["nodes"]
    raw_edges = graph_data["graph"]["edges"]

    if not raw_nodes:
        st.info("No symbol changes or blast radius dependents available to visualize for this comparison.")
        return

    # Modern Cyber-Neon Palette for Impact Categories
    cat_colors = {
        "Breaking Change": {"bg": "#dc2626", "border": "#f87171", "glow": "rgba(220, 38, 38, 0.7)"},
        "Changed Symbol": {"bg": "#d97706", "border": "#fbbf24", "glow": "rgba(217, 119, 6, 0.5)"},
        "Impacted Dependent": {"bg": "#9333ea", "border": "#c084fc", "glow": "rgba(147, 51, 234, 0.5)"},
    }

    counts: dict[str, int] = {}
    for n in raw_nodes:
        c = n.get("category", "Changed Symbol")
        counts[c] = counts.get(c, 0) + 1

    vis_nodes = []
    node_ids = set()
    for n in raw_nodes:
        nid = n["id"]
        node_ids.add(nid)
        cat = n.get("category", "Changed Symbol")
        c_info = cat_colors.get(cat, {"bg": "#64748b", "border": "#94a3b8", "glow": "rgba(100, 116, 139, 0.4)"})
        
        base_size = 26 if cat == "Breaking Change" else (20 if cat == "Changed Symbol" else 15)

        vis_nodes.append({
            "id": nid,
            "label": n["label"],
            "group": cat,
            "qual_name": n["qualified_name"],
            "kind": n.get("kind", "symbol"),
            "status": n.get("status", "MODIFIED"),
            "file_path": n.get("file_path", ""),
            "is_breaking": n.get("is_breaking", False),
            "breaking_reason": n.get("breaking_reason") or "",
            "old_signature": n.get("old_signature") or "",
            "new_signature": n.get("new_signature") or "",
            "shape": "dot",
            "size": base_size,
            "color": {
                "background": c_info["bg"],
                "border": c_info["border"],
                "highlight": {"background": "#38bdf8", "border": "#ffffff"},
                "hover": {"background": c_info["border"], "border": "#ffffff"}
            },
            "borderWidth": 3 if n.get("is_breaking") else 2,
            "shadow": {"enabled": True, "color": c_info["glow"], "size": 10, "x": 0, "y": 0},
            "font": {
                "size": 11,
                "color": "#f8fafc",
                "face": "Inter, system-ui, sans-serif",
                "strokeWidth": 2,
                "strokeColor": "#0b0f19"
            }
        })

    vis_edges = []
    for e in raw_edges:
        src = e["from"]
        tgt = e["to"]
        if src in node_ids and tgt in node_ids:
            vis_edges.append({
                "from": src,
                "to": tgt,
                "label": e.get("relationship", "DEPENDS_ON"),
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}},
                "color": {
                    "color": "rgba(168, 85, 247, 0.55)",
                    "highlight": "#38bdf8",
                    "hover": "rgba(255, 255, 255, 0.9)"
                },
                "font": {
                    "size": 9,
                    "color": "#cbd5e1",
                    "face": "JetBrains Mono, monospace",
                    "strokeWidth": 2,
                    "strokeColor": "#0b0f19",
                    "align": "middle"
                },
                "smooth": {"type": "continuous", "roundness": 0.2},
                "selectionWidth": 3
            })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)
    counts_json = json.dumps(counts)

    canvas_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; user-select: none; }}
        body {{ background: #090d16; color: #f1f5f9; font-family: 'Inter', sans-serif; overflow: hidden; }}
        .graph-container {{
          position: relative;
          width: 100%;
          height: 650px;
          background: radial-gradient(circle at 50% 30%, #111827 0%, #06090f 100%);
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
          overflow: hidden;
        }}
        #impact-network {{ width: 100%; height: 100%; }}
        .glass-toolbar {{
          position: absolute;
          top: 14px; left: 14px; right: 14px;
          display: flex; align-items: center; justify-content: space-between;
          padding: 8px 14px;
          background: rgba(15, 23, 42, 0.8);
          backdrop-filter: blur(16px);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          z-index: 10; gap: 10px; flex-wrap: wrap;
        }}
        .search-box {{
          display: flex; align-items: center;
          background: rgba(30, 41, 59, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 6px; padding: 5px 10px; width: 220px; transition: all 0.2s;
        }}
        .search-box:focus-within {{
          border-color: #38bdf8;
          box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
          width: 260px;
        }}
        .search-box input {{
          background: transparent; border: none; outline: none;
          color: #f8fafc; font-size: 12px; width: 100%; margin-left: 6px; font-family: inherit;
        }}
        .filter-pills {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
        .pill {{
          display: inline-flex; align-items: center; gap: 5px;
          padding: 3px 9px; border-radius: 14px; font-size: 11px; font-weight: 500; cursor: pointer;
          background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); color: #cbd5e1; transition: all 0.2s;
        }}
        .pill:hover {{ transform: translateY(-1px); border-color: rgba(255, 255, 255, 0.25); color: #fff; }}
        .pill.active {{ background: rgba(56, 189, 248, 0.18); border-color: #38bdf8; color: #38bdf8; }}
        .pill-dot {{ width: 7px; height: 7px; border-radius: 50%; }}
        .controls-group {{ display: flex; gap: 5px; }}
        .btn-ctrl {{
          background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.1);
          color: #94a3b8; border-radius: 6px; width: 30px; height: 30px;
          display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 14px; transition: all 0.2s;
        }}
        .btn-ctrl:hover {{ background: #1e293b; color: #f8fafc; border-color: #38bdf8; }}
        .hud-panel {{
          position: absolute; bottom: 16px; right: 16px; width: 330px;
          background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(20px);
          border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px;
          padding: 14px; box-shadow: 0 12px 30px rgba(0, 0, 0, 0.7); display: none; z-index: 15;
          animation: slideIn 0.25s ease-out;
        }}
        @keyframes slideIn {{ from {{ opacity: 0; transform: translateY(12px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .hud-header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 8px; margin-bottom: 10px; }}
        .hud-badge {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding: 2px 8px; border-radius: 4px; }}
        .hud-title {{ font-size: 14px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; word-break: break-word; }}
        .hud-sub {{ font-size: 11px; color: #94a3b8; font-family: 'JetBrains Mono', monospace; margin-bottom: 8px; word-break: break-all; }}
        .hud-reason {{ background: rgba(239, 68, 68, 0.15); border-left: 3px solid #ef4444; padding: 6px 10px; border-radius: 0 6px 6px 0; color: #fca5a5; font-size: 11px; margin-top: 6px; }}
        .hud-close {{ cursor: pointer; color: #64748b; font-size: 16px; }}
        .hud-close:hover {{ color: #f8fafc; }}
        .status-pill {{
          position: absolute; bottom: 14px; left: 14px; font-size: 11px; color: #94a3b8;
          background: rgba(15, 23, 42, 0.75); padding: 4px 12px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.08);
        }}
      </style>
    </head>
    <body>
      <div class="graph-container">
        <div class="glass-toolbar">
          <div class="search-box">
            <span style="color:#64748b; font-size:12px;">🔍</span>
            <input type="text" id="symbol-search" placeholder="Search changed/affected node..." oninput="searchImpactSymbol(this.value)"/>
          </div>
          <div class="filter-pills" id="pills-bar"></div>
          <div class="controls-group">
            <button class="btn-ctrl" title="Zoom In" onclick="impactNetwork.moveTo({{scale: impactNetwork.getScale() * 1.3}})">＋</button>
            <button class="btn-ctrl" title="Zoom Out" onclick="impactNetwork.moveTo({{scale: impactNetwork.getScale() * 0.7}})">－</button>
            <button class="btn-ctrl" title="Fit to Screen" onclick="impactNetwork.fit({{animation: {{duration: 500}}}})">🎯</button>
            <button class="btn-ctrl" id="btn-physics" title="Pause/Resume Simulation" onclick="toggleImpactPhysics()">⏸️</button>
          </div>
        </div>

        <div id="impact-network"></div>

        <div class="hud-panel" id="node-hud">
          <div class="hud-header">
            <span class="hud-badge" id="hud-badge">BREAKING</span>
            <span class="hud-close" onclick="closeImpactHud()">✕</span>
          </div>
          <div class="hud-title" id="hud-title">Symbol Name</div>
          <div class="hud-sub" id="hud-path">src/file.py</div>
          <div id="hud-reason" class="hud-reason" style="display:none;"></div>
          <div style="font-size: 10px; color: #64748b; margin-top: 8px;" id="hud-kind">Kind: Function</div>
        </div>

        <div class="status-pill" id="graph-stats">
          {len(vis_nodes)} Impact Nodes &bull; {len(vis_edges)} Dependency Edges
        </div>
      </div>

      <script type="text/javascript">
        var allNodes = {nodes_json};
        var allEdges = {edges_json};
        var nodeCounts = {counts_json};
        var physicsEnabled = true;

        var catColors = {{
          "Breaking Change": {{ bg: "#dc2626", border: "#f87171" }},
          "Changed Symbol": {{ bg: "#d97706", border: "#fbbf24" }},
          "Impacted Dependent": {{ bg: "#9333ea", border: "#c084fc" }}
        }};

        var pillsBar = document.getElementById('pills-bar');
        pillsBar.innerHTML = '<div class="pill active" id="pill-all" onclick="filterImpactGroup(null)"><span class="pill-dot" style="background:#38bdf8"></span> All (' + allNodes.length + ')</div>';

        for (var grp in nodeCounts) {{
          var c = catColors[grp] || {{ bg: "#64748b" }};
          var p = document.createElement('div');
          p.className = 'pill';
          p.id = 'pill-' + grp.replace(/\\s+/g, '-');
          p.innerHTML = '<span class="pill-dot" style="background:' + c.bg + '"></span> ' + grp + ' (' + nodeCounts[grp] + ')';
          p.onclick = (function(g) {{ return function() {{ filterImpactGroup(g); }}; }})(grp);
          pillsBar.appendChild(p);
        }}

        var nodesDataSet = new vis.DataSet(allNodes);
        var edgesDataSet = new vis.DataSet(allEdges);

        var container = document.getElementById('impact-network');
        var data = {{ nodes: nodesDataSet, edges: edgesDataSet }};

        var options = {{
          nodes: {{ shape: 'dot' }},
          edges: {{
            arrows: {{ to: {{ enabled: true, scaleFactor: 0.7 }} }},
            smooth: {{ type: 'continuous', roundness: 0.25 }}
          }},
          physics: {{
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {{
              gravitationalConstant: -45,
              centralGravity: 0.008,
              springLength: 95,
              springConstant: 0.15,
              damping: 0.85
            }},
            stabilization: {{ iterations: 150 }}
          }},
          interaction: {{ hover: true, tooltipDelay: 100, zoomView: true }}
        }};

        var impactNetwork = new vis.Network(container, data, options);

        impactNetwork.on("click", function(params) {{
          if (params.nodes.length > 0) {{
            var nodeId = params.nodes[0];
            var nodeData = nodesDataSet.get(nodeId);
            if (nodeData) showImpactHud(nodeData);
          }} else {{
            closeImpactHud();
          }}
        }});

        function showImpactHud(node) {{
          var hud = document.getElementById('node-hud');
          var badge = document.getElementById('hud-badge');
          var title = document.getElementById('hud-title');
          var path = document.getElementById('hud-path');
          var reason = document.getElementById('hud-reason');
          var kind = document.getElementById('hud-kind');

          var c = catColors[node.group] || {{ bg: "#38bdf8", border: "#f0f9ff" }};
          badge.style.background = c.bg;
          badge.style.color = "#ffffff";
          badge.innerText = node.group;

          title.innerText = node.qual_name || node.label;
          path.innerText = node.file_path || "in-memory";
          kind.innerText = "Component Type: " + (node.kind || "Symbol") + " | Status: " + (node.status || "N/A");

          if (node.is_breaking && node.breaking_reason) {{
            reason.style.display = "block";
            reason.innerText = "🚨 " + node.breaking_reason;
          }} else {{
            reason.style.display = "none";
          }}

          hud.style.display = "block";
        }}

        function closeImpactHud() {{
          document.getElementById('node-hud').style.display = "none";
        }}

        function toggleImpactPhysics() {{
          physicsEnabled = !physicsEnabled;
          impactNetwork.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
          document.getElementById('btn-physics').innerText = physicsEnabled ? '⏸️' : '▶️';
        }}

        function searchImpactSymbol(query) {{
          if (!query || query.trim() === '') {{
            impactNetwork.fit({{ animation: {{ duration: 300 }} }});
            return;
          }}
          var q = query.toLowerCase().trim();
          var matched = allNodes.filter(function(n) {{
            return (n.qual_name && n.qual_name.toLowerCase().indexOf(q) !== -1) ||
                   (n.label && n.label.toLowerCase().indexOf(q) !== -1);
          }});

          if (matched.length > 0) {{
            var targetId = matched[0].id;
            impactNetwork.focus(targetId, {{
              scale: 1.5,
              animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }}
            }});
            impactNetwork.selectNodes([targetId]);
            showImpactHud(matched[0]);
          }}
        }}

        function filterImpactGroup(groupName) {{
          var pills = document.querySelectorAll('.pill');
          pills.forEach(function(p) {{ p.classList.remove('active'); }});
          if (!groupName) {{
            document.getElementById('pill-all').classList.add('active');
            nodesDataSet.clear();
            nodesDataSet.add(allNodes);
            edgesDataSet.clear();
            edgesDataSet.add(allEdges);
          }} else {{
            var pid = 'pill-' + groupName.replace(/\\s+/g, '-');
            var activePill = document.getElementById(pid);
            if (activePill) activePill.classList.add('active');

            var filteredNodes = allNodes.filter(function(n) {{ return n.group === groupName; }});
            var nodeSet = new Set(filteredNodes.map(function(n) {{ return n.id; }}));
            var filteredEdges = allEdges.filter(function(e) {{
              return nodeSet.has(e.from) || nodeSet.has(e.to);
            }});

            nodesDataSet.clear();
            nodesDataSet.add(filteredNodes);
            edgesDataSet.clear();
            edgesDataSet.add(filteredEdges);
          }}
          impactNetwork.fit({{ animation: {{ duration: 400 }} }});
        }}
      </script>
    </body>
    </html>
    """
    if components is not None:
        components.html(canvas_html, height=670)
    else:
        st.warning("Streamlit HTML components not available.")


def run_app() -> None:
    """Main Streamlit application flow."""
    if st is None:
        print("Streamlit is not installed in the current environment.")
        return

    st.set_page_config(
        page_title="TRACE Code Intelligence Observatory",
        layout="wide",
    )

    # Sidebar: Section 1 - System & Connectivity
    with st.sidebar.container(border=True):
        st.markdown(
            """
            <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 8px;">
              SYSTEM & CONNECTIVITY
            </div>
            """,
            unsafe_allow_html=True,
        )
        theme_mode = st.radio("Theme Mode", ["Light", "Dark"], index=0, horizontal=True)
        inject_neo_brutalist_css(theme_mode.lower())

        api_url = st.text_input(
            "TRACE API Base URL",
            value=os.environ.get("TRACE_API_URL", "http://127.0.0.1:8000/api/v1"),
        )

        health_url = api_url.rsplit("/api/v1", 1)[0] + "/health"
        status_code, health_data = make_api_request(health_url)
        if status_code == 200:
            render_html(
                """
                <div style="display: flex; align-items: center; justify-content: space-between; background: var(--nb-surface); border: 2px solid var(--nb-border); padding: 8px 12px; margin-top: 6px; box-shadow: var(--nb-shadow-sm); border-radius: 0px;">
                  <span style="font-size: 0.78rem; font-weight: 700; color: var(--nb-text); font-family: 'Inter', sans-serif;">API Status</span>
                  <span style="background: #16a34a; color: #FFFFFF; font-size: 0.72rem; font-weight: 800; padding: 2px 8px; border-radius: 0px; font-family: 'JetBrains Mono', monospace;">CONNECTED</span>
                </div>
                """
            )
        else:
            render_html(
                f"""
                <div style="display: flex; align-items: center; justify-content: space-between; background: var(--nb-surface); border: 2px solid #ef4444; padding: 8px 12px; margin-top: 6px; box-shadow: var(--nb-shadow-sm); border-radius: 0px;">
                  <span style="font-size: 0.78rem; font-weight: 700; color: var(--nb-text); font-family: 'Inter', sans-serif;">API Status</span>
                  <span style="background: #ef4444; color: #FFFFFF; font-size: 0.72rem; font-weight: 800; padding: 2px 8px; border-radius: 0px; font-family: 'JetBrains Mono', monospace;">OFFLINE ({status_code})</span>
                </div>
                """
            )

    st.title("TRACE Code Intelligence Observatory")

    # Sidebar: Section 2 - Project Workspace
    # Fetch projects
    projects_code, projects_data = make_api_request(f"{api_url}/projects")
    projects_list = projects_data.get("items", []) if projects_code == 200 and projects_data else []

    with st.sidebar.container(border=True):
        st.markdown(
            """
            <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 8px;">
              PROJECT WORKSPACE
            </div>
            """,
            unsafe_allow_html=True,
        )

        if projects_list:
            project_map = {f"{p['name']} ({p['id'][:8]}...)": p["id"] for p in projects_list}
            selected_project_name = st.selectbox("Active Project", options=list(project_map.keys()))
            selected_project_id = project_map[selected_project_name]
        else:
            selected_project_id = None
            selected_project_name = None

        # Sidebar: Project Management Form
        with st.expander("Create New Project", expanded=(len(projects_list) == 0)):
            with st.form("create_project_form"):
                new_p_name = st.text_input("Project Name", placeholder="e.g. TRACE-Core")
                new_p_desc = st.text_area("Description (optional)", placeholder="Core TRACE engine")
                create_p_btn = st.form_submit_button("Create Project", type="primary", use_container_width=True)
                if create_p_btn:
                    if not new_p_name.strip():
                        st.error("Project name is required.")
                    else:
                        p_code, p_res = make_api_request(
                            f"{api_url}/projects",
                            method="POST",
                            payload={"name": new_p_name.strip(), "description": new_p_desc.strip() or None},
                        )
                        if p_code in (200, 201):
                            st.success(f"Project created: {new_p_name}")
                            st.rerun()
                        else:
                            st.error(f"Failed ({p_code}): {p_res}")

    if not projects_list:
        st.info("Welcome to TRACE! No projects registered yet. Use the sidebar to create your first project.")
        return

    # Sidebar: Section 3 - Repository Configuration
    # Fetch repositories for selected project
    repos_code, repos_data = make_api_request(f"{api_url}/projects/{selected_project_id}/repositories")
    repos_list = repos_data.get("items", []) if repos_code == 200 and repos_data else []

    with st.sidebar.container(border=True):
        st.markdown(
            """
            <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 8px;">
              REPOSITORY CONFIGURATION
            </div>
            """,
            unsafe_allow_html=True,
        )

        if repos_list:
            repo_map = {f"{r['location']} [{r['type']}]": r["id"] for r in repos_list}
            selected_repo_name = st.selectbox("Active Repository", options=list(repo_map.keys()))
            selected_repo_id = repo_map[selected_repo_name]
        else:
            selected_repo_id = None
            selected_repo_name = None

        # Sidebar: Repository Management Form
        with st.expander("Register Repository", expanded=(len(repos_list) == 0)):
            with st.form("register_repo_form"):
                repo_kind = st.radio("Source Type", ["Remote Git Repo", "Local Path"], horizontal=True)
                if repo_kind == "Remote Git Repo":
                    r_type = "REMOTE"
                    r_location = st.text_input(
                        "Git Repository URL (.git)",
                        value="https://github.com/psf/requests.git",
                        placeholder="https://github.com/encode/httpx.git",
                        help="Any public or accessible Git repository URL",
                    )
                else:
                    r_type = "LOCAL"
                    r_location = st.text_input(
                        "Local Directory Path",
                        value="/workspace",
                        help="Container directory path (e.g. /workspace or /app)",
                    )
                r_branch = st.text_input("Branch / Tag / Ref (optional)", value="HEAD")
                reg_btn = st.form_submit_button("Register Repository", type="primary", use_container_width=True)
                if reg_btn:
                    if not r_location.strip():
                        st.error("Location or Git URL is required.")
                    else:
                        reg_code, reg_res = make_api_request(
                            f"{api_url}/projects/{selected_project_id}/repositories",
                            method="POST",
                            payload={
                                "location": r_location.strip(),
                                "type": r_type,
                                "default_branch": r_branch.strip() or None,
                            },
                        )
                        if reg_code in (200, 201):
                            st.success(f"Repository registered ({r_type})!")
                            st.rerun()
                        else:
                            st.error(f"Failed ({reg_code}): {reg_res}")

    if not repos_list:
        st.warning(f"No repositories registered for project **{selected_project_name}**. Use the sidebar to register one.")
        return

    # Sidebar: Section 4 - AI Reasoning Synthesis (Optional)
    with st.sidebar.container(border=True):
        st.markdown(
            """
            <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 8px;">
              AI SYNTHESIS & REASONING (OPTIONAL)
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("AI Reasoning Settings", expanded=False):
            st.caption("Configure OpenRouter API to enrich change impact justifications. Leave blank for 100% offline deterministic heuristic mode.")
            openrouter_key = st.text_input(
                "OpenRouter API Key",
                type="password",
                value=os.getenv("OPENROUTER_API_KEY", ""),
                help="Optional key for OpenRouter models. If omitted, the offline deterministic rule engine runs with zero cost and zero latency.",
            )
            model_options = [
                "nvidia/nemotron-3.5-lightning:free",
                "meta-llama/llama-3.3-70b-instruct:free",
                "google/gemini-2.0-flash",
                "anthropic/claude-3.5-sonnet",
                "openai/gpt-4o",
                "Custom Model (type below)...",
            ]
            selected_model_choice = st.selectbox(
                "AI Model",
                model_options,
                index=0,
                help="Select an OpenRouter model or choose Custom to specify any model ID.",
            )
            if selected_model_choice == "Custom Model (type below)...":
                openrouter_model = st.text_input(
                    "Custom Model Identifier",
                    value="nvidia/nemotron-3.5-lightning:free",
                    help="Enter any valid OpenRouter model tag (e.g. nvidia/nemotron-3.5-lightning:free)",
                ).strip()
            else:
                openrouter_model = selected_model_choice
            enable_ai = st.checkbox(
                "Enable AI Synthesis",
                value=bool(openrouter_key.strip()),
                help="Toggle between AI-enriched explanations and offline deterministic rules.",
            )

    # Observatory Top-Level Navigation - True Segmented Brutalist Tab Tiles
    tab1, tab2, tab3, tab4 = st.tabs([
        "Code Intelligence",
        "Version Analyzer",
        "Impact & Risk",
        "Upgrade Planner",
    ])
    tab_intelligence, tab_version_diff, tab_impact_engine, tab_upgrade_planner = tab1, tab2, tab3, tab4

    with tab_intelligence:
        # Framed Analysis Execution Control Panel
        with st.container(border=True):
            st.markdown(
                """
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 2px;">
                  Analysis Execution Control
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.subheader("Repository Code Analysis Control")
            st.caption("Trigger full AST symbol extraction, structural relationship mapping, and graph ingestion for the target commit.")

            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                target_ref = st.text_input("Target Ref / Commit SHA (optional)", value="HEAD", key="f02_target_ref")
            with col2:
                exclude_patterns_str = st.text_input("Exclude Patterns (comma-separated)", value="tests/*, docs/*", key="f02_exclude")
            with col3:
                st.write("")
                st.write("")
                trigger_btn = st.button("Analyze Repository", type="primary", use_container_width=True)

        if trigger_btn:
            patterns = [p.strip() for p in exclude_patterns_str.split(",") if p.strip()]
            trigger_payload = {"target_ref": target_ref or None, "exclude_patterns": patterns}
            trigger_code, trigger_res = make_api_request(
                f"{api_url}/repositories/{selected_repo_id}/analyze",
                method="POST",
                payload=trigger_payload,
            )

            if trigger_code == 202 and trigger_res:
                run_id = trigger_res["id"]
                st.session_state["active_run_id"] = run_id
                st.success(f"Analysis triggered! Run ID: `{run_id}`")
            else:
                st.error(f"Failed to trigger analysis: {trigger_res}")

        active_run_id = st.session_state.get("active_run_id")

        # Polling & Display Section
        if active_run_id:
            st.divider()
            st.subheader(f"Analysis Run: `{active_run_id}`")

            status_placeholder = st.empty()
            poll_count = 0
            run_status = "PENDING"
            run_record: dict[str, Any] = {}

            while poll_count < 30 and run_status in ("PENDING", "IN_PROGRESS"):
                status_code, run_res = make_api_request(f"{api_url}/analyses/{active_run_id}")
                if status_code == 200 and run_res:
                    run_record = run_res
                    run_status = run_record.get("status", "UNKNOWN")
                    status_placeholder.info(f"Analysis Status: **{run_status}** (polling...)")
                    if run_status in ("COMPLETED", "FAILED"):
                        break
                time.sleep(1.0)
                poll_count += 1

            if run_status == "COMPLETED":
                status_placeholder.success(
                    f"Analysis **COMPLETED** in {run_record.get('duration_ms', 0):.1f} ms | Commit: `{run_record.get('commit_hash', 'N/A')}`"
                )

                # Summary Metrics
                sum_code, sum_data = make_api_request(f"{api_url}/analyses/{active_run_id}/summary")
                metrics = sum_data.get("metrics", {}) if sum_code == 200 and sum_data else {}

                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("Total Files", metrics.get("total_files", 0))
                m2.metric("Python Files", metrics.get("python_files", 0))
                m3.metric("Modules", metrics.get("modules", 0))
                m4.metric("Classes", metrics.get("classes", 0))
                m5.metric("Functions", metrics.get("functions", 0))
                m6.metric("Endpoints", metrics.get("endpoints", 0))

                m7, m8, m9, m10, m11, m12 = st.columns(6)
                m7.metric("Services", metrics.get("services", 0))
                m8.metric("Database Refs", metrics.get("database_models", 0))
                m9.metric("Test Targets", metrics.get("test_functions", 0))
                m10.metric("Dependencies", metrics.get("external_dependencies", 0))
                m11.metric("Relationships", metrics.get("total_relationships", 0))
                m12.metric("Diagnostics", metrics.get("diagnostics_count", 0))

                # Exploration Tabs
                tab_entities, tab_relationships, tab_graph, tab_diagnostics = st.tabs(
                    ["Entities", "Relationships", "Dependency Graph", "Diagnostics"]
                )

                with tab_entities:
                    ent_code, ent_data = make_api_request(f"{api_url}/analyses/{active_run_id}/entities?limit=200")
                    items = ent_data.get("items", []) if ent_code == 200 and ent_data else []
                    if items:
                        st.dataframe(items, use_container_width=True)
                    else:
                        st.info("No entities found.")

                with tab_relationships:
                    rel_code, rel_data = make_api_request(f"{api_url}/analyses/{active_run_id}/relationships?limit=200")
                    rels = rel_data.get("items", []) if rel_code == 200 and rel_data else []
                    if rels:
                        st.dataframe(rels, use_container_width=True)
                    else:
                        st.info("No relationships found.")

                with tab_graph:
                    st.markdown("#### Interactive Dependency Graph Explorer")
                    st.caption("Force-directed interactive visual graph. Drag nodes, zoom, or hover to inspect symbol details.")
                    
                    g_nodes_code, g_nodes_data = make_api_request(f"{api_url}/analyses/{active_run_id}/graph/nodes?limit=1500")
                    g_nodes = g_nodes_data.get("items", []) if g_nodes_code == 200 and g_nodes_data else []

                    g_rels_code, g_rels_data = make_api_request(f"{api_url}/analyses/{active_run_id}/graph/relationships?limit=1500")
                    g_rels = g_rels_data.get("items", []) if g_rels_code == 200 and g_rels_data else []

                    if g_nodes:
                        render_graph_canvas(g_nodes, g_rels)
                    else:
                        st.info("No graph nodes returned yet. Neo4j may still be building the graph.")
                        if st.button("Build / Rebuild Graph in Neo4j", type="secondary"):
                            build_code, build_res = make_api_request(
                                f"{api_url}/analyses/{active_run_id}/graph/build",
                                method="POST",
                            )
                            if build_code in (200, 202):
                                st.success("Graph build triggered! Refreshing...")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"Failed to trigger graph build: {build_res}")

                    st.info("You can also run custom Cypher queries in the dedicated [Neo4j Browser](http://localhost:7474) (user: `neo4j` / pass: `password`).")

                    with st.expander(f"Raw Graph Data ({len(g_nodes)} Nodes, {len(g_rels)} Relationships)"):
                        g_col1, g_col2 = st.columns(2)
                        with g_col1:
                            st.markdown(f"**Graph Nodes ({len(g_nodes)})**")
                            if g_nodes:
                                st.dataframe(g_nodes)
                        with g_col2:
                            st.markdown(f"**Graph Relationships ({len(g_rels)})**")
                            if g_rels:
                                st.dataframe(g_rels)

                with tab_diagnostics:
                    diag_code, diag_data = make_api_request(f"{api_url}/analyses/{active_run_id}/diagnostics?limit=100")
                    diags = diag_data.get("items", []) if diag_code == 200 and diag_data else []
                    if diags:
                        st.dataframe(diags, use_container_width=True)
                    else:
                        st.success("Clean analysis: 0 diagnostics or syntax errors encountered.")

            elif run_status == "FAILED":
                status_placeholder.error(f"Analysis FAILED: {run_record.get('error_message')}")

    with tab_version_diff:
        with st.container(border=True):
            st.markdown(
                """
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 2px;">
                  Version & Change Impact Engine
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_b1, col_b2 = st.columns([5, 1])
            with col_b1:
                st.subheader("Version & Change Impact Analyzer (F04)")
                st.caption("Compare Git branches, commits, or pull request revisions to detect code symbol deltas, breaking changes, and blast radius.")
            with col_b2:
                st.write("")
                refresh_branches = st.button("Sync Git", help="Fetch latest branches from Git remote", use_container_width=True)
            
            b_code, b_data = make_api_request(f"{api_url}/repositories/{selected_repo_id}/branches")
            branches_list = b_data.get("branches", ["main"]) if b_code == 200 and b_data else ["main"]
            default_branch = b_data.get("default_branch", "main") if b_code == 200 and b_data else "main"

            diff_mode = st.radio(
                "Comparison Mode",
                ["Branch vs Branch", "Quick 2-Commit Diff (Branch~1 vs Branch)", "Custom Commit Range"],
                horizontal=True,
            )

            d_col1, d_col2, d_col3 = st.columns([2, 2, 1])

            if diff_mode == "Branch vs Branch":
                with d_col1:
                    base_branch = st.selectbox("Base Branch (e.g. main/production)", options=branches_list, index=0)
                with d_col2:
                    target_idx = 1 if len(branches_list) > 1 else 0
                    target_branch = st.selectbox("Target Branch (e.g. feature/bugfix)", options=branches_list, index=target_idx)
                base_ref_val = base_branch
                target_ref_val = target_branch
            elif diff_mode == "Quick 2-Commit Diff (Branch~1 vs Branch)":
                with d_col1:
                    def_idx = branches_list.index(default_branch) if default_branch in branches_list else 0
                    quick_branch = st.selectbox("Select Branch to Diff (Last 2 Commits)", options=branches_list, index=def_idx)
                with d_col2:
                    st.text_input("Base Revision", value=f"{quick_branch}~1", disabled=True)
                    st.text_input("Target Revision", value=f"{quick_branch}", disabled=True)
                base_ref_val = f"{quick_branch}~1"
                target_ref_val = quick_branch
            else:
                with d_col1:
                    base_ref_val = st.text_input("Base Commit SHA / Branch / Tag", value="HEAD~1")
                with d_col2:
                    target_ref_val = st.text_input("Target Commit SHA / Branch / Tag", value="HEAD")

            with d_col3:
                st.write("")
                st.write("")
                run_diff_btn = st.button("Run Change Analysis", type="primary", use_container_width=True)

        if run_diff_btn:
            with st.spinner("Analyzing semantic changes, signature alterations, and blast radius..."):
                diff_code, diff_res = make_api_request(
                    f"{api_url}/analyses/compare",
                    method="POST",
                    payload={
                        "repository_id": selected_repo_id,
                        "base_ref": base_ref_val,
                        "target_ref": target_ref_val,
                    },
                    timeout=120.0,
                )
                if diff_code == 201 and diff_res:
                    st.session_state["active_diff_id"] = diff_res["comparison_id"]
                    st.success(f"Change comparison completed! ID: `{diff_res['comparison_id']}`")
                else:
                    st.error(f"Comparison failed ({diff_code}): {diff_res}")

        active_diff_id = st.session_state.get("active_diff_id")
        if active_diff_id:
            d_detail_code, d_detail = make_api_request(f"{api_url}/analyses/compare/{active_diff_id}", timeout=60.0)
            if d_detail_code == 200 and d_detail:
                st.divider()

                # Risk Level Banner & Metrics
                risk_lvl = d_detail.get("risk_level", "LOW")
                is_dark_mode = theme_mode == "Dark"
                risk_colors = {
                    "CRITICAL": "#ef4444" if is_dark_mode else "#dc2626",
                    "HIGH": "#f97316" if is_dark_mode else "#ea580c",
                    "MEDIUM": "#f59e0b" if is_dark_mode else "#d97706",
                    "LOW": "#22c55e" if is_dark_mode else "#16a34a",
                }
                r_color = risk_colors.get(risk_lvl, "#16a34a")
                border_color = r_color if risk_lvl in ("CRITICAL", "HIGH") else "var(--nb-border)"

                diff_banner_html = f"""
                <div style="background: var(--nb-surface); border: 2px solid {border_color}; border-left: 8px solid {r_color}; border-radius: 2px; padding: 18px 22px; margin-bottom: 20px; box-shadow: var(--nb-shadow-lg);">
                  <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                    <div>
                      <span style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--nb-text-muted); font-weight: 800; font-family: 'Inter', sans-serif;">Overall Change Impact Risk</span>
                      <h2 style="margin: 4px 0 0 0; color: {r_color}; font-size: 1.9rem; font-weight: 800; letter-spacing: 0.5px; font-family: 'Inter', sans-serif;">{risk_lvl} RISK</h2>
                      <div style="font-size: 0.85rem; color: var(--nb-text-muted); margin-top: 6px; font-family: 'JetBrains Mono', monospace;">
                        Comparing <code>{d_detail.get('base_ref')}</code> ({d_detail.get('base_commit_hash', '')[:7]}) ➜ <code>{d_detail.get('target_ref')}</code> ({d_detail.get('target_commit_hash', '')[:7]})
                      </div>
                    </div>
                    <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 2px; padding: 10px 18px; text-align: right; box-shadow: var(--nb-shadow-sm);">
                      <div style="font-size: 1.6rem; font-weight: 800; color: {r_color}; font-family: 'JetBrains Mono', monospace;">{d_detail['summary'].get('total_breaking_changes', 0)}</div>
                      <div style="font-size: 0.75rem; text-transform: uppercase; color: var(--nb-text-muted); font-weight: 700;">Breaking Changes</div>
                    </div>
                  </div>
                </div>
                """
                render_html(diff_banner_html)

                summ = d_detail.get("summary", {})
                rc1, rc2, rc3, rc4, rc5 = st.columns(5)
                rc1.metric("Files Changed", summ.get("total_files_changed", 0))
                rc2.metric("Insertions (+)", f"+{summ.get('total_insertions', 0)}")
                rc3.metric("Deletions (-)", f"-{summ.get('total_deletions', 0)}")
                rc4.metric("Symbols Changed", summ.get("total_symbols_changed", 0))
                rc5.metric("Breaking Changes", summ.get("total_breaking_changes", 0))

                # Subtabs
                tab_blast, tab_breaking, tab_files, tab_commits = st.tabs([
                    "Impact Graph",
                    "Breaking Changes",
                    "File Diffs",
                    "Commit Log",
                ])

                with tab_blast:
                    st.markdown("#### Change Propagation & Impact Graph")
                    st.caption("Interactive force-directed graph tracking altered code symbols, breaking changes, and all affected downstream callers across the repository.")

                    impact_graph_json = build_impact_graph_json(d_detail)
                    graph_nodes = impact_graph_json.get("graph", {}).get("nodes", [])
                    blast_items = d_detail.get("blast_radius", [])
                    sym_count = summ.get("total_symbols_changed", 0)

                    # Action Bar for Graph JSON Download & Inspection
                    col_g1, col_g2 = st.columns([3, 1])
                    with col_g1:
                        st.markdown(
                            f"**Graph Summary:** `{len(graph_nodes)}` nodes ({impact_graph_json['summary'].get('total_breaking_changes', 0)} breaking, "
                            f"{sym_count} changed, {len(blast_items)} downstream callers) &bull; "
                            f"`{len(impact_graph_json.get('graph', {}).get('edges', []))}` dependency edges"
                        )
                    with col_g2:
                        st.download_button(
                            label="Download Graph JSON",
                            data=json.dumps(impact_graph_json, indent=2),
                            file_name=f"trace_impact_graph_{active_diff_id[:8]}.json",
                            mime="application/json",
                            use_container_width=True,
                            key=f"dl_graph_{active_diff_id}",
                        )

                    # Interactive Graph Visualization Canvas
                    if graph_nodes:
                        render_impact_graph_canvas(d_detail)
                    elif sym_count == 0:
                        st.info("Zero code symbols (functions, classes, endpoints) were modified in this changeset. All changes were in non-code or documentation files, so no code nodes or graph dependencies are affected.")
                    else:
                        st.success("Zero downstream callers or dependents are impacted. The modified symbols are self-contained with no incoming references in the repository graph.")

                    # Downstream Callers Table
                    if blast_items:
                        st.markdown(f"#### {len(blast_items)} Impacted Downstream Components")
                        st.dataframe(blast_items, use_container_width=True)

                    # Expandable JSON Viewer for full transparency
                    with st.expander("View Complete Change Impact Graph JSON"):
                        st.json(impact_graph_json)

                with tab_breaking:
                    sym_diffs = d_detail.get("symbol_diffs", [])
                    breaking_syms = [s for s in sym_diffs if s.get("is_breaking")]
                    non_breaking_syms = [s for s in sym_diffs if not s.get("is_breaking")]

                    if breaking_syms:
                        st.markdown(f"#### {len(breaking_syms)} Breaking Changes Detected")
                        for bs in breaking_syms:
                            with st.container():
                                breaking_card_html = f"""
                                <div style="background: var(--nb-surface); border: 2px solid #dc2626; border-left: 6px solid #dc2626; padding: 14px 16px; border-radius: 2px; margin-bottom: 12px; box-shadow: var(--nb-shadow);">
                                  <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                                    <strong style="color: var(--nb-text); font-size: 1rem; font-family: 'JetBrains Mono', monospace;">[{html.escape(bs.get('kind', '').upper())}] {html.escape(bs.get('qualified_name', ''))}</strong>
                                    <span style="background: #dc2626; color: #FFFFFF; border: 1.5px solid var(--nb-border); padding: 2px 8px; border-radius: 2px; font-size: 0.75rem; font-weight: 800; font-family: 'JetBrains Mono', monospace;">BREAKING</span>
                                  </div>
                                  <div style="color: var(--nb-text); margin-top: 6px; font-size: 0.9rem;"><strong>Reason:</strong> {html.escape(bs.get('breaking_reason', 'Signature altered incompatibly'))}</div>
                                  <div style="margin-top: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: var(--nb-code-bg); border: 1px solid var(--nb-border); padding: 8px 10px; border-radius: 2px;">
                                    <div><span style="color: #dc2626; font-weight: 700;">- Old:</span> {html.escape(bs.get('old_signature') or 'None (Added)')}</div>
                                    <div><span style="color: #16a34a; font-weight: 700;">+ New:</span> {html.escape(bs.get('new_signature') or 'None (Deleted)')}</div>
                                  </div>
                                  <div style="font-size: 0.75rem; color: var(--nb-text-muted); margin-top: 6px; font-family: 'JetBrains Mono', monospace;">File: {html.escape(bs.get('file_path', ''))}</div>
                                </div>
                                """
                                render_html(breaking_card_html)
                    else:
                        st.success("Zero breaking changes detected between these revisions.")

                    if non_breaking_syms:
                        st.markdown(f"#### {len(non_breaking_syms)} Non-Breaking Symbol Modifications")
                        st.dataframe(non_breaking_syms, use_container_width=True)

                with tab_files:
                    st.markdown("#### File-Level Diffs")
                    f_diffs = d_detail.get("file_diffs", [])
                    if f_diffs:
                        for fd in f_diffs:
                            c_type = fd.get("change_type", "MODIFIED")
                            path_disp = fd.get("new_path") or fd.get("old_path") or "unknown"
                            ins = fd.get("insertions", 0)
                            dels = fd.get("deletions", 0)

                            badge_config = {
                                "MODIFIED": {"bg": "#FACC15", "text": "#000000", "label": "MODIFIED"},
                                "ADDED": {"bg": "#16A34A", "text": "#FFFFFF", "label": "ADDED"},
                                "DELETED": {"bg": "#DC2626", "text": "#FFFFFF", "label": "DELETED"},
                                "RENAMED": {"bg": "#2563EB", "text": "#FFFFFF", "label": "RENAMED"},
                            }.get(c_type, {"bg": "#FACC15", "text": "#000000", "label": c_type})

                            file_bar_html = f"""
                            <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 2px; padding: 10px 14px; margin-top: 10px; margin-bottom: 6px; box-shadow: var(--nb-shadow); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                              <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="background: {badge_config['bg']}; color: {badge_config['text']}; border: 1.5px solid var(--nb-border); border-radius: 2px; font-size: 0.72rem; font-weight: 800; font-family: 'JetBrains Mono', monospace; padding: 2px 8px; text-transform: uppercase;">{badge_config['label']}</span>
                                <code style="font-size: 0.92rem; font-weight: 700; color: var(--nb-text); background: transparent; border: none; padding: 0;">{path_disp}</code>
                              </div>
                              <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 700;">
                                <span style="color: #16a34a;">+{ins}</span> <span style="color: #dc2626;">-{dels}</span>
                              </div>
                            </div>
                            """
                            render_html(file_bar_html)
                            with st.expander(f"Diff: {path_disp}", expanded=True):
                                diff_html = render_colored_diff(fd)
                                render_html(diff_html)
                    else:
                        st.info("No file diffs recorded.")

                with tab_commits:
                    st.markdown("#### Commits in Changeset")
                    msgs = d_detail.get("commit_messages", [])
                    if msgs:
                        for idx, m in enumerate(msgs, 1):
                            st.markdown(f"{idx}. `{m}`")
                    else:
                        st.info("No commit messages retrieved for this comparison.")

    with tab_impact_engine:
        st.subheader("Transformation Risk & Behavioral Impact Propagation Engine (F05)")
        st.caption(
            "Bridges Git Diff hunks with AST scopes, evaluates multi-hop blast radius across inverted call graphs ($G^T$), "
            "infers diff syntax deltas (def/return/raise), and synthesizes actionable remediation checklists."
        )

        # Mode indicator badge
        if enable_ai and openrouter_key.strip():
            mode_badge_html = f"""
            <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 2px; padding: 6px 14px; margin-bottom: 16px; display: inline-flex; align-items: center; gap: 8px; box-shadow: var(--nb-shadow-sm);">
                <span style="font-size: 0.85rem; font-weight: 700; color: var(--nb-text); font-family: 'Inter', sans-serif;">Mode: AI-Enriched Synthesis</span>
                <span style="background: #7c3aed; color: #ffffff; border: 1px solid var(--nb-border); padding: 2px 8px; border-radius: 2px; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; font-weight: 700;">{openrouter_model}</span>
            </div>
            """
        else:
            mode_badge_html = """
            <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 2px; padding: 6px 14px; margin-bottom: 16px; display: inline-flex; align-items: center; gap: 8px; box-shadow: var(--nb-shadow-sm);">
                <span style="font-size: 0.85rem; font-weight: 700; color: var(--nb-text); font-family: 'Inter', sans-serif;">Mode: Deterministic Heuristic Engine</span>
                <span style="background: #16a34a; color: #ffffff; border: 1px solid var(--nb-border); padding: 2px 8px; border-radius: 2px; font-size: 0.75rem; font-weight: 700; font-family: 'JetBrains Mono', monospace;">100% Offline · Zero Latency</span>
            </div>
            """
        render_html(mode_badge_html)

        col_i1, col_i2, col_i3 = st.columns([2, 2, 1])
        with col_i1:
            imp_base = st.text_input("Base Revision (Commit SHA / Branch / Tag)", value="HEAD~1", key="f05_base")
        with col_i2:
            imp_target = st.text_input("Target Revision (Commit SHA / Branch / Tag)", value="HEAD", key="f05_target")
        with col_i3:
            st.write("")
            st.write("")
            run_impact_btn = st.button("Evaluate Impact & Risk", type="primary", use_container_width=True)

        if run_impact_btn:
            with st.spinner("Executing mathematical interval intersection, transposed BFS blast radius, and delta inference..."):
                payload = {
                    "repository_id": selected_repo_id,
                    "base_ref": imp_base.strip() or "HEAD~1",
                    "target_ref": imp_target.strip() or "HEAD",
                    "llm_config": {
                        "enabled": bool(enable_ai and openrouter_key.strip()),
                        "api_key": openrouter_key.strip() if enable_ai else None,
                        "model": openrouter_model if enable_ai else "anthropic/claude-3.5-sonnet",
                    },
                }
                imp_code, imp_res = make_api_request(
                    f"{api_url}/impact/evaluate",
                    method="POST",
                    payload=payload,
                    timeout=120.0,
                )
                if imp_code in (200, 201) and imp_res:
                    st.session_state["active_impact_data"] = imp_res
                    st.success("Impact & Risk evaluation completed successfully!")
                else:
                    st.error(f"Impact evaluation failed ({imp_code}): {imp_res}")

        active_impact = st.session_state.get("active_impact_data")
        if active_impact:
            st.divider()

            meta = active_impact.get("analysis_metadata", {})
            risk_meta = active_impact.get("risk_analysis", {})
            risk_lvl = risk_meta.get("risk_level", "LOW")

            is_dark_mode = theme_mode == "Dark"
            risk_colors = {
                "CRITICAL": "#ef4444" if is_dark_mode else "#dc2626",
                "HIGH": "#f97316" if is_dark_mode else "#ea580c",
                "MEDIUM": "#f59e0b" if is_dark_mode else "#d97706",
                "LOW": "#22c55e" if is_dark_mode else "#16a34a",
            }
            r_col = risk_colors.get(risk_lvl, "#16a34a")
            border_col = r_col if risk_lvl in ("CRITICAL", "HIGH") else "var(--nb-border)"

            # Risk Summary Header Banner
            risk_banner_html = f"""
            <div style="background: var(--nb-surface); border: 2px solid {border_col}; border-left: 8px solid {r_col}; border-radius: 2px; padding: 20px 22px; margin-bottom: 22px; box-shadow: var(--nb-shadow-lg);">
              <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                <div>
                  <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--nb-text-muted); font-weight: 800; font-family: 'Inter', sans-serif;">ARCHITECTURAL RISK ASSESSMENT</div>
                  <h2 style="margin: 4px 0 0 0; color: {r_col}; font-size: 2rem; font-weight: 800; letter-spacing: 0.5px; font-family: 'Inter', sans-serif;">{risk_lvl} RISK</h2>
                  <div style="font-size: 0.85rem; color: var(--nb-text-muted); margin-top: 6px; font-family: 'JetBrains Mono', monospace;">
                    Comparing <code>{meta.get('base_commit', '')[:7]}</code> ➜ <code>{meta.get('current_commit', '')[:7]}</code>
                    &bull; Reasoning Mode: <strong>{meta.get('reasoning_mode', 'HEURISTIC')}</strong>
                  </div>
                </div>
                <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                  <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 2px; padding: 8px 16px; text-align: center; box-shadow: var(--nb-shadow-sm);">
                    <div style="font-size: 1.5rem; font-weight: 800; color: {r_col}; font-family: 'JetBrains Mono', monospace;">{meta.get('total_callers_at_risk', 0)}</div>
                    <div style="font-size: 0.72rem; text-transform: uppercase; color: var(--nb-text-muted); font-weight: 700;">Callers At Risk</div>
                  </div>
                  <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-radius: 2px; padding: 8px 16px; text-align: center; box-shadow: var(--nb-shadow-sm);">
                    <div style="font-size: 1.5rem; font-weight: 800; color: var(--nb-accent-blue); font-family: 'JetBrains Mono', monospace;">{meta.get('total_impacted_downstream_files', 0)}</div>
                    <div style="font-size: 0.72rem; text-transform: uppercase; color: var(--nb-text-muted); font-weight: 700;">Downstream Files</div>
                  </div>
                </div>
              </div>
            </div>
            """
            render_html(risk_banner_html)

            # Metric Cards
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Changed Entities", meta.get("total_changed_entities", 0))
            m_col2.metric("Deleted Files", meta.get("total_deleted_files", 0))
            m_col3.metric("Impacted Downstream Files", meta.get("total_impacted_downstream_files", 0))
            m_col4.metric("Upstream Callers At Risk", meta.get("total_callers_at_risk", 0))

            # AI Remediation Directive (Where & What to Change)
            ai_dir = active_impact.get("risk_analysis", {}).get("ai_directive") or active_impact.get("ai_directive")
            if ai_dir:
                where_items = "".join(f"<li><code>{loc}</code></li>" for loc in ai_dir.get("where_to_change", [])) or "<li>All direct callers identified below</li>"
                what_items = "".join(f"<li>{act}</li>" for act in ai_dir.get("what_to_change", [])) or "<li>Verify and test call sites</li>"
                ai_dir_html = f"""
                <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-top: 6px solid #7c3aed; border-radius: 2px; padding: 18px 20px; margin-top: 14px; margin-bottom: 20px; box-shadow: var(--nb-shadow-lg);">
                  <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="font-size: 1.05rem; font-weight: 800; color: var(--nb-text); font-family: 'Inter', sans-serif;">AI Remediation Directive: Where & What to Change</span>
                  </div>
                  <div style="font-size: 0.92rem; color: var(--nb-text); margin-bottom: 14px; font-weight: 500;">
                    {html.escape(ai_dir.get("executive_summary", ""))}
                  </div>
                  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div style="background: var(--nb-code-bg); border: 1.5px solid var(--nb-border); border-radius: 2px; padding: 12px 14px; box-shadow: var(--nb-shadow-sm);">
                      <strong style="color: var(--nb-text); font-size: 0.82rem; text-transform: uppercase; font-family: 'Inter', sans-serif; letter-spacing: 0.5px;">Where to Change:</strong>
                      <ul style="margin: 6px 0 0 0; padding-left: 20px; font-size: 0.85rem; color: var(--nb-text);">
                        {where_items}
                      </ul>
                    </div>
                    <div style="background: var(--nb-code-bg); border: 1.5px solid var(--nb-border); border-radius: 2px; padding: 12px 14px; box-shadow: var(--nb-shadow-sm);">
                      <strong style="color: var(--nb-text); font-size: 0.82rem; text-transform: uppercase; font-family: 'Inter', sans-serif; letter-spacing: 0.5px;">What to Change:</strong>
                      <ul style="margin: 6px 0 0 0; padding-left: 20px; font-size: 0.85rem; color: var(--nb-text);">
                        {what_items}
                      </ul>
                    </div>
                  </div>
                </div>
                """
                render_html(ai_dir_html)

            # Subtabs for F05
            t_graph, t_details, t_plan, t_json = st.tabs([
                "Call Graph",
                "Detailed Impacts",
                "Remediation Plan",
                "JSON Payload",
            ])

            with t_graph:
                st.markdown("#### Behavioral Impact Propagation Tree (G^T)")
                st.caption("Visualizes altered code entities and their direct/multi-hop upstream callers traced via transposed BFS traversal.")

                impact_data = active_impact.get("impact_analysis", {})
                detailed_list = impact_data.get("detailed_impacts", [])

                if detailed_list:
                    for d in detailed_list:
                        ent = d.get("entity", "entity")
                        f_path = d.get("file", "")
                        lines = d.get("lines_affected", [0, 0])
                        callers = d.get("callers_at_risk", [])
                        downstream = d.get("downstream_dependent_files", [])
                        num_callers = len(callers)
                        ent_type = d.get("entity_type", "function").upper()

                        badge_label = f"{num_callers} Callers At Risk" if num_callers > 0 else "Isolated (0 Callers)"

                        with st.expander(f"{f_path}::{ent} (lines {lines[0]}-{lines[1]}) [{ent_type}] — {badge_label}", expanded=True):
                            if callers:
                                st.markdown(f"**Impacts {len(callers)} Upstream Callers:**")
                                for c in callers:
                                    dist = c.get("distance", 1)
                                    c_name = c.get("qualified_name", "")
                                    c_file = c.get("file_path", "")
                                    c_chain = c.get("call_chain", [])

                                    dist_badge = "Direct Caller (Depth 1)" if dist == 1 else f"Transitive Caller (Depth {dist})"
                                    chain_str = " ➜ ".join(c_chain) if c_chain else f"{c_name} ➜ {ent}"

                                    caller_card_html = f"""
                                    <div style="background: var(--nb-surface); border: 1.5px solid var(--nb-border); border-left: 4px solid #f59e0b; padding: 10px 14px; border-radius: 2px; margin-bottom: 8px; box-shadow: var(--nb-shadow-sm);">
                                      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                                        <span style="font-weight: 700; color: var(--nb-text); font-size: 0.9rem;">↳ impacts: <code>{html.escape(c_file)}::{html.escape(c_name)}</code></span>
                                        <span style="font-size: 0.72rem; background: var(--nb-surface); border: 1px solid var(--nb-border); color: {'#dc2626' if dist == 1 else '#d97706'}; padding: 2px 8px; border-radius: 2px; font-weight: 800; font-family: 'JetBrains Mono', monospace;">{dist_badge}</span>
                                      </div>
                                      <div style="font-size: 0.8rem; color: var(--nb-text-muted); margin-top: 4px; font-family: 'JetBrains Mono', monospace;">
                                        Call Chain: <span style="color: var(--nb-text); font-weight: 600;">{html.escape(chain_str)}</span>
                                      </div>
                                    </div>
                                    """
                                    render_html(caller_card_html)
                            else:
                                render_html("<div style='color: #16a34a; font-size: 0.88rem; padding: 6px 0; font-weight: 700; font-family: \"JetBrains Mono\", Consolas, monospace;'>↳ No upstream callers invoke this modified entity directly or transitively.</div>")

                            # Downstream non-code files
                            other_downstream = [f for f in downstream if f != f_path]
                            if other_downstream:
                                st.caption("**Referenced in Non-Code Files:**")
                                st.write(", ".join(f"`{f}`" for f in other_downstream))
                else:
                    st.info("No code symbols modified in this changeset.")

                # Render graphical flowchart in an expander if available
                dep_graph = active_impact.get("dependency_graph", {})
                mermaid_code = dep_graph.get("mermaid", "")
                if mermaid_code:
                    with st.expander("View Graphical Call Graph Flowchart (Mermaid)", expanded=False):
                        mermaid_html = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                          <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
                          <script>mermaid.initialize({{startOnLoad: true, theme: '{'dark' if is_dark_mode else 'default'}'}});</script>
                        </head>
                        <body style="background: transparent; margin: 0; padding: 10px; color: {'#f8fafc' if is_dark_mode else '#09090b'};">
                          <div class="mermaid">
                            {mermaid_code}
                          </div>
                        </body>
                        </html>
                        """
                        if components is not None:
                            components.html(mermaid_html, height=350, scrolling=True)
                        else:
                            st.code(mermaid_code, language="mermaid")

                # Callers at Risk Detailed Table
                flattened_callers = []
                for d in detailed_list:
                    for car in d.get("callers_at_risk", []):
                        flattened_callers.append({
                            "Target Entity": d.get("entity"),
                            "Upstream Caller": car.get("qualified_name"),
                            "File": car.get("file_path"),
                            "Distance": f"Depth {car.get('distance')}",
                            "Call Chain": " ➜ ".join(car.get("call_chain", [])),
                        })

                if flattened_callers:
                    st.divider()
                    st.markdown(f"#### Summary: {len(flattened_callers)} Upstream Callers At Risk")
                    st.dataframe(flattened_callers, use_container_width=True)
                else:
                    st.success("Zero upstream callers at risk. All modified entities are self-contained or entrypoints.")

            with t_details:
                st.markdown("#### Detailed Code Entity Impacts & Prescriptive Guidance")
                st.caption(active_impact.get("impact_analysis", {}).get("summary", ""))

                detailed_list = active_impact.get("impact_analysis", {}).get("detailed_impacts", [])
                if detailed_list:
                    for idx, item in enumerate(detailed_list, 1):
                        with st.container():
                            ent_name = item.get("entity", "")
                            ent_file = item.get("file", "")
                            lines = item.get("lines_affected", [0, 0])
                            ent_type = item.get("entity_type", "function").upper()
                            c_summary = item.get("change_summary", "")
                            rem_guide = item.get("remediation_guidance", "")
                            just = item.get("justification", "")
                            snippet = item.get("diff_snippet", "")
                            inbounds = item.get("inbound_callers", [])
                            outbounds = item.get("outbound_calls", [])
                            downstream = item.get("downstream_dependent_files", [])

                            entity_card_html = f"""
                            <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-left: 5px solid var(--nb-accent-blue); border-radius: 2px; padding: 16px; margin-bottom: 16px; box-shadow: var(--nb-shadow);">
                              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                                <div style="font-size: 1.05rem; font-weight: 800; color: var(--nb-text);">
                                  <span style="background: var(--nb-accent-blue); color: #FFFFFF; border: 1px solid var(--nb-border); padding: 2px 7px; border-radius: 2px; font-size: 0.72rem; text-transform: uppercase; font-family: 'JetBrains Mono', monospace; margin-right: 6px;">{ent_type}</span>
                                  <code>{html.escape(ent_name)}</code>
                                </div>
                                <span style="font-size: 0.8rem; color: var(--nb-text-muted); font-family: 'JetBrains Mono', monospace;">{html.escape(ent_file)} : lines {lines[0]}-{lines[1]}</span>
                              </div>
                              <div style="font-size: 0.9rem; color: var(--nb-text); margin-bottom: 10px;">
                                <strong>Summary:</strong> {html.escape(c_summary)}
                              </div>
                              <div style="background: {'rgba(245, 158, 11, 0.15)' if is_dark_mode else '#FEF3C7'}; border: 1.5px solid var(--nb-border); border-left: 4px solid #f59e0b; border-radius: 2px; padding: 10px 12px; margin-bottom: 10px; font-size: 0.85rem; color: {'#fef3c7' if is_dark_mode else '#78350F'};">
                                <strong>Remediation:</strong> {html.escape(rem_guide)}
                              </div>
                              <div style="font-size: 0.82rem; color: var(--nb-text-muted); margin-bottom: 8px;">
                                <strong>Evidence Justification:</strong> {html.escape(just)}
                              </div>
                            </div>
                            """
                            render_html(entity_card_html)

                            if snippet:
                                with st.expander(f"Diff Snippet for `{ent_name}`"):
                                    st.code(snippet, language="diff")

                            c_sub1, c_sub2, c_sub3 = st.columns(3)
                            with c_sub1:
                                st.caption(f"**Inbound Callers ({len(inbounds)})**")
                                if inbounds:
                                    st.write(", ".join(f"`{c}`" for c in inbounds))
                                else:
                                    st.write("None")
                            with c_sub2:
                                st.caption(f"**Outbound Dependencies ({len(outbounds)})**")
                                if outbounds:
                                    st.write(", ".join(f"`{o}`" for o in outbounds))
                                else:
                                    st.write("None")
                            with c_sub3:
                                st.caption(f"**Downstream Files ({len(downstream)})**")
                                if downstream:
                                    st.write(", ".join(f"`{d}`" for d in downstream))
                                else:
                                    st.write("None")
                else:
                    st.info("No code symbols modified in this changeset.")

            with t_plan:
                st.markdown("#### Prioritized Actionable Remediation Plan")
                st.caption("Step-by-step developer checklist synthesized from diff syntax alterations, broken imports, and graph call sites.")

                rem_plan = active_impact.get("risk_analysis", {}).get("actionable_remediation_plan", [])
                if rem_plan:
                    for step in rem_plan:
                        s_num = step.get("step_number")
                        cat = step.get("category", "")
                        desc = step.get("action_description", "")
                        targets = step.get("affected_targets", [])

                        cat_colors = {
                            "Contract Changes": "#ef4444" if is_dark_mode else "#dc2626",
                            "Missing Modules": "#f97316" if is_dark_mode else "#ea580c",
                            "Direct Callers": "#f59e0b" if is_dark_mode else "#d97706",
                            "Integration Validation": "#38bdf8" if is_dark_mode else "#2563eb",
                        }
                        c_color = cat_colors.get(cat, "#2563eb")

                        step_card_html = f"""
                        <div style="background: var(--nb-surface); border: 2px solid var(--nb-border); border-left: 5px solid {c_color}; border-radius: 2px; padding: 12px 16px; margin-bottom: 10px; box-shadow: var(--nb-shadow);">
                          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                            <span style="font-weight: 800; color: var(--nb-text); font-size: 0.95rem; font-family: 'Inter', sans-serif;">Step {s_num}: {html.escape(cat)}</span>
                            <span style="font-size: 0.72rem; background: var(--nb-surface); color: {c_color}; border: 1.5px solid var(--nb-border); padding: 2px 8px; border-radius: 2px; font-weight: 800; font-family: 'JetBrains Mono', monospace;">{cat.upper()}</span>
                          </div>
                          <div style="font-size: 0.88rem; color: var(--nb-text); margin-top: 6px;">{html.escape(desc)}</div>
                          <div style="font-size: 0.75rem; color: var(--nb-text-muted); margin-top: 4px; font-family: 'JetBrains Mono', monospace;">Targets: {', '.join(targets) if targets else 'N/A'}</div>
                        </div>
                        """
                        render_html(step_card_html)
                else:
                    st.success("No remedial actions required.")

                st.divider()
                st.markdown("#### CI/CD Recommendations")
                ci_recs = active_impact.get("risk_analysis", {}).get("ci_cd_recommendations", [])
                for rec in ci_recs:
                    st.markdown(f"- {rec}")

                st.divider()
                st.markdown("#### Key Risk Factors")
                factors = active_impact.get("risk_analysis", {}).get("key_risk_factors", [])
                if factors:
                    st.dataframe(factors, use_container_width=True)

            with t_json:
                col_dl, _ = st.columns([1, 3])
                with col_dl:
                    st.download_button(
                        label="Download Full Impact JSON",
                        data=json.dumps(active_impact, indent=2),
                        file_name=f"trace_impact_analysis_{meta.get('analysis_id', 'run')[:8]}.json",
                        mime="application/json",
                        use_container_width=True,
                    )
                st.json(active_impact)

    with tab_upgrade_planner:
        with st.container(border=True):
            st.markdown(
                """
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 800; color: var(--nb-text-muted); margin-bottom: 2px;">
                  Upgrade Planner & Orchestration Control
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.subheader("F07: Actionable Upgrade Planner & Dependency Orchestration")
            st.caption("Transforms impact analysis and risk assessments into an actionable, dependency-ordered engineering upgrade plan.")

            # Historical Plans for Repository
            hist_code, hist_res = make_api_request(f"{api_url}/repositories/{selected_repo_id}/upgrade-plans")
            existing_plans: list[dict[str, Any]] = hist_res.get("items", []) if (hist_code == 200 and hist_res) else []

            col_p1, col_p2 = st.columns([2, 1])
            with col_p1:
                st.markdown("##### Plan Generation & Selection")
            with col_p2:
                if existing_plans:
                    plan_options = {f"{p['title']} ({p['status']} - {p['progress_percentage']}%)": p["id"] for p in existing_plans}
                    selected_plan_label = st.selectbox("Load Existing Plan", options=["-- New Plan --"] + list(plan_options.keys()))
                    if selected_plan_label != "-- New Plan --":
                        st.session_state["active_plan_id"] = plan_options[selected_plan_label]

            # Generator form
            with st.expander("Generate New Upgrade Plan", expanded=("active_plan_id" not in st.session_state)):
                c_g1, c_g2, c_g3 = st.columns([2, 2, 2])
                with c_g1:
                    p_base = st.text_input("Base Revision", value="HEAD~1", key="f07_base")
                with c_g2:
                    p_target = st.text_input("Target Revision", value="HEAD", key="f07_target")
                with c_g3:
                    p_title = st.text_input("Plan Title (Optional)", value=f"Upgrade Plan: {p_base} ➜ {p_target}", key="f07_title")

                # Check if active impact analysis from F05 exists
                active_impact_data = st.session_state.get("active_impact_data")
                use_active_impact = False
                active_impact_id = None
                if active_impact_data:
                    active_impact_id = active_impact_data.get("analysis_metadata", {}).get("analysis_id")
                    if active_impact_id:
                        use_active_impact = st.checkbox(
                            f"Link to Active Impact Analysis (`{str(active_impact_id)[:8]}...`)",
                            value=True,
                            help="Reuse already computed AST diffs, callers at risk, and blast radius from F05.",
                        )

                gen_btn = st.button("Generate Upgrade Plan", type="primary", use_container_width=True)

                if gen_btn:
                    with st.spinner("Sequencing task dependency DAG, running Tarjan SCC cycle detection, and classifying architectural tiers..."):
                        gen_payload = {
                            "repository_id": selected_repo_id,
                            "impact_analysis_id": active_impact_id if use_active_impact else None,
                            "base_ref": p_base.strip() or "HEAD~1",
                            "target_ref": p_target.strip() or "HEAD",
                            "title": p_title.strip() or None,
                            "llm_config": {
                                "enabled": bool(enable_ai and openrouter_key.strip()),
                                "api_key": openrouter_key.strip() if enable_ai else None,
                                "model": openrouter_model if enable_ai else "mistralai/mistral-7b-instruct:free",
                            },
                        }
                        g_code, g_res = make_api_request(
                            f"{api_url}/upgrade-plans/generate",
                            method="POST",
                            payload=gen_payload,
                            timeout=120.0,
                        )
                        if g_code in (200, 201) and g_res:
                            st.session_state["active_plan_id"] = g_res["id"]
                            st.success(f"Upgrade Plan generated successfully! Plan ID: `{g_res['id']}`")
                            st.rerun()
                        else:
                            st.error(f"Plan generation failed ({g_code}): {g_res}")

        # Active Plan Inspector & Task Lifecycle
        curr_plan_id = st.session_state.get("active_plan_id")
        if curr_plan_id:
            plan_code, plan_data = make_api_request(f"{api_url}/upgrade-plans/{curr_plan_id}")
            if plan_code == 200 and plan_data:
                st.divider()

                p_status = plan_data.get("status", "DRAFT")
                p_risk = plan_data.get("risk_level", "LOW")
                metrics = plan_data.get("summary_metrics", {})
                pct = metrics.get("progress_percentage", 0.0)

                p_significance = plan_data.get("change_significance", "MODERATE_CHANGE")
                p_reasoning = plan_data.get("significance_reasoning", "")
                p_recommended_action = plan_data.get("recommended_action", "")
                p_order_rationale = plan_data.get("order_rationale", "")
                p_suggestions = plan_data.get("optional_suggestions", [])

                sig_palette = {
                    "MAJOR_CHANGE": {"border": "#ef4444", "bg": "#ef444420", "text": "#dc2626", "label": "Major Change"},
                    "MODERATE_CHANGE": {"border": "#f59e0b", "bg": "#f59e0b20", "text": "#d97706", "label": "Moderate Change"},
                    "MINOR_CHANGE": {"border": "#2563eb", "bg": "#2563eb20", "text": "#2563eb", "label": "Minor Change"},
                    "NO_ACTION_REQUIRED": {"border": "#64748b", "bg": "#64748b20", "text": "#475569", "label": "No Action Required"},
                }
                sig_meta = sig_palette.get(p_significance, sig_palette["MODERATE_CHANGE"])

                risk_colors = {
                    "CRITICAL": "#ef4444",
                    "HIGH": "#ea580c",
                    "MEDIUM": "#d97706",
                    "LOW": "#16a34a",
                }
                r_color = risk_colors.get(p_risk, "#2563eb")

                status_colors = {
                    "COMPLETED": "#16a34a",
                    "IN_PROGRESS": "#2563eb",
                    "DRAFT": "#64748b",
                    "CANCELLED": "#71717a",
                }
                s_color = status_colors.get(p_status, "#64748b")

                # 1. UPGRADE ASSESSMENT CARD
                render_html(f"""
                <div style="background: var(--card-bg); border: 2px solid var(--border-color); border-left: 6px solid {sig_meta['border']}; box-shadow: 3px 3px 0px var(--shadow-color); padding: 18px 20px; margin-bottom: 20px; border-radius: 0px;">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">
                    <div>
                      <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text-secondary); font-weight: 700;">Upgrade Assessment</div>
                      <h3 style="margin: 4px 0 6px 0; color: var(--text-primary); font-size: 1.4rem; font-weight: 800; font-family: 'JetBrains Mono', Consolas, monospace;">{plan_data.get('title', 'Upgrade Plan')}</h3>
                      <div style="font-size: 0.82rem; color: var(--text-secondary); font-family: 'JetBrains Mono', Consolas, monospace;">
                        Revisions: <span style="background: var(--bg-canvas); border: 1px solid var(--border-color); padding: 2px 6px; font-weight: 700; color: var(--text-primary);">{plan_data.get('base_commit', '')[:7]}</span> ➔ <span style="background: var(--bg-canvas); border: 1px solid var(--border-color); padding: 2px 6px; font-weight: 700; color: var(--text-primary);">{plan_data.get('target_commit', '')[:7]}</span>
                        &bull; Mode: <strong style="color: var(--text-primary);">{plan_data.get('reasoning_mode', 'HEURISTIC')}</strong>
                      </div>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                      <div style="background: {sig_meta['bg']}; border: 2px solid {sig_meta['border']}; box-shadow: 2px 2px 0px var(--shadow-color); padding: 6px 12px; text-align: center; border-radius: 0px;">
                        <div style="font-size: 0.85rem; font-weight: 800; color: {sig_meta['text']}; font-family: 'JetBrains Mono', Consolas, monospace;">{sig_meta['label']}</div>
                        <div style="font-size: 0.62rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 700; letter-spacing: 0.5px;">Significance</div>
                      </div>
                      <div style="background: {r_color}18; border: 2px solid {r_color}; box-shadow: 2px 2px 0px var(--shadow-color); padding: 6px 12px; text-align: center; border-radius: 0px;">
                        <div style="font-size: 0.85rem; font-weight: 800; color: {r_color}; font-family: 'JetBrains Mono', Consolas, monospace;">{p_risk}</div>
                        <div style="font-size: 0.62rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 700; letter-spacing: 0.5px;">Risk Rating</div>
                      </div>
                      <div style="background: {s_color}18; border: 2px solid {s_color}; box-shadow: 2px 2px 0px var(--shadow-color); padding: 6px 12px; text-align: center; border-radius: 0px;">
                        <div style="font-size: 0.85rem; font-weight: 800; color: {s_color}; font-family: 'JetBrains Mono', Consolas, monospace;">{p_status}</div>
                        <div style="font-size: 0.62rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 700; letter-spacing: 0.5px;">Status</div>
                      </div>
                    </div>
                  </div>
                </div>
                """)

                # Recommended Action Banner
                if p_significance in ("MINOR_CHANGE", "NO_ACTION_REQUIRED"):
                    st.info(
                        f"**Recommended Action:** {p_recommended_action or 'No major upgrade work required. The revision contains documentation-only changes with no executable behavior or API contract changes.'}"
                    )
                else:
                    st.success(
                        f"**Recommended Action:** {p_recommended_action or 'A coordinated upgrade is recommended.'}"
                    )

                if p_reasoning:
                    st.markdown(f"**Architectural Reasoning:** {p_reasoning}")

                if p_order_rationale:
                    with st.expander("Why this order?", expanded=True):
                        st.markdown(p_order_rationale)

                # AI Plan Review (if available)
                ai_review = plan_data.get("ai_plan_review")
                if ai_review:
                    with st.expander("Senior Architect Review", expanded=False):
                        valid_seq = ai_review.get("sequence_valid", True)
                        conf = ai_review.get("confidence", "HIGH")
                        st.markdown(
                            f"**Topological Sequence:** {'Valid' if valid_seq else 'Review Sequence'} &bull; "
                            f"**Confidence:** `{conf}`"
                        )
                        for w in ai_review.get("warnings", []):
                            st.warning(f"Advisory: {w}")
                        for ms in ai_review.get("missing_task_suggestions", []):
                            st.info(
                                f"Suggested Component to Review: `{ms.get('component')}` — "
                                f"{ms.get('reason')} (Confidence: {ms.get('confidence', 'N/A')})"
                            )
                        for ut in ai_review.get("unnecessary_tasks", []):
                            st.caption(f"Potential Non-Critical Item: `{ut.get('component')}` — {ut.get('reason')}")

                # Progress & Metrics (only if tasks exist)
                all_tasks: list[dict[str, Any]] = plan_data.get("tasks", [])
                if all_tasks:
                    st.progress(float(pct) / 100.0)
                    st.caption(f"**Overall Progress: {pct}%** ({metrics.get('completed_tasks', 0)} of {metrics.get('total_tasks', 0)} tasks resolved)")

                    m_c1, m_c2, m_c3, m_c4, m_c5, m_c6 = st.columns(6)
                    m_c1.metric("Total Tasks", metrics.get("total_tasks", 0))
                    m_c2.metric("Completed", metrics.get("completed_tasks", 0))
                    m_c3.metric("In Progress", metrics.get("in_progress_tasks", 0))
                    m_c4.metric("Pending", metrics.get("pending_tasks", 0))
                    m_c5.metric("Blocked", metrics.get("blocked_tasks", 0))
                    m_c6.metric("Skipped", metrics.get("skipped_tasks", 0))

                    st.divider()

                    # Filter Toolbar
                    t_col1, t_col2, t_col3, t_col4 = st.columns([1.5, 1.5, 2, 1.5])
                    with t_col1:
                        filter_status = st.selectbox(
                            "Status",
                            options=["ALL", "PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED", "SKIPPED"],
                            index=0,
                            key="f07_filter_status",
                        )
                    with t_col2:
                        filter_risk = st.selectbox(
                            "Risk",
                            options=["ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
                            index=0,
                            key="f07_filter_risk",
                        )
                    with t_col3:
                        filter_category = st.selectbox(
                            "Architectural Tier",
                            options=[
                                "ALL",
                                "CONTRACT_API",
                                "CORE_LOGIC",
                                "DATA_MAPPING",
                                "CONSUMER_HANDLER",
                                "CLIENT_UI",
                                "INTEGRATION_TEST",
                                "DOCUMENTATION_CONFIG",
                            ],
                            index=0,
                            key="f07_filter_cat",
                        )
                    with t_col4:
                        st.write("")
                        st.download_button(
                            label="Download Plan JSON",
                            data=json.dumps(plan_data, indent=2),
                            file_name=f"upgrade_plan_{curr_plan_id[:8]}.json",
                            mime="application/json",
                            use_container_width=True,
                        )

                    # Filter Tasks
                    filtered_tasks = all_tasks
                    if filter_status != "ALL":
                        filtered_tasks = [t for t in filtered_tasks if t.get("status") == filter_status]
                    if filter_risk != "ALL":
                        filtered_tasks = [t for t in filtered_tasks if t.get("risk_level") == filter_risk]
                    if filter_category != "ALL":
                        filtered_tasks = [t for t in filtered_tasks if t.get("category") == filter_category]

                    st.markdown(f"#### Ordered Upgrade Tasks ({len(filtered_tasks)} of {len(all_tasks)})")

                    tier_details = {
                        "CONTRACT_API": {
                            "border": "#ef4444", "bg": "#ef444418", "text": "#dc2626",
                            "name": "Tier 1 · API / Contract",
                            "desc": "Public APIs, interfaces, schemas, request/response contracts",
                        },
                        "CORE_LOGIC": {
                            "border": "#8b5cf6", "bg": "#8b5cf618", "text": "#7c3aed",
                            "name": "Tier 2 · Core Logic",
                            "desc": "Business rules, services, domain/application logic",
                        },
                        "DATA_MAPPING": {
                            "border": "#2563eb", "bg": "#2563eb18", "text": "#2563eb",
                            "name": "Tier 3 · Data / Mapping",
                            "desc": "Database models, repositories, ORM mappings, serialization/data transformations",
                        },
                        "CONSUMER_HANDLER": {
                            "border": "#f59e0b", "bg": "#f59e0b18", "text": "#d97706",
                            "name": "Tier 4 · Handlers / Consumers",
                            "desc": "Event handlers, webhooks, message consumers, adapters",
                        },
                        "CLIENT_UI": {
                            "border": "#ec4899", "bg": "#ec489918", "text": "#db2777",
                            "name": "Tier 5 · Client / UI",
                            "desc": "Frontend, UI components, templates, client-facing behavior",
                        },
                        "INTEGRATION_TEST": {
                            "border": "#10b981", "bg": "#10b98118", "text": "#059669",
                            "name": "Tier 6 · Tests / Integration",
                            "desc": "Unit, integration, end-to-end and regression tests",
                        },
                        "DOCUMENTATION_CONFIG": {
                            "border": "#64748b", "bg": "#64748b18", "text": "#475569",
                            "name": "Tier 7 · Documentation / Config",
                            "desc": "Documentation, comments, non-runtime configuration and supporting project files",
                        },
                    }

                    action_type_styles = {
                        "REQUIRED_CHANGE": {"color": "#ef4444", "bg": "#ef444420", "label": "Required Change"},
                        "VALIDATION_ONLY": {"color": "#2563eb", "bg": "#2563eb20", "label": "Validation Only"},
                        "LOW_PRIORITY_REVIEW": {"color": "#d97706", "bg": "#facc1530", "label": "Review"},
                        "NO_ACTION": {"color": "#64748b", "bg": "#64748b20", "label": "No Action"},
                    }

                    if not filtered_tasks:
                        st.info("No tasks match the active filters.")
                    else:
                        for t in filtered_tasks:
                            t_id = t["id"]
                            step_num = t.get("step_number", 0)
                            comp = t.get("component", "unknown")
                            comp_type = t.get("component_type", "function")
                            cat = t.get("category", "CORE_LOGIC")
                            reason = t.get("reason", "")
                            expected = t.get("expected_changes", "")
                            tests = t.get("required_tests", [])
                            deps = t.get("dependencies", [])
                            t_status = t.get("status", "PENDING")
                            t_risk = t.get("risk_level", "LOW")
                            is_circ = t.get("is_circular", False)
                            p_group = t.get("parallel_group_id", 1)
                            evidence = t.get("evidence") or {}

                            t_tier = tier_details.get(cat, tier_details["CORE_LOGIC"])
                            tier_name_display = t.get("tier_name") or t_tier["name"]
                            tier_meaning_display = t.get("tier_meaning") or t_tier["desc"]

                            act_type = t.get("action_type", "REQUIRED_CHANGE")
                            act_style = action_type_styles.get(act_type, action_type_styles["REQUIRED_CHANGE"])

                            circ_alert = ""
                            if is_circ:
                                circ_alert = f"""
                                <div style="background: #ef444418; border: 2px solid #ef4444; box-shadow: 2px 2px 0px var(--shadow-color); padding: 6px 10px; margin-bottom: 10px; font-size: 0.8rem; color: #ef4444; font-weight: 700; border-radius: 0px;">
                                  Circular Dependency: Co-dependent refactoring required across cyclic cluster.
                                </div>
                                """

                            render_html(f"""
                            <div style="background: var(--card-bg); border: 2px solid var(--border-color); border-left: 6px solid {t_tier['border']}; box-shadow: 3px 3px 0px var(--shadow-color); padding: 14px 16px; margin-bottom: 14px; border-radius: 0px;">
                              {circ_alert}
                              <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
                                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                                  <span style="background: var(--text-primary); color: var(--card-bg); border: 1.5px solid var(--border-color); font-weight: 800; font-size: 0.78rem; padding: 2px 8px; font-family: 'JetBrains Mono', Consolas, monospace; border-radius: 0px;">STEP {step_num}</span>
                                  <span style="background: {t_tier['bg']}; color: {t_tier['text']}; border: 1.5px solid {t_tier['border']}; font-size: 0.75rem; padding: 2px 8px; font-weight: 700; font-family: 'JetBrains Mono', Consolas, monospace; border-radius: 0px;">{tier_name_display}</span>
                                  <span style="background: {act_style['bg']}; color: {act_style['color']}; border: 1.5px solid {act_style['color']}; font-size: 0.75rem; padding: 2px 8px; font-weight: 700; font-family: 'JetBrains Mono', Consolas, monospace; border-radius: 0px;">{act_style['label']}</span>
                                  <span style="background: var(--bg-canvas); color: var(--text-secondary); border: 1px solid var(--border-color); font-size: 0.72rem; padding: 2px 6px; font-family: 'JetBrains Mono', Consolas, monospace; border-radius: 0px;">STREAM #{p_group}</span>
                                </div>
                                <div style="display: flex; gap: 6px; align-items: center;">
                                  <span style="font-size: 0.75rem; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: 700; color: {risk_colors.get(t_risk, '#94a3b8')}; border: 1.5px solid {risk_colors.get(t_risk, '#94a3b8')}; padding: 2px 8px; background: {risk_colors.get(t_risk, '#94a3b8')}18; border-radius: 0px;">RISK: {t_risk}</span>
                                  <span style="font-size: 0.75rem; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: 700; color: {status_colors.get(t_status, '#94a3b8')}; border: 1.5px solid {status_colors.get(t_status, '#94a3b8')}; padding: 2px 8px; background: {status_colors.get(t_status, '#94a3b8')}18; border-radius: 0px;">{t_status}</span>
                                </div>
                              </div>
                              <div style="font-size: 0.74rem; color: var(--text-secondary); margin-bottom: 8px;">
                                {tier_meaning_display}
                              </div>
                              <div style="font-size: 1.02rem; font-weight: 800; color: var(--text-primary); margin-bottom: 8px;">
                                <code style="font-family: 'JetBrains Mono', Consolas, monospace; background: var(--bg-canvas); border: 1px solid var(--border-color); padding: 2px 6px; font-size: 0.95rem; color: var(--text-primary);">{comp}</code> <span style="color: var(--text-secondary); font-size: 0.8rem; font-weight: 600; font-family: 'JetBrains Mono', Consolas, monospace;">({comp_type})</span>
                              </div>
                              <div style="font-size: 0.85rem; color: var(--text-primary); margin-bottom: 8px; line-height: 1.4;">
                                <strong>Why this matters:</strong> {reason}
                              </div>
                              <div style="background: var(--bg-canvas); border: 1px solid var(--border-color); border-left: 4px solid var(--accent-blue); padding: 8px 12px; margin-bottom: 8px; font-size: 0.82rem; color: var(--text-primary); border-radius: 0px;">
                                <strong>{'Validation:' if act_type == 'VALIDATION_ONLY' else 'What to change:'}</strong> {expected}
                              </div>
                            </div>
                            """)

                            c_m1, c_m2 = st.columns(2)
                            with c_m1:
                                if deps:
                                    st.caption(f"**Depends on ({len(deps)}):**")
                                    st.write(", ".join(f"`{d}`" for d in deps))
                                else:
                                    st.caption("**Depends on:** None (Root Step)")
                            with c_m2:
                                if tests:
                                    st.caption(f"**Required Tests ({len(tests)}):**")
                                    st.write(", ".join(f"`{test}`" for test in tests))
                                else:
                                    st.caption("**Required Tests:** None")

                            diff_snip = evidence.get("diff_snippet", "")
                            call_chain = evidence.get("call_chain", [])
                            lines_aff = evidence.get("lines_affected", [])
                            if diff_snip or call_chain:
                                with st.expander(f"Evidence for `{comp}`"):
                                    if call_chain:
                                        st.caption(f"Call Chain: `{' ➜ '.join(call_chain)}`")
                                    if lines_aff and len(lines_aff) == 2 and lines_aff != [0, 0]:
                                        st.caption(f"Lines Affected: {lines_aff[0]}–{lines_aff[1]}")
                                    if diff_snip:
                                        st.code(diff_snip, language="diff")

                            # Interactive Status Updater
                            with st.expander(f"Update Step #{step_num} Status", expanded=False):
                                u_col1, u_col2, u_col3 = st.columns([2, 3, 1.5])
                                with u_col1:
                                    new_st = st.selectbox(
                                        "Status",
                                        options=["PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED", "SKIPPED"],
                                        index=["PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED", "SKIPPED"].index(t_status) if t_status in ["PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED", "SKIPPED"] else 0,
                                        key=f"status_sel_{t_id}",
                                    )
                                with u_col2:
                                    new_notes = st.text_input(
                                        "Developer Notes",
                                        value=t.get("notes") or "",
                                        placeholder="e.g. verified locally",
                                        key=f"notes_in_{t_id}",
                                    )
                                with u_col3:
                                    st.write("")
                                    if st.button("Save", key=f"btn_save_{t_id}", use_container_width=True):
                                        patch_payload = {"status": new_st, "notes": new_notes.strip() or None}
                                        p_code, p_res = make_api_request(
                                            f"{api_url}/upgrade-plans/{curr_plan_id}/tasks/{t_id}",
                                            method="PATCH",
                                            payload=patch_payload,
                                        )
                                        if p_code == 200:
                                            st.success(f"Step #{step_num} updated to {new_st}")
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to update task: {p_res}")

                # 3. OPTIONAL RECOMMENDATIONS (TASK != SUGGESTION)
                info_changes = plan_data.get("informational_changes", [])
                if p_suggestions or info_changes:
                    st.divider()
                    st.markdown("#### Optional Recommendations")
                    st.caption(
                        "Advisory guidance and non-code items. Suggestions do NOT affect upgrade "
                        "task count, dependency ordering, or progress tracking."
                    )

                    if p_suggestions:
                        for sug in p_suggestions:
                            st.markdown(f"&bull; {sug}")

                    if info_changes:
                        with st.expander(f"Non-Behavioral & Documentation Changes ({len(info_changes)})", expanded=False):
                            for ic in info_changes:
                                render_html(f"""
                                <div style="background: var(--card-bg); border: 1.5px solid var(--border-color); border-left: 4px solid var(--text-secondary); box-shadow: 2px 2px 0px var(--shadow-color); padding: 8px 12px; margin-bottom: 8px; border-radius: 0px;">
                                  <div style="font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', Consolas, monospace;"><code>{ic.get('component')}</code> <span style="font-size: 0.72rem; color: var(--text-secondary);">({ic.get('actionability', 'INFORMATIONAL')})</span></div>
                                  <div style="font-size: 0.82rem; color: var(--text-secondary); margin-top: 4px;">{ic.get('reason')}</div>
                                </div>
                                """)
                                if ic.get("diff_snippet"):
                                    with st.expander(f"Diff for {ic.get('component')}"):
                                        st.code(ic.get("diff_snippet"), language="diff")
            else:
                st.error(f"Failed to load plan `{curr_plan_id}`: {plan_data}")


if __name__ == "__main__":
    run_app()
