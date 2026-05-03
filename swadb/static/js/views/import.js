(function() {
  const V = AgentDB.views.import = {};
  const el = () => document.getElementById('view-import');

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">Import Manager</h2>
      <div class="card">
        <h3>Import Chat History</h3>
        <div style="display:flex;gap:12px;align-items:center;margin-top:12px">
          <select id="import-provider" style="width:140px">
            <option value="chatgpt">ChatGPT</option>
            <option value="claude">Claude</option>
            <option value="generic">Generic JSONL</option>
          </select>
          <input type="text" id="import-filepath" placeholder="File path on server..." style="flex:1">
          <button class="btn btn-primary" onclick="AgentDB.views.import.start()">Import</button>
        </div>
        <div id="import-progress" style="margin-top:16px;display:none">
          <div class="progress-bar"><div class="progress-fill" id="import-fill" style="width:0%"></div></div>
          <div id="import-status" style="font-size:13px;color:var(--text2);margin-top:4px"></div>
        </div>
        <div id="import-summary" style="margin-top:16px"></div>
      </div>`;
  };

  V.start = async function() {
    var fp = document.getElementById('import-filepath').value.trim();
    var prov = document.getElementById('import-provider').value;
    if (!fp) return AgentDB.toast('File path is required', 'error');
    var prog = document.getElementById('import-progress');
    prog.style.display = 'block';
    document.getElementById('import-status').textContent = 'Importing...';
    document.getElementById('import-fill').style.width = '50%';
    var r = await AgentDB.api('POST', '/api/import', { file_path: fp, provider: prov });
    if (r.status === 'ok') {
      document.getElementById('import-fill').style.width = '100%';
      document.getElementById('import-status').textContent = 'Complete!';
      var d = r.data;
      document.getElementById('import-summary').innerHTML = '<div class="card" style="background:var(--bg3)"><b>Results:</b><br>' +
        'Conversations: ' + (d.conversations_imported||0) + '<br>' +
        'Messages: ' + (d.messages_ingested||0) + '<br>' +
        'Midterm created: ' + (d.midterm_created||0) + '<br>' +
        'Long-term promoted: ' + (d.longterm_promoted||0) + '<br>' +
        'Entities: ' + (d.entities_extracted||0) + '</div>';
      AgentDB.toast('Import completed', 'success');
    } else {
      document.getElementById('import-fill').style.width = '0%';
      document.getElementById('import-status').textContent = 'Error: ' + (r.error || 'Unknown');
      AgentDB.toast('Import failed: ' + (r.error || 'Unknown'), 'error');
    }
  };
})();
