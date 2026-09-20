const content = document.getElementById('content');
const pageTitle = document.getElementById('page-title');
const liveBanner = document.getElementById('live-banner');
const wsState = document.getElementById('ws-state');

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
    try { const j = await r.json(); msg = (j.error && j.error.message) || msg; } catch {}
    throw new Error(msg);
  }
  if (r.status === 204) return null;
  return r.json();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function cards(items) {
  return `<div class="cards">${items.map(([label,value]) =>
    `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`).join('')}</div>`;
}

async function renderOverview() {
  const [h, s, w, intel] = await Promise.all([api('/api/v1/health'), api('/api/v1/status'), api('/api/v1/workers').catch(()=>({counts:{}})), api('/api/v1/intelligence/status').catch(()=>({}))]);
  content.innerHTML = cards([
    ['Version', h.version], ['Daemon', h.daemon], ['Database', h.database],
    ['Tasks running', s.tasks?.running ?? '—'], ['Tasks queued', s.tasks?.queued ?? '—'],
    ['Approvals', s.approvals?.pending ?? '—'], ['Handoffs', s.handoffs?.pending ?? '—'],
    ['Agents', s.agents?.active ?? '—'],
    ['Workers online', w.counts?.online ?? '—'],
    ['Intel chunks', intel.index?.chunks_total ?? '—'],
    ['Embed model', intel.embedding?.id ?? '—'],
    ['CPU %', Number(s.system?.cpu_percent ?? 0).toFixed(1)],
    ['RAM %', Number(s.system?.memory_percent ?? 0).toFixed(1)],
  ]);
}

async function renderTasks() {
  const data = await api('/api/v1/tasks?limit=50');
  const rows = (data.items||[]).map(t => `<tr>
    <td><a href="#task/${t.id}">${t.id}</a></td>
    <td>${escapeHtml(t.title||'')}</td><td>${t.status||''}</td>
    <td>${t.provider||''}</td><td>${t.priority??''}</td></tr>`).join('');
  content.innerHTML = `<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Provider</th><th>Pri</th></tr></thead><tbody>${rows||'<tr><td colspan=5>No tasks</td></tr>'}</tbody></table>`;
}

async function renderTask(id) {
  const [t, tl] = await Promise.all([api('/api/v1/tasks/'+id), api('/api/v1/tasks/'+id+'/timeline')]);
  const events = (tl.items||[]).map(e => `<li><span class="muted">${e.created_at||e.ts||''}</span> ${escapeHtml(e.message||e.kind||'')}</li>`).join('');
  content.innerHTML = `<div class="card" style="margin-bottom:1rem">
      <h3>${escapeHtml(t.title||id)}</h3>
      <p class="muted">${t.id} · ${t.status} · ${t.provider||'—'}</p>
      <div style="display:flex;gap:.5rem;margin-top:.75rem;flex-wrap:wrap">
        <button data-act="queue">Queue</button>
        <button class="secondary" data-act="pause">Pause</button>
        <button class="secondary" data-act="resume">Resume</button>
        <button class="danger" data-act="cancel">Cancel</button>
      </div></div>
    <h3>Timeline</h3>
    <ul class="timeline">${events||'<li class="muted">No events</li>'}</ul>`;
  content.querySelectorAll('button[data-act]').forEach(btn => {
    btn.onclick = async () => { await api(`/api/v1/tasks/${id}/${btn.dataset.act}`, {method:'POST'}); renderTask(id); };
  });
}

async function renderApprovals() {
  const data = await api('/api/v1/approvals?status=pending');
  const rows = (data.items||[]).map(a => `<tr>
    <td>${a.id}</td><td>${escapeHtml(a.action||a.gate||'')}</td><td>${a.task_id||''}</td><td>${a.status}</td>
    <td><button data-id="${a.id}" data-act="approve">Approve</button>
        <button class="danger" data-id="${a.id}" data-act="reject">Reject</button></td></tr>`).join('');
  content.innerHTML = `<table><thead><tr><th>ID</th><th>Action</th><th>Task</th><th>Status</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan=5>No pending approvals</td></tr>'}</tbody></table>`;
  content.querySelectorAll('button[data-act]').forEach(btn => {
    btn.onclick = async () => {
      await api(`/api/v1/approvals/${btn.dataset.id}/${btn.dataset.act}`, {method:'POST', body:{comment:'via dashboard'}});
      renderApprovals();
    };
  });
}

