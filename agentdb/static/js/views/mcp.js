(function() {
  const V = AgentDB.views.mcp = {};
  const el = () => document.getElementById('view-mcp');

  const MCP_TOOLS = [
    { name: 'retrieve_context', desc: 'Retrieve semantically relevant context (memories, entities, goals, skills) for a query' },
    { name: 'ingest_memory', desc: 'Store a new observation as a short-term memory' },
    { name: 'search_memories', desc: 'Semantic search across a memory tier (short, mid, or long)' },
    { name: 'list_memories', desc: 'List memories by tier with optional limit' },
    { name: 'create_entity', desc: 'Create a knowledge graph entity with type and aliases' },
    { name: 'list_entities', desc: 'List entities in the knowledge graph, optionally filtered by type' },
    { name: 'check_goals', desc: 'Check which active goals are relevant to the given context' },
    { name: 'get_health', desc: 'Check AgentDB health status and database info' },
    { name: 'run_consolidation', desc: 'Trigger a memory consolidation cycle' },
  ];

  const CONNECTION_EXAMPLES = {
    claude: `{
  "mcpServers": {
    "agentdb": {
      "command": "agentdb",
      "args": ["mcp", "--transport", "stdio"],
      "env": {}
    }
  }
}`,
    cursor: `{
  "mcpServers": {
    "agentdb": {
      "command": "agentdb",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}`,
    generic: `# stdio transport (default)
agentdb mcp --transport stdio

# SSE transport (HTTP-based)
agentdb mcp --transport sse --port 8421

# Connect via SSE endpoint
# URL: http://localhost:8421/sse`
  };

  V.load = async function() {
    // Fetch MCP status
    var status = await AgentDB.api('GET', '/api/mcp/status').catch(function() { return {}; });
    var mcpEnabled = status && status.data && status.data.enabled;
    var transport = (status && status.data && status.data.transport) || 'stdio';
    var port = (status && status.data && status.data.port) || 8421;

    var statusBadge = mcpEnabled
      ? '<span style="background:#22c55e;color:#fff;padding:2px 10px;border-radius:8px;font-size:12px">Enabled</span>'
      : '<span style="background:var(--text2);color:#fff;padding:2px 10px;border-radius:8px;font-size:12px">Disabled</span>';

    var toolCards = MCP_TOOLS.map(function(t) {
      return '<div style="background:var(--bg3);padding:12px;border-radius:8px">' +
        '<div style="font-weight:600;font-family:var(--mono);font-size:13px;margin-bottom:4px">' + AgentDB.esc(t.name) + '</div>' +
        '<div style="font-size:12px;color:var(--text2)">' + AgentDB.esc(t.desc) + '</div></div>';
    }).join('');

    var toolOptions = MCP_TOOLS.map(function(t) {
      return '<option value="' + t.name + '">' + t.name + '</option>';
    }).join('');

    el().innerHTML = `
      <h2 style="margin-bottom:16px">MCP Server</h2>

      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3>Status</h3>${statusBadge}
        </div>
        <div style="margin-top:12px;font-size:13px;color:var(--text2)">
          Transport: <strong>${AgentDB.esc(transport)}</strong> &nbsp;&bull;&nbsp; Port: <strong>${port}</strong>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>Available Tools (${MCP_TOOLS.length})</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:12px">
          ${toolCards}
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>Connection Instructions</h3>
        <div style="display:flex;gap:8px;margin-top:12px;margin-bottom:12px">
          <button class="btn mcp-conn-tab active" data-client="claude" onclick="AgentDB.views.mcp.switchConn('claude')">Claude Desktop</button>
          <button class="btn mcp-conn-tab" data-client="cursor" onclick="AgentDB.views.mcp.switchConn('cursor')">Cursor</button>
          <button class="btn mcp-conn-tab" data-client="generic" onclick="AgentDB.views.mcp.switchConn('generic')">Generic / CLI</button>
        </div>
        <pre id="mcp-conn-code" style="background:var(--bg1);padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.5"><code>${AgentDB.esc(CONNECTION_EXAMPLES.claude)}</code></pre>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>Test Tool Execution</h3>
        <div style="display:flex;gap:12px;align-items:center;margin-top:12px">
          <select id="mcp-test-tool" style="width:200px">${toolOptions}</select>
          <button class="btn btn-primary" onclick="AgentDB.views.mcp.execTool()">Execute</button>
        </div>
        <textarea id="mcp-test-params" placeholder='{"query": "test"}' style="width:100%;height:80px;margin-top:12px;font-family:var(--mono);font-size:13px"></textarea>
        <pre id="mcp-test-result" style="background:var(--bg1);padding:12px;border-radius:8px;margin-top:12px;font-size:13px;max-height:300px;overflow:auto;display:none"></pre>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>MCP Configuration</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:12px">
          <div>
            <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">MCP Enabled</label>
            <label class="setting-toggle"><input type="checkbox" id="mcp-cfg-enabled" ${mcpEnabled ? 'checked' : ''}
              onchange="AgentDB.views.mcp.saveCfg('mcp_enabled',this.checked?'true':'false')"><span class="slider"></span></label>
          </div>
          <div>
            <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">Transport</label>
            <select id="mcp-cfg-transport" onchange="AgentDB.views.mcp.saveCfg('mcp_transport',this.value)" style="width:100%">
              <option value="stdio" ${transport==='stdio'?'selected':''}>stdio</option>
              <option value="sse" ${transport==='sse'?'selected':''}>sse</option>
            </select>
          </div>
          <div>
            <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">Port</label>
            <input type="number" id="mcp-cfg-port" value="${port}" style="width:100%"
              onchange="AgentDB.views.mcp.saveCfg('mcp_port',this.value)">
          </div>
        </div>
      </div>`;
  };

  V.switchConn = function(client) {
    document.querySelectorAll('.mcp-conn-tab').forEach(function(b) {
      b.classList.toggle('active', b.getAttribute('data-client') === client);
    });
    document.getElementById('mcp-conn-code').innerHTML = '<code>' + AgentDB.esc(CONNECTION_EXAMPLES[client]) + '</code>';
  };

  V.execTool = async function() {
    var tool = document.getElementById('mcp-test-tool').value;
    var paramsText = document.getElementById('mcp-test-params').value.trim();
    var params = {};
    if (paramsText) {
      try { params = JSON.parse(paramsText); }
      catch(e) { return AgentDB.toast('Invalid JSON parameters', 'error'); }
    }

    // Map MCP tools to REST API calls
    var apiMap = {
      'retrieve_context': { method: 'POST', path: '/api/context' },
      'ingest_memory': { method: 'POST', path: '/api/ingest' },
      'search_memories': { method: 'GET', path: '/api/search' },
      'list_memories': { method: 'GET', path: '/api/memories/' + (params.tier || 'short') },
      'create_entity': { method: 'POST', path: '/api/entities' },
      'list_entities': { method: 'GET', path: '/api/entities' },
      'check_goals': { method: 'POST', path: '/api/context' },
      'get_health': { method: 'GET', path: '/api/health' },
      'run_consolidation': { method: 'POST', path: '/api/maintenance/consolidation' },
    };

    var api = apiMap[tool];
    if (!api) return AgentDB.toast('Unknown tool', 'error');

    var resultEl = document.getElementById('mcp-test-result');
    resultEl.style.display = 'block';
    resultEl.textContent = 'Executing...';

    var r;
    if (api.method === 'GET') {
      var qs = Object.keys(params).map(function(k) { return k + '=' + encodeURIComponent(params[k]); }).join('&');
      r = await AgentDB.api('GET', api.path + (qs ? '?' + qs : ''));
    } else {
      r = await AgentDB.api('POST', api.path, params);
    }
    resultEl.textContent = JSON.stringify(r, null, 2);
  };

  V.saveCfg = async function(key, value) {
    var r = await AgentDB.api('PUT', '/api/config/' + key, { value: value });
    if (r.status === 'ok') {
      AgentDB.toast('Saved ' + key, 'success');
    } else {
      AgentDB.toast('Failed to save ' + key, 'error');
    }
  };
})();
