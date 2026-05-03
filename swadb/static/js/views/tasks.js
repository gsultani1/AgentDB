(function() {
  const V = AgentDB.views.tasks = {};
  const el = () => document.getElementById('view-tasks');
  let currentTab = 'queue';

  V.load = async function() {
    el().innerHTML = `
      <div class="view-header">
        <h2>Autonomous Tasks</h2>
        <button class="btn btn-primary" id="tasks-new-btn">+ New Task</button>
      </div>
      <div class="sub-tabs" id="tasks-tabs">
        <button class="sub-tab active" data-tab="queue">Queue</button>
        <button class="sub-tab" data-tab="active">Active</button>
        <button class="sub-tab" data-tab="history">History</button>
      </div>
      <div id="tasks-content"></div>
      <div id="tasks-form" style="display:none"></div>
    `;
    document.querySelectorAll('#tasks-tabs .sub-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#tasks-tabs .sub-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTab = btn.dataset.tab;
        loadTab();
      });
    });
    document.getElementById('tasks-new-btn').addEventListener('click', showNewForm);
    await loadTab();
  };

  async function loadTab() {
    const statusMap = { queue: 'pending', active: 'running', history: null };
    const status = statusMap[currentTab];
    const container = document.getElementById('tasks-content');
    container.innerHTML = '<div class="loading">Loading...</div>';

    let url = '/api/tasks?limit=50';
    if (status) url += `&status=${status}`;
    const res = await AgentDB.api('GET', url);
    const tasks = res?.data || res || [];

    let filtered = tasks;
    if (currentTab === 'history') {
      filtered = tasks.filter(t => ['completed', 'failed', 'cancelled', 'timeout'].includes(t.status));
    }

    if (!filtered.length) {
      container.innerHTML = `<div class="empty">No ${currentTab} tasks.</div>`;
      return;
    }

    container.innerHTML = filtered.map(t => `
      <div class="card task-card">
        <div class="card-header">
          <strong>${AgentDB.esc(t.name)}</strong>
          <span class="badge badge-${statusColor(t.status)}">${t.status}</span>
        </div>
        <div class="card-meta">
          <div>${AgentDB.esc((t.goal || '').substring(0, 200))}</div>
          <span>Agent: ${AgentDB.esc(t.agent_id || 'default')}</span>
          <span>Created: ${AgentDB.formatDate(t.created_at)}</span>
          ${t.current_step ? `<span>Step: ${t.current_step}/${t.max_steps || '?'}</span>` : ''}
        </div>
        <div class="card-actions">
          ${t.status === 'pending' ? `<button class="btn btn-sm btn-primary" onclick="AgentDB.views.tasks.startTask('${t.id}')">Start</button>` : ''}
          ${t.status === 'running' ? `
            <button class="btn btn-sm" onclick="AgentDB.views.tasks.pauseTask('${t.id}')">Pause</button>
            <button class="btn btn-sm btn-danger" onclick="AgentDB.views.tasks.cancelTask('${t.id}')">Cancel</button>
          ` : ''}
          ${t.status === 'paused' ? `<button class="btn btn-sm btn-primary" onclick="AgentDB.views.tasks.startTask('${t.id}')">Resume</button>` : ''}
          <button class="btn btn-sm" onclick="AgentDB.views.tasks.viewTask('${t.id}')">Details</button>
          <button class="btn btn-sm btn-danger" onclick="AgentDB.views.tasks.deleteTask('${t.id}')">Delete</button>
        </div>
      </div>
    `).join('');
  }

  function statusColor(status) {
    const map = { pending: 'gray', running: 'blue', paused: 'yellow', completed: 'green', failed: 'red', cancelled: 'gray', timeout: 'red' };
    return map[status] || 'gray';
  }

  function showNewForm() {
    const container = document.getElementById('tasks-form');
    container.style.display = 'block';
    container.innerHTML = `
      <div class="card">
        <h3>New Autonomous Task</h3>
        <div class="form-group">
          <label>Name</label>
          <input type="text" id="task-name" class="form-input" placeholder="Task name">
        </div>
        <div class="form-group">
          <label>Goal</label>
          <textarea id="task-goal" class="form-input" rows="3" placeholder="Describe the goal..."></textarea>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Max Steps</label>
            <input type="number" id="task-max-steps" class="form-input" value="20" min="1" max="100">
          </div>
          <div class="form-group">
            <label>Require Approval</label>
            <select id="task-approval" class="form-input">
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="task-create-btn">Create Task</button>
          <button class="btn" onclick="document.getElementById('tasks-form').style.display='none'">Cancel</button>
        </div>
      </div>
    `;
    document.getElementById('task-create-btn').addEventListener('click', async () => {
      const name = document.getElementById('task-name').value.trim();
      const goal = document.getElementById('task-goal').value.trim();
      if (!name || !goal) return AgentDB.toast('Name and goal are required', 'error');
      const res = await AgentDB.api('POST', '/api/tasks', {
        name, goal,
        max_steps: parseInt(document.getElementById('task-max-steps').value) || 20,
        require_approval: document.getElementById('task-approval').value === 'true',
      });
      if (res && !res.error) {
        AgentDB.toast('Task created', 'success');
        container.style.display = 'none';
        await loadTab();
      } else {
        AgentDB.toast(res?.error || 'Failed', 'error');
      }
    });
  }

  V.viewTask = async function(id) {
    const container = document.getElementById('tasks-content');
    const [taskRes, stepsRes, actionsRes] = await Promise.all([
      AgentDB.api('GET', `/api/tasks/${id}`),
      AgentDB.api('GET', `/api/tasks/${id}/steps`),
      AgentDB.api('GET', `/api/tasks/${id}/actions`),
    ]);
    const task = taskRes?.data || taskRes;
    const steps = stepsRes?.data || stepsRes || [];
    const actions = actionsRes?.data || actionsRes || [];

    container.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h3>${AgentDB.esc(task?.name || id)}</h3>
          <button class="btn btn-sm" onclick="AgentDB.views.tasks.load()">Back</button>
        </div>
        <div class="card-meta">
          <span class="badge badge-${statusColor(task?.status)}">${task?.status}</span>
          <span>Agent: ${task?.agent_id || 'default'}</span>
          <span>Created: ${AgentDB.formatDate(task?.created_at)}</span>
        </div>
        <div><strong>Goal:</strong> ${AgentDB.esc(task?.goal || '')}</div>
        ${task?.constraints ? `<div><strong>Constraints:</strong> ${AgentDB.esc(task.constraints)}</div>` : ''}

        <h4>Steps (${steps.length})</h4>
        ${steps.length ? `<table class="data-table">
          <thead><tr><th>#</th><th>Status</th><th>Action</th><th>Output</th></tr></thead>
          <tbody>${steps.map((s, i) => `<tr>
            <td>${i + 1}</td>
            <td><span class="badge badge-${statusColor(s.status)}">${s.status}</span></td>
            <td>${AgentDB.esc((s.action_type || '').substring(0, 50))}</td>
            <td>${AgentDB.esc((s.output || '').substring(0, 100))}</td>
          </tr>`).join('')}</tbody>
        </table>` : '<div class="empty">No steps recorded.</div>'}

        <h4>Actions (${actions.length})</h4>
        ${actions.length ? `<table class="data-table">
          <thead><tr><th>Type</th><th>Status</th><th>Duration</th><th>Started</th></tr></thead>
          <tbody>${actions.map(a => `<tr>
            <td>${AgentDB.esc(a.action_type || '')}</td>
            <td><span class="badge badge-${statusColor(a.status)}">${a.status}</span></td>
            <td>${a.duration_ms ? a.duration_ms + 'ms' : '-'}</td>
            <td>${AgentDB.formatDate(a.started_at)}</td>
          </tr>`).join('')}</tbody>
        </table>` : '<div class="empty">No actions recorded.</div>'}
      </div>
    `;
  };

  V.startTask = async function(id) {
    await AgentDB.api('POST', `/api/tasks/${id}/start`);
    AgentDB.toast('Task started', 'success');
    await loadTab();
  };
  V.pauseTask = async function(id) {
    await AgentDB.api('POST', `/api/tasks/${id}/pause`);
    AgentDB.toast('Task paused', 'success');
    await loadTab();
  };
  V.cancelTask = async function(id) {
    if (!confirm('Cancel this task?')) return;
    await AgentDB.api('POST', `/api/tasks/${id}/cancel`);
    AgentDB.toast('Task cancelled', 'success');
    await loadTab();
  };
  V.deleteTask = async function(id) {
    if (!confirm('Delete this task?')) return;
    await AgentDB.api('DELETE', `/api/tasks/${id}`);
    AgentDB.toast('Task deleted', 'success');
    await loadTab();
  };
})();
