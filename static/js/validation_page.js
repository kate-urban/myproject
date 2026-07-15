/** Основная логика страницы /validation. */
    const API = "/api/v1";
    let selectedPlanId = null;
    let disciplines = [];
    let lastRpdReport = null;
    let lastFosReport = null;
    let exportSummary = null;
    let batchRunning = false;
    let allPlans = [];
    let planNavData = null;
    let appConfig = null;
    const navExpanded = SyllabusPlansNav.createExpandedState("validation_nav_expanded");

    const docEditorState = {
      docId: null,
      kind: null,
      disciplineId: null,
      disciplineCode: "",
      sections: [],
      selectedSectionId: null,
      validation: null,
      sectionRuleMap: new Map(),
      collapsedNodes: new Set(),
      activeRuleId: null,
      issuesCollapsed: false,
      sectionsCollapsed: false,
      focusMode: false,
    };
    let docEditorReady = false;
    let docEditorInitPromise = null;

    function toast(msg, isError = false) {
      const el = document.getElementById("toast");
      el.textContent = msg;
      el.classList.toggle("error", isError);
      el.classList.add("show");
      setTimeout(() => el.classList.remove("show"), isError ? 12000 : 4000);
    }

    const LINK_MESSAGES = {
      discipline_not_in_plan: (code) =>
        `Дисциплина ${code || "—"} не найдена в выбранном учебном плане.\n` +
        `Проверьте: выбран ли нужный план слева (подсвечен синим) и файл от той же программы.`,
      discipline_code_not_found:
        "Не удалось определить шифр дисциплины из файла. Имя должно содержать код, например FTD_01_... или B1_O_01_07_...",
      study_plan_not_found: "Учебный план не найден. Обновите страницу (Ctrl+F5).",
    };

    function linkErrorText(link) {
      if (!link) return "Файл не привязан к дисциплине.";
      if (link.message && link.message !== link.reason) return link.message;
      const fn = LINK_MESSAGES[link.reason];
      if (fn) return fn(link.discipline_code);
      return link.reason || "Файл не привязан к дисциплине.";
    }

    function showErrorPanel(text) {
      const panel = document.getElementById("errorPanel");
      if (!panel) return;
      panel.textContent = text;
      panel.style.display = "block";
    }

    function hideErrorPanel() {
      const panel = document.getElementById("errorPanel");
      if (panel) panel.style.display = "none";
    }

    async function api(path, options = {}) {
      const headers = { ...SyllabusAuth.authHeaders(), ...(options.headers || {}) };
      if (!(options.body instanceof FormData) && !headers["Content-Type"] && options.body) {
        headers["Content-Type"] = "application/json";
      }
      const res = await fetch(API + path, { ...options, headers });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = await res.json();
          detail = SyllabusApi.errorFromResponse(res.statusText, j);
        } catch (_) {}
        throw new Error(detail);
      }
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("application/json")) return res.json();
      return res;
    }

    function esc(s) {
      return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
    }

    async function loadPlansListFallback() {
      const plans = await api("/study-plans/");
      allPlans = plans.map(p => ({
        id: String(p.id),
        direction_code: p.direction_code,
        direction_name: p.direction_name,
        profile_name: p.profile_name,
        source_file: p.source_file,
        form: p.form,
        year: p.year,
        disciplines_count: p.disciplines_count,
      }));
      renderPlanTree(null);
    }

    function plansNavOptions() {
      return {
        hideFiles: appConfig?.plans_auto_import !== false,
      };
    }

    function notifyPlanSync(sync) {
      if (!sync) return;
      if (sync.imported > 0) {
        toast(`Автоимпорт: ${sync.imported} план(ов) из папки «УЧЕБНЫЕ ПЛАНЫ»`);
      }
      if (sync.pending > 0) {
        toast(`В папке ещё ${sync.pending} новых файл(ов). Нажмите «Обновить» для продолжения импорта.`);
      }
      if (sync.errors?.length) {
        toast(`Не удалось импортировать ${sync.errors.length} файл(ов) из папки`, true);
      }
    }

    async function loadPlans() {
      hideErrorPanel();
      const list = document.getElementById("planList");
      if (appConfig?.plans_auto_import !== false && list) {
        list.innerHTML = '<div class="empty-state" style="padding:24px;margin:8px;border:none;background:transparent"><p>Импорт планов из папки…</p></div>';
      }
      try {
        planNavData = await api("/study-plans/navigation-tree/");
        allPlans = SyllabusPlansNav.flattenPlans(planNavData.tree);
        renderPlanTree(SyllabusPlansNav.filterTree(planNavData.tree, navSearchQuery()));
        notifyPlanSync(planNavData.sync);
      } catch (err) {
        try {
          planNavData = { root_exists: false, root: "УЧЕБНЫЕ ПЛАНЫ", tree: null };
          await loadPlansListFallback();
          toast(`Дерево папок недоступно: ${err.message}. Показан список планов из БД.`, true);
        } catch (fallbackErr) {
          toast(fallbackErr.message, true);
          showErrorPanel(fallbackErr.message);
        }
      }
    }

    function navSearchQuery() {
      return document.getElementById("planSearch")?.value || "";
    }

    function renderPlanTree(tree) {
      const list = document.getElementById("planList");
      const query = navSearchQuery();
      if (!planNavData?.root_exists) {
        list.innerHTML = SyllabusPlansNav.renderMissingRootHtml(planNavData, allPlans, selectedPlanId);
        SyllabusPlansNav.bindTree(list, navExpanded, {
          onPlanSelect: id => selectPlan(id),
        });
        return;
      }
      if (!tree) {
        list.innerHTML = '<div class="empty-state" style="padding:24px;margin:8px;border:none;background:transparent"><p>Ничего не найдено</p></div>';
        return;
      }
      list.innerHTML = SyllabusPlansNav.renderTreeHtml(tree, navExpanded, {
        rootTitle: planNavData.root,
        selectedPlanId,
        query,
        ...plansNavOptions(),
      });
      bindPlanTreeEvents(list);
    }

    function bindPlanTreeEvents(root) {
      const callbacks = {
        onPlanSelect: id => selectPlan(id),
        onRerender: () => renderPlanTree(SyllabusPlansNav.filterTree(planNavData.tree, navSearchQuery())),
      };
      if (appConfig?.plans_auto_import === false) {
        callbacks.onFileImport = path => importPlanFromFolder(path);
      }
      SyllabusPlansNav.bindTree(root, navExpanded, callbacks);
    }

    async function importPlanFromFolder(relativePath) {
      try {
        toast("Импорт учебного плана…");
        const plan = await api(
          `/study-plans/import-from-folder/?relative_path=${encodeURIComponent(relativePath)}`,
          { method: "POST" }
        );
        await loadPlans();
        await selectPlan(plan.id);
        toast(`Импортирован: ${plan.source_file}`);
      } catch (err) {
        toast(err.message, true);
      }
    }

    async function selectPlan(planId) {
      selectedPlanId = planId;
      exportSummary = null;
      hideErrorPanel();
      if (planNavData?.tree) {
        renderPlanTree(SyllabusPlansNav.filterTree(planNavData.tree, navSearchQuery()));
      }
      const plan = await api(`/study-plans/${planId}/`);
      disciplines = await api(`/study-plans/${planId}/disciplines/`);
      lastRpdReport = null;
      lastFosReport = null;
      renderPlan(plan);
    }

    function lockBadge(discipline) {
      if (!discipline.lock_holder) return "";
      return `<span class="badge busy" title="Редактирует ${esc(discipline.lock_holder)}">🔒 ${esc(discipline.lock_holder)}</span>`;
    }

    function docBadge(docId, kind, discipline) {
      if (!docId) return '<span class="badge no">нет</span>';
      const label = kind === "fos" ? "ФОС" : "РПД";
      const item = getCachedValidationItem(discipline.id, kind);
      const validated = isValidationReportReady(kind);

      if (!validated) {
        return `<button type="button" class="badge pending doc-open-btn"
          data-doc-id="${docId}" data-kind="${kind}"
          data-discipline-id="${discipline.id}" data-discipline-code="${esc(discipline.code)}"
          title="Документ загружен — нажмите «Сверка ${kind === "rpd" ? "РПД" : "ФОС"}»">${label}</button>`;
      }

      if (!item || item.skipped) {
        return `<button type="button" class="badge no doc-open-btn"
          data-doc-id="${docId}" data-kind="${kind}"
          data-discipline-id="${discipline.id}" data-discipline-code="${esc(discipline.code)}"
          title="Сверка не выполнялась для этой дисциплины">—</button>`;
      }

      const fails = countFailedRules(item);
      if (!item.passed && fails > 0) {
        return `<button type="button" class="badge fail doc-open-btn"
          data-doc-id="${docId}" data-kind="${kind}"
          data-discipline-id="${discipline.id}" data-discipline-code="${esc(discipline.code)}"
          title="Ошибок сверки: ${fails}. Нажмите, чтобы открыть и исправить">${label} ${fails}</button>`;
      }

      if (item.passed) {
        return `<button type="button" class="badge ok doc-open-btn"
          data-doc-id="${docId}" data-kind="${kind}"
          data-discipline-id="${discipline.id}" data-discipline-code="${esc(discipline.code)}"
          title="Сверка пройдена">${label} ✓</button>`;
      }

      return `<button type="button" class="badge fail doc-open-btn"
        data-doc-id="${docId}" data-kind="${kind}"
        data-discipline-id="${discipline.id}" data-discipline-code="${esc(discipline.code)}"
        title="Есть ошибки сверки">${label} !</button>`;
    }

    function countFailedRules(item) {
      if (!item || !item.results) return 0;
      return item.results.filter(r => !r.skipped && r.severity === "critical" && !r.passed).length;
    }

    function isValidationReportReady(kind) {
      const report = kind === "rpd" ? lastRpdReport : lastFosReport;
      return !!(report && report.items && report.items.length);
    }

    function disciplineHasValidationErrors(d) {
      const rpd = getCachedValidationItem(d.id, "rpd");
      const fos = getCachedValidationItem(d.id, "fos");
      const rpdBad = rpd && !rpd.passed && !rpd.skipped && countFailedRules(rpd) > 0;
      const fosBad = fos && !fos.passed && !fos.skipped && countFailedRules(fos) > 0;
      return rpdBad || fosBad;
    }

    function getCachedValidationItem(disciplineId, kind) {
      const report = kind === "rpd" ? lastRpdReport : lastFosReport;
      if (!report || !report.items) return null;
      return report.items.find(i => String(i.discipline_id) === String(disciplineId)) || null;
    }

    function updateCachedValidationItem(disciplineId, kind, item) {
      let report = kind === "rpd" ? lastRpdReport : lastFosReport;
      if (!report) {
        report = { items: [] };
        if (kind === "rpd") lastRpdReport = report;
        else lastFosReport = report;
      }
      const idx = report.items.findIndex(i => String(i.discipline_id) === String(disciplineId));
      if (idx >= 0) report.items[idx] = item;
      else report.items.push(item);
    }

    function renderPlan(plan) {
      const main = document.getElementById("main");
      const rows = disciplines.map(d => disciplineRowHtml(d)).join("");

      main.innerHTML = `
        <div id="errorPanel" class="error-panel"></div>
        <div class="plan-hero">
          <div class="eyebrow">Учебный план</div>
          <h2>${esc(plan.direction_name)}</h2>
          <p>${esc(plan.profile_name)} · ${esc(plan.form)} ${plan.year || ""}</p>
          <div class="plan-hero-tags">
            <span class="plan-tag">${esc(plan.direction_code)}</span>
            <span class="plan-tag">${esc(plan.source_file)}</span>
            <span class="plan-tag">${disciplines.length} дисциплин</span>
          </div>
        </div>
        <div class="action-bar">
          <div class="action-group">
            <span class="action-label">Загрузка документов</span>
            <label class="btn primary" for="uploadFolder" title="Все .doc и .docx из папки (РПД и FOS_*.docx автоматически)">📁 Загрузить папку</label>
            <input type="file" id="uploadFolder" accept=".doc,.docx" webkitdirectory hidden>
            <label class="btn" for="uploadRpd" title="Один файл РПД">+ РПД</label>
            <input type="file" id="uploadRpd" accept=".doc,.docx" hidden>
            <label class="btn" for="uploadFos" title="Один файл FOS_*.docx">+ ФОС</label>
            <input type="file" id="uploadFos" accept=".doc,.docx" hidden>
          </div>
          <div class="action-divider"></div>
          <div class="action-group">
            <span class="action-label">Сверка и отчёты</span>
            <button class="btn success" id="btnValidateRpd" type="button">▶ Сверка РПД</button>
            <button class="btn success" id="btnValidateFos" type="button">▶ Сверка ФОС</button>
            <button class="btn" id="btnReportJson" type="button">JSON</button>
            <button class="btn" id="btnReportHtml" type="button">HTML</button>
          </div>
          <div class="action-divider"></div>
          <div class="action-group">
            <span class="action-label">Экспорт DOCX</span>
            <button class="btn primary" id="btnExportPassedRpd" type="button" disabled title="Сначала выполните сверку РПД">⬇ РПД (OK)</button>
            <button class="btn primary" id="btnExportPassedFos" type="button" disabled title="Сначала выполните сверку ФОС">⬇ ФОС (OK)</button>
          </div>
        </div>
        <details class="help-panel">
          <summary>Как работать со сверкой</summary>
          <div class="help-body">
            1) Выберите учебный план слева, нажмите «📁 Загрузить папку» и укажите каталог с .doc/.docx
            (например <code>samples/ИЛИП … 05.03.06</code>) — старые .doc конвертируются в .docx автоматически.<br>
            2) Файлы без префикса <code>FOS_</code> — это <strong>РПД</strong>, с префиксом <code>FOS_</code> — <strong>ФОС</strong>
            (разные документы: программа дисциплины и фонд оценочных средств).<br>
            3) Нажмите «Сверка РПД» / «Сверка ФОС» — в таблице появятся цветные метки.<br>
            4) Клик по РПД/ФОС откроет редактор с подсветкой ошибок.<br>
            5) После правки: «Сохранить раздел» → «Повторить сверку».<br>
            6) Если сверка OK — «⬇ РПД (OK)» / «⬇ ФОС (OK)» скачает DOCX по макету FGOS.
            <div class="legend">
              <span class="badge pending">РПД</span> не проверено ·
              <span class="badge ok">РПД ✓</span> OK ·
              <span class="badge fail">РПД 2</span> ошибки
            </div>
          </div>
        </details>
        <div class="batch-panel" id="batchPanel">
          <h4 id="batchTitle">Пакетная загрузка</h4>
          <div id="batchStatus" style="color:var(--muted);margin-bottom:4px"></div>
          <div class="batch-progress"><div class="batch-progress-bar" id="batchBar"></div></div>
          <div class="batch-log" id="batchLog"></div>
        </div>
        <div class="stats" id="stats"></div>
        <div class="table-card">
          <div class="table-head-bar">
            <h3>Сводная таблица</h3>
            <span style="font-size:12px;color:var(--muted)">Год утверждения и переутверждение — из загруженной РПД</span>
          </div>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Шифр</th><th>Дисциплина</th><th>з.е.</th><th>РПД</th><th>ФОС</th><th>Год утв.</th><th>Переутверждение</th><th></th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
        <div class="report-panel" id="reportPanel" style="display:none"></div>
      `;

      document.getElementById("btnValidateRpd").onclick = () => runValidation("rpd");
      document.getElementById("btnValidateFos").onclick = () => runValidation("fos");
      document.getElementById("btnReportJson").onclick = () => downloadReport("json");
      document.getElementById("btnReportHtml").onclick = () => downloadReport("html");
      document.getElementById("btnExportPassedRpd").onclick = () => downloadPlanExport("rpd");
      document.getElementById("btnExportPassedFos").onclick = () => downloadPlanExport("fos");

      const bindUpload = (inputId) => {
        const el = document.getElementById(inputId);
        if (!el) return;
        el.onchange = async e => {
          const file = e.target.files[0];
          if (!file) return;
          await uploadDoc(file);
          e.target.value = "";
        };
      };
      bindUpload("uploadRpd");
      bindUpload("uploadFos");
      bindBatchUpload("uploadFolder");

      bindRowUploadInputs(main);
      bindDocOpenButtons(main);
      bindExportButtons(main);
      updateExportButtons();
    }

    function formatApprovalYear(d) {
      if (!d.document_id) return "—";
      return d.rpd_approval_year ?? "—";
    }

    function formatReapproval(d) {
      if (!d.document_id) return "—";
      if (d.rpd_reapproval_years && d.rpd_reapproval_years.length) {
        return d.rpd_reapproval_years.join(", ");
      }
      if (d.rpd_has_reapproval_section) return "нет";
      return "—";
    }

    function exportBtnHtml(d, kind) {
      const item = getCachedValidationItem(d.id, kind);
      const hasDoc = kind === "rpd" ? d.document_id : d.fos_document_id;
      if (!hasDoc || !item || !item.passed || item.skipped) return "";
      return `<button type="button" class="btn sm export-one-btn" data-export-kind="${kind}" data-discipline-id="${d.id}" title="Скачать ${kind === "rpd" ? "РПД" : "ФОС"} DOCX">⬇</button>`;
    }

    function disciplineRowHtml(d) {
      const rowClass = disciplineHasValidationErrors(d) ? ' class="row-has-errors"' : "";
      return `
        <tr${rowClass}>
          <td><code>${esc(d.code)}</code></td>
          <td>${esc(d.name)}</td>
          <td>${d.credits ?? "—"}</td>
          <td>${docBadge(d.document_id, "rpd", d)} ${lockBadge(d)} ${exportBtnHtml(d, "rpd")}</td>
          <td>${docBadge(d.fos_document_id, "fos", d)} ${exportBtnHtml(d, "fos")}</td>
          <td>${formatApprovalYear(d)}</td>
          <td>${formatReapproval(d)}</td>
          <td>
            <label class="btn sm" title="Загрузить файл для этой дисциплины">
              ＋<input type="file" accept=".docx" hidden data-upload="${d.id}">
            </label>
          </td>
        </tr>
      `;
    }

    function bindExportButtons(root) {
      (root || document).querySelectorAll(".export-one-btn").forEach(btn => {
        btn.onclick = () => downloadDisciplineExport(btn.dataset.disciplineId, btn.dataset.exportKind);
      });
    }

    function bindDocOpenButtons(root) {
      (root || document).querySelectorAll(".doc-open-btn").forEach(btn => {
        btn.onclick = () => openDocumentEditor({
          docId: btn.dataset.docId,
          kind: btn.dataset.kind,
          disciplineId: btn.dataset.disciplineId,
          disciplineCode: btn.dataset.disciplineCode,
        });
      });
    }

    function bindRowUploadInputs(root) {
      (root || document).querySelectorAll("input[data-upload]").forEach(input => {
        input.addEventListener("change", async e => {
          const file = e.target.files[0];
          if (!file) return;
          await uploadDoc(file);
          e.target.value = "";
        });
      });
    }

    async function refreshPlanData() {
      if (!selectedPlanId) return;
      disciplines = await api(`/study-plans/${selectedPlanId}/disciplines/`);
      renderStats();
      const tbody = document.querySelector("#main table tbody");
      if (tbody) {
        tbody.innerHTML = disciplines.map(disciplineRowHtml).join("");
        bindRowUploadInputs(tbody);
        bindDocOpenButtons(tbody);
        bindExportButtons(tbody);
      }
      updateExportButtons();
    }

    function updateExportButtons() {
      const rpdBtn = document.getElementById("btnExportPassedRpd");
      const fosBtn = document.getElementById("btnExportPassedFos");
      const rpdCount = exportSummary?.rpd_passed ?? lastRpdReport?.passed ?? 0;
      const fosCount = exportSummary?.fos_passed ?? lastFosReport?.passed ?? 0;
      if (rpdBtn) {
        rpdBtn.disabled = !selectedPlanId || rpdCount <= 0;
        rpdBtn.textContent = rpdCount > 0 ? `⬇ РПД (${rpdCount})` : "⬇ РПД (OK)";
      }
      if (fosBtn) {
        fosBtn.disabled = !selectedPlanId || fosCount <= 0;
        fosBtn.textContent = fosCount > 0 ? `⬇ ФОС (${fosCount})` : "⬇ ФОС (OK)";
      }
    }

    async function refreshExportSummary() {
      if (!selectedPlanId) return;
      try {
        exportSummary = await api(`/study-plans/${selectedPlanId}/export-summary/`);
      } catch (_) {
        exportSummary = null;
      }
      updateExportButtons();
    }

    async function downloadDisciplineExport(disciplineId, kind, force = false) {
      if (!selectedPlanId) return;
      const path = `/study-plans/${selectedPlanId}/disciplines/${disciplineId}/export/?kind=${kind}${force ? "&force=true" : ""}`;
      try {
        const res = await fetch(API + path, { headers: SyllabusAuth.authHeaders() });
        if (!res.ok) {
          let detail = res.statusText;
          try {
            const j = await res.json();
            detail = SyllabusApi.errorFromResponse(res.statusText, j);
          } catch (_) {}
          throw new Error(detail);
        }
        const blob = await res.blob();
        const cd = res.headers.get("Content-Disposition") || "";
        const match = cd.match(/filename="?([^";]+)"?/i);
        const filename = match ? match[1] : `${kind}_${disciplineId}.docx`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        toast(`Скачан ${kind.toUpperCase()}: ${filename}`);
      } catch (err) {
        toast(err.message, true);
      }
    }

    async function downloadPlanExport(kind) {
      if (!selectedPlanId) return;
      const path = `/study-plans/${selectedPlanId}/export-passed/?kind=${kind}`;
      try {
        toast(`Формирование ZIP (${kind.toUpperCase()})…`);
        const res = await fetch(API + path, { headers: SyllabusAuth.authHeaders() });
        if (!res.ok) {
          let detail = res.statusText;
          try {
            const j = await res.json();
            detail = SyllabusApi.errorFromResponse(res.statusText, j);
          } catch (_) {}
          throw new Error(detail);
        }
        const blob = await res.blob();
        const count = res.headers.get("X-Exported-Count") || "?";
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `export_${kind}_${selectedPlanId}.zip`;
        a.click();
        URL.revokeObjectURL(url);
        toast(`ZIP: ${count} документ(ов) ${kind.toUpperCase()}`);
      } catch (err) {
        toast(err.message, true);
      }
    }

    function renderStats() {
      const stats = document.getElementById("stats");
      if (!stats) return;
      const withRpd = disciplines.filter(d => d.document_id).length;
      const withFos = disciplines.filter(d => d.fos_document_id).length;
      stats.innerHTML = `
        <div class="stat accent"><div class="label">Дисциплин</div><div class="value">${disciplines.length}</div></div>
        <div class="stat"><div class="label">С РПД</div><div class="value">${withRpd}</div></div>
        <div class="stat"><div class="label">С ФОС</div><div class="value">${withFos}</div></div>
        <div class="stat ${lastRpdReport && lastRpdReport.failed ? "fail" : "ok"}"><div class="label">РПД OK</div><div class="value">${lastRpdReport ? lastRpdReport.passed : "—"}</div></div>
        <div class="stat ${lastFosReport && lastFosReport.failed ? "fail" : "ok"}"><div class="label">ФОС OK</div><div class="value">${lastFosReport ? lastFosReport.passed : "—"}</div></div>
        ${exportSummary ? `<div class="stat ok"><div class="label">К экспорту РПД</div><div class="value">${exportSummary.rpd_passed}</div></div>` : ""}
      `;
      updateExportButtons();
    }

    function isFosFilename(name) {
      const base = String(name).split(/[/\\]/).pop() || "";
      const stem = base.replace(/\.docx$/i, "");
      return stem.toUpperCase().startsWith("FOS_");
    }

    function filterBatchFiles(fileList) {
      return [...fileList].filter(f => /\.(docx?|DOCX?)$/.test(f.name));
    }

    function setToolbarDisabled(disabled) {
      document.querySelectorAll(".toolbar .btn, .toolbar label.btn").forEach(el => {
        if (el.tagName === "LABEL") {
          const input = el.htmlFor ? document.getElementById(el.htmlFor) : null;
          if (input) input.disabled = disabled;
        } else {
          el.disabled = disabled;
        }
      });
    }

    function showBatchPanel(title) {
      const panel = document.getElementById("batchPanel");
      if (!panel) return;
      panel.classList.add("active");
      document.getElementById("batchTitle").textContent = title;
      document.getElementById("batchStatus").textContent = "";
      document.getElementById("batchBar").style.width = "0%";
      document.getElementById("batchLog").innerHTML = "";
    }

    function appendBatchLog(html) {
      const log = document.getElementById("batchLog");
      if (log) log.insertAdjacentHTML("beforeend", html + "<br>");
    }

    function bindBatchUpload(inputId) {
      const el = document.getElementById(inputId);
      if (!el) return;
      el.onchange = async e => {
        const files = e.target.files;
        if (!files || !files.length) return;
        await runBatchUpload(files);
        e.target.value = "";
      };
    }

    async function runBatchUpload(fileList) {
      if (!selectedPlanId) {
        toast("Сначала выберите учебный план слева (клик по строке в списке)", true);
        return;
      }
      if (batchRunning) {
        toast("Уже идёт пакетная загрузка", true);
        return;
      }

      const files = filterBatchFiles(fileList);
      if (!files.length) {
        toast("В папке нет файлов .doc или .docx", true);
        return;
      }

      hideErrorPanel();
      batchRunning = true;
      setToolbarDisabled(true);
      showBatchPanel(`Загрузка папки (${files.length} файлов)`);

      const summary = { linked: 0, unlinked: 0, errors: 0 };
      const total = files.length;

      try {
        for (let i = 0; i < total; i++) {
          const file = files[i];
          const pct = Math.round(((i + 1) / total) * 100);
          document.getElementById("batchStatus").textContent =
            `Файл ${i + 1} из ${total}: ${file.name}`;
          document.getElementById("batchBar").style.width = pct + "%";

          const result = await uploadDocOne(file);
          if (!result.ok) {
            summary.errors++;
            appendBatchLog(`<span class="fail">✗ ${esc(result.file)} — ${esc(result.error)}</span>`);
            continue;
          }

          const link = result.link;
          if (link && link.linked) {
            summary.linked++;
            appendBatchLog(
              `<span class="ok">✓ ${esc(result.file)} → ${esc(link.discipline_code)} (${esc(link.doc_kind || "docx")})</span>`
            );
          } else if (link) {
            summary.unlinked++;
            appendBatchLog(
              `<span class="warn">⚠ ${esc(result.file)} — ${esc(linkErrorText(link))}</span>`
            );
          } else {
            summary.unlinked++;
            appendBatchLog(`<span class="warn">⚠ ${esc(result.file)} — не привязан к плану</span>`);
          }
        }

        document.getElementById("batchStatus").textContent =
          `Готово: привязано ${summary.linked}, без привязки ${summary.unlinked}, ошибок ${summary.errors} (всего ${total})`;
        document.getElementById("batchBar").style.width = "100%";

        if (summary.errors || summary.unlinked) {
          toast(`Пакет завершён: OK ${summary.linked}, проблем ${summary.unlinked + summary.errors}`, true);
        } else {
          toast(`Папка загружена: ${summary.linked} документов`);
        }
      } catch (err) {
        appendBatchLog(`<span class="fail">✗ ${esc(err.message)}</span>`);
        toast(err.message, true);
      } finally {
        batchRunning = false;
        setToolbarDisabled(false);
        await refreshPlanData();
      }
    }

    async function uploadDocOne(file) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("study_plan_id", selectedPlanId);
      try {
        const doc = await api("/upload/", { method: "POST", body: fd });
        return { ok: true, file: file.name, link: doc.program_link };
      } catch (err) {
        return { ok: false, file: file.name, error: err.message };
      }
    }

    async function uploadDoc(file) {
      if (!selectedPlanId) {
        toast("Сначала выберите учебный план слева (клик по строке в списке)", true);
        return;
      }
      hideErrorPanel();
      const result = await uploadDocOne(file);
      if (!result.ok) {
        showErrorPanel(result.error);
        toast(result.error, true);
        return;
      }
      const link = result.link;
      if (link && link.linked) {
        toast(`Привязано: ${link.discipline_code} (${link.doc_kind || "docx"})`);
        await selectPlan(selectedPlanId);
      } else if (link) {
        const text = linkErrorText(link);
        showErrorPanel(text);
      } else {
        toast("Документ сохранён, но не привязан к плану.", true);
      }
    }

    async function getDisciplineValidation(disciplineId, kind) {
      const cached = getCachedValidationItem(disciplineId, kind);
      if (cached) return cached;
      try {
        const path = kind === "rpd"
          ? `/study-plans/${selectedPlanId}/disciplines/${disciplineId}/validate/`
          : `/study-plans/${selectedPlanId}/disciplines/${disciplineId}/validate-fos/`;
        return await api(path);
      } catch (_) {
        return null;
      }
    }

    async function runValidation(kind) {
      if (!selectedPlanId) return;
      const path = kind === "rpd"
        ? `/study-plans/${selectedPlanId}/validate/`
        : `/study-plans/${selectedPlanId}/validate-fos/`;
      const report = await api(path);
      if (kind === "rpd") lastRpdReport = report;
      else lastFosReport = report;
      renderStats();
      renderReportPanel(kind, report);
      await refreshPlanData();
      await refreshExportSummary();
      toast(kind === "rpd" ? "Сверка РПД завершена" : "Сверка ФОС завершена");
    }

    function renderReportPanel(kind, report) {
      const panel = document.getElementById("reportPanel");
      panel.style.display = "block";
      const title = kind === "rpd" ? "Результаты сверки РПД ↔ УП" : "Результаты сверки ФОС ↔ УП/РПД";
      const summary = kind === "rpd"
        ? `Проверено ${report.checked}, OK ${report.passed}, ошибок ${report.failed}, без РПД ${report.missing_rpd}`
        : `Проверено ${report.checked}, OK ${report.passed}, ошибок ${report.failed}, без ФОС ${report.missing_fos}`;

      const items = (report.items || []).map(item => {
        const failed = (item.results || []).filter(r => !r.skipped && r.severity === "critical" && !r.passed);
        const rules = failed.length
          ? failed.map(r => formatReportRuleDetail(r, kind)).join("")
          : `<div class="rule-ok">${item.skipped ? "пропущено" : "OK"}</div>`;
        const openBtns = [];
        const disc = disciplines.find(d => String(d.id) === String(item.discipline_id));
        if (disc && disc.document_id && kind === "rpd") {
          openBtns.push(`<button type="button" class="link-open" data-open-doc="${disc.document_id}" data-open-kind="rpd" data-discipline-id="${disc.id}" data-discipline-code="${esc(disc.code)}">РПД</button>`);
        }
        if (disc && disc.fos_document_id && kind === "fos") {
          openBtns.push(`<button type="button" class="link-open" data-open-doc="${disc.fos_document_id}" data-open-kind="fos" data-discipline-id="${disc.id}" data-discipline-code="${esc(disc.code)}">ФОС</button>`);
        }
        const openCell = openBtns.length
          ? openBtns.join(" · ")
          : '<span style="color:var(--muted)">—</span>';
        return `<tr>
          <td>${esc(item.discipline_code)}</td>
          <td>${item.passed ? '<span class="badge ok">OK</span>' : '<span class="badge fail">FAIL</span>'}</td>
          <td>${rules}</td>
          <td>${openCell}</td>
        </tr>`;
      }).join("");

      panel.innerHTML = `
        <h3>${title}</h3>
        <p style="color:var(--muted);margin-bottom:8px">${summary}</p>
        <table><thead><tr><th>Дисциплина</th><th>Статус</th><th>Правила</th><th>Открыть</th></tr></thead><tbody>${items || "<tr><td colspan=4>Нет проверенных дисциплин</td></tr>"}</tbody></table>
      `;
      panel.querySelectorAll(".link-open").forEach(btn => {
        btn.onclick = () => openDocumentEditor({
          docId: btn.dataset.openDoc,
          kind: btn.dataset.openKind,
          disciplineId: btn.dataset.disciplineId,
          disciplineCode: btn.dataset.disciplineCode,
        });
      });
    }

    function downloadReport(format) {
      if (!selectedPlanId) return;
      window.open(`${API}/study-plans/${selectedPlanId}/validation-report/?format=${format}`, "_blank");
    }

    document.getElementById("importPlx").addEventListener("change", async e => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      toast("Импорт учебного плана…");
      try {
        const plan = await api("/study-plans/import/", { method: "POST", body: fd });
        toast(`Импортирован: ${plan.direction_code} · ${plan.profile_name}`);
        selectedPlanId = plan.id;
        await loadPlans();
        await selectPlan(plan.id);
      } catch (err) {
        toast(err.message, true);
        showErrorPanel(err.message);
      }
      e.target.value = "";
    });

    document.getElementById("refreshPlans").onclick = loadPlans;
    document.getElementById("planSearch")?.addEventListener("input", () => {
      renderPlanTree(SyllabusPlansNav.filterTree(planNavData?.tree, navSearchQuery()));
    });

    (async () => {
      if (!(await SyllabusAuth.requireAuth("/"))) return;
      try {
        appConfig = await SyllabusAuth.getConfig();
      } catch (_) {
        appConfig = { plans_auto_import: true };
      }
      loadPlans().catch(err => toast(err.message, true));
    })();

