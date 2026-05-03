(function() {
  const V = AgentDB.views.dbconsole = {};
  const el = () => document.getElementById('view-dbconsole');

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">DB Console</h2>

      <div class="card" style="margin-bottom:16px">
        <div class="tabs" id="db-mode-tabs" style="margin-bottom:12px">
          <button class="tab active" data-mode="ai">AI Query</button>
          <button class="tab" data-mode="sql">Raw SQL</button>
        </div>

        <div id="db-ai-mode">
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <input type="text" id="db-ai-input" placeholder="Ask a question about your data..." style="flex:1;font-size:14px">
            <button class="btn btn-primary" id="db-ai-btn">Ask</button>
          </div>
          <p style="font-size:12px;color:var(--text2)">AI will generate and execute a SQL query to answer your question.</p>
        </div>

        <div id="db-sql-mode" style="display:none">
          <textarea id="db-sql-input" rows="4" placeholder="SELECT * FROM short_term_memory LIMIT 10;" style="width:100%;font-family:var(--mono);font-size:13px;resize:vertical"></textarea>
          <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
            <button class="btn btn-primary" id="db-sql-btn">Execute</button>
            <span style="font-size:12px;color:var(--text2)" id="db-write-status"></span>
          </div>
        </div>
      </div>

      <div id="db-generated-sql" style="display:none;margin-bottom:12px" class="card">
        <h3>Generated SQL</h3>
        <pre style="margin-top:8px;background:var(--bg3);padding:12px;border-radius:var(--radius,8px);font-family:var(--mono);font-size:12px;overflow-x:auto" id="db-sql-display"></pre>
      </div>

      <div id="db-results" class="card" style="display:none">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h3>Results</h3>
          <span style="font-size:12px;color:var(--text2)" id="db-row-count"></span>
        </div>
        <div id="db-results-table" style="overflow-x:auto"></div>
      </div>

      <div id="db-error" style="display:none;margin-bottom:12px" class="card">
        <h3 style="color:var(--red)">Error</h3>
        <pre style="margin-top:8px;color:var(--red);font-size:13px;white-space:pre-wrap" id="db-error-text"></pre>
      </div>

      <div class="card" style="margin-top:16px">
        <h3>Quick Queries</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
          <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT COUNT(*) as count, \\'short_term_memory\\' as tier FROM short_term_memory UNION ALL SELECT COUNT(*), \\'midterm_memory\\' FROM midterm_memory UNION ALL SELECT COUNT(*), \\'long_term_memory\\' FROM long_term_memory')">Memory Counts</button>
          <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT canonical_name, entity_type, created_at FROM entities ORDER BY created_at DESC LIMIT 20')">Recent Entities</button>
          <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT name, action_type, status, last_run_at FROM scheduled_tasks ORDER BY last_run_at DESC')">Scheduled Tasks</button>
          <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT key, value FROM meta_config ORDER BY key')">All Config</button>
          <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT table_name, operation, COUNT(*) as count FROM audit_log GROUP BY table_name, operation ORDER BY count DESC LIMIT 20')">Audit Summary</button>
        </div>
      </div>`;

    // Wire tabs
    document.getElementById('db-mode-tabs').addEventListener('click', function(e) {
      var btn = e.target.closest('.tab');
      if (!btn) return;
      document.querySelectorAll('#db-mode-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
      btn.classList.add('active');
      var mode = btn.dataset.mode;
      document.getElementById('db-ai-mode').style.display = mode === 'ai' ? 'block' : 'none';
      document.getElementById('db-sql-mode').style.display = mode === 'sql' ? 'block' : 'none';
    });

    // Wire AI query
    document.getElementById('db-ai-btn').addEventListener('click', V.askAI);
    document.getElementById('db-ai-input').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') V.askAI();
    });

    // Wire SQL execute
    document.getElementById('db-sql-btn').addEventListener('click', V.executeSQL);
    document.getElementById('db-sql-input').addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && e.ctrlKey) V.executeSQL();
    });

    // Check write status
    AgentDB.api('GET', '/api/config/db_console_write_enabled').then(function(r) {
      var status = document.getElementById('db-write-status');
      if (r.status === 'ok' && r.data && r.data.value === 'true') {
        status.innerHTML = '<span style="color:var(--yellow)">Write mode enabled</span>';
      } else {
        status.textContent = 'Read-only mode (SELECT/PRAGMA only)';
      }
    });
  };

  V.askAI = async function() {
    var input = document.getElementById('db-ai-input');
    var question = input.value.trim();
    if (!question) return;

    hideAll();
    document.getElementById('db-results').style.display = 'block';
    document.getElementById('db-results-table').innerHTML = '<div class="spinner"></div>';

    var r = await AgentDB.api('POST', '/api/db/ai-query', { question: question });
    if (r.status === 'ok' && r.data) {
      if (r.data.sql) {
        document.getElementById('db-generated-sql').style.display = 'block';
        document.getElementById('db-sql-display').textContent = r.data.sql;
      }
      renderResults(r.data);
    } else {
      showError(r.error || 'Query failed');
      if (r.data && r.data.sql) {
        document.getElementById('db-generated-sql').style.display = 'block';
        document.getElementById('db-sql-display').textContent = r.data.sql;
      }
    }
  };

  V.executeSQL = async function() {
    var input = document.getElementById('db-sql-input');
    var sql = input.value.trim();
    if (!sql) return;

    hideAll();
    document.getElementById('db-results').style.display = 'block';
    document.getElementById('db-results-table').innerHTML = '<div class="spinner"></div>';

    var r = await AgentDB.api('POST', '/api/db/query', { sql: sql });
    if (r.status === 'ok' && r.data) {
      renderResults(r.data);
    } else {
      showError(r.error || 'Query failed');
    }
  };

  V.quickQuery = function(sql) {
    // Switch to SQL mode
    document.querySelectorAll('#db-mode-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelector('#db-mode-tabs .tab[data-mode="sql"]').classList.add('active');
    document.getElementById('db-ai-mode').style.display = 'none';
    document.getElementById('db-sql-mode').style.display = 'block';
    document.getElementById('db-sql-input').value = sql;
    V.executeSQL();
  };

  function hideAll() {
    document.getElementById('db-generated-sql').style.display = 'none';
    document.getElementById('db-error').style.display = 'none';
  }

  function showError(msg) {
    document.getElementById('db-results').style.display = 'none';
    document.getElementById('db-error').style.display = 'block';
    document.getElementById('db-error-text').textContent = msg;
  }

  function renderResults(data) {
    var columns = data.columns || [];
    var rows = data.rows || [];
    document.getElementById('db-row-count').textContent = data.row_count + ' row' + (data.row_count !== 1 ? 's' : '');
    document.getElementById('db-results').style.display = 'block';

    if (!columns.length) {
      document.getElementById('db-results-table').innerHTML = '<p style="color:var(--text2)">Query executed successfully. No results returned.</p>';
      return;
    }

    var html = '<table><thead><tr>' +
      columns.map(function(c) { return '<th>' + AgentDB.esc(c) + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      rows.map(function(row) {
        return '<tr>' + columns.map(function(c) {
          var val = row[c];
          if (val === null || val === undefined) return '<td style="color:var(--text2);font-style:italic">NULL</td>';
          var s = String(val);
          if (s.length > 200) s = s.substring(0, 200) + '...';
          return '<td style="font-size:12px">' + AgentDB.esc(s) + '</td>';
        }).join('') + '</tr>';
      }).join('') +
      '</tbody></table>';

    document.getElementById('db-results-table').innerHTML = html;
  }
})();
