import { validateProject } from './project.mjs';

export const projectFileMaxBytes = 65536;
const draftKey = 'anicca.monk-factory.drafts.v1';
const fileVersion = 'ai-monk-factory.web-project.v1';
export function isLocalMode(token, hostname) {
  return ['127.0.0.1', 'localhost', '[::1]'].includes(hostname) && /^[A-Za-z0-9_-]{32,}$/.test(token) && token !== '__FACTORY_TOKEN__';
}
export function encodeProjectFile(project) {
  return JSON.stringify({ schema_version: fileVersion, project: validateProject(project) }, null, 2) + '\n';
}
export function decodeProjectFile(text) {
  if (typeof text !== "string" || new TextEncoder().encode(text).byteLength > projectFileMaxBytes) throw new Error('This project file is too large.');
  const value = JSON.parse(text);
  if (!value || Object.keys(value).sort().join(',') !== 'project,schema_version' || value.schema_version !== fileVersion) throw new Error('Unsupported project file format or version.');
  return validateProject(value.project);
}
export function readDrafts(storage) {
  const value = JSON.parse(storage.getItem(draftKey) ?? '[]');
  if (!Array.isArray(value) || value.length > 100) throw new Error('The stored drafts have an invalid format.');
  return value.map(project => validateProject(project));
}
export function saveDraft(storage, project) {
  const valid = validateProject(project);
  const rows = readDrafts(storage).filter(row => row.project_id !== valid.project_id);
  if (rows.length >= 100) throw new Error('This browser already holds 100 projects. Export a project before creating another.');
  rows.push(valid);
  storage.setItem(draftKey, JSON.stringify(rows));
  return valid;
}

