"""TRACE Static Code Analysis Evaluation Observatory (Streamlit Dashboard).

This dashboard provides an evaluation interface to trigger, observe, and inspect
TRACE Phase 2 (F02) repository code analysis runs via REST API endpoints.
Completely decoupled from backend internal domain and database models.
"""

import html
import json
import os
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


def render_colored_diff(file_diff: dict[str, Any]) -> str:
    """Render a GitHub-style colored unified diff with green additions and red deletions."""
    hunks = file_diff.get("hunks", [])
    if not hunks:
        return "<div style='color: #94a3b8; font-style: italic; padding: 10px;'>No line hunks available for this file.</div>"

    html_parts = [
        """<div style="font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px; background: #0b0f19; border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; margin-top: 8px; margin-bottom: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);">"""
    ]

    for h_idx, h in enumerate(hunks, 1):
        old_start = h.get("old_start", 0)
        old_lines = h.get("old_lines", 0)
        new_start = h.get("new_start", 0)
        new_lines = h.get("new_lines", 0)
        header_text = h.get("header", "").strip()

        context_str = f" &bull; <span style='color: #93c5fd;'>{html.escape(header_text)}</span>" if header_text else ""
        html_parts.append(
            f"""<div style="background: #111827; color: #38bdf8; padding: 7px 12px; font-weight: 600; font-size: 11px; border-bottom: 1px solid #1e293b; border-top: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between;">
                <div><span>📍 Hunk #{h_idx}: Lines {new_start}–{new_start + max(0, new_lines - 1)}</span>{context_str}</div>
                <div style="font-size: 10px; color: #64748b; font-family: monospace;">- {old_start},{old_lines} / + {new_start},{new_lines}</div>
            </div>"""
        )

        content = h.get("content", "")
        if not content:
            continue

        old_ptr = old_start
        new_ptr = new_start

        html_parts.append("""<table style="width: 100%; border-collapse: collapse; table-layout: fixed;">""")

        for raw_line in content.splitlines():
            line_str = html.escape(raw_line)
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                bg = "rgba(16, 185, 129, 0.15)"
                text_color = "#34d399"
                border_style = "border-left: 3px solid #10b981;"
                old_num = ""
                new_num = str(new_ptr)
                new_ptr += 1
                sym = "+"
                code_text = line_str[1:] if len(line_str) > 1 else ""
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                bg = "rgba(239, 68, 68, 0.15)"
                text_color = "#f87171"
                border_style = "border-left: 3px solid #ef4444;"
                old_num = str(old_ptr)
                new_num = ""
                old_ptr += 1
                sym = "-"
                code_text = line_str[1:] if len(line_str) > 1 else ""
            else:
                bg = "transparent"
                text_color = "#cbd5e1"
                border_style = "border-left: 3px solid transparent;"
                old_num = str(old_ptr)
                new_num = str(new_ptr)
                old_ptr += 1
                new_ptr += 1
                sym = " "
                code_text = line_str[1:] if (len(line_str) > 1 and raw_line.startswith(" ")) else line_str

            html_parts.append(
                f"""<tr style="background: {bg}; {border_style}; line-height: 20px;">
                    <td style="width: 38px; text-align: right; padding: 0 6px; color: #475569; user-select: none; font-size: 11px; border-right: 1px solid rgba(255,255,255,0.05); font-family: monospace;">{old_num}</td>
                    <td style="width: 38px; text-align: right; padding: 0 6px; color: #475569; user-select: none; font-size: 11px; border-right: 1px solid rgba(255,255,255,0.05); font-family: monospace;">{new_num}</td>
                    <td style="width: 18px; text-align: center; color: {text_color}; font-weight: bold; user-select: none; font-family: monospace;">{sym}</td>
                    <td style="padding: 0 8px; color: {text_color}; white-space: pre-wrap; word-break: break-all; font-family: 'JetBrains Mono', monospace;">{code_text}</td>
                </tr>"""
            )

        html_parts.append("""</table>""")

    html_parts.append("""</div>""")
    return "".join(html_parts)


