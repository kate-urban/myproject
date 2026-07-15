/** Русская локализация интерфейса (названия, подписи ролей, TinyMCE). */
window.SyllabusUiRu = {
  APP_NAME: "Syllabus",

  tinymceLanguage: {
    language: "ru",
    language_url: "https://cdn.jsdelivr.net/npm/tinymce@6/langs/ru.js",
  },

  signatureRoleLabel(role) {
    const map = {
      director: "Директор института",
      dept_head: "Заведующий кафедрой",
      discipline_head: "Руководитель программы",
    };
    return map[role] || role || "—";
  },

  signatureRoleOptions: [
    { value: "director", label: "Директор института" },
    { value: "dept_head", label: "Заведующий кафедрой" },
    { value: "discipline_head", label: "Руководитель программы" },
  ],

  studyFormLabel(form) {
    const map = {
      ochnaya: "Очная",
      zaochnaya: "Заочная",
      ochno_zaochnaya: "Очно-заочная",
    };
    const key = String(form || "").trim().toLowerCase();
    return map[key] || form || "—";
  },
};

/** Утилиты UI: debounce/throttle для поиска и resize. */
window.SyllabusUi = {
  debounce(fn, waitMs = 250) {
    let timer = null;
    return function debounced(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), waitMs);
    };
  },

  throttle(fn, waitMs = 150) {
    let last = 0;
    let pending = null;
    return function throttled(...args) {
      const now = Date.now();
      const run = () => {
        last = Date.now();
        pending = null;
        fn.apply(this, args);
      };
      if (now - last >= waitMs) {
        run();
      } else if (!pending) {
        pending = setTimeout(run, waitMs - (now - last));
      }
    };
  },
};
