// ===== 认证状态管理 =====

function isLoggedIn() {
    return !!localStorage.getItem('token');
}

function requireAuth() {
    if (!isLoggedIn()) {
        window.location.href = '/login.html';
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login.html';
}

async function loadUser() {
    try {
        const res = await api.getMe();
        if (res && res.data) {
            localStorage.setItem('user', JSON.stringify(res.data));
            return res.data;
        }
    } catch {
        return null;
    }
    return null;
}

function getUser() {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
}

// 更新导航栏登录状态
function updateNavAuth() {
    const actions = document.querySelector('.navbar-actions');
    if (!actions) return;
    if (isLoggedIn()) {
        const user = getUser();
        actions.innerHTML = `
            <span style="color:var(--text-secondary);font-size:13px">${user ? user.username : ''}</span>
            <a href="/dashboard.html" class="btn btn-sm btn-primary">Dashboard</a>
            <button class="btn btn-sm btn-ghost" onclick="logout()">Logout</button>
        `;
    } else {
        actions.innerHTML = `
            <a href="/login.html" class="btn btn-sm btn-secondary">Sign In</a>
            <a href="/login.html?tab=register" class="btn btn-sm btn-primary">Get Started</a>
        `;
    }
}
