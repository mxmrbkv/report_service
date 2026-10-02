const API = '/api/reports';
let currentPage = 1;
let totalPages = 1;
let selectedFile = null;
let authEnabled = false;
let authenticated = false;
let userRoles = [];

// --- DOM Elements ---
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileName = document.getElementById('fileName');
const uploadBtn = document.getElementById('uploadBtn');
const uploadCard = document.getElementById('uploadCard');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const alertEl = document.getElementById('alert');
const reportsBody = document.getElementById('reportsBody');
const pagination = document.getElementById('pagination');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const pageInfo = document.getElementById('pageInfo');
const loginOverlay = document.getElementById('loginOverlay');
const loginBtn = document.getElementById('loginBtn');
const userBadge = document.getElementById('userBadge');
const userAvatar = document.getElementById('userAvatar');
const userName = document.getElementById('userName');
const logoutBtn = document.getElementById('logoutBtn');
const rolePill = document.getElementById('rolePill');
const reportsMeta = document.getElementById('reportsMeta');
const themeToggle = document.getElementById('themeToggle');

// --- Role Helpers ---
const ROLE_LEVELS = { viewer: 0, reporter: 1, admin: 2 };
function topRole(roles) {
    if (!roles || !roles.length) return 'viewer';
    return roles.reduce((a, b) => (ROLE_LEVELS[b] > ROLE_LEVELS[a] ? b : a), roles[0]);
}
function hasRole(roles, min) {
    const levels = (roles || []).map(r => ROLE_LEVELS[r] ?? -1);
    return Math.max(...levels, -1) >= (ROLE_LEVELS[min] ?? 99);
}

// --- Auth Handling ---
async function checkAuth() {
    try {
        const resp = await fetch('/auth/me');
        const data = await resp.json();
        authEnabled = data.auth_enabled;
        authenticated = data.authenticated;

        if (authEnabled && !authenticated) {
            showLoginOverlay();
            return false;
        }

        hideLoginOverlay();
        if (data.user) {
            showUserBadge(data.user);
            userRoles = data.user.roles || [];
            applyRoleVisibility();
        }
        return true;
    } catch {
        hideLoginOverlay();
        return true;
    }
}

function applyRoleVisibility() {
    if (uploadCard) {
        uploadCard.style.display = hasRole(userRoles, 'reporter') ? '' : 'none';
    }
    const role = topRole(userRoles);
    if (rolePill) {
        rolePill.textContent = role;
        rolePill.style.display = authEnabled ? 'inline-flex' : 'none';
    }
}

function showLoginOverlay() { 
    if (loginOverlay) loginOverlay.classList.add('show'); 
}
function hideLoginOverlay() { 
    if (loginOverlay) loginOverlay.classList.remove('show'); 
}

function showUserBadge(user) {
    if (!userBadge) return;
    userBadge.style.display = 'flex';
    if (logoutBtn) logoutBtn.style.display = 'inline-flex';
    if (userName) userName.textContent = user.name || user.email || 'User';
    const initials = (user.name || user.email || '?')
        .split(/\s+/)
        .map(w => w[0])
        .slice(0, 2)
        .join('')
        .toUpperCase();
    if (userAvatar) userAvatar.textContent = initials;
}

if (loginBtn) {
    loginBtn.addEventListener('click', () => { window.location.href = '/auth/login'; });
}
if (logoutBtn) {
    logoutBtn.addEventListener('click', () => { window.location.href = '/auth/logout'; });
}

function handleUnauthorized() {
    if (authEnabled) { 
        showLoginOverlay(); 
        return true; 
    }
    return false;
}

// --- Drag & Drop Zone ---
if (dropZone && fileInput) {
    dropZone.addEventListener('dragover', (e) => { 
        e.preventDefault(); 
        dropZone.classList.add('dragover'); 
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFileSelect(e.target.files[0]);
    });
}

function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith('.zip')) {
        showAlert('Ожидается файл с расширением .zip', 'error');
        return;
    }
    selectedFile = file;
    fileName.innerHTML = '';
    const ico = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    ico.setAttribute('viewBox', '0 0 24 24');
    ico.setAttribute('fill', 'none');
    ico.setAttribute('stroke', 'currentColor');
    ico.setAttribute('stroke-width', '2');
    ico.setAttribute('stroke-linecap', 'round');
    ico.setAttribute('stroke-linejoin', 'round');
    ico.style.width = '14px';
    ico.style.height = '14px';
    ico.innerHTML = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>';
    fileName.appendChild(ico);
    fileName.append(` ${file.name} · ${formatSize(file.size)}`);
    fileName.style.display = 'inline-flex';
    uploadBtn.disabled = false;
    hideAlert();
}

