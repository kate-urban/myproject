/** Скрыть шапку при встраивании в единую оболочку (?embed=1). */
(function () {
  if (new URLSearchParams(location.search).get("embed") !== "1") return;
  window.SyllabusEmbed = true;
  document.documentElement.classList.add("embed-mode-root");
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector(".app-header")?.remove();
    document.body.classList.add("embed-mode");
    document.querySelectorAll('a[href="/"]').forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        window.parent.postMessage({ type: "syllabus:navigate", view: "workspace" }, location.origin);
      });
    });
  });
})();
