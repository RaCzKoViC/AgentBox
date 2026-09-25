const content = document.getElementById('content');
const pageTitle = document.getElementById('page-title');
const liveBanner = document.getElementById('live-banner');
const wsState = document.getElementById('ws-state');
const liveEvents = [];
const LIVE_MAX = 40;

function token() { return sessionStorage.getItem('ab_token') || ''; }
function authHeaders() { const t = token(); return t ? {Authorization: 'Bearer ' + t} : {}; }

async function api(path, opts={}) {
  const r = await fetch(path, {
    ...opts,
    headers: {...authHeaders(), ...(opts.headers||{}), ...(opts.body ? {'Content-Type':'application/json'} : {})},
    body: opts.body ? (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body)) : undefined,
  });
  if (r.status === 401) { location.href = '/login'; throw new Error('auth'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = (j.error && j.error.message) || j.detail || msg; } catch {}
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  if (r.status === 204) return null;
  return r.json();
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function statusPill(val, map) {
  const v = String(val ?? '—').toLowerCase();
  let cls = 'idle';
  if (map) cls = map(v) || cls;
  else if (['ok','healthy','running','online','busy','up','live','pass','passed','approved'].includes(v)) cls = 'ok';
  else if (['warn','warning','degraded','pending','queued','drift','paused'].includes(v)) cls = 'warn';
  else if (['error','bad','down','stopped','failed','fail','rejected','quarantined','offline','critical'].includes(v)) cls = 'bad';
  else if (v === '—' || v === '') cls = 'idle';
  return `<span class="pill ${cls}">${escapeHtml(val ?? '—')}</span>`;
}

function cards(items) {
  return `<div class="cards">${items.map(it => {
    const [label, value, html] = it;
    return `<div class="card dense"><div class="label">${label}</div><div class="value">${html ? value : escapeHtml(value)}</div></div>`;
  }).join('')}</div>`;
}

function emptyState(title, hint) {
  return `<div class="empty"><strong>${escapeHtml(title)}</strong>${escapeHtml(hint || '')}</div>`;
}

function tableWrap(html) {
  return `<div class="table-wrap">${html}</div>`;
}

function closeNav() {
  document.body.classList.remove('nav-open');
  const bd = document.getElementById('sidebar-backdrop');
  if (bd) bd.hidden = true;
}
function openNav() {
  document.body.classList.add('nav-open');
  const bd = document.getElementById('sidebar-backdrop');
  if (bd) bd.hidden = false;
}

function pushLive(msg) {
  const ts = msg.timestamp || msg.ts || new Date().toISOString();
  const type = msg.type || msg.event || 'event';
  const detail = msg.message || msg.task_id || msg.id || JSON.stringify(msg).slice(0, 120);
  liveEvents.unshift({ts, type, detail});
  if (liveEvents.length > LIVE_MAX) liveEvents.pop();
  const feed = document.getElementById('live-feed');
  if (feed) renderLiveFeed(feed);
}

function renderLiveFeed(el) {
  if (!liveEvents.length) {
    el.innerHTML = '<li class="muted">Waiting for events…</li>';
    return;
  }
  el.innerHTML = liveEvents.map(e =>
    `<li><span class="muted">${escapeHtml(String(e.ts).replace('T',' ').slice(0,19))}</span>
     <span><span class="ev-type">${escapeHtml(e.type)}</span> ${escapeHtml(e.detail)}</span></li>`
  ).join('');
}

async function renderOverview() {
  const [h, s, w, intel, ops, fc] = await Promise.all([
    api('/api/v1/health'),
    api('/api/v1/status'),
    api('/api/v1/workers').catch(()=>({counts:{}})),
    api('/api/v1/intelligence/status').catch(()=>({})),
    api('/api/v1/ops/status').catch(()=>({})),
    api('/api/v1/ops/forecast').catch(()=>({})),
  ]);
  const doc = ops.doctor || {};
  const forecast = fc.level || (ops.forecast || {}).level || '—';
  const docHealth = doc.health || doc.status || '—';
  content.innerHTML = `
    <div class="status-pills">
      ${statusPill('v' + (h.version || ''), ()=>'idle')}
      ${statusPill('daemon: ' + (h.daemon || '—'), v => v.includes('run') ? 'ok' : 'bad')}
      ${statusPill('web: up', ()=>'ok')}
      ${statusPill('db: ' + (h.database || '—'), v => v.includes('ok') ? 'ok' : 'bad')}
      ${statusPill('doctor: ' + docHealth, v => v.includes('health') || v.includes('ok') ? 'ok' : (v.includes('warn') ? 'warn' : (v === 'doctor: —' ? 'idle' : 'bad')))}
      ${statusPill('forecast: ' + forecast, v => v.includes('ok') || v.includes('green') || v.includes('low') ? 'ok' : (v.includes('warn') || v.includes('med') ? 'warn' : (v === 'forecast: —' ? 'idle' : 'warn')))}
      ${statusPill('ws: ' + (h.websocket || '—'), v => v.includes('run') ? 'ok' : 'warn')}
    </div>
    ${cards([
      ['Version', h.version, false],
      ['Daemon', h.daemon, false],
      ['Database', h.database, false],
      ['Doctor', docHealth, false],
      ['Forecast', forecast, false],
      ['Tasks running', s.tasks?.running ?? '—', false],
      ['Tasks queued', s.tasks?.queued ?? '—', false],
      ['Approvals', s.approvals?.pending ?? '—', false],
      ['Handoffs', s.handoffs?.pending ?? '—', false],
      ['Agents', s.agents?.active ?? '—', false],
      ['Workers online', w.counts?.online ?? '—', false],
      ['Intel chunks', intel.index?.chunks_total ?? '—', false],
      ['CPU %', Number(s.system?.cpu_percent ?? 0).toFixed(1), false],
      ['RAM %', Number(s.system?.memory_percent ?? 0).toFixed(1), false],
    ])}
    <div class="panel-block">
      <div class="row-between">
        <h3>Quick actions</h3>
        <div class="actions" style="margin:0">
          <button type="button" id="qa-daemon">Start daemon</button>
          <button type="button" class="secondary" id="qa-scan">Run ops scan</button>
          <button type="button" class="ghost" id="qa-ops">Open Ops</button>
        </div>
      </div>
      <div id="qa-flash" hidden></div>
    </div>
    <div class="panel-block">
      <div class="row-between"><h3>Live events</h3><span class="muted" style="font-size:.75rem">WebSocket feed</span></div>
      <ul class="live-feed" id="live-feed"></ul>
    </div>`;
  renderLiveFeed(document.getElementById('live-feed'));
  const flash = document.getElementById('qa-flash');
  const showFlash = (msg, isErr) => {
    flash.hidden = false;
    flash.className = 'flash' + (isErr ? ' err' : '');
    flash.textContent = msg;
  };
  document.getElementById('qa-daemon').onclick = async () => {
    try {
      const r = await api('/api/v1/ops/daemon/start', {method:'POST', body:{}});
      showFlash('Daemon: ' + JSON.stringify(r.started?.daemon || r));
      setTimeout(() => route(), 800);
    } catch (e) {
      showFlash(e.message, true);
    }
  };
  document.getElementById('qa-scan').onclick = async () => {
    try {
      const r = await api('/api/v1/ops/scan');
      const n = (r.proposals || []).length;
      showFlash(`Ops scan: ${n} proposal(s)`);
      pushLive({type:'ops.scan', message:`${n} proposals`, timestamp:new Date().toISOString()});
    } catch (e) {
      showFlash(e.message, true);
    }
  };
  document.getElementById('qa-ops').onclick = () => { location.hash = '#ops'; };
}

async function renderTasks() {
  const data = await api('/api/v1/tasks?limit=50&order=desc');
  const items = data.items || [];
  const rows = items.map(t => `<tr>
    <td><a href="#task/${escapeHtml(t.id)}">${escapeHtml(t.id)}</a></td>
    <td>${escapeHtml(t.title||'')}</td>
    <td>${statusPill(t.status)}</td>
    <td>${escapeHtml(t.provider||'')}</td>
    <td>${t.priority??''}</td></tr>`).join('');
  content.innerHTML = `
    <div class="panel-block">
      <h3>Create task</h3>
      <form id="create-task" class="form-grid">
        <label class="full">Title<input name="title" required placeholder="Short task title"/></label>
        <label class="full">Project path<input name="project" value="/workspace/projects/demo-python"/></label>
        <label>Provider
          <select name="provider">
            <option value="stub">stub</option>
            <option value="codex">codex</option>
          </select>
        </label>
        <label>Priority<input name="priority" type="number" value="50" min="0" max="100"/></label>
        <label class="full">Description<textarea name="description" rows="2" placeholder="Optional"></textarea></label>
        <div class="full actions"><button type="submit">Create</button></div>
      </form>
      <div id="task-flash" hidden></div>
    </div>
    <h3 class="section">Recent tasks</h3>
    ${items.length ? tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Provider</th><th>Pri</th></tr></thead><tbody>${rows}</tbody></table>`)
      : emptyState('No tasks yet', 'Create one above — default project is /workspace/projects/demo-python')}
  `;
  const form = document.getElementById('create-task');
  const flash = document.getElementById('task-flash');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    try {
      const body = {
        title: fd.get('title'),
        project: fd.get('project'),
        provider: fd.get('provider'),
        priority: Number(fd.get('priority') || 50),
        description: fd.get('description') || '',
      };
      const t = await api('/api/v1/tasks', {method:'POST', body});
      flash.hidden = false;
      flash.className = 'flash';
      flash.innerHTML = `Created <a href="#task/${escapeHtml(t.id)}">${escapeHtml(t.id)}</a>`;
      form.reset();
      form.project.value = '/workspace/projects/demo-python';
      form.provider.value = 'stub';
      setTimeout(() => renderTasks(), 400);
    } catch (ex) {
      flash.hidden = false;
      flash.className = 'flash err';
      flash.textContent = ex.message;
    }
  };
}

async function renderTask(id) {
  const [t, tl] = await Promise.all([api('/api/v1/tasks/'+id), api('/api/v1/tasks/'+id+'/timeline')]);
  const events = (tl.items||[]).map(e => `<li><span class="muted">${escapeHtml(e.created_at||e.ts||'')}</span> <span>${escapeHtml(e.message||e.kind||'')}</span></li>`).join('');
  content.innerHTML = `<div class="panel-block">
      <h3>${escapeHtml(t.title||id)}</h3>
      <p class="muted">${escapeHtml(t.id)} · ${statusPill(t.status)} · ${escapeHtml(t.provider||'—')}</p>
      <div class="actions">
        ${t.provider === 'journal' ? '<span class="muted">Journal entry (logged manually) — Queue/Resume disabled to avoid a Codex run.</span>' : `<button data-act="queue">Queue</button>`}
        <button class="secondary" data-act="pause">Pause</button>
        ${t.provider === 'journal' ? '' : `<button class="secondary" data-act="resume">Resume</button>`}
        <button class="danger" data-act="cancel">Cancel</button>
        <button class="ghost" type="button" onclick="location.hash='#tasks'">Back</button>
      </div></div>
    <h3 class="section">Timeline</h3>
    <ul class="timeline">${events||'<li class="muted">No events</li>'}</ul>`;
  content.querySelectorAll('button[data-act]').forEach(btn => {
    btn.onclick = async () => { await api(`/api/v1/tasks/${id}/${btn.dataset.act}`, {method:'POST'}); renderTask(id); };
  });
}

async function renderApprovals() {
  const data = await api('/api/v1/approvals?status=pending');
  const items = data.items || [];
  if (!items.length) {
    content.innerHTML = emptyState('No pending approvals', 'Gates and high-risk remediations will show up here.');
    return;
  }
  const rows = items.map(a => `<tr>
    <td>${escapeHtml(a.id)}</td><td>${escapeHtml(a.action||a.gate||'')}</td><td>${escapeHtml(a.task_id||'')}</td><td>${statusPill(a.status)}</td>
    <td><button data-id="${escapeHtml(a.id)}" data-act="approve">Approve</button>
        <button class="danger" data-id="${escapeHtml(a.id)}" data-act="reject">Reject</button></td></tr>`).join('');
  content.innerHTML = tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Action</th><th>Task</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table>`);
  content.querySelectorAll('button[data-act]').forEach(btn => {
    btn.onclick = async () => {
      await api(`/api/v1/approvals/${btn.dataset.id}/${btn.dataset.act}`, {method:'POST', body:{comment:'via dashboard'}});
      renderApprovals();
    };
  });
}

