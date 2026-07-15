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

  isEmbed() {
    if (window.SyllabusEmbed) return true;
    try {
      return window.self !== window.top;
    } catch (_) {
      return true;
    }
  },

  notifyParent(type, payload = {}) {
    if (!this.isEmbed()) return;
    try {
      window.parent.postMessage({ type, ...payload }, location.origin);
    } catch (_) {}
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
    try {
      const config = await this.getConfig();
      if (!config.auth_enabled) return true;
      const status = await this.getAuthStatus();
      if (status.authenticated) return true;
      this.setToken("");
      if (this.isEmbed()) {
        this.notifyParent("syllabus:auth-required");
        return false;
      }
      location.href = redirectTo;
      return false;
    } catch (err) {
      if (this.isEmbed()) {
        this.notifyParent("syllabus:error", { message: err.message || "Ошибка сети" });
      }
      throw err;
    }
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
    if (this.isEmbed()) {
      this.notifyParent("syllabus:logout");
      return;
    }
    location.href = "/";
  },
};
