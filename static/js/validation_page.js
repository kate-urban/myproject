/** Основная логика страницы /validation. */
    const API = "/api/v1";
    let selectedPlanId = null;
    let currentPlan = null;
    let disciplines = [];
    let lastRpdReport = null;
    let lastFosReport = null;
    let exportSummary = null;
    let batchRunning = false;
    let allPlans = [];
    let planNavData = null;
    let planLoading = false;
    let validationRunning = false;
    const navExpanded = SyllabusPlansNav.createExpandedState("validation_nav_expanded");

    const docEditorState = {
      docId: null,
      programId: null,
      kind: null,
      disciplineId: null,
      disciplineCode: "",
      editorMode: "sections",
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
    let planLoadSeq = 0;

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

    async function loadPlans({ sync = false } = {}) {
      hideErrorPanel();
      const list = document.getElementById("planList");
      if (sync && list) {
        list.innerHTML = '<div class="empty-state" style="padding:24px;margin:8px;border:none;background:transparent"><p>Импорт планов из папки…</p></div>';
      }
      try {
        const navPath = sync ? "/study-plans/navigation-tree/?sync=true" : "/study-plans/navigation-tree/";
        planNavData = await api(navPath);
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

    function refreshRibbon() {
      const rpdCount = exportReadyCount("rpd");
      const fosCount = exportReadyCount("fos");
      const validateDisabled = !selectedPlanId || planLoading || validationRunning;
      SyllabusShell.initPage("validation", {
        planId: selectedPlanId,
        directionCode: currentPlan?.direction_code,
        year: currentPlan?.year,
        validateDisabled,
        validationRunning,
        header: {
          context: currentPlan
            ? `${currentPlan.direction_code || ""} · ${currentPlan.profile_name || ""}`
            : "",
        },
        exportRpdDisabled: !selectedPlanId || rpdCount <= 0,
        exportFosDisabled: !selectedPlanId || fosCount <= 0,
        onImportPlan: () => document.getElementById("importPlx")?.click(),
        onBatchUpload: () => {
          if (!selectedPlanId) {
            toast("Сначала выберите учебный план", true);
            return;
          }
          document.getElementById("uploadFolder")?.click();
        },
        onUploadRpd: () => {
          if (!selectedPlanId) return toast("Сначала выберите учебный план", true);
          document.getElementById("uploadRpd")?.click();
        },
        onUploadFos: () => {
          if (!selectedPlanId) return toast("Сначала выберите учебный план", true);
          document.getElementById("uploadFos")?.click();
        },
        onRefreshPlans: () => loadPlans({ sync: true }),
        onValidateRpd: () => runValidation("rpd"),
        onValidateFos: () => runValidation("fos"),
        onValidationReport: () => downloadReport("html"),
        onValidationReportJson: () => downloadReport("json"),
        onExportRpdOk: () => downloadPlanExport("rpd"),
        onExportFosOk: () => downloadPlanExport("fos"),
        onExportRpdAll: () => downloadPlanExport("rpd", true),
        onExportFosAll: () => downloadPlanExport("fos", true),
      });
    }

    async function selectPlan(planId) {
      const loadId = ++planLoadSeq;
      selectedPlanId = planId;
      exportSummary = null;
      hideErrorPanel();
      planLoading = true;
      refreshRibbon();
      if (planNavData?.tree) {
        renderPlanTree(SyllabusPlansNav.filterTree(planNavData.tree, navSearchQuery()));
      }
      try {
        const plan = await api(`/study-plans/${planId}/`);
        if (loadId !== planLoadSeq || String(selectedPlanId) !== String(planId)) return;

        currentPlan = plan;
        const disc = await api(`/study-plans/${planId}/disciplines/`);
        if (loadId !== planLoadSeq || String(selectedPlanId) !== String(planId)) return;

        disciplines = disc;
        lastRpdReport = null;
        lastFosReport = null;
        document.getElementById("validationBanner")?.classList.add("hidden");
        renderPlan(plan);
        refreshRibbon();
        await maybeOpenStructuredDeepLink();
      } catch (err) {
        if (loadId !== planLoadSeq) return;
        toast(err.message, true);
        showErrorPanel(err.message);
      } finally {
        if (loadId === planLoadSeq) {
          planLoading = false;
          refreshRibbon();
        }
      }
    }

    let structuredDeepLinkHandled = false;

    async function maybeOpenStructuredDeepLink() {
      if (structuredDeepLinkHandled) return;
      const hp = SyllabusShell.parseHashParams();
      if (hp.mode !== "structured" || !hp.discipline) return;
      const disc = disciplines.find(row => row.id === hp.discipline);
      if (!disc?.document_id) return;
      structuredDeepLinkHandled = true;
      await openDocumentEditor({
        docId: disc.document_id,
        kind: "rpd",
        disciplineId: disc.id,
        disciplineCode: disc.code,
        programId: disc.program_id,
      });
      window.ValidationStructured?.setDocEditorMode("structured");
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
          title="Сверка пройдена">${label}</button>`;
      }

      return `<button type="button" class="badge fail doc-open-btn"
        data-doc-id="${docId}" data-kind="${kind}"
        data-discipline-id="${discipline.id}" data-discipline-code="${esc(discipline.code)}"
        title="Есть ошибки сверки">${label} !</button>`;
    }

    function countFailedRules(item) {
      if (!item || !item.results) return 0;
      return item.results.filter(
        r => !r.skipped && !r.passed && !r.waived && r.severity === "critical"
      ).length;
    }

    function recalculateReportTotals(report) {
      if (!report?.items) return;
      let passed = 0;
      let failed = 0;
      for (const item of report.items) {
        if (item.skipped) continue;
        if (item.passed) passed += 1;
        else failed += 1;
      }
      report.passed = passed;
      report.failed = failed;
    }

    function exportReadyCount(kind) {
      if (exportSummary) {
        return kind === "rpd"
          ? (exportSummary.rpd_passed ?? 0)
          : (exportSummary.fos_passed ?? 0);
      }
      const report = kind === "rpd" ? lastRpdReport : lastFosReport;
      if (!report?.items) return 0;
      return report.items.filter(i => i.passed && !i.skipped).length;
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
      recalculateReportTotals(report);
      refreshRibbon();
    }

    function renderPlan(plan) {
      const main = document.getElementById("main");
      const rows = disciplines.map(d => disciplineRowHtml(d)).join("");

      main.innerHTML = `
        <div id="errorPanel" class="error-panel"></div>
        <div class="plan-hero">
          <div class="eyebrow">Учебный план</div>
          <h2>${esc(plan.direction_name)}</h2>
          <p>${esc(plan.profile_name)} · ${esc(SyllabusUiRu.studyFormLabel(plan.form))} ${plan.year || ""}</p>
          <div class="plan-hero-tags">
            <span class="plan-tag">${esc(plan.direction_code)}</span>
            <span class="plan-tag">${esc(plan.source_file)}</span>
            <span class="plan-tag">${disciplines.length} дисциплин</span>
          </div>
        </div>
        <details class="help-panel">
          <summary>Как работать со сверкой</summary>
          <div class="help-body">
            1) Выберите учебный план слева. Импорт — «Импорт УП» на ленте.<br>
            2) Загрузка документов — «Папка», «РПД» или «ФОС» на ленте.<br>
            3) Файлы без префикса <code>FOS_</code> — РПД, с префиксом — ФОС.<br>
            4) «РПД» / «ФОС» в группе «Сверка» — метки в таблице.<br>
            5) Клик по ячейке РПД/ФОС откроет редактор; после правки — «Сохранить», затем «Сверка».<br>
            6) «DOCX» / «PDF» в строке — выгрузка одной дисциплины (ошибки не блокируют).<br>
            7) «РПД (без ошибок)» — только прошедшие сверку; «РПД все» — все документы.
            <div class="legend">
              <span class="badge pending">РПД</span> не проверено ·
              <span class="badge ok">РПД</span> без ошибок ·
              <span class="badge fail">РПД 2</span> ошибки
            </div>
          </div>
        </details>
        <div class="batch-panel" id="batchPanel">
          <h4 id="batchTitle">Пакетная загрузка</h4>
          <label class="batch-option" style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
            <input type="checkbox" id="propagateAllPlans" checked>
            Привязать ко всем планам направления (все годы и формы)
          </label>
          <div id="batchStatus" style="color:var(--muted);margin-bottom:4px"></div>
          <div class="batch-progress"><div class="batch-progress-bar" id="batchBar"></div></div>
          <div class="batch-log" id="batchLog"></div>
        </div>
        <div class="stats" id="stats"></div>
        <div class="validation-banner hidden" id="validationBanner" aria-live="polite"></div>
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
      `;

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

    function disciplineExportNeedsForce(disciplineId, kind) {
      const item = getCachedValidationItem(disciplineId, kind);
      if (!item || item.skipped) return true;
      return !item.passed;
    }

    function exportBtnHtml(d, kind) {
      const hasDoc = kind === "rpd" ? d.document_id : d.fos_document_id;
      if (!hasDoc) return "";
      const needsForce = disciplineExportNeedsForce(d.id, kind);
      const forceHint = needsForce ? " (игнорируя ошибки сверки)" : "";
      const label = kind === "rpd" ? "РПД" : "ФОС";
      return `<span class="export-btns">
        <button type="button" class="btn sm export-one-btn" data-export-kind="${kind}" data-discipline-id="${d.id}"
          data-export-format="docx" data-export-force="${needsForce ? "1" : "0"}"
          title="Скачать ${label} DOCX${forceHint}">DOCX</button>
        <button type="button" class="btn sm export-one-btn" data-export-kind="${kind}" data-discipline-id="${d.id}"
          data-export-format="pdf" data-export-force="${needsForce ? "1" : "0"}"
          title="PDF ${label}${forceHint}">PDF</button>
      </span>`;
    }

    function refreshDisciplineExportRow(disciplineId) {
      const d = disciplines.find(row => String(row.id) === String(disciplineId));
      const row = document.querySelector(`tr[data-discipline-id="${disciplineId}"]`);
      if (!d || !row) return;
      const cells = row.querySelectorAll("td");
      if (cells.length >= 5) {
        cells[3].innerHTML = `${docBadge(d.document_id, "rpd", d)} ${lockBadge(d)} ${exportBtnHtml(d, "rpd")}`;
        cells[4].innerHTML = `${docBadge(d.fos_document_id, "fos", d)} ${exportBtnHtml(d, "fos")}`;
        bindDocOpenButtons(row);
        bindExportButtons(row);
      }
    }

    function disciplineRowHtml(d) {
      const rowClass = disciplineHasValidationErrors(d) ? ' class="row-has-errors"' : "";
      return `
        <tr data-discipline-id="${d.id}"${rowClass}>
          <td><code>${esc(d.code)}</code></td>
          <td>${esc(d.name)}</td>
          <td>${d.credits ?? "—"}</td>
          <td>${docBadge(d.document_id, "rpd", d)} ${lockBadge(d)} ${exportBtnHtml(d, "rpd")}</td>
          <td>${docBadge(d.fos_document_id, "fos", d)} ${exportBtnHtml(d, "fos")}</td>
          <td>${formatApprovalYear(d)}</td>
          <td>${formatReapproval(d)}</td>
          <td>
            ${d.program_id && selectedPlanId ? `<a class="btn sm" href="/?#plan=${encodeURIComponent(selectedPlanId)}&discipline=${encodeURIComponent(d.id)}" title="Переутверждение">Переутв.</a>` : ""}
            <label class="btn sm" title="Загрузить файл">
              Файл<input type="file" accept=".docx" hidden data-upload="${d.id}">
            </label>
          </td>
        </tr>
      `;
    }

    function bindExportButtons(root) {
      (root || document).querySelectorAll(".export-one-btn").forEach(btn => {
        btn.onclick = () => {
          const force = btn.dataset.exportForce === "1";
          const format = btn.dataset.exportFormat || "docx";
          if (format === "pdf") {
            downloadDisciplinePdf(btn.dataset.disciplineId, btn.dataset.exportKind, force);
          } else {
            downloadDisciplineExport(btn.dataset.disciplineId, btn.dataset.exportKind, force);
          }
        };
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
      refreshRibbon();
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
      if (window.ValidationEditor?.isEditorOpenForDiscipline?.(disciplineId)) {
        try {
          toast("Сохраняем правки из редактора…");
          await window.ValidationEditor.persistAllDocumentSections();
        } catch (err) {
          toast(err.message, true);
          return;
        }
      }
      const tryDownload = async (useForce) => {
        const path = `/study-plans/${selectedPlanId}/disciplines/${disciplineId}/export/?kind=${kind}&export_mode=template${useForce ? "&force=true" : ""}`;
        return SyllabusApi.downloadFile(path, {
          defaultFilename: `${kind}_${disciplineId}.docx`,
        });
      };
      try {
        const { filename, headers } = await tryDownload(force);
        const mode = headers?.get?.("X-Export-Mode") || "";
        const injected = headers?.get?.("X-Sections-Injected") || "";
        const modeHint = mode ? ` · ${mode}` : "";
        const injHint = injected ? ` · разделов ${injected}` : "";
        toast(`Скачан ${kind.toUpperCase()}: ${filename}${modeHint}${injHint}`);
      } catch (err) {
        const msg = String(err.message || err);
        if (!force && /сверк|validation|не пройден/i.test(msg)) {
          try {
            const { filename } = await tryDownload(true);
            toast(`Скачан ${kind.toUpperCase()} (игнорируя оставшиеся ошибки): ${filename}`, false);
            return;
          } catch (retryErr) {
            toast(retryErr.message || "Экспорт не удался", true);
            return;
          }
        }
        toast(msg, true);
      }
    }

    async function downloadDisciplinePdf(disciplineId, kind, force = false) {
      if (!selectedPlanId) return;
      if (window.ValidationEditor?.isEditorOpenForDiscipline?.(disciplineId)) {
        try {
          await window.ValidationEditor.persistAllDocumentSections();
        } catch (err) {
          toast(err.message, true);
          return;
        }
      }
      const tryDownload = async (useForce) => {
        const path = `/study-plans/${selectedPlanId}/disciplines/${disciplineId}/export.pdf?kind=${kind}&export_mode=template${useForce ? "&force=true" : ""}`;
        return SyllabusApi.downloadFile(path, {
          defaultFilename: `${kind}_${disciplineId}.pdf`,
        });
      };
      try {
        toast("Формирование PDF…");
        const { filename } = await tryDownload(force);
        toast(`PDF ${kind.toUpperCase()}: ${filename}`);
      } catch (err) {
        const msg = String(err.message || err);
        if (!force && /сверк|validation|не пройден/i.test(msg)) {
          try {
            toast("Повтор PDF с игнорированием ошибок…");
            const { filename } = await tryDownload(true);
            toast(`PDF ${kind.toUpperCase()}: ${filename}`);
            return;
          } catch (retryErr) {
            toast(retryErr.message || "PDF не удался", true);
            return;
          }
        }
        toast(msg, true);
      }
    }

    async function downloadPlanExport(kind, force = false) {
      if (!selectedPlanId) return;
      const ready = exportReadyCount(kind);
      if (!force && ready <= 0) {
        toast(
          `Нет дисциплин без критических ошибок. Снимите оставшиеся ошибки или нажмите «${kind === "rpd" ? "РПД" : "ФОС"} все».`,
          true
        );
        return;
      }
      const path = `/study-plans/${selectedPlanId}/export-passed/?kind=${kind}${force ? "&force=true" : ""}`;
      try {
        toast(`Формирование архива (${kind === "rpd" ? "РПД" : "ФОС"})…`);
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
        toast(`Архив: ${count} документ(ов) ${kind === "rpd" ? "РПД" : "ФОС"}`);
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
        <div class="stat ${lastRpdReport && lastRpdReport.failed ? "fail" : "ok"}"><div class="label">РПД без ошибок</div><div class="value">${lastRpdReport ? lastRpdReport.passed : "—"}</div></div>
        <div class="stat ${lastFosReport && lastFosReport.failed ? "fail" : "ok"}"><div class="label">ФОС без ошибок</div><div class="value">${lastFosReport ? lastFosReport.passed : "—"}</div></div>
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
            const extra = [];
            if (link.propagated_plans) extra.push(`+${link.propagated_plans} планов`);
            if (link.reused_document) extra.push("из библиотеки");
            const suffix = extra.length ? ` (${extra.join(", ")})` : "";
            appendBatchLog(
              `<span class="ok">${esc(result.file)} → ${esc(link.discipline_code)} (${esc(link.doc_kind || "docx")})${esc(suffix)}</span>`
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
          toast(`Пакет завершён: привязано ${summary.linked}, проблем ${summary.unlinked + summary.errors}`, true);
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
      if (document.getElementById("propagateAllPlans")?.checked) {
        fd.append("propagate_all_plans", "true");
      }
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

    function applyValidationToTable() {
      const tbody = document.querySelector("#main table tbody");
      if (!tbody || !disciplines.length) return;
      tbody.innerHTML = disciplines.map(d => disciplineRowHtml(d)).join("");
      bindRowUploadInputs(tbody);
      bindDocOpenButtons(tbody);
      bindExportButtons(tbody);
    }

    function showValidationBanner(kind, report) {
      const banner = document.getElementById("validationBanner");
      if (!banner || !report) return;
      const isRpd = kind === "rpd";
      const title = isRpd ? "Сверка РПД ↔ УП" : "Сверка ФОС ↔ УП/РПД";
      const missing = isRpd ? report.missing_rpd : report.missing_fos;
      const ok = (report.failed || 0) === 0;
      banner.className = `validation-banner ${ok ? "ok" : "fail"}`;
      banner.innerHTML = `
        <div class="validation-banner-title">${title} — ${ok ? "без критичных ошибок" : `ошибок: ${report.failed}`}</div>
        <div class="validation-banner-meta">
          проверено ${report.checked || 0} · без ошибок ${report.passed || 0} · с ошибками ${report.failed || 0}
          · без документа ${missing ?? 0}
        </div>
      `;
      banner.classList.remove("hidden");
      banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    async function runValidation(kind) {
      if (!selectedPlanId) {
        toast("Сначала выберите учебный план слева", true);
        return;
      }
      if (planLoading) {
        toast("План ещё загружается — подождите секунду", true);
        return;
      }
      if (validationRunning) return;
      if (!document.getElementById("stats")) {
        toast("Таблица плана ещё не готова — выберите план ещё раз", true);
        return;
      }
      validationRunning = true;
      refreshRibbon();
      const label = kind === "rpd" ? "РПД" : "ФОС";
      toast(`Сверка ${label}…`);
      try {
        const path = kind === "rpd"
          ? `/study-plans/${selectedPlanId}/validate/`
          : `/study-plans/${selectedPlanId}/validate-fos/`;
        const report = await api(path);
        if (kind === "rpd") lastRpdReport = report;
        else lastFosReport = report;
        renderStats();
        showValidationBanner(kind, report);
        applyValidationToTable();
        await refreshExportSummary();
        renderStats();
        toast(
          `${label}: проверено ${report.checked}, без ошибок ${report.passed}, ошибок ${report.failed}`,
          (report.failed || 0) > 0
        );
      } catch (err) {
        toast(err.message || `Ошибка сверки ${label}`, true);
        showErrorPanel(err.message || `Не удалось выполнить сверку ${label}`);
      } finally {
        validationRunning = false;
        refreshRibbon();
      }
    }

    function downloadReport(format) {
      if (!selectedPlanId) return;
      window.open(`${API}/study-plans/${selectedPlanId}/validation-report/?format=${format}`, "_blank");
    }

    (function bindValidationUploads() {
      const bindUpload = inputId => {
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
    })();

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

    document.getElementById("planSearch")?.addEventListener(
      "input",
      SyllabusUi.debounce(() => {
        renderPlanTree(SyllabusPlansNav.filterTree(planNavData?.tree, navSearchQuery()));
      }, 250)
    );

    (async () => {
      try {
        if (!(await SyllabusAuth.requireAuth("/"))) return;
        try {
          appConfig = await SyllabusAuth.getConfig();
        } catch (_) {
          appConfig = { plans_auto_import: true };
        }
        refreshRibbon();
        await loadPlans().catch(err => toast(err.message, true));
        const urlPlan = SyllabusShell.parsePlanIdFromUrl();
        if (urlPlan) {
          try {
            await selectPlan(urlPlan);
          } catch (err) {
            toast(err.message, true);
          }
        }
      } catch (err) {
        toast(err.message || "Ошибка сети при загрузке страницы.", true);
        showErrorPanel(err.message || "Не удалось загрузить страницу сверки. Проверьте, что сервер запущен.");
      }
    })();

    window.ValidationExport = {
      downloadDocx: (disciplineId, kind, force = true) =>
        downloadDisciplineExport(disciplineId, kind, force),
      downloadPdf: (disciplineId, kind, force = true) =>
        downloadDisciplinePdf(disciplineId, kind, force),
      refreshDisciplineRow: disciplineId => refreshDisciplineExportRow(disciplineId),
    };