async function renderHandoffs() {
  const data = await api('/api/v1/handoffs?limit=50');
  const items = data.items || [];
  if (!items.length) {
    content.innerHTML = emptyState('No handoffs', 'Agent-to-agent transfers appear here.');
    return;
  }
  const rows = items.map(h => `<tr>
    <td>${escapeHtml(h.id)}</td><td>${escapeHtml(h.source_agent||h.from_agent||'')}</td><td>${escapeHtml(h.target_agent||h.to_agent||'')}</td>
    <td>${escapeHtml(h.task_id||'')}</td><td>${statusPill(h.status)}</td></tr>`).join('');
  content.innerHTML = tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>From</th><th>To</th><th>Task</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`);
}

async function renderAgents() {
  const data = await api('/api/v1/agents');
  const items = data.items || [];
  if (!items.length) {
    content.innerHTML = emptyState('No agents', 'Register agents to see status here.');
    return;
  }
  content.innerHTML = `<div class="cards">${items.map(a =>
    `<div class="card"><div class="label">${escapeHtml(a.name||a.id)}</div>
     <div class="value" style="font-size:1rem">${statusPill(a.status)}</div>
     <div class="muted">${escapeHtml((a.provider||'') + ' ' + (a.model||''))}</div></div>`).join('')}</div>`;
}

async function renderNodes() {
  const data = await api('/api/v1/workers');
  const counts = data.counts || {};
  const items = data.items || [];
  const rows = items.map(w => {
    const caps = w.capabilities || {};
    const capStr = [caps.docker&&'docker', caps.gpu&&'gpu', (caps.providers||[]).join(',')].filter(Boolean).join(' ');
    return `<tr>
      <td>${escapeHtml(w.name||w.id)}</td>
      <td>${escapeHtml(w.hostname||'')}</td>
      <td>${escapeHtml(w.tailscale_ip||'')}</td>
      <td>${statusPill(w.status)}</td>
      <td>${w.current_load??0}/${w.max_parallel_tasks??1}</td>
      <td class="muted">${escapeHtml(capStr||'—')}</td>
      <td>${escapeHtml(w.version||'')}</td>
      <td class="muted">${escapeHtml(w.last_heartbeat||'')}</td>
    </tr>`;
  }).join('');
  content.innerHTML = cards([
    ['Workers', counts.total ?? items.length, false],
    ['Online', counts.online ?? '—', false],
    ['Offline', counts.offline ?? '—', false],
    ['Quarantined', counts.quarantined ?? '—', false],
  ]) + (items.length
    ? tableWrap(`<table class="tbl" style="margin-top:1rem"><thead><tr>
    <th>Name</th><th>Host</th><th>IP</th><th>Status</th><th>Tasks</th><th>Capabilities</th><th>Ver</th><th>Heartbeat</th>
  </tr></thead><tbody>${rows}</tbody></table>`)
    : `<div style="margin-top:1rem">${emptyState('No workers enrolled', 'Use agent5-worker enroll on remote nodes.')}</div>`);
}

async function renderIntelligence() {
  const data = await api('/api/v1/intelligence/status');
  const idxs = (data.index?.indexes||[]).map(i => `<tr>
    <td>${escapeHtml(i.project_id||'')}</td>
    <td>${statusPill(i.status)}</td>
    <td>${i.files_count??'—'}</td>
    <td>${i.chunks_count??'—'}</td>
    <td>${escapeHtml(i.embedding_model||'')}</td>
    <td>${escapeHtml(i.updated_at||'')}</td>
  </tr>`).join('');
  const models = (data.models||[]).map(m => `<tr>
    <td>${escapeHtml(m.provider)}</td><td>${escapeHtml(m.model)}</td>
    <td>${m.local?'local':'remote'}</td><td>${m.context_window||'—'}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Version', data.version||'—', false],
    ['Embedding', data.embedding?.id||'—', false],
    ['Vector backend', data.vector_store?.backend||'—', false],
    ['Vectors', data.vector_store?.total??'—', false],
    ['Chunks', data.index?.chunks_total??'—', false],
    ['Memories', data.memories??'—', false],
    ['Quality signals', data.quality?.total_signals??'—', false],
  ]) + `<h3 class="section">Semantic indexes</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Project</th><th>Status</th><th>Files</th><th>Chunks</th><th>Model</th><th>Updated</th></tr></thead>
  <tbody>${idxs||'<tr><td colspan=6 class="muted">No indexes yet</td></tr>'}</tbody></table>`)}
  <h3 class="section">Model registry</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Provider</th><th>Model</th><th>Locality</th><th>Context</th></tr></thead>
  <tbody>${models||'<tr><td colspan=4 class="muted">None</td></tr>'}</tbody></table>`)}`;
}

