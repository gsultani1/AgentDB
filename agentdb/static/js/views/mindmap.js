(function() {
  const V = AgentDB.views.mindmap = {};
  const el = () => document.getElementById('view-mindmap');

  V.load = function() {
    el().innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2>Entity Mind Map</h2>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px">
        <input type="text" id="mm-entity" placeholder="Entity name or ID..." style="flex:1">
        <label style="font-size:12px;color:var(--text2)">Depth:</label>
        <input type="number" id="mm-depth" min="1" max="5" value="2" style="width:60px">
        <button class="btn" id="mm-render-btn">Render</button>
      </div>
      <div id="mm-canvas-wrap" style="position:relative;width:100%;overflow:hidden;border-radius:8px">
        <canvas id="mm-canvas" style="display:block;width:100%;background:var(--bg2,#1a1a2e);border-radius:8px"></canvas>
      </div>
      <div id="mm-status" style="margin-top:8px;font-size:12px;color:var(--text2)"></div>`;

    document.getElementById('mm-render-btn').addEventListener('click', V.render);
    document.getElementById('mm-entity').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') V.render();
    });

    // Set initial canvas size
    const canvas = document.getElementById('mm-canvas');
    canvas.width = canvas.parentElement.offsetWidth || 800;
    canvas.height = 600;
  };

  V.render = async function() {
    const query = document.getElementById('mm-entity').value.trim();
    const depth = parseInt(document.getElementById('mm-depth').value) || 2;
    const status = document.getElementById('mm-status');

    if (!query) { AgentDB.toast('Enter an entity name or ID'); return; }

    status.textContent = 'Loading entities...';

    // Fetch all entities, find match
    const listRes = await AgentDB.api('GET', '/api/entities?limit=200');
    if (listRes.status !== 'ok' || !listRes.data) {
      status.textContent = 'Failed to load entities.';
      return;
    }

    const entities = listRes.data;
    const match = entities.find(e =>
      e.id === query ||
      (e.name || '').toLowerCase() === query.toLowerCase() ||
      (e.name || '').toLowerCase().includes(query.toLowerCase())
    );

    if (!match) {
      status.textContent = `No entity found matching "${query}".`;
      return;
    }

    status.textContent = `Loading graph for "${match.name}" (depth ${depth})...`;

    const graphRes = await AgentDB.api('GET', `/api/entities/${match.id}/graph?depth=${depth}`);
    if (graphRes.status !== 'ok' || !graphRes.data) {
      status.textContent = 'Failed to load entity graph.';
      return;
    }

    const nodes = graphRes.data.nodes || [];
    const edges = graphRes.data.edges || [];

    if (!nodes.length) {
      status.textContent = 'Graph has no nodes.';
      return;
    }

    status.textContent = `Rendered ${nodes.length} nodes, ${edges.length} edges.`;

    const canvas = document.getElementById('mm-canvas');
    const wrap = document.getElementById('mm-canvas-wrap');
    canvas.width = wrap.offsetWidth || 800;
    canvas.height = Math.max(600, depth * 300);

    const ctx = canvas.getContext('2d');
    V.drawGraph(ctx, canvas, nodes, edges, depth);
  };

  V.drawGraph = function(ctx, canvas, nodes, edges, maxDepth) {
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;

    // Get CSS custom property colors
    const style = getComputedStyle(document.documentElement);
    const textColor = style.getPropertyValue('--text').trim() || '#e0e0e0';
    const bg2 = style.getPropertyValue('--bg2').trim() || '#1a1a2e';
    const stmColor = style.getPropertyValue('--stm').trim() || '#f39c12';
    const mtmColor = style.getPropertyValue('--mtm').trim() || '#2ecc71';
    const ltmColor = style.getPropertyValue('--ltm').trim() || '#3498db';

    const typeColors = {
      entity: '#0d9488',
      entities: '#0d9488',
      short_term_memory: stmColor,
      midterm_memory: mtmColor,
      long_term_memory: ltmColor,
      skill: mtmColor,
      skills: mtmColor,
      goal: '#3b82f6',
      goals: '#3b82f6',
      session: '#e74c3c',
      sessions: '#e74c3c'
    };

    // Clear canvas
    ctx.fillStyle = bg2;
    ctx.fillRect(0, 0, w, h);

    // Group nodes by depth
    const depthGroups = {};
    nodes.forEach(n => {
      const d = n.depth != null ? n.depth : 0;
      if (!depthGroups[d]) depthGroups[d] = [];
      depthGroups[d].push(n);
    });

    // Position nodes in concentric circles
    const positions = {};
    Object.keys(depthGroups).sort((a, b) => a - b).forEach(d => {
      const group = depthGroups[d];
      const depth = parseInt(d);
      if (depth === 0) {
        // Center node
        group.forEach(n => {
          positions[n.id] = { x: cx, y: cy, node: n };
        });
      } else {
        const radius = depth * 140 + 10;
        group.forEach((n, i) => {
          const angle = (2 * Math.PI * i) / group.length - Math.PI / 2;
          positions[n.id] = {
            x: cx + radius * Math.cos(angle),
            y: cy + radius * Math.sin(angle),
            node: n
          };
        });
      }
    });

    // Draw edges
    edges.forEach(e => {
      const from = positions[e.source] || positions[e.from];
      const to = positions[e.target] || positions[e.to];
      if (!from || !to) return;

      const weight = e.weight != null ? e.weight : 0.5;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.strokeStyle = 'rgba(13,148,136,0.3)';
      ctx.lineWidth = Math.max(0.5, weight * 3);
      ctx.stroke();

      // Edge label
      if (e.relation || e.label) {
        const mx = (from.x + to.x) / 2;
        const my = (from.y + to.y) / 2;
        ctx.font = '9px sans-serif';
        ctx.fillStyle = 'rgba(13,148,136,0.6)';
        ctx.textAlign = 'center';
        ctx.fillText(e.relation || e.label || '', mx, my - 4);
      }
    });

    // Draw nodes
    Object.values(positions).forEach(pos => {
      const n = pos.node;
      const depth = n.depth != null ? n.depth : 0;
      const r = depth === 0 ? 12 : 8;
      const type = (n.type || 'entity').toLowerCase();
      const color = typeColors[type] || '#0d9488';

      // Filled circle
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // Border for center node
      if (depth === 0) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Label above node
      const label = n.name || n.label || (n.id || '').substring(0, 8);
      ctx.font = depth === 0 ? 'bold 13px sans-serif' : '11px sans-serif';
      ctx.fillStyle = textColor;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText(label, pos.x, pos.y - r - 4);
    });
  };
})();
