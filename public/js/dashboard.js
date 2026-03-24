// ===== 初始化 =====
if (!requireAuth()) throw new Error('Not authenticated');
updateNavAuth();

let currentPage = 1;
const PAGE_SIZE = 20;

// ===== 侧边栏导航 =====
document.querySelectorAll('.sidebar-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`panel-${item.dataset.panel}`).classList.add('active');

        if (item.dataset.panel === 'overview') loadOverview();
        if (item.dataset.panel === 'monitors') loadMonitors();
        if (item.dataset.panel === 'tweets') loadTweets();
        if (item.dataset.panel === 'settings') loadSettings();
    });
});

// ===== 概览 =====
async function loadOverview() {
    try {
        const [statsRes, tweetsRes] = await Promise.all([api.getStats(), api.getTweets({ limit: 5 })]);
        if (statsRes && statsRes.data) {
            const s = statsRes.data;
            document.getElementById('stat-active').textContent = s.active_count;
            document.getElementById('stat-monitors').textContent = s.monitor_count;
            document.getElementById('stat-today').textContent = s.today_tweets;
            document.getElementById('stat-total').textContent = s.total_tweets;
        }
        if (tweetsRes && tweetsRes.data) {
            renderTweetList('recent-tweets', tweetsRes.data.items);
        }
    } catch {}
}

