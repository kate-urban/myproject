/** Общая авторизация для страниц Syllabus */
window.SyllabusAuth = {
  TOKEN_KEY: "ws_token",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY) || "";
  },

  setToken(token) {
    if (token) localStorage.setItem(this.TOKEN_KEY, token);
    else localStorage.removeItem(this.TOKEN_KEY);
  },

  authHeaders(extra = {}) {
    const headers = { ...extra };
    const token = this.getToken();
    if (token && token !== "auth-disabled") {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  },

  async getConfig() {
    const res = await fetch("/api/v1/workspace/config/");
    if (!res.ok) throw new Error("Не удалось загрузить настройки");
    return res.json();
  },

  async getAuthStatus() {
    const res = await fetch("/api/v1/workspace/auth-status/", {
      headers: this.authHeaders(),
    });
    if (!res.ok) throw new Error("Не удалось проверить вход");
    return res.json();
  },

  async requireAuth(redirectTo = "/") {
    const config = await this.getConfig();
    if (!config.auth_enabled) return true;
    const status = await this.getAuthStatus();
    if (status.authenticated) return true;
    this.setToken("");
    location.href = redirectTo;
    return false;
  },

  async logout() {
    const token = this.getToken();
    if (token && token !== "auth-disabled") {
      await fetch("/api/v1/workspace/logout/", {
        method: "POST",
        headers: this.authHeaders(),
      }).catch(() => {});
    }
    this.setToken("");
    location.href = "/";
  },
};
