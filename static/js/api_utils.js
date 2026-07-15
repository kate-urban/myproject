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
};
