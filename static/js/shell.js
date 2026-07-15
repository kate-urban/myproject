/** Единая навигационная лента Syllabus (UI «как 1С»). */

window.SyllabusShell = {

  API: "/api/v1",



  PAGES: [

    { id: "workspace", href: "/", label: "Главная" },

    { id: "validation", href: "/validation", label: "Сверка" },

    { id: "reference", href: "/reference", label: "Справочники" },

  ],



  PAGE_META: {

    workspace: { title: "Рабочее место", subtitle: "Учебные планы и дисциплины" },

    validation: { title: "Сверка", subtitle: "Учебный план, РПД и ФОС" },

    editor: { title: "Редактор", subtitle: "Правка документов" },

    reference: { title: "Справочники", subtitle: "Фразы, подписи, архив" },

  },



  ensureAppRail(page) {

    if (window.SyllabusEmbed) return;

    const host = document.getElementById("app") || document.body;

    host.classList.add("has-app-rail");

    if (host === document.body) document.body.classList.add("has-app-rail");



    let rail = document.getElementById("appRail");

    if (!rail) {

      rail = document.createElement("aside");

      rail.className = "app-rail";

      rail.id = "appRail";

      host.insertBefore(rail, host.firstChild);

    }



    rail.innerHTML = `

      <a href="/" class="rail-brand" title="Syllabus">

        <span class="rail-logo">S</span>

      </a>

      <nav class="rail-nav" aria-label="Разделы">

        ${this.PAGES.map(p => {

          const meta = this.PAGE_META[p.id] || {};

          const active = p.id === page ? " active" : "";

          return `<a href="${p.href}" class="rail-link${active}" title="${p.label}">

            <span class="rail-text">${p.label}</span>

          </a>`;

        }).join("")}

      </nav>

      <button type="button" class="rail-link rail-logout hidden" id="btnRailLogout" title="Выход">

        <span class="rail-text">Выход</span>

      </button>

    `;



    const headerNav = document.getElementById("appHeaderNav");

    if (headerNav) headerNav.classList.add("hidden");



    const btnRailLogout = document.getElementById("btnRailLogout");

    const btnHeaderLogout = document.getElementById("btnHeaderLogout");

    if (btnRailLogout && btnHeaderLogout) {

      btnRailLogout.classList.toggle("hidden", btnHeaderLogout.classList.contains("hidden"));

      btnRailLogout.onclick = () => btnHeaderLogout.click();

    }

  },



  syncRailLogout(show) {

    const btnRailLogout = document.getElementById("btnRailLogout");

    if (btnRailLogout) btnRailLogout.classList.toggle("hidden", !show);

  },



  ensureHeaderStructure() {

    const header = document.querySelector(".app-header");

    if (!header) return;



    const brand = header.querySelector(".app-brand");

    const logo = header.querySelector(".app-logo");

    if (logo && !logo.id) logo.id = "appHeaderLogo";



    let ctxEl = document.getElementById("appHeaderContext");

    if (!ctxEl) {

      ctxEl = document.createElement("span");

      ctxEl.className = "header-context";

      ctxEl.id = "appHeaderContext";

      brand?.after(ctxEl);

    }



    let extraEl = document.getElementById("appHeaderExtra");

    if (!extraEl) {

      extraEl = document.createElement("span");

      extraEl.className = "header-extra";

      extraEl.id = "appHeaderExtra";

      ctxEl.after(extraEl);

    }

    const docChip = document.getElementById("doc-name");

    if (docChip && !extraEl.contains(docChip)) extraEl.appendChild(docChip);



    let actionsEl = document.getElementById("appHeaderActions");

    if (!actionsEl) {

      actionsEl = document.createElement("div");

      actionsEl.className = "header-actions";

      actionsEl.id = "appHeaderActions";

      const nav = document.getElementById("appHeaderNav") || header.querySelector(".header-nav");

      nav?.before(actionsEl);

    }



    let userEl = document.getElementById("headerUser");

    if (!userEl) {

      userEl = document.createElement("span");

      userEl.className = "user-chip hidden";

      userEl.id = "headerUser";

      actionsEl.appendChild(userEl);

    } else if (!actionsEl.contains(userEl)) {

      actionsEl.appendChild(userEl);

    }



    let logoutBtn = document.getElementById("btnHeaderLogout") || document.getElementById("btnLogout");

    const nav = document.getElementById("appHeaderNav") || header.querySelector(".header-nav");

    if (nav && !nav.id) nav.id = "appHeaderNav";



    if (!logoutBtn) {

      logoutBtn = document.createElement("button");

      logoutBtn.type = "button";

      logoutBtn.className = "btn-header hidden";

      logoutBtn.id = "btnHeaderLogout";

      logoutBtn.textContent = "Выход";

    } else {

      logoutBtn.id = "btnHeaderLogout";

    }

    if (nav) nav.after(logoutBtn);

    else header.appendChild(logoutBtn);



    if (actionsEl && nav && actionsEl.nextElementSibling !== nav) nav.before(actionsEl);

  },



  async bindHeaderAuth(options = {}) {

    if (window.SyllabusEmbed) return;

    this.ensureHeaderStructure();

    const userEl = document.getElementById("headerUser");

    const logoutBtn = document.getElementById("btnHeaderLogout");



    if (logoutBtn && !logoutBtn.dataset.bound) {

      logoutBtn.dataset.bound = "1";

      logoutBtn.onclick = () => SyllabusAuth?.logout?.();

    }



    let userName = options.userName;

    let showLogout = options.logoutHidden === false;



    if (userName === undefined) {

      try {

        const config = await SyllabusAuth.getConfig();

        if (!config.auth_enabled) {

          userName = "";

          showLogout = false;

        } else {

          const status = await SyllabusAuth.getAuthStatus();

          userName = status.user?.display_name || status.display_name || "";

          showLogout = !!status.authenticated;

        }

      } catch (_) {

        userName = "";

        showLogout = false;

      }

    } else {

      showLogout = options.logoutHidden !== true && !!userName;

    }



    if (userEl) {

      userEl.textContent = userName || "";

      userEl.classList.toggle("hidden", !userName);

    }

    if (logoutBtn) logoutBtn.classList.toggle("hidden", !showLogout);

    this.syncRailLogout(showLogout);

  },



    mountHeader(page, options = {}) {

    this.ensureHeaderStructure();

    this.ensureAppRail(page);

    const meta = this.PAGE_META[page] || this.PAGE_META.workspace;

    const brand = document.querySelector(".app-brand");

    if (brand && brand.tagName === "A") brand.href = "/";



    const logo = document.getElementById("appHeaderLogo") || document.querySelector(".app-logo");

    if (logo) logo.textContent = "S";



    const titleEl = document.getElementById("appHeaderTitle") || document.querySelector(".app-header h1");

    if (titleEl) titleEl.textContent = meta.title;



    const subEl = document.getElementById("appHeaderSubtitle") || document.querySelector(".app-header .subtitle");

    if (subEl) subEl.textContent = options.subtitle || meta.subtitle;



    const ctxEl = document.getElementById("appHeaderContext");

    if (ctxEl) ctxEl.textContent = options.context || "";



    const nav = document.getElementById("appHeaderNav") || document.querySelector(".header-nav");

    if (nav) {

      nav.innerHTML = this.PAGES.map(p => {

        const active = p.id === page ? " active" : "";

        return `<a class="nav-link${active}" href="${p.href}">${p.label}</a>`;

      }).join("");

    }



    const userEl = document.getElementById("headerUser");

    if (userEl && options.userName !== undefined) {

      userEl.textContent = options.userName || "";

      userEl.classList.toggle("hidden", !options.userName);

    }

    const logoutBtn = document.getElementById("btnHeaderLogout");

    if (logoutBtn && options.logoutHidden !== undefined) {

      logoutBtn.classList.toggle("hidden", !!options.logoutHidden);

    }



    const paths = { workspace: "/", validation: "/validation", editor: "/editor", reference: "/reference" };

    this.setActiveNav(paths[page] || "/");

  },



  mountRibbon(container, groups) {

    if (!container) return;

    const list = (groups || []).filter(g => g && (g.actions || []).length);

    if (!list.length) {

      container.setAttribute("data-hidden", "true");

      container.innerHTML = "";

      return;

    }

    container.removeAttribute("data-hidden");

    container.innerHTML = list.map(group => `

      <div class="ribbon-group">

        <div class="ribbon-label">${group.label}</div>

        <div class="ribbon-actions">

          ${(group.actions || []).map(action => {

            if (action.href) {

              const disabled = action.disabled ? 'aria-disabled="true" tabindex="-1"' : "";

              return `<a class="ribbon-btn ${action.primary ? "primary" : ""} ${action.disabled ? "disabled" : ""}" href="${action.disabled ? "#" : action.href}" ${disabled}>${action.title}</a>`;

            }

            const id = action.id ? `id="${action.id}"` : "";

            const disabled = action.disabled ? "disabled" : "";

            return `<button type="button" class="ribbon-btn ${action.primary ? "primary" : ""}" ${id} ${disabled}>${action.title}</button>`;

          }).join("")}

        </div>

      </div>`).join("");

    list.forEach(group => {

      (group.actions || []).forEach(action => {

        if (action.onClick && action.id) {

          const el = document.getElementById(action.id);

          if (el) el.onclick = action.onClick;

        }

      });

    });

  },



  setActiveNav(pathname) {

    const viewFromPath = (value) => {

      const raw = (value || "").replace(/^\/#/, "").replace(/^\//, "");

      if (!raw || raw === "") return "workspace";

      if (raw.startsWith("view=") || raw.includes("view=")) {

        return new URLSearchParams(raw).get("view") || "workspace";

      }

      const legacy = {

        validation: "validation",

        editor: "editor",

        reference: "reference",

      };

      return legacy[raw.split("/")[0]] || legacy[raw] || "workspace";

    };

    const targetView = viewFromPath(pathname);

    document.querySelectorAll(".header-nav .nav-link").forEach(link => {

      const href = link.getAttribute("href") || "";

      const view = href === "/" ? "workspace" : viewFromPath(href.replace(/^\//, ""));

      link.classList.toggle("active", view === targetView);

    });

    document.querySelectorAll(".rail-nav .rail-link[href]").forEach(link => {

      const href = link.getAttribute("href") || "";

      const view = href === "/" ? "workspace" : viewFromPath(href.replace(/^\//, ""));

      link.classList.toggle("active", view === targetView);

    });

  },



  parsePlanIdFromUrl() {

    return this.parseHashParams().plan || new URLSearchParams(location.search).get("plan");

  },



  parseHashParams() {

    const hash = (location.hash || "").replace(/^#/, "");

    const raw = hash.includes("=") ? hash : hash ? `plan=${hash.replace(/^plan=/, "")}` : "";

    const params = new URLSearchParams(raw);

    const out = {};

    for (const [key, value] of params.entries()) out[key] = value;

    return out;

  },



  parseDocIdFromUrl() {

    const fromHash = this.parseHashParams().doc;

    if (fromHash) return fromHash;

    return new URLSearchParams(location.search).get("doc");

  },



  buildGroups(page, ctx = {}) {

    const API = this.API;

    const planId = ctx.planId || null;

    const programId = ctx.programId || null;

    const docId = ctx.docId || null;

    const directionCode = ctx.directionCode || null;

    const year = ctx.year || null;



    const reports = {

      label: "Отчёты",

      actions: [

        {

          title: "Свод 7.1",

          href: planId ? `${API}/reports/study-plans/${planId}/plan-summary.xlsx` : "#",

          disabled: !planId,

        },

        {

          title: "Рейтинг 7.2",

          href: planId ? `${API}/reports/study-plans/${planId}/author-rating.xlsx` : "#",

          disabled: !planId,

        },

        {

          title: "PDF переутв.",

          href: programId ? `${API}/programs/${programId}/reapproval.pdf?variant=auto` : "#",

          disabled: !programId,

        },

      ],

    };



    const exportGroup = {

      label: "Экспорт",

      actions: [

        {

          title: "Архив",

          href: "/reference#archive",

        },

        {

          title: "Архив прошедших",

          href: planId ? `${API}/study-plans/${planId}/export-passed/?kind=rpd` : "#",

          disabled: !planId,

        },

        {

          title: "Пакет архива",

          href:

            directionCode && year

              ? `${API}/study-plans/export-package/?direction_code=${encodeURIComponent(directionCode)}&year=${year}`

              : "#",

          disabled: !(directionCode && year),

        },

      ],

    };



    if (page === "validation") {

      return [

        {

          label: "План",

          actions: [

            { id: "rbImportPlx", title: "Импорт УП", onClick: ctx.onImportPlan, primary: true },

            { id: "rbRefreshPlans", title: "Обновить", onClick: ctx.onRefreshPlans },

          ],

        },

        {

          label: "Документы",

          actions: [

            { id: "rbUploadFolder", title: "Папка", onClick: ctx.onBatchUpload, disabled: !planId },

            { id: "rbUploadRpd", title: "РПД", onClick: ctx.onUploadRpd, disabled: !planId },

            { id: "rbUploadFos", title: "ФОС", onClick: ctx.onUploadFos, disabled: !planId },

          ],

        },

        {

          label: "Сверка",

          actions: [

            { id: "rbValidateRpd", title: ctx.validationRunning ? "… РПД" : "РПД", onClick: ctx.onValidateRpd, disabled: !!ctx.validateDisabled, primary: true },

            { id: "rbValidateFos", title: ctx.validationRunning ? "… ФОС" : "ФОС", onClick: ctx.onValidateFos, disabled: !!ctx.validateDisabled },

            { id: "rbReportHtml", title: "Отчёт HTML", onClick: ctx.onValidationReport, disabled: !planId },

            { id: "rbReportJson", title: "Отчёт JSON", onClick: ctx.onValidationReportJson, disabled: !planId },

          ],

        },

        {

          label: "Выгрузка",

          actions: [

            { id: "rbExportRpdOk", title: "РПД (без ошибок)", onClick: ctx.onExportRpdOk, disabled: !!ctx.exportRpdDisabled },

            { id: "rbExportFosOk", title: "ФОС (без ошибок)", onClick: ctx.onExportFosOk, disabled: !!ctx.exportFosDisabled },

            { id: "rbExportRpdAll", title: "РПД все", onClick: ctx.onExportRpdAll, disabled: !ctx.planId },

            { id: "rbExportFosAll", title: "ФОС все", onClick: ctx.onExportFosAll, disabled: !ctx.planId },

          ],

        },

        reports,

      ];

    }



    if (page === "editor") {

      return [

        {

          label: "Документ",

          actions: [

            { id: "rbOpenFile", title: "Открыть", onClick: ctx.onOpenFile },

            { id: "rbSave", title: "Сохранить", onClick: ctx.onSave, primary: true, disabled: !docId },

            { id: "rbExportDoc", title: "Экспорт DOCX", onClick: ctx.onExport, disabled: !docId },

          ],

        },

      ];

    }



    if (page === "reference") {

      return [];

    }



    return [

      {

        label: "План",

        actions: [

          { id: "rbImport", title: "Импорт УП", onClick: ctx.onImportPlan, primary: true },

          { id: "rbRefreshTree", title: "Обновить", onClick: ctx.onRefreshTree },

        ],

      },

      {

        label: "Дисциплина",

        actions: [

          { id: "rbEditor", title: "Редактор", onClick: ctx.onOpenEditor, disabled: !ctx.hasDoc },

          { id: "rbValidation", title: "Сверка", onClick: ctx.onOpenValidation, disabled: !planId },

          { id: "rbTakeLock", title: "Запись", onClick: ctx.onTakeLock, disabled: !ctx.canLock },

        ],

      },

      reports,

      exportGroup,

    ];

  },



  initPage(page, ctx = {}, containerId = "appRibbon") {

    this.mountHeader(page, ctx.header || {});

    this.bindHeaderAuth(ctx.header || {});

    const ribbon = document.getElementById(containerId);

    if (page === "reference" && ribbon) {

      ribbon.setAttribute("data-hidden", "true");

      ribbon.innerHTML = "";

      return;

    }

    this.mountRibbon(ribbon, this.buildGroups(page, ctx));

  },

};



document.addEventListener("DOMContentLoaded", () => {

  if (document.querySelector(".app-header") && !window.SyllabusEmbed) {

    SyllabusShell.ensureHeaderStructure();

    SyllabusShell.bindHeaderAuth();

  }

});