async function renderPlans() {
  const [goals, plans, wfs] = await Promise.all([
    api('/api/v1/goals').catch(()=>({goals:[]})),
    api('/api/v1/plans').catch(()=>({plans:[]})),
    api('/api/v1/workflows').catch(()=>({workflows:[]})),
  ]);
  const gRows = (goals.goals||[]).map(g => `<tr>
    <td>${escapeHtml(g.id||'')}</td>
    <td>${escapeHtml(g.title||'')}</td>
    <td>${statusPill(g.status)}</td>
    <td>${escapeHtml(g.risk_profile||'')}</td>
    <td>${escapeHtml(g.updated_at||g.created_at||'')}</td>
  </tr>`).join('');
  const pRows = (plans.plans||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml(p.goal_id||'')}</td>
    <td>v${p.version??'—'}</td>
    <td>${statusPill(p.status)}</td>
    <td>${p.quality_score??'—'}</td>
    <td>${escapeHtml(p.workflow_template||'')}</td>
  </tr>`).join('');
  const wRows = (wfs.workflows||[]).map(w => `<tr>
    <td>${escapeHtml(w.name||'')}</td>
    <td>${escapeHtml((w.stages||[]).join(' → '))}</td>
    <td>${escapeHtml(w.description||'')}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Goals', (goals.goals||[]).length, false],
    ['Plans', (plans.plans||[]).length, false],
    ['Workflow templates', (wfs.workflows||[]).length, false],
  ]) + `<h3 class="section">Goals</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Risk</th><th>Updated</th></tr></thead>
  <tbody>${gRows||'<tr><td colspan=5 class="muted">No goals</td></tr>'}</tbody></table>`)}
  <h3 class="section">Plans</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Goal</th><th>Ver</th><th>Status</th><th>Quality</th><th>Template</th></tr></thead>
  <tbody>${pRows||'<tr><td colspan=6 class="muted">No plans</td></tr>'}</tbody></table>`)}
  <h3 class="section">Workflows</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Name</th><th>Stages</th><th>Description</th></tr></thead>
  <tbody>${wRows||'<tr><td colspan=3 class="muted">No templates</td></tr>'}</tbody></table>`)}`;
}

async function renderTools() {
  const [tools, health, runs] = await Promise.all([
    api('/api/v1/tools').catch(()=>({tools:[]})),
    api('/api/v1/tools/health').catch(()=>({health:[]})),
    api('/api/v1/tool-runs?limit=20').catch(()=>({runs:[]})),
  ]);
  const healthMap = {};
  (health.health||[]).forEach(h => { healthMap[h.tool_id] = h.status; });
  const rows = (tools.tools||[]).map(t => `<tr>
    <td>${escapeHtml(t.name||t.id||'')}</td>
    <td>${escapeHtml(t.category||'')}</td>
    <td>${escapeHtml((t.capabilities||[]).slice(0,4).join(', '))}</td>
    <td>${statusPill(healthMap[t.id]||t.health_status||'')}</td>
    <td>${escapeHtml(t.risk_level||'')}</td>
    <td>${t.reliability_score??'—'}</td>
    <td>${escapeHtml(t.version||'')}</td>
  </tr>`).join('');
  const runRows = (runs.runs||[]).map(r => `<tr>
    <td>${escapeHtml(r.tool_id||'')}</td>
    <td>${statusPill(r.status)}</td>
    <td>${r.duration_ms??'—'}</td>
    <td>${escapeHtml(r.risk_level||'')}</td>
    <td>${escapeHtml(r.decision||'')}</td>
    <td>${escapeHtml(r.created_at||'')}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Tools', (tools.tools||[]).length, false],
    ['Healthy', (health.health||[]).filter(h=>h.status==='healthy').length, false],
    ['Recent runs', (runs.runs||[]).length, false],
  ]) + `<h3 class="section">Registry</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Name</th><th>Category</th><th>Capabilities</th><th>Health</th><th>Risk</th><th>Reliability</th><th>Version</th></tr></thead>
  <tbody>${rows||'<tr><td colspan=7 class="muted">No tools</td></tr>'}</tbody></table>`)}
  <h3 class="section">Recent tool runs</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Tool</th><th>Status</th><th>Duration</th><th>Risk</th><th>Decision</th><th>When</th></tr></thead>
  <tbody>${runRows||'<tr><td colspan=6 class="muted">No runs</td></tr>'}</tbody></table>`)}`;
}