// ===== 监控账号 =====
async function loadMonitors() {
    try {
        const res = await api.getMonitors();
        if (!res || !res.data) return;
        const list = document.getElementById('monitor-list');
        if (res.data.length === 0) {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#9673;</div><p class="empty-state-text">No monitors yet.</p><button class="btn btn-primary" onclick="openAddModal()">Add Your First Monitor</button></div>';
            return;
        }
        list.innerHTML = res.data.map(m => `
            <div class="monitor-card" data-id="${m.id}">
                <div class="monitor-card-header">
                    <img class="monitor-avatar" src="${m.avatar_url || ''}" onerror="this.style.display='none'" alt="">
                    <div class="monitor-info">
                        <div class="monitor-name">${m.display_name || m.twitter_username}</div>
                        <div class="monitor-handle">@${m.twitter_username}</div>
                    </div>
                    <span class="badge ${m.is_active ? 'badge-success' : 'badge-danger'}">${m.is_active ? 'Active' : 'Paused'}</span>
                </div>
                <div class="monitor-card-footer">
                    <select class="priority-select" onchange="updatePriority(${m.id}, this.value)">
                        <option value="normal" ${m.priority==='normal'?'selected':''}>Normal</option>
                        <option value="important" ${m.priority==='important'?'selected':''}>Important</option>
                        <option value="urgent" ${m.priority==='urgent'?'selected':''}>Urgent</option>
                    </select>
                    <div style="display:flex;gap:8px">
                        <label class="toggle">
                            <input type="checkbox" ${m.is_active ? 'checked' : ''} onchange="toggleActive(${m.id}, this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                        <button class="btn btn-sm btn-danger" onclick="removeMonitor(${m.id})">Del</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch {}
}

async function updatePriority(id, priority) {
    try { await api.updateMonitor(id, { priority }); showToast('Priority updated', 'success'); } catch {}
}

async function toggleActive(id, active) {
    try { await api.updateMonitor(id, { is_active: active ? 1 : 0 }); showToast(active ? 'Activated' : 'Paused', 'success'); } catch {}
}

async function removeMonitor(id) {
    if (!confirm('Confirm delete this monitor?')) return;
    try { await api.deleteMonitor(id); showToast('Deleted', 'success'); loadMonitors(); } catch {}
}

// 弹窗
function openAddModal() { document.getElementById('addModal').classList.add('show'); }
function closeAddModal() { document.getElementById('addModal').classList.remove('show'); }

document.getElementById('addMonitorForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const btn = e.target.querySelector('[type="submit"]');
    btn.disabled = true; btn.textContent = 'Adding...';
    try {
        await api.addMonitor({ twitter_username: fd.get('twitter_username'), priority: fd.get('priority') });
        showToast('Monitor added!', 'success');
        closeAddModal();
        e.target.reset();
        loadMonitors();
    } catch {
    } finally {
        btn.disabled = false; btn.textContent = 'Add';
    }
});

// ===== 推文 =====
async function loadTweets(page = 1) {
    currentPage = page;
    const monitorId = document.getElementById('tweet-filter-monitor').value;
    const params = { page, limit: PAGE_SIZE };
    if (monitorId) params.monitor_id = monitorId;

    try {
        const res = await api.getTweets(params);
        if (!res || !res.data) return;
        renderTweetList('tweet-list', res.data.items);
        renderPagination(res.data.total, page, PAGE_SIZE);
    } catch {}
}

function renderTweetList(containerId, items) {
    const el = document.getElementById(containerId);
    if (!items || items.length === 0) {
        el.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#9993;</div><p class="empty-state-text">No tweets found.</p></div>';
        return;
    }
    el.innerHTML = items.map(t => {
        const metrics = typeof t.metrics === 'string' ? JSON.parse(t.metrics) : (t.metrics || {});
        return `
        <div class="tweet-item">
            <div class="tweet-header">
                <img class="tweet-avatar" src="${t.avatar_url || ''}" onerror="this.style.display='none'" alt="">
                <div class="tweet-meta">
                    <span class="tweet-author">${t.display_name || t.twitter_username || ''}</span>
                    <span class="tweet-time" style="margin-left:8px">@${t.twitter_username || ''} - ${timeAgo(t.fetched_at)}</span>
                </div>
                <span class="badge badge-info">${t.tweet_type || 'tweet'}</span>
            </div>
            <div class="tweet-content">${escapeHtml(t.content_original || '')}</div>
            ${t.content_translated ? `<div class="tweet-translated">${escapeHtml(t.content_translated)}</div>` : ''}
            <div class="tweet-metrics">
                <span>Likes ${formatNumber(metrics.likes || 0)}</span>
                <span>RT ${formatNumber(metrics.retweets || 0)}</span>
                <span>Replies ${formatNumber(metrics.replies || 0)}</span>
            </div>
        </div>`;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderPagination(total, page, limit) {
    const el = document.getElementById('tweet-pagination');
    const pages = Math.ceil(total / limit);
    if (pages <= 1) { el.innerHTML = ''; return; }
    let html = '';
    for (let i = 1; i <= Math.min(pages, 10); i++) {
        html += `<button class="page-btn ${i===page?'active':''}" onclick="loadTweets(${i})">${i}</button>`;
    }
    el.innerHTML = html;
}

// 筛选器
document.getElementById('tweet-filter-monitor').addEventListener('change', () => loadTweets(1));

async function populateMonitorFilter() {
    try {
        const res = await api.getMonitors();
        if (!res || !res.data) return;
        const sel = document.getElementById('tweet-filter-monitor');
        res.data.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = `@${m.twitter_username}`;
            sel.appendChild(opt);
        });
    } catch {}
}

// ===== 设置 =====
async function loadSettings() {
    try {
        const res = await api.getSettings();
        if (!res || !res.data) return;
        const form = document.getElementById('settingsForm');
        const d = res.data;
        form.feishu_webhook_url.value = d.feishu_webhook_url || '';
        form.feishu_user_id.value = d.feishu_user_id || '';
        form.phone_enabled.checked = !!d.phone_enabled;
        form.phone_retry_max.value = d.phone_retry_max || 3;
        form.phone_retry_interval.value = d.phone_retry_interval || 120;
        form.poll_interval.value = d.poll_interval || 300;
    } catch {}
}

document.getElementById('settingsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
        await api.updateSettings({
            feishu_webhook_url: form.feishu_webhook_url.value,
            feishu_user_id: form.feishu_user_id.value,
            phone_enabled: form.phone_enabled.checked ? 1 : 0,
            phone_retry_max: parseInt(form.phone_retry_max.value),
            phone_retry_interval: parseInt(form.phone_retry_interval.value),
            poll_interval: parseInt(form.poll_interval.value),
        });
        showToast('Settings saved!', 'success');
    } catch {}
});

// ===== 初始加载 =====
(async () => {
    await loadUser();
    updateNavAuth();
    loadOverview();
    populateMonitorFilter();
})();
