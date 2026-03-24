// API 基地址 - 开发环境指向本地，生产环境需修改
const API_BASE = window.API_BASE || 'http://localhost:8080';

async function apiRequest(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const token = localStorage.getItem('token');

    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
        const resp = await fetch(url, { ...options, headers });
        const data = await resp.json();

        if (resp.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login.html';
            return null;
        }
        if (!resp.ok) {
            throw new Error(data.detail || data.message || '请求失败');
        }
        return data;
    } catch (err) {
        if (err.message === 'Failed to fetch') {
            showToast('无法连接服务器，请确认监控服务已启动', 'error');
        } else {
            showToast(err.message, 'error');
        }
        throw err;
    }
}

const api = {
    // 认证
    register: (data) => apiRequest('/api/auth/register', { method: 'POST', body: JSON.stringify(data) }),
    login: (data) => apiRequest('/api/auth/login', { method: 'POST', body: JSON.stringify(data) }),
    getMe: () => apiRequest('/api/auth/me'),

    // 监控
    getMonitors: () => apiRequest('/api/monitors'),
    addMonitor: (data) => apiRequest('/api/monitors', { method: 'POST', body: JSON.stringify(data) }),
    updateMonitor: (id, data) => apiRequest(`/api/monitors/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteMonitor: (id) => apiRequest(`/api/monitors/${id}`, { method: 'DELETE' }),

    // 推文
    getTweets: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return apiRequest(`/api/tweets?${qs}`);
    },
    getStats: () => apiRequest('/api/tweets/stats'),

    // 设置
    getSettings: () => apiRequest('/api/settings'),
    updateSettings: (data) => apiRequest('/api/settings', { method: 'PUT', body: JSON.stringify(data) }),
};