async function renderEval() {
  const [suites, runs, proposals, baselines, failures] = await Promise.all([
    api('/api/v1/eval/suites').catch(()=>({suites:[]})),
    api('/api/v1/eval/runs?limit=20').catch(()=>({runs:[]})),
    api('/api/v1/proposals').catch(()=>({proposals:[]})),
    api('/api/v1/eval/baselines').catch(()=>({baselines:[]})),
    api('/api/v1/eval/failures').catch(()=>({clusters:[]})),
  ]);
  const sRows = (suites.suites||[]).map(s => `<tr>
    <td>${escapeHtml(s.id||'')}</td>
    <td>${escapeHtml(String(s.version??''))}</td>
    <td>${s.case_count??'—'}</td>
    <td>${escapeHtml(s.description||'')}</td>
  </tr>`).join('');
  const rRows = (runs.runs||[]).map(r => `<tr>
    <td>${escapeHtml(r.id||'')}</td>
    <td>${escapeHtml(r.suite_id||'')}</td>
    <td>${statusPill(r.status)}</td>
    <td>${r.score??'—'}</td>
    <td>${statusPill(r.gate_status)}</td>
    <td>${escapeHtml(r.created_at||'')}</td>
  </tr>`).join('');
  const pRows = (proposals.proposals||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml((p.target_type||'')+'/'+(p.target_id||''))}</td>
    <td>${escapeHtml(p.risk_level||'')}</td>
    <td>${statusPill(p.status)}</td>
    <td>${escapeHtml((p.proposal&&p.proposal.title)||'')}</td>
  </tr>`).join('');
  const bRows = (baselines.baselines||(baselines.baseline?[baselines.baseline]:[])).map(b => `<tr>
    <td>${escapeHtml(b.suite_id||'')}</td>
    <td>${(b.summary&&b.summary.score)!=null?b.summary.score:'—'}</td>
    <td>${(b.summary&&b.summary.pass_rate)!=null?b.summary.pass_rate:'—'}</td>
    <td>${escapeHtml(b.created_at||'')}</td>
  </tr>`).join('');
  const fRows = (failures.clusters||[]).slice(0,10).map(c => `<tr>
    <td>${escapeHtml(c.signature||'')}</td>
    <td>${c.count??0}</td>
    <td>${escapeHtml(c.case_id||'')}</td>
    <td>${escapeHtml((c.error_sample||'').slice(0,80))}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Suites', (suites.suites||[]).length, false],
    ['Runs', (runs.runs||[]).length, false],
    ['Proposals', (proposals.proposals||[]).length, false],
    ['Failure clusters', (failures.clusters||[]).length, false],
  ]) + `<h3 class="section">Suites</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Suite</th><th>Ver</th><th>Cases</th><th>Description</th></tr></thead>
  <tbody>${sRows||'<tr><td colspan=4 class="muted">No suites</td></tr>'}</tbody></table>`)}
  <h3 class="section">Recent evaluation runs</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Run</th><th>Suite</th><th>Status</th><th>Score</th><th>Gate</th><th>When</th></tr></thead>
  <tbody>${rRows||'<tr><td colspan=6 class="muted">No runs</td></tr>'}</tbody></table>`)}
  <h3 class="section">Baselines</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Suite</th><th>Score</th><th>Pass rate</th><th>When</th></tr></thead>
  <tbody>${bRows||'<tr><td colspan=4 class="muted">No baselines</td></tr>'}</tbody></table>`)}
  <h3 class="section">Improvement proposals</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Target</th><th>Risk</th><th>Status</th><th>Title</th></tr></thead>
  <tbody>${pRows||'<tr><td colspan=5 class="muted">No proposals</td></tr>'}</tbody></table>`)}
  <h3 class="section">Failure mining</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Signature</th><th>Count</th><th>Case</th><th>Sample</th></tr></thead>
  <tbody>${fRows||'<tr><td colspan=4 class="muted">No failures</td></tr>'}</tbody></table>`)}`;
}

async function renderOps() {
  const [st, scan, pbs, fc, drift, plans, rem, health, incidents, drills] = await Promise.all([
    api('/api/v1/ops/status').catch(()=>({})),
    api('/api/v1/ops/scan').catch(()=>({proposals:[]})),
    api('/api/v1/ops/playbooks').catch(()=>({playbooks:[]})),
    api('/api/v1/ops/forecast').catch(()=>({})),
    api('/api/v1/ops/drift').catch(()=>({scopes:{}})),
    api('/api/v1/ops/plans').catch(()=>({plans:[]})),
    api('/api/v1/ops/remediations?limit=20').catch(()=>({actions:[]})),
    api('/api/v1/ops/health-score').catch(()=>({})),
    api('/api/v1/ops/incidents?limit=20').catch(()=>({incidents:[]})),
    api('/api/v1/ops/restore-drills?limit=10').catch(()=>({drills:[]})),
  ]);
  const doc = st.doctor || {};
  const res = (fc.resources) || ((st.forecast||{}).resources) || {};
  const pbRows = (pbs.playbooks||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml(p.title||'')}</td>
    <td>${statusPill(p.risk_level)}</td>
    <td>${p.auto_eligible?'auto':'approval'}</td>
    <td>${escapeHtml(p.description||'')}</td>
  </tr>`).join('');
  const propRows = (scan.proposals||[]).map(p => `<tr>
    <td>${escapeHtml(p.playbook_id||'')}</td>
    <td>${statusPill(p.risk_level)}</td>
    <td>${p.auto?'yes':'no'}</td>
    <td>${escapeHtml(p.reason||'')}</td>
  </tr>`).join('');
  const remRows = (rem.actions||[]).map(a => `<tr>
    <td>${escapeHtml(a.id||'')}</td>
    <td>${escapeHtml(a.action_type||'')}</td>
    <td>${statusPill(a.risk_level)}</td>
    <td>${statusPill(a.status)}</td>
    <td>${escapeHtml(a.created_at||'')}</td>
  </tr>`).join('');
  const planRows = (plans.plans||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml(p.title||'')}</td>
    <td>${escapeHtml(p.priority||'')}</td>
    <td>${statusPill(p.status)}</td>
    <td>${(p.actions||[]).length}</td>
  </tr>`).join('');
  const sigRows = (fc.signals||(st.forecast||{}).signals||[]).map(s => `<tr>
    <td>${statusPill(s.level)}</td>
    <td>${escapeHtml(s.code||'')}</td>
    <td>${escapeHtml(s.message||'')}</td>
  </tr>`).join('');
  const hs = health.score ?? (st.health||{}).score;
  const hstat = health.status || (st.health||{}).status || '—';
  const incRows = (incidents.incidents||st.open_incidents||[]).map(i => `<tr>
    <td>${escapeHtml(i.id||'')}</td>
    <td>${statusPill(i.severity)}</td>
    <td>${statusPill(i.status)}</td>
    <td>${escapeHtml(i.component||'')}</td>
    <td>${escapeHtml(i.title||'')}</td>
    <td>${escapeHtml(i.detected_at||'')}</td>
  </tr>`).join('');
  const drillRows = (drills.drills||[]).map(d => `<tr>
    <td>${escapeHtml(d.id||'')}</td>
    <td>${escapeHtml(d.backup_id||'')}</td>
    <td>${statusPill(d.result)}</td>
    <td>${escapeHtml(d.created_at||'')}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Health score', (hs!=null?hs+'/100':'—')+' '+hstat, false],
    ['Doctor', doc.health||doc.status||'—', false],
    ['Forecast', fc.level||(st.forecast||{}).level||'—', false],
    ['Open incidents', (incidents.incidents||st.open_incidents||[]).filter(i=>!['resolved','closed'].includes(i.status)).length, false],
    ['Drift', drift.drifted?'yes':'no', false],
    ['Playbooks', (pbs.playbooks||[]).length, false],
    ['Disk %', res.disk_percent??'—', false],
    ['DB MB', res.db_mb??'—', false],
  ]) + `<div class="panel-block">
    <div class="row-between">
      <h3>Actions</h3>
      <div class="actions" style="margin:0">
        <button type="button" id="ops-rescan">Refresh scan</button>
        <button type="button" class="secondary" id="ops-remediate-dry">Remediate (dry-run)</button>
        <button type="button" class="secondary" id="ops-restore-drill">Restore drill</button>
      </div>
    </div>
    <div id="ops-flash" hidden></div>
  </div>
  <h3 class="section">Forecast signals</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Level</th><th>Code</th><th>Message</th></tr></thead>
  <tbody>${sigRows||'<tr><td colspan=3 class="muted">None</td></tr>'}</tbody></table>`)}
  <h3 class="section">Scan proposals</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>Playbook</th><th>Risk</th><th>Auto</th><th>Reason</th></tr></thead>
  <tbody>${propRows||'<tr><td colspan=4 class="muted">No proposals</td></tr>'}</tbody></table>`)}
  <h3 class="section">Playbooks</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Risk</th><th>Mode</th><th>Description</th></tr></thead>
  <tbody>${pbRows||'<tr><td colspan=5 class="muted">None</td></tr>'}</tbody></table>`)}
  <h3 class="section">Recent remediations</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Action</th><th>Risk</th><th>Status</th><th>When</th></tr></thead>
  <tbody>${remRows||'<tr><td colspan=5 class="muted">None</td></tr>'}</tbody></table>`)}
  <h3 class="section">Incidents</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Severity</th><th>Status</th><th>Component</th><th>Title</th><th>Detected</th></tr></thead>
  <tbody>${incRows||'<tr><td colspan=6 class="muted">No incidents</td></tr>'}</tbody></table>`)}
  <h3 class="section">Restore drills</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Backup</th><th>Result</th><th>When</th></tr></thead>
  <tbody>${drillRows||'<tr><td colspan=4 class="muted">No drills</td></tr>'}</tbody></table>`)}
  <h3 class="section">Maintenance plans</h3>
  ${tableWrap(`<table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead>
  <tbody>${planRows||'<tr><td colspan=5 class="muted">None</td></tr>'}</tbody></table>`)}`;
  const flash = document.getElementById('ops-flash');
  document.getElementById('ops-rescan').onclick = () => renderOps();
  document.getElementById('ops-remediate-dry').onclick = async () => {
    try {
      const r = await api('/api/v1/ops/remediate', {method:'POST', body:{dry_run:true, auto_low_risk:true}});
      flash.hidden = false;
      flash.className = 'flash';
      flash.textContent = 'Dry-run remediate: ' + JSON.stringify(r).slice(0, 240);
      pushLive({type:'ops.remediate', message:'dry-run complete', timestamp:new Date().toISOString()});
    } catch (e) {
      flash.hidden = false;
      flash.className = 'flash err';
      flash.textContent = e.message;
    }
  };
  document.getElementById('ops-restore-drill').onclick = async () => {
    try {
      flash.hidden = false;
      flash.className = 'flash';
      flash.textContent = 'Running restore drill…';
      const r = await api('/api/v1/ops/restore-drill', {method:'POST', body:{approve_destructive:false}});
      flash.textContent = 'Restore drill: ' + (r.result||'?') + ' backup=' + (r.backup_id||'');
      pushLive({type:'ops.restore_drill', message:r.result, timestamp:new Date().toISOString()});
      renderOps();
    } catch (e) {
      flash.hidden = false;
      flash.className = 'flash err';
      flash.textContent = e.message;
    }
  };
}

