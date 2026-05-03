(function() {
  const V = AgentDB.views.skills = {};
  const el = () => document.getElementById('view-skills');

  V.load = function() {
    el().innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2>Skills</h2>
        <button class="btn btn-primary" id="skills-new-btn">New Skill</button>
      </div>
      <div id="skills-form" style="display:none;margin-bottom:16px;padding:16px;background:var(--bg2);border-radius:8px">
        <div style="margin-bottom:8px">
          <label style="display:block;margin-bottom:4px;font-weight:600">Name</label>
          <input id="skill-name" style="width:100%" placeholder="Skill name" />
        </div>
        <div style="margin-bottom:8px">
          <label style="display:block;margin-bottom:4px;font-weight:600">Description</label>
          <textarea id="skill-desc" rows="3" style="width:100%" placeholder="What does this skill do?"></textarea>
        </div>
        <div style="margin-bottom:12px">
          <label style="display:block;margin-bottom:4px;font-weight:600">Execution Type</label>
          <select id="skill-exec-type" style="width:200px">
            <option value="prompt_template">Prompt Template</option>
            <option value="code_procedure">Code Procedure</option>
            <option value="tool_invocation">Tool Invocation</option>
            <option value="composite">Composite</option>
          </select>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" id="skill-save-btn">Save</button>
          <button class="btn" id="skill-cancel-btn">Cancel</button>
        </div>
      </div>
      <div id="skills-table"></div>`;
    document.getElementById('skills-new-btn').onclick = function() {
      const form = document.getElementById('skills-form');
      form.style.display = form.style.display === 'none' ? 'block' : 'none';
    };
    document.getElementById('skill-cancel-btn').onclick = function() {
      document.getElementById('skills-form').style.display = 'none';
    };
    document.getElementById('skill-save-btn').onclick = V.create;
    V.loadTable();
  };

  V.loadTable = async function() {
    const r = await AgentDB.api('GET', '/api/skills');
    const items = r.data?.skills || r.data || [];
    if (!items.length) {
      document.getElementById('skills-table').innerHTML = '<p style="color:var(--text2)">No skills found.</p>';
      return;
    }
    let html = `<table><thead><tr>
      <th>Name</th><th>Type</th><th>Version</th><th>Uses</th><th>Success%</th><th>Last Used</th><th></th>
    </tr></thead><tbody>`;
    items.forEach(s => {
      const uses = s.usage_count || s.uses || 0;
      const success = s.success_rate != null ? (s.success_rate * 100).toFixed(0) + '%' : '-';
      const lastUsed = s.last_used ? AgentDB.formatDate(s.last_used) : '-';
      html += `<tr>
        <td><strong>${AgentDB.esc(s.name)}</strong><br><small style="color:var(--text2)">${AgentDB.esc(AgentDB.truncate(s.description || '', 60))}</small></td>
        <td>${AgentDB.esc(s.execution_type || '-')}</td>
        <td>${AgentDB.esc(String(s.version || 1))}</td>
        <td>${uses}</td>
        <td>${success}</td>
        <td>${lastUsed}</td>
        <td><button class="btn btn-danger btn-sm" onclick="AgentDB.views.skills.delete('${AgentDB.esc(s.id || s.skill_id)}')">Delete</button></td>
      </tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('skills-table').innerHTML = html;
  };

  V.create = async function() {
    const name = document.getElementById('skill-name').value.trim();
    const description = document.getElementById('skill-desc').value.trim();
    const execution_type = document.getElementById('skill-exec-type').value;
    if (!name) { AgentDB.toast('Name is required', 'error'); return; }
    const r = await AgentDB.api('POST', '/api/skills', { name, description, execution_type });
    if (r.error) { AgentDB.toast('Error: ' + r.error, 'error'); return; }
    AgentDB.toast('Skill created', 'success');
    document.getElementById('skills-form').style.display = 'none';
    document.getElementById('skill-name').value = '';
    document.getElementById('skill-desc').value = '';
    V.loadTable();
  };

  V.delete = async function(id) {
    if (!await AgentDB.confirm('Delete this skill?')) return;
    const r = await AgentDB.api('DELETE', '/api/skills/' + id);
    if (r.error) { AgentDB.toast('Error: ' + r.error, 'error'); return; }
    AgentDB.toast('Skill deleted', 'success');
    V.loadTable();
  };
})();
