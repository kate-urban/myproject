/** Единая оболочка Syllabus — переключение разделов без перезагрузки страницы. */

window.SyllabusApp = {
  currentView: "workspace",
  _framesLoaded: {},

  VIEWS: {
    workspace: { frame: null },
    validation: { src: "/validation?embed=1" },
    reference: { src: "/reference?embed=1" },
    editor: { src: "/editor?embed=1" },
  },

  init() {
    if (!document.getElementById("appRouterHost")) return;

    document.body.classList.add("app-unified");
    SyllabusShell.PAGES = SyllabusShell.PAGES.map((page) => ({
      ...page,
      href: page.id === "workspace" ? "/" : `/#view=${page.id}`,
    }));

    const brand = document.querySelector(".app-brand");
    if (brand && brand.tagName === "A") {
      brand.href = "/";
      brand.addEventListener("click", (event) => {
        event.preventDefault();
        this.navigate("workspace");
      });
    }

    const nav = document.getElementById("appHeaderNav");
    nav?.addEventListener("click", (event) => {
      const link = event.target.closest("a.nav-link");
      if (!link) return;
      event.preventDefault();
      const view = this._viewFromHref(link.getAttribute("href"));
      this.navigate(view);
    });

    window.addEventListener("hashchange", () => this.applyRoute());
    window.addEventListener("message", (event) => {
      if (event.origin !== location.origin) return;
      if (event.data?.type === "syllabus:auth-required") {
        this._showAuthGate();
      }
      if (event.data?.type === "syllabus:navigate") {
        this.navigate(event.data.view || "workspace");
      }
      if (event.data?.type === "syllabus:error") {
        this._setFrameStatus(this.currentView, event.data.message || "Ошибка загрузки", true);
      }
    });

    this.applyRoute();
  },

  _viewFromHref(href) {
    if (!href || href === "/") return "workspace";
    const raw = href.replace(/^\/#/, "").replace(/^#/, "");
    const params = new URLSearchParams(raw.includes("=") ? raw : `view=${raw}`);
    return params.get("view") || "workspace";
  },

  parseRoute() {
    const params = SyllabusShell.parseHashParams();
    return {
      view: params.view || "workspace",
      plan: params.plan || null,
      section: params.section || null,
      doc: params.doc || null,
    };
  },

  navigate(view, extra = {}) {
    const params = new URLSearchParams();
    if (view && view !== "workspace") params.set("view", view);
    if (extra.plan) params.set("plan", extra.plan);
    if (extra.section) params.set("section", extra.section);
    if (extra.doc) params.set("doc", extra.doc);
    const next = params.toString() ? `#${params.toString()}` : "";
    if (location.hash === next) {
      this.applyRoute();
    } else {
      location.hash = next;
    }
  },

  resetFrames() {
    this._framesLoaded = {};
    ["validation", "reference", "editor"].forEach((view) => {
      const frame = document.getElementById(`${view}Frame`);
      if (frame) {
        frame.removeAttribute("src");
        frame.dataset.route = "";
      }
      this._setFrameStatus(view, "", false);
    });
  },

  onAuthReady() {
    this.resetFrames();
    this.applyRoute();
  },

  _showAuthGate() {
    window.workspaceShowAuth?.();
    const route = this.parseRoute();
    if (route.view !== "workspace") {
      this._setFrameStatus(route.view, "Войдите в систему на главной странице", true);
    }
  },

  async _canLoadFrames() {
    try {
      const config = await SyllabusAuth.getConfig();
      if (!config.auth_enabled) return true;
      const status = await SyllabusAuth.getAuthStatus();
      return !!status.authenticated;
    } catch (_) {
      return true;
    }
  },

  async applyRoute() {
    const route = this.parseRoute();
    let view = this.VIEWS[route.view] ? route.view : "workspace";
    if (view !== "workspace" && !(await this._canLoadFrames())) {
      this._showAuthGate();
      view = "workspace";
    }
    this.currentView = view;

    document.querySelectorAll(".app-view").forEach((el) => {
      el.classList.toggle("active", el.id === `view-${view}`);
    });

    const parentRibbon = document.getElementById("appRibbon");
    if (parentRibbon) {
      if (view === "workspace") {
        parentRibbon.removeAttribute("data-hidden");
      } else {
        parentRibbon.setAttribute("data-hidden", "true");
        parentRibbon.innerHTML = "";
      }
    }

    if (view !== "workspace") {
      this._ensureFrame(view, route);
    }

    SyllabusShell.mountHeader(view, this._headerOptions(view, route));
    SyllabusShell.setActiveNav(view === "workspace" ? "/" : `/#view=${view}`);

    if (view === "workspace" && typeof window.refreshWorkspaceRibbon === "function") {
      window.refreshWorkspaceRibbon();
    }
  },

  _headerOptions(view, route) {
    if (view === "workspace" && window.workspaceHeaderOptions) {
      return window.workspaceHeaderOptions();
    }
    return {};
  },

  _setFrameStatus(view, message, isError) {
    const el = document.getElementById(`${view}FrameStatus`);
    if (!el) return;
    if (!message) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.classList.remove("hidden");
    el.classList.toggle("error", !!isError);
    el.textContent = message;
  },

  _buildFrameSrc(view, route) {
    const cfg = this.VIEWS[view];
    if (!cfg?.src) return "";
    let src = cfg.src;
    const hashParts = [];
    if (route.plan) hashParts.push(`plan=${encodeURIComponent(route.plan)}`);
    if (route.section) hashParts.push(route.section);
    if (route.doc) hashParts.push(`doc=${encodeURIComponent(route.doc)}`);
    if (hashParts.length) src += `#${hashParts.join("&")}`;
    return src;
  },

  _ensureFrame(view, route) {
    const cfg = this.VIEWS[view];
    if (!cfg?.src) return;

    const frame = document.getElementById(`${view}Frame`);
    if (!frame) return;

    const src = this._buildFrameSrc(view, route);
    this._setFrameStatus(view, "Загрузка…", false);

    if (this._framesLoaded[view] && frame.dataset.route === src && frame.src) {
      this._setFrameStatus(view, "", false);
      return;
    }

    frame.onload = () => this._setFrameStatus(view, "", false);
    frame.onerror = () => this._setFrameStatus(view, "Не удалось загрузить страницу", true);

    frame.src = src;
    frame.dataset.route = src;
    this._framesLoaded[view] = true;
  },
};

document.addEventListener("DOMContentLoaded", () => SyllabusApp.init());