async function renderHandoffs() {
  const data = await api('/api/v1/handoffs?limit=50');
  const rows = (data.items||[]).map(h => `<tr>
    <td>${h.id}</td><td>${h.source_agent||h.from_agent||''}</td><td>${h.target_agent||h.to_agent||''}</td>
    <td>${h.task_id||''}</td><td>${h.status||''}</td></tr>`).join('');
  content.innerHTML = `<table><thead><tr><th>ID</th><th>From</th><th>To</th><th>Task</th><th>Status</th></tr></thead><tbody>${rows||'<tr><td colspan=5>No handoffs</td></tr>'}</tbody></table>`;
}

async function renderAgents() {
  const data = await api('/api/v1/agents');
  content.innerHTML = `<div class="cards">${(data.items||[]).map(a =>
    `<div class="card"><div class="label">${escapeHtml(a.name||a.id)}</div>
     <div class="value" style="font-size:1rem">${a.status||''}</div>
     <div class="muted">${a.provider||''} ${a.model||''}</div></div>`).join('')||'<p class="muted">No agents</p>'}</div>`;
}


async function renderNodes() {
  const data = await api('/api/v1/workers');
  const counts = data.counts || {};
  const rows = (data.items||[]).map(w => {
    const caps = w.capabilities || {};
    const capStr = [caps.docker&&'docker', caps.gpu&&'gpu', (caps.providers||[]).join(',')].filter(Boolean).join(' ');
    return `<tr>
      <td>${escapeHtml(w.name||w.id)}</td>
      <td>${escapeHtml(w.hostname||'')}</td>
      <td>${escapeHtml(w.tailscale_ip||'')}</td>
      <td><span class="pill ${w.status==='online'||w.status==='busy'?'ok':(w.status==='quarantined'?'bad':'')}">${w.status||''}</span></td>
      <td>${w.current_load??0}/${w.max_parallel_tasks??1}</td>
      <td class="muted">${escapeHtml(capStr||'—')}</td>
      <td>${escapeHtml(w.version||'')}</td>
      <td class="muted">${escapeHtml(w.last_heartbeat||'')}</td>
    </tr>`;
  }).join('');
  content.innerHTML = cards([
    ['Workers', counts.total ?? (data.items||[]).length],
    ['Online', counts.online ?? '—'],
    ['Offline', counts.offline ?? '—'],
    ['Quarantined', counts.quarantined ?? '—'],
  ]) + `<table style="margin-top:1rem"><thead><tr>
    <th>Name</th><th>Host</th><th>IP</th><th>Status</th><th>Tasks</th><th>Capabilities</th><th>Ver</th><th>Heartbeat</th>
  </tr></thead><tbody>${rows||'<tr><td colspan=8>No workers enrolled</td></tr>'}</tbody></table>`;
}