async function startWorkspace() {
  const $ = id => document.getElementById(id);
  const form = $('project-form');
  const token = document.querySelector('meta[name="factory-token"]')?.content ?? '';
  const local = isLocalMode(token, location.hostname);
  const fields = ['project_id', 'language', 'avatar_id', 'voice_id', 'platform', 'integration_id', 'native_handle', 'product_name', 'product_url', 'brief', 'script', 'cta'];
  let projects = [];
  let selectedRun = null;
  let videoSource = null;
  let videoKey = null;
  let busy = false;
  let polling = false;
  function notice(message, error = false) {
    $('notice').textContent = message;
    $('notice').dataset.error = String(error);
    $('notice').hidden = !message;
  }
  async function api(path, body) {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers: { 'x-factory-token': token, ...(body === undefined ? {} : { 'content-type': 'application/json' }) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), cache: 'no-store' });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error ?? `The local workspace returned ${response.status}.`);
    return value;
  }
  function projectFromForm(ready = false) {
    return validateProject(Object.fromEntries(fields.map(name => [name, form.elements.namedItem(name).value])), { ready });
  }
  function fillProject(project) {
    for (const name of fields) form.elements.namedItem(name).value = project?.[name] ?? (name === 'language' ? 'en' : name === 'platform' ? 'tiktok' : '');
    $('project-picker').value = project?.project_id ?? '';
    $('save-status').textContent = project ? 'Saved project' : 'Unsaved draft';
  }
  function drawProjects(selected = '') {
    const options = [new Option('New project', ''), ...projects.map(project => new Option(project.product_name || project.project_id, project.project_id))];
    $('project-picker').replaceChildren(...options);
    $('project-picker').value = selected;
  }
  async function saveProject() {
    const project = projectFromForm();
    if (local) {
      const value = await api('/api/projects', { project });
      const saved = value.project;
      projects = projects.filter(row => row.project_id !== saved.project_id).concat(saved);
    } else {
      saveDraft(localStorage, project);
      projects = readDrafts(localStorage);
    }
    drawProjects(project.project_id);
    $('save-status').textContent = local ? 'Saved on this computer' : 'Saved in this browser';
    return project;
  }
  async function action(fn) {
    try { await fn(); } catch (error) { notice(error.message ?? 'The workspace could not complete this action.', true); }
  }
  function download(filename, text) {
    const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    const link = document.createElement('a');link.href = url;link.download = filename;link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function runLabel(state) { return String(state ?? 'unknown').replaceAll('_', ' '); }
  async function showRun(run) {
    selectedRun = run.run_id;
    $('run-detail').hidden = false;
    $('run-id').textContent = run.run_id;
    $('run-state').textContent = runLabel(run.state);
    $('run-exit').textContent = run.exit_code === null || run.exit_code === undefined ? 'Exit pending' : `Exit ${run.exit_code}`;
    $('run-summary').textContent = typeof run.summary === 'string' ? run.summary : run.summary ? JSON.stringify(run.summary, null, 2) : 'The run’s actual result will appear here.';
    $('run-receipts').textContent = JSON.stringify(run.tool_results ?? [], null, 2);
    if (run.artifact_url && videoKey !== `${run.run_id}:${run.artifact_url}`) {
      const response = await fetch(run.artifact_url, { headers: { 'x-factory-token': token }, cache: 'no-store' });
      if (!response.ok) throw new Error('The video could not be verified or loaded. The run receipts remain available.');
      if (videoSource) URL.revokeObjectURL(videoSource);
      videoSource = URL.createObjectURL(await response.blob());
      videoKey = `${run.run_id}:${run.artifact_url}`;
      $('run-video').src = videoSource;
      $('run-video').hidden = false;
    } else if (!run.artifact_url) {
      $('run-video').hidden = true;
      $('run-video').removeAttribute('src');
      if (videoSource) URL.revokeObjectURL(videoSource);
      videoSource = null;videoKey = null;
    }
  }
  async function refreshRuns() {
    if (!local || polling) return;
    polling = true;
    try {
      const { runs } = await api('/api/runs');
      if (runs.length) {
        const buttons = runs.map(run => {
          const button = document.createElement('button');button.type = 'button';button.className = 'run-row';
          const title = document.createElement('span');title.textContent = run.project_id;
          const subtitle = document.createElement('small');subtitle.textContent = `${run.mode} · ${new Date(run.created_at).toLocaleString()}`;title.append(subtitle);
          const state = document.createElement('span');state.className = 'run-row-state';state.textContent = runLabel(run.state);
          button.append(title, state);
          button.addEventListener('click', () => action(async () => { const value = await api(`/api/runs/${encodeURIComponent(run.run_id)}`);await showRun(value.run); }));
          return button;
        });
        $('run-list').replaceChildren(...buttons);
      }
      if (selectedRun) { const value = await api(`/api/runs/${encodeURIComponent(selectedRun)}`);await showRun(value.run); }
    } finally { polling = false; }
  }
  form.addEventListener('submit', event => { event.preventDefault();action(async () => { await saveProject();notice(local ? 'Project saved on this computer.' : 'Draft saved in this browser. Export it to move it into your local workspace.'); }); });
  form.addEventListener('input', () => { $('save-status').textContent = 'Unsaved changes'; });
  $('project-picker').addEventListener('change', () => fillProject(projects.find(project => project.project_id === $('project-picker').value)));
  $('new-project').addEventListener('click', () => { fillProject(null);form.elements.namedItem('project_id').focus(); });
  $('export-project').addEventListener('click', () => action(async () => { const project = projectFromForm();download(`${project.project_id}.monk.json`, encodeProjectFile(project));notice('Draft exported. Import this file into the local workspace.'); }));
  $('import-project').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', event => action(async () => {
    const file = event.target.files?.[0];if (!file) return;
    if (file.size > projectFileMaxBytes) throw new Error('This project file is too large.');
    const project = decodeProjectFile(await file.text());fillProject(project);await saveProject();notice('Project imported and saved.');event.target.value = '';
  }));
  $('setup-toggle').addEventListener('click', () => { const open = $('setup-instructions').hidden;$('setup-instructions').hidden = !open;$('setup-toggle').setAttribute('aria-expanded', String(open)); });
  $('copy-setup').addEventListener('click', () => action(async () => { await navigator.clipboard.writeText($('setup-command').textContent);notice('Setup commands copied.'); }));
  for (const button of document.querySelectorAll('[data-run-mode]')) button.addEventListener('click', () => action(async () => {
    if (!local || busy) return;
    projectFromForm(true);
    busy = true;document.querySelectorAll('[data-run-mode]').forEach(node => { node.disabled = true; });
    try {
      const project = await saveProject();
      const { run } = await api('/api/runs', { project_id: project.project_id, mode: button.dataset.runMode });
      await showRun(run);await refreshRuns();notice('Run started. You can leave the page open to follow the actual result.');
      $('runs-section').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    } finally { busy = false;document.querySelectorAll('[data-run-mode]').forEach(node => { node.disabled = false; }); }
  }));
  $('refresh-runs').addEventListener('click', () => action(refreshRuns));
  if (local) {
    $('mode-label').lastChild.textContent = ' Local runtime';
    $('setup-card').hidden = true;$('local-card').hidden = false;$('refresh-runs').hidden = false;
    await action(async () => { projects = (await api('/api/projects')).projects;drawProjects();await refreshRuns(); });
    const interval = setInterval(() => { if (!document.hidden) action(refreshRuns); }, 5000);
    window.addEventListener('pagehide', () => { clearInterval(interval);if (videoSource) URL.revokeObjectURL(videoSource); }, { once: true });
  } else {
    await action(async () => { projects = readDrafts(localStorage);drawProjects(); });
  }
}

if (typeof document !== 'undefined') startWorkspace().catch(() => {
  const notice = document.getElementById('notice');notice.hidden = false;notice.dataset.error = 'true';notice.textContent = 'The workspace could not start. Your saved projects have not been changed.';
});
