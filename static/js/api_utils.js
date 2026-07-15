/** Разбор ответов FastAPI (detail: string | object | array) для показа пользователю */
window.SyllabusApi = {
  formatDetail(detail) {
    if (detail == null || detail === "") return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map(item => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object") {
            const loc = Array.isArray(item.loc)
              ? item.loc.filter(x => x !== "body").join(" → ")
              : "";
            const msg = item.msg || item.message || "";
            return loc ? `${loc}: ${msg}` : msg;
          }
          return String(item);
        })
        .filter(Boolean)
        .join("; ");
    }
    if (typeof detail === "object") {
      return detail.msg || detail.message || JSON.stringify(detail);
    }
    return String(detail);
  },

  errorFromResponse(statusText, json) {
    const detail = json?.detail ?? json?.message ?? statusText;
    return this.formatDetail(detail) || statusText || "Ошибка запроса";
  },

  /** Скачать файл с API (с авторизацией). path — от /api/v1 или полный URL. */
  async downloadFile(path, opts = {}) {
    const apiBase = opts.apiBase || "/api/v1";
    const url = path.startsWith("http") ? path : `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
    const res = await fetch(url, { headers: SyllabusAuth.authHeaders() });
    if (res.status === 401 && window.SyllabusAuth?.getConfig) {
      try {
        const cfg = await SyllabusAuth.getConfig();
        if (cfg?.auth_enabled) {
          SyllabusAuth.setToken("");
          throw new Error("Требуется вход");
        }
      } catch (_) {}
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = this.errorFromResponse(res.statusText, j);
      } catch (_) {}
      throw new Error(detail);
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : opts.defaultFilename || "download";
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(objectUrl);
    return { filename, blob, headers: res.headers };
  },
};