async function renderIntelligence() {
  const data = await api('/api/v1/intelligence/status');
  const idxs = (data.index?.indexes||[]).map(i => `<tr>
    <td>${escapeHtml(i.project_id||'')}</td>
    <td>${escapeHtml(i.status||'')}</td>
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
    ['Version', data.version||'—'],
    ['Embedding', data.embedding?.id||'—'],
    ['Vector backend', data.vector_store?.backend||'—'],
    ['Vectors', data.vector_store?.total??'—'],
    ['Chunks', data.index?.chunks_total??'—'],
    ['Memories', data.memories??'—'],
    ['Quality signals', data.quality?.total_signals??'—'],
  ]) + `<h3>Semantic indexes</h3>
  <table class="tbl"><thead><tr><th>Project</th><th>Status</th><th>Files</th><th>Chunks</th><th>Model</th><th>Updated</th></tr></thead>
  <tbody>${idxs||'<tr><td colspan=6>No indexes yet</td></tr>'}</tbody></table>
  <h3>Model registry</h3>
  <table class="tbl"><thead><tr><th>Provider</th><th>Model</th><th>Locality</th><th>Context</th></tr></thead>
  <tbody>${models||'<tr><td colspan=4>None</td></tr>'}</tbody></table>`;
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
    <td>${escapeHtml(g.status||'')}</td>
    <td>${escapeHtml(g.risk_profile||'')}</td>
    <td>${escapeHtml(g.updated_at||g.created_at||'')}</td>
  </tr>`).join('');
  const pRows = (plans.plans||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml(p.goal_id||'')}</td>
    <td>v${p.version??'—'}</td>
    <td>${escapeHtml(p.status||'')}</td>
    <td>${p.quality_score??'—'}</td>
    <td>${escapeHtml(p.workflow_template||'')}</td>
  </tr>`).join('');
  const wRows = (wfs.workflows||[]).map(w => `<tr>
    <td>${escapeHtml(w.name||'')}</td>
    <td>${escapeHtml((w.stages||[]).join(' → '))}</td>
    <td>${escapeHtml(w.description||'')}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Goals', (goals.goals||[]).length],
    ['Plans', (plans.plans||[]).length],
    ['Workflow templates', (wfs.workflows||[]).length],
  ]) + `<h3>Goals</h3>
  <table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Risk</th><th>Updated</th></tr></thead>
  <tbody>${gRows||'<tr><td colspan=5>No goals</td></tr>'}</tbody></table>
  <h3>Plans</h3>
  <table class="tbl"><thead><tr><th>ID</th><th>Goal</th><th>Ver</th><th>Status</th><th>Quality</th><th>Template</th></tr></thead>
  <tbody>${pRows||'<tr><td colspan=6>No plans</td></tr>'}</tbody></table>
  <h3>Workflows</h3>
  <table class="tbl"><thead><tr><th>Name</th><th>Stages</th><th>Description</th></tr></thead>
  <tbody>${wRows||'<tr><td colspan=3>No templates</td></tr>'}</tbody></table>`;
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
    <td>${escapeHtml(healthMap[t.id]||t.health_status||'')}</td>
    <td>${escapeHtml(t.risk_level||'')}</td>
    <td>${t.reliability_score??'—'}</td>
    <td>${escapeHtml(t.version||'')}</td>
  </tr>`).join('');
  const runRows = (runs.runs||[]).map(r => `<tr>
    <td>${escapeHtml(r.tool_id||'')}</td>
    <td>${escapeHtml(r.status||'')}</td>
    <td>${r.duration_ms??'—'}</td>
    <td>${escapeHtml(r.risk_level||'')}</td>
    <td>${escapeHtml(r.decision||'')}</td>
    <td>${escapeHtml(r.created_at||'')}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Tools', (tools.tools||[]).length],
    ['Healthy', (health.health||[]).filter(h=>h.status==='healthy').length],
    ['Recent runs', (runs.runs||[]).length],
  ]) + `<h3>Registry</h3>
  <table class="tbl"><thead><tr><th>Name</th><th>Category</th><th>Capabilities</th><th>Health</th><th>Risk</th><th>Reliability</th><th>Version</th></tr></thead>
  <tbody>${rows||'<tr><td colspan=7>No tools</td></tr>'}</tbody></table>
  <h3>Recent tool runs</h3>
  <table class="tbl"><thead><tr><th>Tool</th><th>Status</th><th>Duration</th><th>Risk</th><th>Decision</th><th>When</th></tr></thead>
  <tbody>${runRows||'<tr><td colspan=6>No runs</td></tr>'}</tbody></table>`;
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
    <td>${escapeHtml(r.status||'')}</td>
    <td>${r.score??'—'}</td>
    <td>${escapeHtml(r.gate_status||'')}</td>
    <td>${escapeHtml(r.created_at||'')}</td>
  </tr>`).join('');
  const pRows = (proposals.proposals||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml((p.target_type||'')+'/'+(p.target_id||''))}</td>
    <td>${escapeHtml(p.risk_level||'')}</td>
    <td>${escapeHtml(p.status||'')}</td>
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
    ['Suites', (suites.suites||[]).length],
    ['Runs', (runs.runs||[]).length],
    ['Proposals', (proposals.proposals||[]).length],
    ['Failure clusters', (failures.clusters||[]).length],
  ]) + `<h3>Suites</h3>
  <table class="tbl"><thead><tr><th>Suite</th><th>Ver</th><th>Cases</th><th>Description</th></tr></thead>
  <tbody>${sRows||'<tr><td colspan=4>No suites</td></tr>'}</tbody></table>
  <h3>Recent evaluation runs</h3>
  <table class="tbl"><thead><tr><th>Run</th><th>Suite</th><th>Status</th><th>Score</th><th>Gate</th><th>When</th></tr></thead>
  <tbody>${rRows||'<tr><td colspan=6>No runs</td></tr>'}</tbody></table>
  <h3>Baselines</h3>
  <table class="tbl"><thead><tr><th>Suite</th><th>Score</th><th>Pass rate</th><th>When</th></tr></thead>
  <tbody>${bRows||'<tr><td colspan=4>No baselines</td></tr>'}</tbody></table>
  <h3>Improvement proposals</h3>
  <table class="tbl"><thead><tr><th>ID</th><th>Target</th><th>Risk</th><th>Status</th><th>Title</th></tr></thead>
  <tbody>${pRows||'<tr><td colspan=5>No proposals</td></tr>'}</tbody></table>
  <h3>Failure mining</h3>
  <table class="tbl"><thead><tr><th>Signature</th><th>Count</th><th>Case</th><th>Sample</th></tr></thead>
  <tbody>${fRows||'<tr><td colspan=4>No failures</td></tr>'}</tbody></table>`;
}



async function renderOps() {
  const [st, scan, pbs, fc, drift, plans, rem] = await Promise.all([
    api('/api/v1/ops/status').catch(()=>({})),
    api('/api/v1/ops/scan').catch(()=>({proposals:[]})),
    api('/api/v1/ops/playbooks').catch(()=>({playbooks:[]})),
    api('/api/v1/ops/forecast').catch(()=>({})),
    api('/api/v1/ops/drift').catch(()=>({scopes:{}})),
    api('/api/v1/ops/plans').catch(()=>({plans:[]})),
    api('/api/v1/ops/remediations?limit=20').catch(()=>({actions:[]})),
  ]);
  const doc = st.doctor || {};
  const res = (fc.resources) || ((st.forecast||{}).resources) || {};
  const pbRows = (pbs.playbooks||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml(p.title||'')}</td>
    <td>${escapeHtml(p.risk_level||'')}</td>
    <td>${p.auto_eligible?'auto':'approval'}</td>
    <td>${escapeHtml(p.description||'')}</td>
  </tr>`).join('');
  const propRows = (scan.proposals||[]).map(p => `<tr>
    <td>${escapeHtml(p.playbook_id||'')}</td>
    <td>${escapeHtml(p.risk_level||'')}</td>
    <td>${p.auto?'yes':'no'}</td>
    <td>${escapeHtml(p.reason||'')}</td>
  </tr>`).join('');
  const remRows = (rem.actions||[]).map(a => `<tr>
    <td>${escapeHtml(a.id||'')}</td>
    <td>${escapeHtml(a.action_type||'')}</td>
    <td>${escapeHtml(a.risk_level||'')}</td>
    <td>${escapeHtml(a.status||'')}</td>
    <td>${escapeHtml(a.created_at||'')}</td>
  </tr>`).join('');
  const planRows = (plans.plans||[]).map(p => `<tr>
    <td>${escapeHtml(p.id||'')}</td>
    <td>${escapeHtml(p.title||'')}</td>
    <td>${escapeHtml(p.priority||'')}</td>
    <td>${escapeHtml(p.status||'')}</td>
    <td>${(p.actions||[]).length}</td>
  </tr>`).join('');
  const sigRows = (fc.signals||(st.forecast||{}).signals||[]).map(s => `<tr>
    <td>${escapeHtml(s.level||'')}</td>
    <td>${escapeHtml(s.code||'')}</td>
    <td>${escapeHtml(s.message||'')}</td>
  </tr>`).join('');
  content.innerHTML = cards([
    ['Doctor', doc.health||'—'],
    ['Forecast', fc.level||(st.forecast||{}).level||'—'],
    ['Drift', drift.drifted?'yes':'no'],
    ['Playbooks', (pbs.playbooks||[]).length],
    ['Disk %', res.disk_percent??'—'],
    ['DB MB', res.db_mb??'—'],
  ]) + `<h3>Forecast signals</h3>
  <table class="tbl"><thead><tr><th>Level</th><th>Code</th><th>Message</th></tr></thead>
  <tbody>${sigRows||'<tr><td colspan=3>None</td></tr>'}</tbody></table>
  <h3>Scan proposals</h3>
  <table class="tbl"><thead><tr><th>Playbook</th><th>Risk</th><th>Auto</th><th>Reason</th></tr></thead>
  <tbody>${propRows||'<tr><td colspan=4>No proposals</td></tr>'}</tbody></table>
  <h3>Playbooks</h3>
  <table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Risk</th><th>Mode</th><th>Description</th></tr></thead>
  <tbody>${pbRows||'<tr><td colspan=5>None</td></tr>'}</tbody></table>
  <h3>Recent remediations</h3>
  <table class="tbl"><thead><tr><th>ID</th><th>Action</th><th>Risk</th><th>Status</th><th>When</th></tr></thead>
  <tbody>${remRows||'<tr><td colspan=5>None</td></tr>'}</tbody></table>
  <h3>Maintenance plans</h3>
  <table class="tbl"><thead><tr><th>ID</th><th>Title</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead>
  <tbody>${planRows||'<tr><td colspan=5>None</td></tr>'}</tbody></table>`;
}