def build_impact_graph_json(d_detail: dict[str, Any]) -> dict[str, Any]:
    """Construct a complete, structured JSON graph representing code changes and blast radius."""
    sym_diffs = d_detail.get("symbol_diffs", [])
    blast_items = d_detail.get("blast_radius", [])
    summ = d_detail.get("summary", {})

    nodes_dict: dict[str, dict[str, Any]] = {}
    edges_list: list[dict[str, Any]] = []

    # 1. Add changed & breaking symbol nodes
    for s in sym_diffs:
        sid = s.get("symbol_id") or s.get("qualified_name", "")
        is_breaking = s.get("is_breaking", False)
        ch_kind = s.get("change_kind", "MODIFIED")

        category = "Breaking Change" if is_breaking else "Changed Symbol"
        status = "BREAKING" if is_breaking else ch_kind

        short_name = s.get("qualified_name", sid)
        if "::" in short_name:
            short_name = short_name.split("::")[1]
        elif "." in short_name:
            short_name = short_name.split(".")[-1]

        nodes_dict[sid] = {
            "id": sid,
            "label": str(short_name)[:24],
            "qualified_name": s.get("qualified_name"),
            "kind": s.get("kind", "symbol"),
            "category": category,
            "status": status,
            "file_path": s.get("file_path", ""),
            "is_breaking": is_breaking,
            "breaking_reason": s.get("breaking_reason"),
            "old_signature": s.get("old_signature"),
            "new_signature": s.get("new_signature"),
        }

    # 2. Add affected blast radius nodes & edges
    for b in blast_items:
        t_id = b.get("target_symbol_id")
        aff_id = b.get("affected_symbol_id") or b.get("affected_qualified_name", "")
        aff_name = b.get("affected_qualified_name") or aff_id

        short_aff = aff_name
        if "::" in short_aff:
            short_aff = short_aff.split("::")[1]
        elif "." in short_aff:
            short_aff = short_aff.split(".")[-1]

        if aff_id not in nodes_dict:
            nodes_dict[aff_id] = {
                "id": aff_id,
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

        if t_id:
            edges_list.append({
                "from": aff_id,
                "to": t_id,
                "relationship": b.get("relationship_kind", "DEPENDS_ON"),
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
        page_icon="🔬",
        layout="wide",
    )

    st.title("🔬 TRACE Code Intelligence Observatory")
    st.caption("Phase 2 (F02) — Deterministic Static Code Analysis & Structural Intelligence")

    # Sidebar configuration
    st.sidebar.header("Configuration & Connectivity")
    api_url = st.sidebar.text_input(
        "TRACE API Base URL",
        value=os.environ.get("TRACE_API_URL", "http://127.0.0.1:8000/api/v1"),
    )

    health_url = api_url.rsplit("/api/v1", 1)[0] + "/health"
    status_code, health_data = make_api_request(health_url)
    if status_code == 200:
        st.sidebar.success("Backend API Connected")
    else:
        st.sidebar.warning(f"Backend API Offline ({status_code})")

    # Fetch projects
    projects_code, projects_data = make_api_request(f"{api_url}/projects")
    projects_list = projects_data.get("items", []) if projects_code == 200 and projects_data else []

    # Sidebar: Project Management
    with st.sidebar.expander("➕ Create New Project", expanded=(len(projects_list) == 0)):
        with st.form("create_project_form"):
            new_p_name = st.text_input("Project Name", placeholder="e.g. TRACE-Core")
            new_p_desc = st.text_area("Description (optional)", placeholder="Core TRACE engine")
            create_p_btn = st.form_submit_button("Create Project", type="primary")
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
        st.info("👋 Welcome to TRACE! No projects registered yet. Use the sidebar to create your first project.")
        return

    project_map = {f"{p['name']} ({p['id'][:8]}...)": p["id"] for p in projects_list}
    selected_project_name = st.sidebar.selectbox("Select Project", options=list(project_map.keys()))
    selected_project_id = project_map[selected_project_name]

    # Fetch repositories for selected project
    repos_code, repos_data = make_api_request(f"{api_url}/projects/{selected_project_id}/repositories")
    repos_list = repos_data.get("items", []) if repos_code == 200 and repos_data else []

    # Sidebar: Repository Management
    with st.sidebar.expander("➕ Register Repository", expanded=(len(repos_list) == 0)):
        with st.form("register_repo_form"):
            repo_kind = st.radio("Source Type", ["🌐 Remote Git Repo", "📁 Local Path"], horizontal=True)
            if repo_kind == "🌐 Remote Git Repo":
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
            reg_btn = st.form_submit_button("Register Repository", type="primary")
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

    repo_map = {f"{r['location']} [{r['type']}]": r["id"] for r in repos_list}
    selected_repo_name = st.sidebar.selectbox("Select Repository", options=list(repo_map.keys()))
    selected_repo_id = repo_map[selected_repo_name]


    # Observatory Top-Level Navigation
    tab_intelligence, tab_version_diff = st.tabs([
        "🔬 Code Intelligence & Dependency Graph (F02/F03)",
        "⚡ Version & Change Impact Analyzer (F04)",
    ])

    with tab_intelligence:
        # Analysis Control Panel
        st.subheader("Repository Code Analysis Control")
        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            target_ref = st.text_input("Target Ref / Commit SHA (optional)", value="HEAD", key="f02_target_ref")
        with col2:
            exclude_patterns_str = st.text_input("Exclude Patterns (comma-separated)", value="tests/*, docs/*", key="f02_exclude")
        with col3:
            st.write("")
            st.write("")
            trigger_btn = st.button("🚀 Analyze Repository", type="primary", use_container_width=True)

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
                    ["🧩 Discovered Entities", "🔗 Structural Relationships", "🌐 Dependency Graph (Neo4j)", "⚠️ Diagnostics"]
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
                    st.markdown("#### 🌐 Interactive Dependency Graph Explorer")
                    st.caption("Force-directed interactive visual graph. Drag nodes, zoom, or hover to inspect symbol details.")
                    
                    g_nodes_code, g_nodes_data = make_api_request(f"{api_url}/analyses/{active_run_id}/graph/nodes?limit=300")
                    g_nodes = g_nodes_data.get("items", []) if g_nodes_code == 200 and g_nodes_data else []

                    g_rels_code, g_rels_data = make_api_request(f"{api_url}/analyses/{active_run_id}/graph/relationships?limit=300")
                    g_rels = g_rels_data.get("items", []) if g_rels_code == 200 and g_rels_data else []

                    if g_nodes:
                        render_graph_canvas(g_nodes, g_rels)
                    else:
                        st.info("No graph nodes returned yet. Neo4j may still be building the graph.")
                        if st.button("🔨 Build / Rebuild Graph in Neo4j", type="secondary"):
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

                    st.info("💡 You can also run custom Cypher queries in the dedicated [Neo4j Browser](http://localhost:7474) (user: `neo4j` / pass: `password`).")

                    with st.expander(f"📋 Raw Graph Data ({len(g_nodes)} Nodes, {len(g_rels)} Relationships)"):
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
        st.subheader("⚡ Version & Change Impact Analyzer (F04)")
        st.caption("Compare Git branches, commits, or pull request revisions to detect code symbol deltas, breaking changes, and blast radius.")

        # Fetch branches from backend
        b_code, b_data = make_api_request(f"{api_url}/repositories/{selected_repo_id}/branches")
        branches_list = b_data.get("branches", ["main"]) if b_code == 200 and b_data else ["main"]
        default_branch = b_data.get("default_branch", "main") if b_code == 200 and b_data else "main"

        diff_mode = st.radio(
            "Comparison Mode",
            ["🌿 Branch vs Branch", "⏱️ Quick Diff (HEAD~1 vs HEAD)", "🎯 Custom Commit Range"],
            horizontal=True,
        )

        d_col1, d_col2, d_col3 = st.columns([2, 2, 1])

        if diff_mode == "🌿 Branch vs Branch":
            with d_col1:
                base_branch = st.selectbox("Base Branch (e.g. main/production)", options=branches_list, index=0)
            with d_col2:
                target_idx = 1 if len(branches_list) > 1 else 0
                target_branch = st.selectbox("Target Branch (e.g. development/feature)", options=branches_list, index=target_idx)
            base_ref_val = base_branch
            target_ref_val = target_branch
        elif diff_mode == "⏱️ Quick Diff (HEAD~1 vs HEAD)":
            with d_col1:
                st.text_input("Base Revision", value="HEAD~1", disabled=True)
            with d_col2:
                st.text_input("Target Revision", value="HEAD", disabled=True)
            base_ref_val = "HEAD~1"
            target_ref_val = "HEAD"
        else:
            with d_col1:
                base_ref_val = st.text_input("Base Commit SHA / Tag", value="HEAD~1")
            with d_col2:
                target_ref_val = st.text_input("Target Commit SHA / Tag", value="HEAD")

        with d_col3:
            st.write("")
            st.write("")
            run_diff_btn = st.button("⚡ Run Change Analysis", type="primary", use_container_width=True)

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
                risk_colors = {
                    "CRITICAL": "#ef4444",
                    "HIGH": "#f97316",
                    "MEDIUM": "#eab308",
                    "LOW": "#10b981",
                }
                r_color = risk_colors.get(risk_lvl, "#10b981")

                st.markdown(
                    f"""
                    <div style="background: linear-gradient(135deg, rgba(15,23,42,0.9), rgba(30,41,59,0.9)); border: 1px solid {r_color}; border-radius: 12px; padding: 18px; margin-bottom: 20px; box-shadow: 0 0 25px {r_color}33;">
                      <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                          <span style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1.5px; color: #94a3b8; font-weight: 600;">Overall Change Impact Risk</span>
                          <h2 style="margin: 4px 0 0 0; color: {r_color}; font-size: 1.9rem; font-weight: 800; letter-spacing: 0.5px;">{risk_lvl} RISK</h2>
                          <div style="font-size: 0.85rem; color: #cbd5e1; margin-top: 6px;">
                            Comparing <code>{d_detail.get('base_ref')}</code> ({d_detail.get('base_commit_hash', '')[:7]}) ➜ <code>{d_detail.get('target_ref')}</code> ({d_detail.get('target_commit_hash', '')[:7]})
                          </div>
                        </div>
                        <div style="background: {r_color}22; border: 1px solid {r_color}; border-radius: 8px; padding: 10px 18px; text-align: right;">
                          <div style="font-size: 1.6rem; font-weight: 800; color: {r_color};">{d_detail['summary'].get('total_breaking_changes', 0)}</div>
                          <div style="font-size: 0.75rem; text-transform: uppercase; color: #cbd5e1; font-weight: 600;">Breaking Changes</div>
                        </div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                summ = d_detail.get("summary", {})
                rc1, rc2, rc3, rc4, rc5 = st.columns(5)
                rc1.metric("Files Changed", summ.get("total_files_changed", 0))
                rc2.metric("Insertions (+)", f"+{summ.get('total_insertions', 0)}")
                rc3.metric("Deletions (-)", f"-{summ.get('total_deletions', 0)}")
                rc4.metric("Symbols Changed", summ.get("total_symbols_changed", 0))
                rc5.metric("Breaking Changes", summ.get("total_breaking_changes", 0))

                # Subtabs
                tab_blast, tab_breaking, tab_files, tab_commits = st.tabs([
                    "🌐 Visual Impact Graph & Blast Radius",
                    "💥 Breaking Changes & Symbol Deltas",
                    "📁 File Diffs & Hunks",
                    "📜 Commit Log",
                ])

                with tab_blast:
                    st.markdown("#### 🌐 Change Propagation & Impact Graph")
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
                            label="📥 Download Graph JSON",
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
                        st.info("ℹ️ **Zero code symbols (functions, classes, endpoints) were modified in this changeset.** All changes were in non-code or documentation files, so no code nodes or graph dependencies are affected.")
                    else:
                        st.success("✅ **Zero downstream callers or dependents are impacted.** The modified symbols are self-contained with no incoming references in the repository graph.")

                    # Downstream Callers Table
                    if blast_items:
                        st.markdown(f"#### 💥 {len(blast_items)} Impacted Downstream Component(s)")
                        st.dataframe(blast_items, use_container_width=True)

                    # Expandable JSON Viewer for full transparency
                    with st.expander("📋 View Complete Change Impact Graph JSON"):
                        st.json(impact_graph_json)

                with tab_breaking:
                    sym_diffs = d_detail.get("symbol_diffs", [])
                    breaking_syms = [s for s in sym_diffs if s.get("is_breaking")]
                    non_breaking_syms = [s for s in sym_diffs if not s.get("is_breaking")]

                    if breaking_syms:
                        st.markdown(f"#### ⚠️ {len(breaking_syms)} Breaking Change(s) Detected")
                        for bs in breaking_syms:
                            with st.container():
                                st.markdown(
                                    f"""
                                    <div style="background: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                                      <div style="display: flex; justify-content: space-between;">
                                        <strong style="color: #fca5a5; font-size: 1rem;">[{bs.get('kind', '').upper()}] {bs.get('qualified_name')}</strong>
                                        <span style="background: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">BREAKING</span>
                                      </div>
                                      <div style="color: #fecaca; margin-top: 6px; font-size: 0.9rem;"><strong>Reason:</strong> {bs.get('breaking_reason', 'Signature altered incompatibly')}</div>
                                      <div style="margin-top: 8px; font-family: monospace; font-size: 0.85rem; color: #94a3b8;">
                                        <div><span style="color: #ef4444;">- Old:</span> {bs.get('old_signature') or 'None (Added)'}</div>
                                        <div><span style="color: #10b981;">+ New:</span> {bs.get('new_signature') or 'None (Deleted)'}</div>
                                      </div>
                                      <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">File: {bs.get('file_path')}</div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                 )
                    else:
                        st.success("✅ Zero breaking changes detected between these revisions.")

                    if non_breaking_syms:
                        st.markdown(f"#### 🔄 {len(non_breaking_syms)} Non-Breaking Symbol Modification(s)")
                        st.dataframe(non_breaking_syms, use_container_width=True)

                with tab_files:
                    st.markdown("#### 📁 File-Level Diffs")
                    f_diffs = d_detail.get("file_diffs", [])
                    if f_diffs:
                        for fd in f_diffs:
                            c_type = fd.get("change_type", "MODIFIED")
                            path_disp = fd.get("new_path") or fd.get("old_path")
                            ins = fd.get("insertions", 0)
                            dels = fd.get("deletions", 0)
                            
                            type_icon = {
                                "ADDED": "🟢 ADDED",
                                "DELETED": "🔴 DELETED",
                                "MODIFIED": "🟡 MODIFIED",
                                "RENAMED": "🟣 RENAMED",
                            }.get(c_type, c_type)

                            with st.expander(f"{type_icon}: `{path_disp}`  |  +{ins} / -{dels} lines"):
                                diff_html = render_colored_diff(fd)
                                st.markdown(diff_html, unsafe_allow_html=True)
                    else:
                        st.info("No file diffs recorded.")

                with tab_commits:
                    st.markdown("#### 📜 Commits in Changeset")
                    msgs = d_detail.get("commit_messages", [])
                    if msgs:
                        for idx, m in enumerate(msgs, 1):
                            st.markdown(f"{idx}. `{m}`")
                    else:
                        st.info("No commit messages retrieved for this comparison.")


if __name__ == "__main__":
    run_app()
