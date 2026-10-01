const API = '/api/reports';
        let currentPage = 1;
        let totalPages = 1;
        let selectedFile = null;
        let authEnabled = false;
        let authenticated = false;
        let userRoles = [];

        // --- Elements ---
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

        // --- Role helpers ---
        const ROLE_LEVELS = { viewer: 0, reporter: 1, admin: 2 };
        function topRole(roles) {
            if (!roles || !roles.length) return 'viewer';
            return roles.reduce((a, b) => ROLE_LEVELS[b] > ROLE_LEVELS[a] ? b : a, roles[0]);
        }
        function hasRole(roles, min) {
            const levels = (roles || []).map(r => ROLE_LEVELS[r] ?? -1);
            return Math.max(...levels, -1) >= (ROLE_LEVELS[min] ?? 99);
        }

        // --- Auth ---
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
            // Upload card visible only for reporter+
            uploadCard.style.display = hasRole(userRoles, 'reporter') ? '' : 'none';
            // Role pill
            const role = topRole(userRoles);
            rolePill.textContent = role;
            rolePill.style.display = authEnabled ? 'inline-flex' : 'none';
        }

        function showLoginOverlay() { loginOverlay.classList.add('show'); }
        function hideLoginOverlay() { loginOverlay.classList.remove('show'); }

        function showUserBadge(user) {
            userBadge.style.display = 'flex';
            logoutBtn.style.display = 'inline-flex';
            userName.textContent = user.name || user.email || 'User';
            const initials = (user.name || user.email || '?')
                .split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
            userAvatar.textContent = initials;
        }

        loginBtn.addEventListener('click', () => { window.location.href = '/auth/login'; });
        logoutBtn.addEventListener('click', () => { window.location.href = '/auth/logout'; });

        function handleUnauthorized() {
            if (authEnabled) { showLoginOverlay(); return true; }
            return false;
        }

        // --- Drop zone: pointer glow ---
        dropZone.addEventListener('pointermove', (e) => {
            const r = dropZone.getBoundingClientRect();
            dropZone.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100) + '%');
            dropZone.style.setProperty('--my', ((e.clientY - r.top) / r.height * 100) + '%');
        });
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) handleFileSelect(e.target.files[0]);
        });

        function handleFileSelect(file) {
            if (!file.name.toLowerCase().endsWith('.zip')) {
                showAlert('Ожидается файл с расширением .zip', 'error');
                return;
            }
            selectedFile = file;
            fileName.innerHTML = '';
            const ico = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            ico.setAttribute('viewBox', '0 0 24 24'); ico.setAttribute('fill', 'none');
            ico.setAttribute('stroke', 'currentColor'); ico.setAttribute('stroke-width', '2');
            ico.setAttribute('stroke-linecap', 'round'); ico.setAttribute('stroke-linejoin', 'round');
            ico.style.width = '14px'; ico.style.height = '14px';
            ico.innerHTML = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>';
            fileName.appendChild(ico);
            fileName.append(` ${file.name} · ${formatSize(file.size)}`);
            fileName.style.display = 'inline-flex';
            uploadBtn.disabled = false;
            hideAlert();
        }

        // --- Upload ---
        uploadBtn.addEventListener('click', async () => {
            if (!selectedFile) return;
            uploadBtn.disabled = true;
            progressBar.classList.add('active');
            progressText.querySelector('span:last-child') ? null : null;
            progressText.lastChild.textContent = 'Генерация отчёта...';

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
                    `Проект «${escapeHtml(data.project)}» ${verb} — загрузок: ${data.uploads_count}, результатов: ${data.results_count}. ` +
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
                progressBar.classList.remove('active');
                uploadBtn.disabled = false;
            }
        });

        // --- Reports list ---
        async function loadReports(page) {
            currentPage = page;
            try {
                const resp = await fetch(`${API}?page=${page}&page_size=20`);
                if (resp.status === 401) { handleUnauthorized(); return; }
                const data = await resp.json();
                totalPages = Math.ceil(data.total / data.page_size) || 1;
                reportsMeta.textContent = data.total ? `${data.total} всего` : '';

                if (data.items.length === 0) {
                    reportsBody.innerHTML = `
                        <tr><td colspan="7">
                            <div class="empty-state">
                                <div class="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg></div>
                                <div class="t">Нет загруженных проектов</div>
                                <div class="s">Загрузите ZIP-архив с результатами тестов, чтобы создать первый отчёт</div>
                            </div>
                        </td></tr>`;
                    pagination.style.display = 'none';
                    return;
                }

                const canDelete = hasRole(userRoles, 'admin');
                reportsBody.innerHTML = data.items.map((r, i) => `
                    <tr style="animation-delay:${i * 0.05}s">
                        <td><span class="badge">${escapeHtml(r.project)}</span></td>
                        <td><span class="badge-uploads">${r.uploads_count}</span></td>
                        <td><span class="num">${r.results_count}</span></td>
                        <td><span class="date">${formatDate(r.created_at)}</span></td>
                        <td><span class="date">${formatDate(r.updated_at)}</span></td>
                        <td><span class="num">${formatSize(r.size_bytes)}</span></td>
                        <td>
                            <div class="actions-cell">
                                <a href="${r.url}" target="_blank" class="btn btn-open">Открыть</a>
                                ${canDelete ? `<button class="btn btn-danger" onclick="deleteReport('${escapeHtml(r.project)}')">Удалить</button>` : ''}
                            </div>
                        </td>
                    </tr>
                `).join('');

                pagination.style.display = 'flex';
                prevBtn.disabled = page <= 1;
                nextBtn.disabled = page >= totalPages;
                pageInfo.textContent = `${page} / ${totalPages}`;
            } catch (err) {
                reportsBody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="t">Ошибка: ${escapeHtml(err.message)}</div></div></td></tr>`;
            }
        }

        async function deleteReport(project) {
            if (!confirm(`Удалить проект «${project}» со всеми результатами?`)) return;
            try {
                const resp = await fetch(`${API}/${encodeURIComponent(project)}`, { method: 'DELETE' });
                if (resp.status === 401) { handleUnauthorized(); return; }
                if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || 'Ошибка'); }
                loadReports(currentPage);
            } catch (err) {
                alert(`Ошибка: ${err.message}`);
            }
        }

        // --- Pagination ---
        prevBtn.addEventListener('click', () => { if (currentPage > 1) loadReports(currentPage - 1); });
        nextBtn.addEventListener('click', () => { if (currentPage < totalPages) loadReports(currentPage + 1); });

        // --- Helpers ---
        function showAlert(msg, type) {
            const icon = type === 'success'
                ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
                : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
            alertEl.innerHTML = icon + '<span>' + msg + '</span>';
            alertEl.className = `alert show alert-${type}`;
        }
        function hideAlert() { alertEl.className = 'alert'; alertEl.innerHTML = ''; }
        function formatSize(bytes) {
            if (!bytes) return '—';
            const units = ['Б', 'КБ', 'МБ', 'ГБ'];
            let i = 0; let size = bytes;
            while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
            return `${size.toFixed(1)} ${units[i]}`;
        }
        function formatDate(iso) {
            const d = new Date(iso);
            return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        }
        function escapeHtml(s) {
            const div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }

        // --- Theme toggle ---
        const themeToggle = document.getElementById('themeToggle');
        const themeIcon = document.getElementById('themeIcon');
        const sunSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
        const moonSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

        function applyTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            themeIcon.innerHTML = theme === 'dark' ? moonSvg : sunSvg;
        }
        const savedTheme = localStorage.getItem('theme') || 'dark';
        applyTheme(savedTheme);
        themeToggle.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            localStorage.setItem('theme', next);
        });

        // --- Init ---
        (async () => {
            const ok = await checkAuth();
            if (ok) loadReports(1);
        })();