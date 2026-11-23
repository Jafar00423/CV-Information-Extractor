/**
 * CV Information Extractor – Frontend Logic
 * ==========================================
 * Pure Vanilla JavaScript (no framework).
 * Handles: file staging, upload, extraction, rendering, filtering,
 *          analytics, detail modal, JSON/CSV export, and toast notifications.
 */

'use strict';

// ─────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────

/** @type {File[]} Files staged for upload */
let stagedFiles = [];

/** @type {Object[]} All extraction results */
let allResults = [];

/** @type {Object[]} Filtered subset currently shown */
let filteredResults = [];

/** Currently open result index for modal */
let activeModalIndex = null;

const API_BASE = '';  // Same origin; change to 'http://localhost:8000' if needed

// ─────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  initDropZone();
  initFileInput();
});

// ─────────────────────────────────────────────
// SECTION NAVIGATION
// ─────────────────────────────────────────────

/**
 * Show a named section and update nav button state.
 * @param {'upload'|'results'|'analytics'} name
 */
function showSection(name) {
  ['upload', 'results', 'analytics'].forEach(s => {
    document.getElementById(`section-${s}`).classList.toggle('hidden', s !== name);
    const btn = document.getElementById(`nav-${s}`);
    if (btn) btn.classList.toggle('active', s === name);
  });
  if (name === 'analytics') renderAnalytics();
}

// ─────────────────────────────────────────────
// HEALTH CHECK
// ─────────────────────────────────────────────

async function checkHealth() {
  const dot  = document.getElementById('health-dot');
  const text = document.getElementById('health-text');
  dot.className = 'w-2 h-2 rounded-full inline-block loading';
  text.textContent = 'Connecting…';

  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) throw new Error('Non-2xx');
    const data = await res.json();
    dot.className = 'w-2 h-2 rounded-full inline-block ok';
    const methods = Object.entries(data.capabilities)
      .filter(([, v]) => v).map(([k]) => k.replace(/_/g, ' ')).join(', ');
    text.textContent = `API ready · ${methods}`;
  } catch {
    dot.className = 'w-2 h-2 rounded-full inline-block error';
    text.textContent = 'API offline';
  }
}

// ─────────────────────────────────────────────
// DROP ZONE & FILE INPUT
// ─────────────────────────────────────────────

function initDropZone() {
  const zone = document.getElementById('drop-zone');

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('dragover');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    addFiles([...e.dataTransfer.files]);
  });
  zone.addEventListener('click', e => {
    // Avoid double-trigger from inner span click
    if (e.target.closest('span[onclick]')) return;
    document.getElementById('file-input').click();
  });
}

function initFileInput() {
  document.getElementById('file-input').addEventListener('change', e => {
    addFiles([...e.target.files]);
    e.target.value = ''; // allow re-selecting same file
  });
}

/** Validate and add files to staging area. */
function addFiles(files) {
  const ALLOWED_EXT = ['.pdf', '.docx', '.jpg', '.jpeg', '.png'];
  const MAX_MB = 10;

  files.forEach(file => {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      showToast(`"${file.name}" – unsupported format.`, 'error');
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      showToast(`"${file.name}" exceeds ${MAX_MB} MB limit.`, 'error');
      return;
    }
    // Avoid duplicate filenames
    if (stagedFiles.some(f => f.name === file.name)) {
      showToast(`"${file.name}" already staged.`, 'info');
      return;
    }
    stagedFiles.push(file);
  });

  renderStagedFiles();
}

/** Render the list of staged files with status indicators. */
function renderStagedFiles() {
  const container = document.getElementById('staged-files');
  const list      = document.getElementById('staged-list');
  const count     = document.getElementById('staged-count');
  const btnExtract = document.getElementById('btn-extract');
  const btnClear   = document.getElementById('btn-clear');

  if (stagedFiles.length === 0) {
    container.classList.add('hidden');
    btnExtract.disabled = true;
    btnClear.classList.add('hidden');
    return;
  }

  container.classList.remove('hidden');
  btnExtract.disabled = false;
  btnClear.classList.remove('hidden');
  count.textContent = `(${stagedFiles.length})`;

  list.innerHTML = stagedFiles.map((file, i) => {
    const ext = file.name.slice(file.name.lastIndexOf('.')+1).toLowerCase();
    const iconClass = ext === 'pdf' ? 'pdf' : (ext === 'docx' ? 'docx' : 'img');
    const sizeLabel = (file.size / 1024 < 1024)
      ? `${(file.size / 1024).toFixed(1)} KB`
      : `${(file.size / (1024*1024)).toFixed(1)} MB`;

    return `
      <li class="staged-item" id="staged-item-${i}">
        <div class="file-icon ${iconClass}">${ext.toUpperCase()}</div>
        <div class="flex-1 min-w-0">
          <p class="font-medium text-gray-800 truncate text-sm">${escHtml(file.name)}</p>
          <p class="text-xs text-gray-400">${sizeLabel}</p>
        </div>
        <span class="status-dot pending" id="dot-${i}"></span>
        <button class="remove-btn" onclick="removeFile(${i})" title="Remove">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </li>`;
  }).join('');
}

