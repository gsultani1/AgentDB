(function() {
  const V = AgentDB.views.dbconsole = {};
  const el = () => document.getElementById('view-dbconsole');

  V.lastResults = null; // captured for CSV/JSON export

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">DB Console</h2>

      <div style="display:grid;grid-template-columns:280px 1fr;gap:16px;align-items:start">
        <!-- Schema explorer (collapsible per-table) -->
        <div class="card" style="position:sticky;top:0;max-height:calc(100vh - 100px);overflow:auto">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <h3 style="margin:0">Schema</h3>
            <button class="btn btn-sm" id="db-schema-refresh" title="Reload schema">↻</button>
          </div>
          <div id="db-schema-list" style="font-size:12px"><div class="spinner"></div></div>
        </div>

        <!-- Main column -->
        <div>
          <div class="card" style="margin-bottom:16px">
            <div class="tabs" id="db-mode-tabs" style="margin-bottom:12px">
              <button class="tab active" data-mode="ai">AI Query</button>
              <button class="tab" data-mode="sql">Raw SQL</button>
              <button class="tab" data-mode="history">History</button>
            </div>

            <div id="db-ai-mode">
              <div style="display:flex;gap:8px;margin-bottom:8px">
                <input type="text" id="db-ai-input" placeholder="Ask a question about your data..." style="flex:1;font-size:14px">
                <button class="btn btn-primary" id="db-ai-btn">Ask</button>
              </div>
              <p style="font-size:12px;color:var(--text2)">AI generates a SQL SELECT to answer your question. The generated SQL is shown below for inspection — switch to <b>Raw SQL</b> to edit and re-run.</p>
            </div>

            <div id="db-sql-mode" style="display:none">
              <textarea id="db-sql-input" rows="4" placeholder="SELECT * FROM short_term_memory LIMIT 10;" style="width:100%;font-family:var(--mono);font-size:13px;resize:vertical"></textarea>
              <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
                <button class="btn btn-primary" id="db-sql-btn">Execute</button>
                <span style="font-size:12px;color:var(--text2)" id="db-write-status"></span>
                <span style="margin-left:auto;font-size:11px;color:var(--text2)">Ctrl+Enter to run</span>
              </div>
            </div>

            <div id="db-history-mode" style="display:none">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <p style="font-size:12px;color:var(--text2);margin:0">Last 50 successful queries. Click any to load into Raw SQL.</p>
                <button class="btn btn-sm" id="db-history-clear" style="color:var(--red)">Clear History</button>
              </div>
              <div id="db-history-list" style="max-height:400px;overflow:auto"></div>
            </div>
          </div>

          <div id="db-generated-sql" style="display:none;margin-bottom:12px" class="card">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <h3 style="margin:0">Generated SQL</h3>
              <button class="btn btn-sm" id="db-edit-generated">Edit in Raw SQL</button>
            </div>
            <pre style="margin-top:8px;background:var(--bg3);padding:12px;border-radius:var(--radius,8px);font-family:var(--mono);font-size:12px;overflow-x:auto" id="db-sql-display"></pre>
          </div>

          <div id="db-results" class="card" style="display:none">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px">
              <h3 style="margin:0">Results</h3>
              <span style="font-size:12px;color:var(--text2);margin-right:auto" id="db-row-count"></span>
              <button class="btn btn-sm" id="db-export-csv">Export CSV</button>
              <button class="btn btn-sm" id="db-export-json">Export JSON</button>
            </div>
            <div id="db-results-table" style="overflow-x:auto"></div>
          </div>

          <div id="db-error" style="display:none;margin-bottom:12px" class="card">
            <h3 style="color:var(--red);margin:0 0 8px 0">Error</h3>
            <pre style="color:var(--red);font-size:13px;white-space:pre-wrap" id="db-error-text"></pre>
          </div>

          <div class="card" style="margin-top:16px">
            <h3>Quick Queries</h3>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
              <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT COUNT(*) as count, \\'short_term_memory\\' as tier FROM short_term_memory UNION ALL SELECT COUNT(*), \\'midterm_memory\\' FROM midterm_memory UNION ALL SELECT COUNT(*), \\'long_term_memory\\' FROM long_term_memory')">Memory Counts</button>
              <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT canonical_name, entity_type, first_seen, last_seen FROM entities ORDER BY first_seen DESC LIMIT 20')">Recent Entities</button>
              <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT name, action_type, status, last_run_at FROM scheduled_tasks ORDER BY last_run_at DESC')">Scheduled Tasks</button>
              <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT key, value FROM meta_config ORDER BY key')">All Config</button>
              <button class="btn btn-sm" onclick="AgentDB.views.dbconsole.quickQuery('SELECT table_name, operation, COUNT(*) as count FROM audit_log GROUP BY table_name, operation ORDER BY count DESC LIMIT 20')">Audit Summary</button>
            </div>
          </div>
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
      document.getElementById('db-history-mode').style.display = mode === 'history' ? 'block' : 'none';
      if (mode === 'history') V.loadHistory();
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

    // Edit generated SQL → switch to Raw mode pre-filled
    document.getElementById('db-edit-generated').addEventListener('click', function() {
      var sql = document.getElementById('db-sql-display').textContent;
      V.switchToSQL(sql);
    });

    // Export buttons
    document.getElementById('db-export-csv').addEventListener('click', V.exportCSV);
    document.getElementById('db-export-json').addEventListener('click', V.exportJSON);

    // History
    document.getElementById('db-history-list').addEventListener('click', function(e) {
      var item = e.target.closest('[data-history-sql]');
      if (item) V.switchToSQL(item.dataset.historySql);
    });
    document.getElementById('db-history-clear').addEventListener('click', V.clearHistory);

    // Schema explorer
    document.getElementById('db-schema-refresh').addEventListener('click', V.loadSchema);
    document.getElementById('db-schema-list').addEventListener('click', function(e) {
      var hdr = e.target.closest('[data-table-name]');
      if (hdr) {
        var body = hdr.nextElementSibling;
        if (body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
      }
      var qb = e.target.closest('[data-quick-select]');
      if (qb) {
        e.stopPropagation();
        V.quickQuery('SELECT * FROM ' + qb.dataset.quickSelect + ' LIMIT 50');
      }
    });

    V.loadSchema();

    // Check write status
    AgentDB.api('GET', '/api/config/db_console_write_enabled').then(function(r) {
      var status = document.getElementById('db-write-status');
      if (r.status === 'ok' && r.data && r.data.value === 'true') {
        status.innerHTML = '<span style="color:var(--yellow)">Write mode enabled</span>';
      } else {
        status.textContent = 'Read-only mode (SELECT/PRAGMA/EXPLAIN/WITH only)';
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
    V.switchToSQL(sql, /*execute=*/true);
  };

  V.switchToSQL = function(sql, execute) {
    document.querySelectorAll('#db-mode-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelector('#db-mode-tabs .tab[data-mode="sql"]').classList.add('active');
    document.getElementById('db-ai-mode').style.display = 'none';
    document.getElementById('db-history-mode').style.display = 'none';
    document.getElementById('db-sql-mode').style.display = 'block';
    document.getElementById('db-sql-input').value = sql;
    if (execute) V.executeSQL();
  };

  // ── Schema explorer ─────────────────────────────────────────────────
  V.loadSchema = async function() {
    var list = document.getElementById('db-schema-list');
    list.innerHTML = '<div class="spinner"></div>';
    var r = await AgentDB.api('GET', '/api/db-query/schema');
    if (r.status !== 'ok' || !r.data) {
      list.innerHTML = '<div style="color:var(--red);font-size:11px">Failed to load schema</div>';
      return;
    }
    var tables = r.data;
    if (!tables.length) {
      list.innerHTML = '<div style="color:var(--text2);font-size:11px">No tables</div>';
      return;
    }
    var html = '';
    tables.forEach(function(t) {
      var cols = parseColumns(t.sql);
      html += '<div style="margin-bottom:4px">';
      html += '<div data-table-name="' + AgentDB.esc(t.name) + '" style="display:flex;justify-content:space-between;align-items:center;padding:4px 6px;cursor:pointer;border-radius:4px;background:var(--bg3)">';
      html += '<span style="font-family:var(--mono);font-weight:600">' + AgentDB.esc(t.name) + '</span>';
      html += '<span style="display:flex;gap:4px;align-items:center"><span style="color:var(--text2);font-size:10px">' + cols.length + ' col' + (cols.length === 1 ? '' : 's') + '</span>';
      html += '<button class="btn btn-sm" data-quick-select="' + AgentDB.esc(t.name) + '" style="padding:1px 6px;font-size:10px" title="SELECT * FROM ' + AgentDB.esc(t.name) + ' LIMIT 50">▶</button></span>';
      html += '</div>';
      html += '<div style="display:none;padding:4px 6px 6px 12px;font-family:var(--mono);font-size:11px;color:var(--text2)">';
      cols.forEach(function(c) {
        html += '<div>' + AgentDB.esc(c.name) + ' <span style="color:var(--text2);opacity:0.7">' + AgentDB.esc(c.type || '') + '</span></div>';
      });
      html += '</div>';
      html += '</div>';
    });
    list.innerHTML = html;
  };

  // Coarse column extractor: parses CREATE TABLE DDL for name + type pairs.
  function parseColumns(sql) {
    if (!sql) return [];
    var open = sql.indexOf('(');
    var close = sql.lastIndexOf(')');
    if (open < 0 || close < 0 || close <= open) return [];
    var body = sql.substring(open + 1, close);
    // Split on commas at depth 0 (CHECK constraints etc. have nested parens)
    var parts = [];
    var depth = 0, start = 0;
    for (var i = 0; i < body.length; i++) {
      var ch = body[i];
      if (ch === '(') depth++;
      else if (ch === ')') depth--;
      else if (ch === ',' && depth === 0) {
        parts.push(body.substring(start, i));
        start = i + 1;
      }
    }
    parts.push(body.substring(start));
    var cols = [];
    parts.forEach(function(p) {
      p = p.trim();
      // Skip table-level constraints
      var head = p.split(/\s+/)[0].toUpperCase();
      if (['CONSTRAINT','PRIMARY','FOREIGN','UNIQUE','CHECK'].indexOf(head) >= 0) return;
      var match = p.match(/^["']?(\w+)["']?\s+(\S+)/);
      if (match) cols.push({ name: match[1], type: match[2] });
    });
    return cols;
  }

  // ── Query history ───────────────────────────────────────────────────
  V.loadHistory = async function() {
    var list = document.getElementById('db-history-list');
    list.innerHTML = '<div class="spinner"></div>';
    var r = await AgentDB.api('GET', '/api/db-query/history');
    if (r.status !== 'ok') {
      list.innerHTML = '<div style="color:var(--red);font-size:12px">Failed to load history</div>';
      return;
    }
    var hist = r.data || [];
    if (!hist.length) {
      list.innerHTML = '<div style="color:var(--text2);font-size:12px;padding:8px 0">No queries yet. Run something in Raw SQL to populate history.</div>';
      return;
    }
    list.innerHTML = hist.map(function(h) {
      var preview = (h.sql || '').replace(/\s+/g, ' ').trim();
      if (preview.length > 120) preview = preview.substring(0, 120) + '…';
      return '<div data-history-sql="' + AgentDB.esc(h.sql || '') +
             '" style="padding:8px 10px;background:var(--bg3);border-radius:6px;margin-bottom:4px;cursor:pointer">' +
             '<div style="font-family:var(--mono);font-size:11px">' + AgentDB.esc(preview) + '</div>' +
             '<div style="font-size:10px;color:var(--text2);margin-top:2px">' +
             AgentDB.esc(h.ts || '') + ' • ' + (h.rows || 0) + ' row' + (h.rows === 1 ? '' : 's') + '</div></div>';
    }).join('');
  };

  V.clearHistory = async function() {
    if (!confirm('Clear all query history?')) return;
    var r = await AgentDB.api('DELETE', '/api/db-query/history');
    if (r.status === 'ok') {
      AgentDB.toast('History cleared', 'success');
      V.loadHistory();
    } else {
      AgentDB.toast('Failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  // ── Export ──────────────────────────────────────────────────────────
  V.exportCSV = function() {
    if (!V.lastResults) return AgentDB.toast('No results to export', 'error');
    var cols = V.lastResults.columns || [];
    var rows = V.lastResults.rows || [];
    var lines = [cols.map(csvEscape).join(',')];
    rows.forEach(function(r) {
      lines.push(cols.map(function(c) { return csvEscape(r[c]); }).join(','));
    });
    downloadBlob(lines.join('\n'), 'query-results.csv', 'text/csv');
  };

  V.exportJSON = function() {
    if (!V.lastResults) return AgentDB.toast('No results to export', 'error');
    downloadBlob(JSON.stringify(V.lastResults.rows || [], null, 2),
                 'query-results.json', 'application/json');
  };

  function csvEscape(v) {
    if (v === null || v === undefined) return '';
    var s = String(v);
    if (/[,"\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function downloadBlob(content, filename, mime) {
    var blob = new Blob([content], { type: mime + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function() { URL.revokeObjectURL(url); }, 0);
  }

  // ── Result rendering ────────────────────────────────────────────────
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
    V.lastResults = data;
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
