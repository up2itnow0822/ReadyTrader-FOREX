// Where the dashboard finds the API server (app/api_server.py).
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// When the API runs with API_OPERATOR_TOKEN, every /api/ call but /api/health needs it, and live
// proposals can only be approved with it. The operator types it once per browser tab; it is kept in
// sessionStorage (this tab only) and never in the page source.
const TOKEN_KEY = 'readytrader.operatorToken';
let asked = false;

function storedToken(): string {
    try {
        return window.sessionStorage.getItem(TOKEN_KEY) || '';
    } catch {
        return '';
    }
}

function withToken(init: RequestInit, token: string): RequestInit {
    const headers = new Headers(init.headers);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return { ...init, headers };
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const res = await fetch(`${API_URL}${path}`, withToken(init, storedToken()));
    if (res.status !== 401 || asked || typeof window === 'undefined') return res;
    asked = true; // ask once per page load, not on every poll
    const entered = (window.prompt('This API requires its operator token (API_OPERATOR_TOKEN):') || '').trim();
    if (!entered) return res;
    try {
        window.sessionStorage.setItem(TOKEN_KEY, entered);
    } catch {
        // storage unavailable: the token still works for this request
    }
    asked = false;
    return fetch(`${API_URL}${path}`, withToken(init, entered));
}
