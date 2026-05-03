(function() {
  const V = AgentDB.views.scheduler = {};
  const el = () => document.getElementById('view-scheduler');

  const ACTION_TYPES = ['consolidate', 'sleep_cycle', 'integrity_check', 'workspace_scan', 'notify'];

  V.load = async function() {
    el().innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2>Scheduler</h2>
        <button class="btn" id="sched-toggle-create">+ New Task</button>
      </div>
      <div id="sched-status" class="card" style="margin-bottom:16px"></div>
      <div id="sched-create-form" style="display:none;margin-bottom:16px" class="card">
        <h3>Create Scheduled Task</h3>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
          <input type="text" id="sched-name" placeholder="Task name">
          <textarea id="sched-desc" rows="2" placeholder="Description (optional)"></textarea>
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
            <label style="font-size:12px;color:var(--text2)">Action:</label>
            <select id="sched-action">${ACTION_TYPES.map(a => '<option value="'+a+'">'+a.replace(/_/g,' ')+'</option>').join('')}</select>
            <label style="font-size:12px;color:var(--text2)">Interval (sec):</label>
            <input type="number" id="sched-interval" value="300" min="10" style="width:100px">
            <button class="btn" id="sched-submit-create">Create</button>
          </div>
        </div>
      </div>
      <div id="sched-table-wrap"></div>`;

    document.getElementById('sched-toggle-create').onclick = function() {
      var f = document.getElementById('sched-create-form');
      f.style.display = f.style.display === 'none' ? 'block' : 'none';
    };
    document.getElementById('sched-submit-create').onclick = createTask;
    document.getElementById('sched-table-wrap').addEventListener('click', handleTableClick);

    await loadStatus();
    await loadTasks();
  };

  async function loadStatus() {
    var r = await AgentDB.api('GET', '/api/scheduler/status');
    var el = document.getElementById('sched-status');
    if (r.status !== 'ok') { el.innerHTML = '<p style="color:var(--text2)">Could not load scheduler status.</p>'; return; }
    var d = r.data;
    el.innerHTML = '<h3>Scheduler Status</h3>' +
      '<div style="display:flex;gap:20px;margin-top:8px;font-size:13px">' +
      '<span>Enabled: ' + (d.enabled ? '<span class="status ok">Yes</span>' : '<span class="status error">No</span>') + '</span>' +
      '<span>Runner: ' + (d.runner_started ? '<span class="status ok">Running</span>' : '<span class="status closed">Stopped</span>') + '</span>' +
      '<span>Poll Interval: ' + d.poll_interval_seconds + 's</span>' +
      (d.last_result ? '<span>Last: ' + AgentDB.esc(d.last_result.task_name || '') + ' at ' + AgentDB.esc((d.last_result.ran_at||'').substring(0,19)) + '</span>' : '') +
      '</div>';
  }

  async function loadTasks() {
    var r = await AgentDB.api('GET', '/api/scheduled-tasks');
    var wrap = document.getElementById('sched-table-wrap');
    if (r.status !== 'ok' || !r.data || !r.data.length) {
      wrap.innerHTML = '<p style="color:var(--text2)">No scheduled tasks.</p>';
      return;
    }
    wrap.innerHTML = '<table><thead><tr><th>Name</th><th>Action</th><th>Interval</th><th>Status</th><th>Last Run</th><th>Next Run</th><th>Actions</th></tr></thead><tbody>' +
      r.data.map(function(t) {
        var statusCls = t.status === 'active' ? 'ok' : (t.status === 'error' ? 'error' : 'closed');
        return '<tr>' +
          '<td><b>' + AgentDB.esc(t.name) + '</b>' + (t.description ? '<div style="font-size:11px;color:var(--text2)">' + AgentDB.esc(t.description) + '</div>' : '') + '</td>' +
          '<td>' + AgentDB.esc(t.action_type) + '</td>' +
          '<td>' + t.interval_seconds + 's</td>' +
          '<td><span class="status ' + statusCls + '">' + t.status + '</span></td>' +
          '<td style="font-size:12px">' + AgentDB.esc((t.last_run_at||'Never').substring(0,19)) + '</td>' +
          '<td style="font-size:12px">' + AgentDB.esc((t.next_run_at||'-').substring(0,19)) + '</td>' +
          '<td style="white-space:nowrap">' +
            '<button class="btn" style="padding:2px 8px;font-size:11px;margin-right:4px" data-run="' + t.id + '">Run Now</button>' +
            '<button class="btn" style="padding:2px 8px;font-size:11px;margin-right:4px" data-toggle="' + t.id + '" data-status="' + t.status + '">' + (t.status === 'paused' ? 'Resume' : 'Pause') + '</button>' +
            '<button class="btn" style="padding:2px 8px;font-size:11px;color:var(--red)" data-del="' + t.id + '">Del</button>' +
          '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  async function handleTableClick(e) {
    var btn;
    if ((btn = e.target.closest('[data-run]'))) {
      var r = await AgentDB.api('POST', '/api/scheduled-tasks/' + btn.dataset.run + '/run', {});
      if (r.status === 'ok') {
        AgentDB.toast('Task executed', 'success');
      } else {
        AgentDB.toast('Error: ' + (r.error || 'Unknown'), 'error');
      }
      await loadStatus();
      await loadTasks();
    } else if ((btn = e.target.closest('[data-toggle]'))) {
      var newStatus = btn.dataset.status === 'paused' ? 'active' : 'paused';
      await AgentDB.api('PUT', '/api/scheduled-tasks/' + btn.dataset.toggle, { status: newStatus });
      AgentDB.toast('Task ' + newStatus);
      await loadTasks();
    } else if ((btn = e.target.closest('[data-del]'))) {
      if (!await AgentDB.confirm('Delete this scheduled task?')) return;
      await AgentDB.api('DELETE', '/api/scheduled-tasks/' + btn.dataset.del);
      AgentDB.toast('Task deleted');
      await loadTasks();
    }
  }

  async function createTask() {
    var name = document.getElementById('sched-name').value.trim();
    if (!name) return AgentDB.toast('Name is required', 'error');
    var body = {
      name: name,
      description: document.getElementById('sched-desc').value.trim(),
      action_type: document.getElementById('sched-action').value,
      interval_seconds: parseInt(document.getElementById('sched-interval').value) || 300,
    };
    var r = await AgentDB.api('POST', '/api/scheduled-tasks', body);
    if (r.status === 'ok') {
      AgentDB.toast('Task created', 'success');
      document.getElementById('sched-name').value = '';
      document.getElementById('sched-desc').value = '';
      document.getElementById('sched-create-form').style.display = 'none';
      await loadTasks();
    } else {
      AgentDB.toast('Error: ' + (r.error || 'Unknown'), 'error');
    }
  }
})();