// --- Upload Handler ---
if (uploadBtn) {
    uploadBtn.addEventListener('click', async () => {
        if (!selectedFile) return;
        uploadBtn.disabled = true;
        progressBar.style.display = 'flex';
        progressText.textContent = 'Обработка архива и генерация Allure-отчёта...';

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('project_name', document.getElementById('projectName').value || 'default');

        try {
            const resp = await fetch(API, { method: 'POST', body: formData });
            if (resp.status === 401) { handleUnauthorized(); return; }
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || 'Ошибка загрузки');
            const verb = data.uploads_count > 1 ? 'обновлён' : 'создан';
            showAlert(
                `Проект «${escapeHtml(data.project)}» ${verb} — результатов: ${data.results_count}. ` +
                `<a href="${data.url}" target="_blank">Открыть отчёт →</a>`,
                'success'
            );
            selectedFile = null;
            fileName.style.display = 'none';
            fileName.textContent = '';
            uploadBtn.disabled = true;
            fileInput.value = '';
            loadReports(currentPage);
        } catch (err) {
            showAlert(err.message, 'error');
        } finally {
            progressBar.style.display = 'none';
            uploadBtn.disabled = false;
        }
    });
}

// --- Reports Listing ---
async function loadReports(page) {
    currentPage = page;
    try {
        const resp = await fetch(`${API}?page=${page}&page_size=20`);
        if (resp.status === 401) { handleUnauthorized(); return; }
        const data = await resp.json();
        totalPages = Math.ceil(data.total / data.page_size) || 1;
        if (reportsMeta) {
            reportsMeta.textContent = data.total ? `${data.total} проектов` : '';
        }

        if (data.items.length === 0) {
            reportsBody.innerHTML = `
                <div class="empty-state">
                    <div class="ico">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/>
                        </svg>
                    </div>
                    <div class="t">Нет загруженных отчетов</div>
                    <div class="s">Загрузите ZIP-архив с результатами allure, чтобы создать первый отчет</div>
                </div>`;
            pagination.style.display = 'none';
            return;
        }

        const canDelete = hasRole(userRoles, 'admin');
        reportsBody.innerHTML = data.items.map(r => `
            <div class="table-row">
                <div class="col col-name">
                    <div class="report-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                    </div>
                    <div class="report-meta-text">
                        <span class="report-title">${escapeHtml(r.project)}</span>
                        <span class="report-sub">${formatSize(r.size_bytes)} · ${r.uploads_count} загр.</span>
                    </div>
                </div>
                <div class="col col-status">
                    <span class="status-pill status-ready">
                        <span class="status-dot"></span>
                        Готов (${r.results_count})
                    </span>
                </div>
                <div class="col col-date">
                    <span class="date-text">${formatDate(r.updated_at)}</span>
                </div>
                <div class="col col-actions">
                    <a href="${r.url}" target="_blank" class="btn btn-sm btn-open">
                        Открыть
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                            <polyline points="15 3 21 3 21 9"/>
                            <line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                    </a>
                    ${canDelete ? `
                        <button class="btn btn-sm btn-danger icon-only" title="Удалить проект" onclick="deleteReport('${escapeHtml(r.project)}')">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');

        pagination.style.display = 'flex';
        prevBtn.disabled = page <= 1;
        nextBtn.disabled = page >= totalPages;
        pageInfo.textContent = `${page} / ${totalPages}`;
    } catch (err) {
        reportsBody.innerHTML = `
            <div class="empty-state">
                <div class="t" style="color: var(--danger)">Ошибка загрузки списка: ${escapeHtml(err.message)}</div>
            </div>`;
    }
}

async function deleteReport(project) {
    if (!confirm(`Удалить проект «${project}» со всеми отчетами и результатами?`)) return;
    try {
        const resp = await fetch(`${API}/${encodeURIComponent(project)}`, { method: 'DELETE' });
        if (resp.status === 401) { handleUnauthorized(); return; }
        if (!resp.ok) { 
            const e = await resp.json(); 
            throw new Error(e.detail || 'Ошибка при удалении'); 
        }
        loadReports(currentPage);
    } catch (err) {
        alert(`Ошибка: ${err.message}`);
    }
}

// --- Pagination Controls ---
if (prevBtn) {
    prevBtn.addEventListener('click', () => { if (currentPage > 1) loadReports(currentPage - 1); });
}
if (nextBtn) {
    nextBtn.addEventListener('click', () => { if (currentPage < totalPages) loadReports(currentPage + 1); });
}

// --- Helper Functions ---
function showAlert(msg, type) {
    if (!alertEl) return;
    const icon = type === 'success'
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
    alertEl.innerHTML = icon + '<span>' + msg + '</span>';
    alertEl.className = `alert alert-${type}`;
    alertEl.style.display = 'flex';
}

function hideAlert() { 
    if (alertEl) {
        alertEl.style.display = 'none';
        alertEl.innerHTML = ''; 
    }
}

function formatSize(bytes) {
    if (!bytes) return '0 Б';
    const units = ['Б', 'КБ', 'МБ', 'ГБ'];
    let i = 0; 
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) { 
        size /= 1024; 
        i++; 
    }
    return `${size.toFixed(1)} ${units[i]}`;
}

function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('ru-RU', { 
        day: '2-digit', 
        month: '2-digit', 
        year: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
    });
}

function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

// --- Theme Toggle ---
const sunSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
const moonSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    if (themeToggle) {
        themeToggle.innerHTML = theme === 'dark' ? sunSvg : moonSvg;
    }
}

const savedTheme = localStorage.getItem('theme') || 'dark';
applyTheme(savedTheme);

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        localStorage.setItem('theme', next);
    });
}

// --- Initialization ---
(async () => {
    const ok = await checkAuth();
    if (ok) {
        loadReports(1);
    }
})();