async function renderMetrics() {
  const m = await api('/api/v1/metrics');
  const sys = m.system || {};
  content.innerHTML = cards([
    ['WS connections', m.websocket_connections ?? 0, false],
    ['CPU %', sys.cpu_percent ?? '—', false],
    ['RAM %', sys.memory_percent ?? '—', false],
    ['Disk %', sys.disk_percent ?? '—', false],
    ['Metric samples', (m.items||[]).length, false],
  ]);
}

async function route() {
  const hash = location.hash.replace(/^#/, '') || 'overview';
  const [page, id] = hash.split('/');
  const titles = {
    overview:'Overview', tasks:'Tasks', task:'Task detail', approvals:'Approvals',
    handoffs:'Handoffs', agents:'Agents', nodes:'Nodes', intelligence:'Intelligence',
    plans:'Plans', tools:'Tools', eval:'Eval', ops:'Ops', metrics:'Metrics',
  };
  pageTitle.textContent = titles[page] || (page.charAt(0).toUpperCase() + page.slice(1));
  document.querySelectorAll('.sidebar nav a, .bottom-nav a').forEach(a => {
    const p = a.dataset.page;
    const active = p === page || (page === 'task' && p === 'tasks') || (page === 'metrics' && !['overview','tasks','ops','approvals'].includes(page) && p === 'metrics');
    a.classList.toggle('active', a.dataset.page === page || (page === 'task' && a.dataset.page === 'tasks'));
  });
  closeNav();
  try {
    if (page === 'overview') await renderOverview();
    else if (page === 'tasks') await renderTasks();
    else if (page === 'task' && id) await renderTask(id);
    else if (page === 'approvals') await renderApprovals();
    else if (page === 'handoffs') await renderHandoffs();
    else if (page === 'agents') await renderAgents();
    else if (page === 'nodes') await renderNodes();
    else if (page === 'intelligence') await renderIntelligence();
    else if (page === 'plans') await renderPlans();
    else if (page === 'tools') await renderTools();
    else if (page === 'eval') await renderEval();
    else if (page === 'ops') await renderOps();
    else if (page === 'metrics') await renderMetrics();
    else content.innerHTML = '<p class="muted">Unknown page</p>';
  } catch (e) {
    if (e.message !== 'auth') content.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  }
}

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const t = token();
  const url = `${proto}://${location.host}/ws` + (t ? `?token=${encodeURIComponent(t)}` : '');
  const ws = new WebSocket(url);
  ws.onopen = () => {
    wsState.textContent = 'ws: live';
    wsState.className = 'pill ok';
    liveBanner.textContent = 'Live updates connected';
  };
  ws.onclose = () => {
    wsState.textContent = 'ws: down';
    wsState.className = 'pill bad';
    liveBanner.textContent = 'Reconnecting…';
    setTimeout(connectWs, 3000);
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      liveBanner.textContent = `${msg.type || 'event'} @ ${msg.timestamp || ''}`;
      pushLive(msg);
      const typ = String(msg.type||'');
      if (typ.startsWith('task.') || typ.startsWith('approval.') || typ.startsWith('ops.')) {
        const h = location.hash.replace(/^#/, '') || 'overview';
        if (h === 'overview' || h.startsWith('task') || h === 'approvals' || h === 'ops') route();
      }
    } catch {}
  };
}

document.getElementById('logout').onclick = async () => {
  try { await api('/api/v1/auth/logout', {method:'POST'}); } catch {}
  sessionStorage.removeItem('ab_token');
  location.href = '/login';
};

const navToggle = document.getElementById('nav-toggle');
const navClose = document.getElementById('nav-close');
const backdrop = document.getElementById('sidebar-backdrop');
if (navToggle) navToggle.onclick = openNav;
if (navClose) navClose.onclick = closeNav;
if (backdrop) backdrop.onclick = closeNav;
document.querySelectorAll('#main-nav a').forEach(a => a.addEventListener('click', closeNav));

window.addEventListener('hashchange', route);
route();
connectWs();
setInterval(() => {
  const h = location.hash || '#overview';
  if (h === '#overview' || h === '') route();
}, 15000);
