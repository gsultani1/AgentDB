(function() {
  const V = AgentDB.views.connect = {};
  const el = () => document.getElementById('view-connect');

  const ENDPOINTS = [
    { method: 'GET',  path: '/api/health',               desc: 'Health check and system status',              body: '' },
    { method: 'POST', path: '/api/context',               desc: 'Retrieve relevant context for a query',       body: '{"query":"...", "agent_id":"default"}' },
    { method: 'POST', path: '/api/ingest',                desc: 'Ingest a new short-term memory',              body: '{"content":"...", "source":"conversation"}' },
    { method: 'GET',  path: '/api/memories/:tier',        desc: 'List memories by tier (short/mid/long)',       body: '' },
    { method: 'GET',  path: '/api/search',                desc: 'Semantic search across memories',             body: '' },
    { method: 'GET',  path: '/api/entities',              desc: 'List knowledge graph entities',               body: '' },
    { method: 'POST', path: '/api/entities',              desc: 'Create a new entity',                         body: '{"canonical_name":"...", "entity_type":"concept"}' },
    { method: 'GET',  path: '/api/goals',                 desc: 'List active goals',                           body: '' },
    { method: 'GET',  path: '/api/config',                desc: 'List all configuration values',               body: '' },
    { method: 'PUT',  path: '/api/config/:key',           desc: 'Update a configuration value',                body: '{"value":"..."}' },
    { method: 'POST', path: '/api/maintenance/:action',   desc: 'Run maintenance (consolidation/sleep/check)', body: '' },
  ];

  const CODE_EXAMPLES = {
    curl: `# Health check
curl http://localhost:8420/api/health

# Retrieve context for a query
curl -X POST http://localhost:8420/api/context \\
  -H "Content-Type: application/json" \\
  -d '{"query": "What do I know about project deadlines?"}'

# Ingest a new memory
curl -X POST http://localhost:8420/api/ingest \\
  -H "Content-Type: application/json" \\
  -d '{"content": "Meeting moved to Friday 3pm", "source": "conversation"}'

# Search memories
curl "http://localhost:8420/api/search?q=deadlines&tier=short&limit=5"

# Chat with context
curl -X POST http://localhost:8420/api/chat \\
  -H "Content-Type: application/json" \\
  -d '{"message": "Summarize what you know about the project"}'`,

    python: `import requests

BASE = "http://localhost:8420"

# Health check
r = requests.get(f"{BASE}/api/health")
print(r.json())

# Retrieve context
r = requests.post(f"{BASE}/api/context", json={
    "query": "What do I know about project deadlines?",
    "agent_id": "default"
})
ctx = r.json()["data"]
print(f"Found {len(ctx['memories'].get('short_term', []))} short-term matches")

# Ingest a memory
r = requests.post(f"{BASE}/api/ingest", json={
    "content": "Meeting moved to Friday 3pm",
    "source": "conversation"
})
print(f"Created memory: {r.json()['id']}")

# Chat with context
r = requests.post(f"{BASE}/api/chat", json={
    "message": "Summarize what you know about the project"
})
print(r.json()["response"])`,

    js: `const BASE = "http://localhost:8420";

// Health check
const health = await fetch(\`\${BASE}/api/health\`).then(r => r.json());
console.log("Status:", health.status);

// Retrieve context
const ctx = await fetch(\`\${BASE}/api/context\`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: "What do I know about project deadlines?",
    agent_id: "default"
  })
}).then(r => r.json());
console.log("Context:", ctx.data);

// Ingest a memory
const mem = await fetch(\`\${BASE}/api/ingest\`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    content: "Meeting moved to Friday 3pm",
    source: "conversation"
  })
}).then(r => r.json());
console.log("Memory ID:", mem.id);

// Chat with context
const chat = await fetch(\`\${BASE}/api/chat\`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Summarize what you know about the project" })
}).then(r => r.json());
console.log("Response:", chat.response);`
  };

  V.load = async function() {
    var health = await AgentDB.api('GET', '/api/health');
    var isUp = health && health.status === 'ok';
    var badge = isUp
      ? '<span style="background:#22c55e;color:#fff;padding:2px 10px;border-radius:8px;font-size:12px">Connected</span>'
      : '<span style="background:var(--red);color:#fff;padding:2px 10px;border-radius:8px;font-size:12px">Offline</span>';
    var baseUrl = window.location.origin;

    var endpointRows = ENDPOINTS.map(function(ep) {
      var color = ep.method === 'GET' ? '#3b82f6' : ep.method === 'POST' ? '#22c55e' : '#f59e0b';
      return '<tr><td><span style="background:' + color + ';color:#fff;padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600">' +
        ep.method + '</span></td><td style="font-family:var(--mono);font-size:13px">' + AgentDB.esc(ep.path) +
        '</td><td>' + AgentDB.esc(ep.desc) +
        '</td><td style="font-family:var(--mono);font-size:11px;color:var(--text2)">' + AgentDB.esc(ep.body) + '</td></tr>';
    }).join('');

    el().innerHTML = `
      <h2 style="margin-bottom:16px">Connect to AgentDB</h2>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3>API Status</h3>${badge}
        </div>
        <div style="margin-top:12px;display:flex;align-items:center;gap:8px">
          <span style="color:var(--text2);font-size:13px">Base URL:</span>
          <code style="background:var(--bg3);padding:4px 12px;border-radius:4px;font-size:13px" id="connect-base-url">${AgentDB.esc(baseUrl)}</code>
          <button class="btn" onclick="navigator.clipboard.writeText(document.getElementById('connect-base-url').textContent);AgentDB.toast('Copied!','success')" style="font-size:12px;padding:4px 10px">Copy</button>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>API Endpoints</h3>
        <div style="overflow-x:auto;margin-top:12px">
          <table><thead><tr><th>Method</th><th>Path</th><th>Description</th><th>Body</th></tr></thead>
          <tbody>${endpointRows}</tbody></table>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>Code Examples</h3>
        <div style="display:flex;gap:8px;margin-top:12px;margin-bottom:12px">
          <button class="btn connect-tab active" data-lang="curl" onclick="AgentDB.views.connect.switchTab('curl')">cURL</button>
          <button class="btn connect-tab" data-lang="python" onclick="AgentDB.views.connect.switchTab('python')">Python</button>
          <button class="btn connect-tab" data-lang="js" onclick="AgentDB.views.connect.switchTab('js')">JavaScript</button>
        </div>
        <pre id="connect-code" style="background:var(--bg1);padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.5;max-height:420px;overflow-y:auto"><code>${AgentDB.esc(CODE_EXAMPLES.curl)}</code></pre>
      </div>`;
  };

  V.switchTab = function(lang) {
    document.querySelectorAll('.connect-tab').forEach(function(b) {
      b.classList.toggle('active', b.getAttribute('data-lang') === lang);
    });
    document.getElementById('connect-code').innerHTML = '<code>' + AgentDB.esc(CODE_EXAMPLES[lang]) + '</code>';
  };
})();