async function renderMetrics() {
  const m = await api('/api/v1/metrics');
  const sys = m.system || {};
  content.innerHTML = cards([
    ['WS connections', m.websocket_connections ?? 0],
    ['CPU %', sys.cpu_percent ?? '—'], ['RAM %', sys.memory_percent ?? '—'],
    ['Disk %', sys.disk_percent ?? '—'], ['Metric samples', (m.items||[]).length],
  ]);
}

async function route() {
  const hash = location.hash.replace(/^#/, '') || 'overview';
  const [page, id] = hash.split('/');
  pageTitle.textContent = page === 'task' ? 'Task detail' : page.charAt(0).toUpperCase() + page.slice(1);
  document.querySelectorAll('.sidebar nav a').forEach(a => a.classList.toggle('active', a.dataset.page === page));
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
  ws.onopen = () => { wsState.textContent = 'ws: live'; wsState.className = 'pill ok'; liveBanner.textContent = 'Live updates connected'; };
  ws.onclose = () => { wsState.textContent = 'ws: down'; wsState.className = 'pill bad'; liveBanner.textContent = 'Reconnecting…'; setTimeout(connectWs, 3000); };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      liveBanner.textContent = `${msg.type || 'event'} @ ${msg.timestamp || ''}`;
      if (String(msg.type||'').startsWith('task.') || String(msg.type||'').startsWith('approval.')) route();
    } catch {}
  };
}

document.getElementById('logout').onclick = async () => {
  try { await api('/api/v1/auth/logout', {method:'POST'}); } catch {}
  sessionStorage.removeItem('ab_token');
  location.href = '/login';
};
window.addEventListener('hashchange', route);
route();
connectWs();
setInterval(() => { const h = location.hash || '#overview'; if (h === '#overview' || h === '') route(); }, 15000);
