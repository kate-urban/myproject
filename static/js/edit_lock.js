/** Блокировки редактирования РПД (heartbeat + снятие при закрытии вкладки). */
window.SyllabusEditLock = {
  _token: null,
  _timer: null,
  _programId: null,
  _onUnload: null,

  async acquire(programId) {
    if (!programId) return null;
    const config = await SyllabusAuth.getConfig().catch(() => ({}));
    if (!config.edit_locks_enabled) return null;

    if (this._programId && String(this._programId) !== String(programId)) {
      await this.release();
    }

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
    this._bindUnload();
    return lock;
  },

  _bindUnload() {
    if (!this._onUnload) {
      this._onUnload = () => this._releaseOnUnload();
    }
    window.removeEventListener("beforeunload", this._onUnload);
    window.removeEventListener("pagehide", this._onUnload);
    window.addEventListener("beforeunload", this._onUnload);
    window.addEventListener("pagehide", this._onUnload);
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
    fetch(`/api/v1/workspace/locks/${SyllabusEditLock._token}/`, {
      method: "DELETE",
      headers: SyllabusAuth.authHeaders(),
      keepalive: true,
    }).catch(() => {});
  },

  async release() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    if (this._onUnload) {
      window.removeEventListener("beforeunload", this._onUnload);
      window.removeEventListener("pagehide", this._onUnload);
    }
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
