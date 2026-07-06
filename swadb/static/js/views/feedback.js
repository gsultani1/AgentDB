(function() {
  const V = swadb.views.feedback = {};
  const el = () => document.getElementById('view-feedback');

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">Feedback &amp; Contradictions</h2>
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <button class="btn btn-primary" id="tab-contradictions">Contradictions</button>
        <button class="btn" id="tab-feedback">Pending Feedback</button>
      </div>
      <div id="feedback-content"></div>`;
    document.getElementById('tab-contradictions').onclick = function() {
      document.getElementById('tab-contradictions').className = 'btn btn-primary';
      document.getElementById('tab-feedback').className = 'btn';
      V.loadContradictions();
    };
    document.getElementById('tab-feedback').onclick = function() {
      document.getElementById('tab-feedback').className = 'btn btn-primary';
      document.getElementById('tab-contradictions').className = 'btn';
      V.loadFeedback();
    };
    V.loadContradictions();
  };

  V.loadContradictions = async function() {
    const r = await swadb.api('GET', '/api/contradictions?resolution=unresolved');
    const items = r.data?.contradictions || r.data || [];
    const box = document.getElementById('feedback-content');
    if (!items.length) {
      box.innerHTML = '<p style="color:var(--text2)">No unresolved contradictions.</p>';
      return;
    }
    let html = '';
    items.forEach(c => {
      const idA = (c.memory_a_id || '').slice(0, 8);
      const idB = (c.memory_b_id || '').slice(0, 8);
      html += `<div class="card" style="margin-bottom:12px;padding:16px">
        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px">
          <div>
            <strong>Memory A</strong> <code>${swadb.esc(idA)}</code>
            &nbsp;&mdash;&nbsp;
            <strong>Memory B</strong> <code>${swadb.esc(idB)}</code>
          </div>
          <span class="badge" style="background:var(--yellow);color:#000">unresolved</span>
        </div>
        <p style="margin-bottom:8px;color:var(--text2)">${swadb.esc(swadb.truncate(c.description || c.explanation || '', 120))}</p>
        <div style="display:flex;gap:8px">
          <button class="btn btn-sm btn-primary" onclick="swadb.views.feedback.resolve('${swadb.esc(c.id || c.contradiction_id)}','keep_a')">Keep A</button>
          <button class="btn btn-sm btn-primary" onclick="swadb.views.feedback.resolve('${swadb.esc(c.id || c.contradiction_id)}','keep_b')">Keep B</button>
          <button class="btn btn-sm" onclick="swadb.views.feedback.resolve('${swadb.esc(c.id || c.contradiction_id)}','merge')">Merge</button>
        </div>
      </div>`;
    });
    box.innerHTML = html;
  };

  V.resolve = async function(id, resolution) {
    const r = await swadb.api('POST', '/api/contradictions/' + id + '/resolve', {
      resolution: resolution,
      reasoning: 'User resolved via UI',
      resolved_by: 'user'
    });
    if (r.error) { swadb.toast('Error: ' + r.error, 'error'); return; }
    swadb.toast('Contradiction resolved: ' + resolution, 'success');
    V.loadContradictions();
  };

  V.loadFeedback = function() {
    document.getElementById('feedback-content').innerHTML =
      '<p style="color:var(--text2)">Feedback items shown in audit log.</p>';
  };
})();
