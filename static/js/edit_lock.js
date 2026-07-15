/** Блокировки редактирования РПД (heartbeat + снятие при закрытии вкладки). */
window.SyllabusEditLock = {
  _token: null,
  _timer: null,
  _programId: null,

  async acquire(programId) {
    if (!programId) return null;
    const config = await SyllabusAuth.getConfig().catch(() => ({}));
    if (!config.edit_locks_enabled) return null;

    const res = await fetch("/api/v1/workspace/locks/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...SyllabusAuth.authHeaders(),
      },
      body: JSON.stringify({ resource_type: "program", resource_id: programId }),
    });
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Документ занят другим пользователем");
    }
    if (!res.ok) return null;
    const lock = await res.json();
    this._token = lock.token;
    this._programId = programId;
    this._startHeartbeat();
    window.addEventListener("beforeunload", this._releaseOnUnload);
    return lock;
  },

  _startHeartbeat() {
    if (this._timer) clearInterval(this._timer);
    this._timer = setInterval(() => {
      if (!this._token) return;
      fetch(`/api/v1/workspace/locks/heartbeat/${this._token}/`, {
        method: "POST",
        headers: SyllabusAuth.authHeaders(),
      }).catch(() => {});
    }, 120000);
  },

  _releaseOnUnload() {
    if (!SyllabusEditLock._token) return;
    const headers = SyllabusAuth.authHeaders();
    fetch(`/api/v1/workspace/locks/${SyllabusEditLock._token}/`, {
      method: "DELETE",
      headers,
      keepalive: true,
    }).catch(() => {});
  },

  async release() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    window.removeEventListener("beforeunload", this._releaseOnUnload);
    const token = this._token;
    this._token = null;
    this._programId = null;
    if (!token) return;
    await fetch(`/api/v1/workspace/locks/${token}/`, {
      method: "DELETE",
      headers: SyllabusAuth.authHeaders(),
    }).catch(() => {});
  },

  async status(programId) {
    if (!programId) return null;
    const res = await fetch(
      `/api/v1/workspace/locks/program/${programId}/`,
      { headers: SyllabusAuth.authHeaders() }
    );
    if (!res.ok) return null;
    return res.json();
  },
};