function removeFile(index) {
  stagedFiles.splice(index, 1);
  renderStagedFiles();
}

function clearFiles() {
  stagedFiles = [];
  renderStagedFiles();
  document.getElementById('error-container').classList.add('hidden');
}

// ─────────────────────────────────────────────
// EXTRACTION
// ─────────────────────────────────────────────

async function startExtraction() {
  if (stagedFiles.length === 0) return;

  const btnExtract  = document.getElementById('btn-extract');
  const btnClear    = document.getElementById('btn-clear');
  const progressCon = document.getElementById('progress-container');
  const progressBar = document.getElementById('progress-bar');
  const progressLbl = document.getElementById('progress-label');
  const progressCnt = document.getElementById('progress-count');
  const errCon      = document.getElementById('error-container');

  // Disable controls
  btnExtract.disabled = true;
  btnClear.classList.add('hidden');
  progressCon.classList.remove('hidden');
  errCon.classList.add('hidden');
  errCon.innerHTML = '';

  // Mark all as loading
  stagedFiles.forEach((_, i) => setDotStatus(i, 'loading'));

  const formData = new FormData();
  stagedFiles.forEach(file => formData.append('files', file));

  progressLbl.textContent = `Processing ${stagedFiles.length} file(s)…`;
  progressCnt.textContent = `0 / ${stagedFiles.length}`;
  progressBar.style.width = '10%';

  // Simulate incremental progress during server processing
  let fakeProgress = 10;
  const progressTimer = setInterval(() => {
    fakeProgress = Math.min(fakeProgress + 5, 85);
    progressBar.style.width = fakeProgress + '%';
  }, 400);

  try {
    const res = await fetch(`${API_BASE}/api/extract`, {
      method: 'POST',
      body: formData,
    });

    clearInterval(progressTimer);

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Server error ${res.status}: ${errText}`);
    }

    const data = await res.json();

    // Complete progress bar
    progressBar.style.width = '100%';
    progressCnt.textContent = `${data.success} / ${stagedFiles.length}`;
    progressLbl.textContent = `Done! ${data.success} extracted, ${data.failed} failed.`;

    // Update dot statuses
    // We match by filename since API returns in-order results
    const successNames = new Set(
      data.results.map(r => r.extraction_metadata?.source_filename)
    );
    const errorNames = new Set(data.errors.map(e => e.filename));

    stagedFiles.forEach((file, i) => {
      if (successNames.has(file.name))  setDotStatus(i, 'success');
      else if (errorNames.has(file.name)) setDotStatus(i, 'error');
    });

    // Accumulate results
    allResults = [...allResults, ...data.results];

    // Render errors
    if (data.errors.length > 0) {
      errCon.classList.remove('hidden');
      errCon.innerHTML = data.errors.map(e => `
        <div class="error-alert mb-2">
          <svg class="w-4 h-4 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
          </svg>
          <div>
            <p class="font-medium">${escHtml(e.filename)}</p>
            <p class="text-xs mt-0.5 opacity-80">${escHtml(e.error)}</p>
          </div>
        </div>`).join('');
    }

    if (data.success > 0) {
      showToast(`${data.success} CV(s) extracted successfully!`, 'success');
      // Populate filter dropdowns and navigate to results
      buildFilterOptions();
      filterCandidates();
      setTimeout(() => showSection('results'), 600);
    } else {
      showToast('No CVs were successfully extracted.', 'error');
    }

  } catch (err) {
    clearInterval(progressTimer);
    progressBar.style.width = '0%';
    progressLbl.textContent = 'Extraction failed.';
    stagedFiles.forEach((_, i) => setDotStatus(i, 'error'));
    errCon.classList.remove('hidden');
    errCon.innerHTML = `<div class="error-alert">
      <svg class="w-4 h-4 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
      </svg>
      <div><p class="font-medium">Request failed</p><p class="text-xs mt-0.5 opacity-80">${escHtml(err.message)}</p></div>
    </div>`;
    showToast('Could not connect to extraction server.', 'error');
  } finally {
    btnExtract.disabled = false;
    btnClear.classList.remove('hidden');
  }
}

function setDotStatus(index, status) {
  const dot = document.getElementById(`dot-${index}`);
  if (dot) dot.className = `status-dot ${status}`;
}

// ─────────────────────────────────────────────
// FILTER & SEARCH
// ─────────────────────────────────────────────

/** Populate skill filter dropdown from all results. */
function buildFilterOptions() {
  const sel = document.getElementById('filter-skill');
  const allSkills = new Set();
  allResults.forEach(r => {
    (r.skills?.hard_skills || []).forEach(s => allSkills.add(s));
    (r.skills?.tools || []).forEach(s => allSkills.add(s));
  });
  const existing = new Set([...sel.options].map(o => o.value).filter(Boolean));
  [...allSkills].sort().forEach(skill => {
    if (!existing.has(skill)) {
      const opt = document.createElement('option');
      opt.value = skill;
      opt.textContent = skill;
      sel.appendChild(opt);
    }
  });
}

/** Compute approximate years of experience for a result. */
function computeExperienceYears(result) {
  const exps = result.work_experience || [];
  if (exps.length === 0) return 0;
  let total = 0;
  const now = new Date();
  exps.forEach(exp => {
    const start = exp.start_date ? new Date(exp.start_date + '-01') : null;
    const end   = exp.is_current ? now : (exp.end_date ? new Date(exp.end_date + '-01') : null);
    if (start && end && end >= start) {
      total += (end - start) / (1000 * 60 * 60 * 24 * 365.25);
    }
  });
  return Math.round(total * 10) / 10;
}

/** Filter and render candidates based on current input values. */
function filterCandidates() {
  const query     = (document.getElementById('search-input').value || '').toLowerCase().trim();
  const skillFilt = document.getElementById('filter-skill').value;
  const expFilt   = document.getElementById('filter-exp').value;

  filteredResults = allResults.filter(r => {
    const name    = (r.candidate_profile?.full_name || '').toLowerCase();
    const email   = (r.candidate_profile?.email || '').toLowerCase();
    const skills  = [...(r.skills?.hard_skills || []), ...(r.skills?.tools || [])].map(s => s.toLowerCase());
    const companies = (r.work_experience || []).map(e => (e.company || '').toLowerCase()).join(' ');

    // Text search
    if (query) {
      const haystack = `${name} ${email} ${skills.join(' ')} ${companies}`;
      if (!haystack.includes(query)) return false;
    }

    // Skill filter
    if (skillFilt) {
      const hasSkill = skills.some(s => s.toLowerCase() === skillFilt.toLowerCase());
      if (!hasSkill) return false;
    }

    // Experience filter
    if (expFilt) {
      const years = computeExperienceYears(r);
      if (expFilt === '0-2'  && years >= 2)  return false;
      if (expFilt === '2-5'  && (years < 2 || years >= 5)) return false;
      if (expFilt === '5+'   && years < 5)   return false;
    }

    return true;
  });

  renderResultsGrid();
}

// ─────────────────────────────────────────────
// RESULTS GRID RENDERING
// ─────────────────────────────────────────────

function renderResultsGrid() {
  const grid     = document.getElementById('results-grid');
  const noResult = document.getElementById('no-results');
  const countEl  = document.getElementById('results-count');

  countEl.textContent = `Showing ${filteredResults.length} of ${allResults.length} candidate(s)`;

  if (filteredResults.length === 0) {
    grid.innerHTML = '';
    noResult.classList.remove('hidden');
    return;
  }
  noResult.classList.add('hidden');

  grid.innerHTML = filteredResults.map((r, i) => buildResultCard(r, i)).join('');
}

/** Build the HTML string for one result card. */
function buildResultCard(result, index) {
  const p       = result.candidate_profile || {};
  const name    = p.full_name || 'Unknown Candidate';
  const email   = p.email || '—';
  const phone   = p.phone || '—';
  const location = p.location || '—';
  const initials = name.split(' ').slice(0, 2).map(w => w[0]?.toUpperCase() || '').join('');

  const skills  = [...(result.skills?.hard_skills || []), ...(result.skills?.tools || [])].slice(0, 5);
  const expYears = computeExperienceYears(result);
  const eduCount = (result.education || []).length;
  const expCount = (result.work_experience || []).length;
  const conf     = result.extraction_metadata?.confidence_notes || 'Low';
  const method   = result.extraction_metadata?.extraction_method || '—';
  const filename = result.extraction_metadata?.source_filename || '—';
  const totalSkills = (result.skills?.hard_skills?.length || 0) + (result.skills?.tools?.length || 0);

  const skillPills = skills.map(s => `<span class="skill-pill">${escHtml(s)}</span>`).join('');
  const moreSkills = totalSkills > 5 ? `<span class="skill-pill bg-gray-100 text-gray-500">+${totalSkills - 5}</span>` : '';

  return `
    <div class="result-card" onclick="openModal(${index})">
      <!-- Card header -->
      <div class="flex items-start gap-3 mb-4">
        <div class="candidate-avatar">${escHtml(initials || '?')}</div>
        <div class="flex-1 min-w-0">
          <h3 class="font-semibold text-gray-900 truncate text-sm">${escHtml(name)}</h3>
          <p class="text-xs text-gray-500 truncate">${escHtml(email)}</p>
          <p class="text-xs text-gray-400 truncate">${escHtml(location)}</p>
        </div>
        <span class="confidence-badge ${escHtml(conf)}">${escHtml(conf)}</span>
      </div>

      <!-- Stats row -->
      <div class="grid grid-cols-3 gap-2 mb-4">
        <div class="bg-indigo-50 rounded-xl p-2.5 text-center">
          <p class="text-lg font-bold text-primary">${expYears > 0 ? expYears + 'y' : '—'}</p>
          <p class="text-xs text-gray-500">Experience</p>
        </div>
        <div class="bg-purple-50 rounded-xl p-2.5 text-center">
          <p class="text-lg font-bold text-secondary">${expCount}</p>
          <p class="text-xs text-gray-500">Jobs</p>
        </div>
        <div class="bg-green-50 rounded-xl p-2.5 text-center">
          <p class="text-lg font-bold text-success">${eduCount}</p>
          <p class="text-xs text-gray-500">Education</p>
        </div>
      </div>

      <!-- Skills -->
      ${skills.length > 0 ? `
        <div class="flex flex-wrap gap-1.5 mb-3">
          ${skillPills}${moreSkills}
        </div>` : '<p class="text-xs text-gray-400 mb-3">No skills detected.</p>'
      }

      <!-- Footer -->
      <div class="flex items-center justify-between pt-3 border-t border-gray-100">
        <span class="text-xs text-gray-400 truncate max-w-[180px]" title="${escHtml(filename)}">${escHtml(filename)}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 uppercase tracking-wide">${escHtml(method)}</span>
      </div>
    </div>`;
}

// ─────────────────────────────────────────────
// MODAL
// ─────────────────────────────────────────────

function openModal(index) {
  activeModalIndex = index;
  const result = filteredResults[index];
  const p = result.candidate_profile || {};

  document.getElementById('modal-name').textContent =
    p.full_name || 'Unknown Candidate';
  document.getElementById('modal-meta').textContent =
    [p.email, p.phone, p.location].filter(Boolean).join(' · ') || '—';

  // Reset to profile tab
  switchTab('profile');

  document.getElementById('detail-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('detail-modal').classList.add('hidden');
  document.body.style.overflow = '';
  activeModalIndex = null;
}

// Close modal on backdrop click
document.addEventListener('click', e => {
  if (e.target.id === 'detail-modal') closeModal();
});

function switchTab(tab) {
  document.querySelectorAll('.modal-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  if (activeModalIndex === null) return;
  const result = filteredResults[activeModalIndex];
  document.getElementById('modal-content').innerHTML = buildTabContent(tab, result);
}

function buildTabContent(tab, result) {
  switch (tab) {
    case 'profile':   return buildProfileTab(result);
    case 'education': return buildEducationTab(result);
    case 'experience':return buildExperienceTab(result);
    case 'skills':    return buildSkillsTab(result);
    case 'meta':      return buildMetaTab(result);
    default:          return '';
  }
}

function buildProfileTab(result) {
  const p = result.candidate_profile || {};
  const rows = [
    ['Full Name',   p.full_name],
    ['Email',       p.email ? `<a href="mailto:${escHtml(p.email)}">${escHtml(p.email)}</a>` : null],
    ['Phone',       p.phone],
    ['Location',    p.location],
    ['LinkedIn',    p.linkedin ? `<a href="${escHtml(p.linkedin)}" target="_blank" rel="noopener">${escHtml(p.linkedin)}</a>` : null],
    ['GitHub',      p.github   ? `<a href="${escHtml(p.github)}"   target="_blank" rel="noopener">${escHtml(p.github)}</a>`   : null],
    ['Portfolio',   p.portfolio? `<a href="${escHtml(p.portfolio)}" target="_blank" rel="noopener">${escHtml(p.portfolio)}</a>`: null],
  ];
  const infoRows = rows.map(([label, val]) => `
    <div class="info-row">
      <span class="info-label">${label}</span>
      <span class="info-value">${val || '<span class="text-gray-300">—</span>'}</span>
    </div>`).join('');

  const summary = p.profile_summary
    ? `<div class="mt-4">
         <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Profile Summary</p>
         <p class="text-sm text-gray-700 leading-relaxed">${escHtml(p.profile_summary)}</p>
       </div>`
    : '';

  return `<div>${infoRows}${summary}</div>`;
}

function buildEducationTab(result) {
  const edus = result.education || [];
  if (edus.length === 0) return '<p class="text-sm text-gray-400">No education data found.</p>';
  return edus.map(e => `
    <div class="section-block">
      <h4>${escHtml(e.institution || '—')}</h4>
      <p><strong>${escHtml(e.degree || '—')}</strong>${e.field_of_study ? ' · ' + escHtml(e.field_of_study) : ''}</p>
      <p class="text-gray-400 text-xs">${e.start_date || '?'} → ${e.end_date || 'Present'}</p>
      ${e.gpa ? `<p class="text-xs mt-1">GPA: <strong>${e.gpa}</strong></p>` : ''}
    </div>`).join('');
}

function buildExperienceTab(result) {
  const exps = result.work_experience || [];
  if (exps.length === 0) return '<p class="text-sm text-gray-400">No experience data found.</p>';
  return exps.map(e => {
    const dateStr = `${e.start_date || '?'} → ${e.is_current ? 'Present' : (e.end_date || '?')}`;
    const bullets = (e.responsibilities || []).map(r => `<li>${escHtml(r)}</li>`).join('');
    return `
      <div class="section-block">
        <h4>${escHtml(e.job_title || '—')}</h4>
        <p class="text-primary font-medium text-xs">${escHtml(e.company || '—')}${e.location ? ' · ' + escHtml(e.location) : ''}</p>
        <p class="text-gray-400 text-xs mt-0.5">${dateStr}${e.is_current ? ' <span class="text-green-600 font-semibold">(Current)</span>' : ''}</p>
        ${bullets ? `<ul class="mt-2">${bullets}</ul>` : ''}
      </div>`;
  }).join('');
}

function buildSkillsTab(result) {
  const s = result.skills || {};
  const hardSkills = s.hard_skills || [];
  const tools      = s.tools || [];
  const languages  = s.languages || [];

  const renderPills = arr => arr.map(sk => `<span class="skill-pill">${escHtml(sk)}</span>`).join('');

  const hardHtml = hardSkills.length
    ? `<div class="mb-4">
         <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Technical / Hard Skills</p>
         <div class="flex flex-wrap gap-1.5">${renderPills(hardSkills)}</div>
       </div>` : '';

  const toolsHtml = tools.length
    ? `<div class="mb-4">
         <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Tools &amp; Software</p>
         <div class="flex flex-wrap gap-1.5">${renderPills(tools)}</div>
       </div>` : '';

  const langsHtml = languages.length
    ? `<div class="mb-4">
         <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Languages</p>
         ${languages.map(l => `
           <div class="info-row">
             <span class="info-label">${escHtml(l.language || '—')}</span>
             <span class="info-value">${escHtml(l.proficiency || '—')}</span>
           </div>`).join('')}
       </div>` : '';

  // Certifications
  const certs = result.certifications || [];
  const certsHtml = certs.length
    ? `<div class="mb-2">
         <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Certifications</p>
         ${certs.map(c => `
           <div class="section-block py-2 px-3">
             <p class="font-medium text-sm">${escHtml(c.name || '—')}</p>
             ${c.issuer ? `<p class="text-xs text-gray-400">${escHtml(c.issuer)}</p>` : ''}
             ${c.issued_year ? `<p class="text-xs text-gray-400">${escHtml(c.issued_year)}</p>` : ''}
           </div>`).join('')}
       </div>` : '';

  if (!hardHtml && !toolsHtml && !langsHtml && !certsHtml) {
    return '<p class="text-sm text-gray-400">No skills or certifications data found.</p>';
  }
  return hardHtml + toolsHtml + langsHtml + certsHtml;
}

function buildMetaTab(result) {
  const m = result.extraction_metadata || {};
  const warnings = m.warnings || [];

  const rows = [
    ['Source File',   m.source_filename],
    ['Method',        m.extraction_method],
    ['Confidence',    m.confidence_notes],
    ['Extracted At',  m.extracted_at ? new Date(m.extracted_at).toLocaleString() : null],
    ['Processing Time', m.processing_time_seconds != null ? m.processing_time_seconds + 's' : null],
  ];

  const infoRows = rows.map(([label, val]) => `
    <div class="info-row">
      <span class="info-label">${label}</span>
      <span class="info-value">${val ? escHtml(String(val)) : '<span class="text-gray-300">—</span>'}</span>
    </div>`).join('');

  const warningsHtml = warnings.length
    ? `<div class="mt-4">
         <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Warnings</p>
         <div class="flex flex-wrap gap-2">
           ${warnings.map(w => `<span class="warning-chip">⚠ ${escHtml(w)}</span>`).join('')}
         </div>
       </div>` : '';

  return `<div>${infoRows}${warningsHtml}</div>`;
}

// ─────────────────────────────────────────────
// ANALYTICS
// ─────────────────────────────────────────────

function renderAnalytics() {
  const total = allResults.length;
  document.getElementById('kpi-total').textContent = total;

  if (total === 0) {
    document.getElementById('kpi-success').textContent = '—';
    document.getElementById('kpi-avg-exp').textContent = '—';
    document.getElementById('kpi-skills').textContent  = '0';
    document.getElementById('skills-chart').innerHTML  = '<p class="text-sm text-gray-400">No data yet.</p>';
    document.getElementById('methods-chart').innerHTML = '<p class="text-sm text-gray-400">No data yet.</p>';
    return;
  }

  // Success rate: results with at least a name or email
  const successCount = allResults.filter(r =>
    r.candidate_profile?.full_name || r.candidate_profile?.email
  ).length;
  document.getElementById('kpi-success').textContent =
    `${Math.round((successCount / total) * 100)}%`;

  // Avg experience
  const totalExp = allResults.reduce((sum, r) => sum + computeExperienceYears(r), 0);
  const avgExp = totalExp / total;
  document.getElementById('kpi-avg-exp').textContent =
    avgExp > 0 ? `${avgExp.toFixed(1)} yrs` : '—';

  // Unique skills
  const allSkills = new Map();
  allResults.forEach(r => {
    [...(r.skills?.hard_skills || []), ...(r.skills?.tools || [])].forEach(s => {
      allSkills.set(s, (allSkills.get(s) || 0) + 1);
    });
  });
  document.getElementById('kpi-skills').textContent = allSkills.size;

  // Top 10 skills bar chart
  const sortedSkills = [...allSkills.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  const maxCount = sortedSkills[0]?.[1] || 1;
  document.getElementById('skills-chart').innerHTML = sortedSkills.map(([skill, count]) => `
    <div class="chart-bar-row">
      <span class="chart-bar-label" title="${escHtml(skill)}">${escHtml(skill)}</span>
      <div class="chart-bar-track">
        <div class="chart-bar-fill" style="width:${Math.round((count/maxCount)*100)}%"></div>
      </div>
      <span class="chart-bar-count">${count}</span>
    </div>`).join('');

  // Extraction methods
  const methods = {};
  const confidences = {};
  allResults.forEach(r => {
    const m = r.extraction_metadata?.extraction_method || 'unknown';
    const c = r.extraction_metadata?.confidence_notes  || 'Low';
    methods[m]     = (methods[m]     || 0) + 1;
    confidences[c] = (confidences[c] || 0) + 1;
  });

  const methodColors = { text: '#4F46E5', ocr: '#7C3AED', hybrid: '#10B981', unknown: '#9CA3AF' };
  const confColors   = { High: '#10B981', Medium: '#F59E0B', Low: '#EF4444' };

  const methodRows = Object.entries(methods).map(([m, count]) => `
    <div class="chart-bar-row">
      <span class="chart-bar-label capitalize">${escHtml(m)}</span>
      <div class="chart-bar-track">
        <div class="chart-bar-fill" style="width:${Math.round((count/total)*100)}%;background:${methodColors[m]||'#4F46E5'}"></div>
      </div>
      <span class="chart-bar-count">${count}</span>
    </div>`).join('');

  const confRows = Object.entries(confidences).map(([c, count]) => `
    <div class="chart-bar-row mt-1">
      <span class="chart-bar-label"><span class="confidence-badge ${escHtml(c)}">${escHtml(c)}</span></span>
      <div class="chart-bar-track">
        <div class="chart-bar-fill" style="width:${Math.round((count/total)*100)}%;background:${confColors[c]||'#9CA3AF'}"></div>
      </div>
      <span class="chart-bar-count">${count}</span>
    </div>`).join('');

  document.getElementById('methods-chart').innerHTML = `
    <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">By Method</p>
    ${methodRows}
    <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4 mb-2">By Confidence</p>
    ${confRows}`;
}

// ─────────────────────────────────────────────
// EXPORT
// ─────────────────────────────────────────────

function exportJSON() {
  if (allResults.length === 0) { showToast('No data to export.', 'info'); return; }
  downloadFile(
    JSON.stringify(allResults, null, 2),
    `cv_extraction_${timestamp()}.json`,
    'application/json'
  );
  showToast('JSON exported!', 'success');
}

function exportSingleJSON() {
  if (activeModalIndex === null) return;
  const result = filteredResults[activeModalIndex];
  const filename = result.extraction_metadata?.source_filename?.replace(/\.[^.]+$/, '') || 'candidate';
  downloadFile(
    JSON.stringify(result, null, 2),
    `${filename}_${timestamp()}.json`,
    'application/json'
  );
  showToast('JSON exported!', 'success');
}

function exportCSV() {
  if (allResults.length === 0) { showToast('No data to export.', 'info'); return; }

  const headers = [
    'Full Name', 'Email', 'Phone', 'Location', 'LinkedIn', 'GitHub',
    'Experience (years)', 'Education Count', 'Hard Skills', 'Tools',
    'Certifications', 'Extraction Method', 'Confidence', 'Source File',
  ];

  const rows = allResults.map(r => {
    const p    = r.candidate_profile || {};
    const s    = r.skills || {};
    const meta = r.extraction_metadata || {};
    return [
      p.full_name       || '',
      p.email           || '',
      p.phone           || '',
      p.location        || '',
      p.linkedin        || '',
      p.github          || '',
      computeExperienceYears(r),
      (r.education || []).length,
      (s.hard_skills || []).join('; '),
      (s.tools       || []).join('; '),
      (r.certifications || []).map(c => c.name).join('; '),
      meta.extraction_method   || '',
      meta.confidence_notes    || '',
      meta.source_filename     || '',
    ].map(csvEsc);
  });

  const csv = [headers.map(csvEsc).join(','), ...rows.map(r => r.join(','))].join('\n');
  downloadFile(csv, `cv_extraction_${timestamp()}.csv`, 'text/csv;charset=utf-8;');
  showToast('CSV exported!', 'success');
}

/** Escape a value for CSV */
function csvEsc(val) {
  const str = String(val ?? '');
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function downloadFile(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}

// ─────────────────────────────────────────────
// TOAST NOTIFICATIONS
// ─────────────────────────────────────────────

let toastTimer = null;

/**
 * Show a toast notification.
 * @param {string} message
 * @param {'success'|'error'|'info'} type
 */
function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className   = `toast ${type}`;
  toast.classList.remove('hidden');

  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add('hidden'), 3500);
}

// ─────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────

/** Escape HTML special characters to prevent XSS. */
function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
