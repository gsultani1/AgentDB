(function() {
  const V = AgentDB.views.audit = {};
  const el = () => document.getElementById('view-audit');

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">Audit Log</h2>
      <div class="search-bar">
        <select id="audit-table" style="width:180px"><option value="">All Tables</option>
          <option>short_term_memory</option><option>midterm_memory</option><option>long_term_memory</option>
          <option>entities</option><option>skills</option><option>goals</option><option>relations</option>
          <option>agents</option><option>sessions</option><option>notifications</option>
        </select>
        <select id="audit-op" style="width:120px"><option value="">All Ops</option>
          <option>insert</option><option>update</option><option>delete</option><option>promote</option><option>demote</option>
        </select>
        <button class="btn" onclick="AgentDB.views.audit.loadList()">Filter</button>
      </div>
      <div id="audit-content"></div>`;
    V.loadList();
  };

  V.loadList = async function() {
    var table = document.getElementById('audit-table').value;
    var op = document.getElementById('audit-op').value;
    var url = '/api/audit?limit=50';
    if (table) url += '&table_name=' + table;
    if (op) url += '&operation=' + op;
    var r = await AgentDB.api('GET', url);
    var c = document.getElementById('audit-content');
    if (r.status !== 'ok' || !r.data || !r.data.length) {
      c.innerHTML = '<p style="color:var(--text2)">No audit entries.</p>';
      return;
    }
    c.innerHTML = '<table><thead><tr><th>Timestamp</th><th>Table</th><th>Operation</th><th>Row ID</th><th>Triggered By</th></tr></thead><tbody>' +
      r.data.map(function(a) {
        return '<tr><td style="font-size:12px;white-space:nowrap">' + AgentDB.esc((a.timestamp||'').substring(0,19)) +
          '</td><td>' + AgentDB.esc(a.table_name) +
          '</td><td>' + AgentDB.esc(a.operation) +
          '</td><td style="font-family:var(--mono);font-size:12px">' + AgentDB.esc((a.row_id||'').substring(0,8)) +
          '</td><td>' + AgentDB.esc(a.triggered_by) + '</td></tr>';
      }).join('') + '</tbody></table>';
  };
})();
