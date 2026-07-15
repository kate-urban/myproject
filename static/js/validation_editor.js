/** Встроенный редактор РПД/ФОС на странице сверки. */
    function ensureDocHtml(content) {
      if (!content) return "";
      if (/<[a-z][\s\S]*>/i.test(content)) return content;
      return content
        .split(/\n\s*\n/)
        .filter(p => p.trim())
        .map(p => `<p>${p.trim().replace(/\n/g, "<br>")}</p>`)
        .join("");
    }

    function ensureDocEditorReady() {
      if (docEditorReady) return Promise.resolve();
      if (docEditorInitPromise) return docEditorInitPromise;
      docEditorInitPromise = new Promise(resolve => {
        tinymce.init({
          selector: "#docEditor",
          height: "100%",
          resize: false,
          menubar: false,
          ...(window.SyllabusUiRu?.tinymceLanguage || {}),
          plugins: [
            "advlist", "autolink", "lists", "link", "charmap", "preview",
            "anchor", "searchreplace", "visualblocks", "code", "fullscreen",
            "insertdatetime", "media", "table", "help", "wordcount"
          ],
          toolbar: "undo redo | blocks | bold italic | alignleft aligncenter alignright | " +
            "bullist numlist outdent indent | table | removeformat | code | help",
          content_style: 'body { font-family: "Calibri", "Segoe UI", Arial, sans-serif; font-size: 14px; line-height: 1.6; } ' +
            "table { border-collapse: collapse; width: 100%; } " +
            "table td, table th { border: 1px solid #999; padding: 8px; } " +
            "mark.val-err-mark { background: #fde7e9; color: #a4262c; outline: 2px solid #d13438; }",
          table_sizing_mode: "relative",
          table_toolbar: "tableprops tabledelete | tableinsertrowbefore tableinsertrowafter tabledeleterow | " +
            "tableinsertcolbefore tableinsertcolafter tabledeletecol",
          setup: editor => {
            editor.on("init", () => {
              docEditorReady = true;
              resizeDocEditor();
              resolve();
            });
            editor.on("change keyup", () => {
              const section = docEditorState.sections.find(
                s => s.id === docEditorState.selectedSectionId
              );
              if (section) section.content = stripHighlightMarks(editor.getContent());
            });
          },
        });
      });
      return docEditorInitPromise;
    }

    function resizeDocEditor() {
      const editor = tinymce.get("docEditor");
      const wrap = document.querySelector(".doc-editor-wrap");
      if (!editor || !wrap) return;
      const height = Math.max(wrap.clientHeight - 8, 240);
      const container = editor.getContainer();
      if (container) container.style.height = `${height}px`;
      if (typeof editor.theme?.resizeTo === "function") {
        editor.theme.resizeTo(container?.clientWidth || wrap.clientWidth, height);
      }
    }

    function updateDocPanelControls() {
      const issuesToggle = document.getElementById("docIssuesToggle");
      const sectionsToggle = document.getElementById("docSectionsToggle");
      const focusBtn = document.getElementById("docEditorFocus");
      const issuesPanel = document.getElementById("docEditorIssues");
      const body = document.getElementById("docEditorBody");

      if (issuesPanel) {
        issuesPanel.classList.toggle("collapsed", docEditorState.issuesCollapsed);
      }
      if (issuesToggle) {
        issuesToggle.textContent = docEditorState.issuesCollapsed ? "Развернуть" : "Свернуть";
        issuesToggle.classList.toggle("active", docEditorState.issuesCollapsed);
      }
      if (body) {
        body.classList.toggle("sections-collapsed", docEditorState.sectionsCollapsed);
      }
      if (sectionsToggle) {
        sectionsToggle.textContent = docEditorState.sectionsCollapsed ? "Развернуть" : "Свернуть";
        sectionsToggle.title = docEditorState.sectionsCollapsed
          ? "Развернуть список разделов"
          : "Свернуть список разделов";
        sectionsToggle.classList.toggle("active", docEditorState.sectionsCollapsed);
      }
      if (focusBtn) {
        focusBtn.classList.toggle("active", docEditorState.focusMode);
        focusBtn.textContent = docEditorState.focusMode ? "Панели" : "На весь экран";
      }
      requestAnimationFrame(resizeDocEditor);
    }

    function toggleDocIssuesPanel(forceCollapsed) {
      if (typeof forceCollapsed === "boolean") {
        docEditorState.issuesCollapsed = forceCollapsed;
      } else {
        docEditorState.issuesCollapsed = !docEditorState.issuesCollapsed;
      }
      docEditorState.focusMode = docEditorState.issuesCollapsed && docEditorState.sectionsCollapsed;
      updateDocPanelControls();
      renderDocEditorIssues();
    }

    function toggleDocSectionsPanel(forceCollapsed) {
      if (typeof forceCollapsed === "boolean") {
        docEditorState.sectionsCollapsed = forceCollapsed;
      } else {
        docEditorState.sectionsCollapsed = !docEditorState.sectionsCollapsed;
      }
      docEditorState.focusMode = docEditorState.issuesCollapsed && docEditorState.sectionsCollapsed;
      updateDocPanelControls();
    }

    function toggleDocFocusMode() {
      if (docEditorState.focusMode) {
        docEditorState.issuesCollapsed = false;
        docEditorState.sectionsCollapsed = false;
        docEditorState.focusMode = false;
      } else {
        docEditorState.issuesCollapsed = true;
        docEditorState.sectionsCollapsed = true;
        docEditorState.focusMode = true;
      }
      updateDocPanelControls();
    }

    function flushDocEditor() {
      if (!docEditorState.selectedSectionId) return;
      const editor = tinymce.get("docEditor");
      const content = editor ? editor.getContent() : "";
      const section = docEditorState.sections.find(s => s.id === docEditorState.selectedSectionId);
      if (section) section.content = stripHighlightMarks(content);
    }

    function renderDocEditorSections() {
      const list = document.getElementById("docEditorSections");
      if (!list) return;
      list.innerHTML = "";
      docEditorState.sections.forEach(section => {
        const rules = docEditorState.sectionRuleMap.get(section.id) || [];
        const item = document.createElement("div");
        item.className = `doc-section-item level-${section.level || 1}` +
          (docEditorState.selectedSectionId === section.id ? " active" : "") +
          (rules.length ? " has-error" : "");
        item.dataset.sectionId = section.id;
        const errBadge = rules.length
          ? `<span class="err-count">${rules.length}</span>`
          : "";
        item.innerHTML = `${esc(section.section_name)}${errBadge}`;
        item.onclick = () => {
          const firstRule = rules[0]?.rule_id || null;
          selectDocSection(section.id, firstRule);
        };
        list.appendChild(item);
      });
    }

    function renderDocEditorIssues() {
      const panel = document.getElementById("docEditorIssues");
      const body = document.getElementById("docEditorIssuesBody");
      const title = document.getElementById("docIssuesTitle");
      if (!panel || !body) return;
      const rules = failedRules(docEditorState.validation);
      const warnings = warningRules(docEditorState.validation);
      const waived = waivedRules(docEditorState.validation);
      if (!rules.length && !warnings.length && !waived.length) {
        panel.classList.add("empty");
        body.innerHTML = "";
        if (title) title.textContent = "Ошибки сверки";
        return;
      }
      panel.classList.remove("empty");
      const totalIssues = rules.length + warnings.length;
      if (title) {
        title.textContent = totalIssues
          ? docEditorState.issuesCollapsed
            ? `Ошибки сверки (${totalIssues}) — нажмите «Развернуть»`
            : `Ошибки сверки (${totalIssues})`
          : "Ошибки сверки";
      }
      const issueHint = totalIssues && !docEditorState.issuesCollapsed
        ? `<p class="doc-issues-hint">Строка — перейти к разделу · «Снять» — исключить из контроля</p>`
        : "";
      const warningsBlock = warnings.length && !docEditorState.issuesCollapsed
        ? `<div class="doc-warnings-block">
            <div class="doc-warnings-head">Замечания (${warnings.length})</div>
            ${warnings.map(rule => {
              const sections = findSectionsForRule(
                rule.rule_id, docEditorState.kind, docEditorState.sections
              );
              return formatRuleIssueCompact(
                rule, docEditorState.kind, sections,
                docEditorState.activeRuleId === rule.rule_id, true
              );
            }).join("")}
          </div>`
        : "";
      const waivedBlock = waived.length && !docEditorState.issuesCollapsed
        ? `<div class="doc-waived-block">
            <div class="doc-waived-head">Снято (${waived.length})</div>
            <div class="doc-waived-list">${waived.map(rule => formatWaivedRuleCard(rule, docEditorState.kind)).join("")}</div>
          </div>`
        : "";
      body.innerHTML = issueHint +
        rules.map(rule => {
          const sections = findSectionsForRule(
            rule.rule_id, docEditorState.kind, docEditorState.sections
          );
          return formatRuleIssueCompact(
            rule, docEditorState.kind, sections,
            docEditorState.activeRuleId === rule.rule_id
          );
        }).join("") +
        warningsBlock +
        waivedBlock;
      body.querySelectorAll(".doc-issue-compact").forEach(btn => {
        btn.onclick = e => {
          if (e.target.closest(".doc-issue-waive-btn")) return;
          if (btn.dataset.sectionId) {
            selectDocSection(btn.dataset.sectionId, btn.dataset.ruleId || null);
          }
          body.querySelectorAll(".doc-issue-compact").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
        };
      });
      body.querySelectorAll(".doc-issue-waive-btn").forEach(btn => {
        const stop = e => e.stopPropagation();
        btn.addEventListener("mousedown", stop);
        btn.addEventListener("click", e => {
          e.stopPropagation();
          e.preventDefault();
          waiveValidationRule(btn.dataset.ruleId);
        });
      });
      body.querySelectorAll(".doc-issue-restore-btn").forEach(btn => {
        btn.onclick = () => restoreValidationRule(btn.dataset.ruleId);
      });
    }

    async function applyValidationResult(item) {
      docEditorState.validation = item;
      updateCachedValidationItem(docEditorState.disciplineId, docEditorState.kind, item);
      docEditorState.sectionRuleMap = buildSectionRuleMap(
        item, docEditorState.kind, docEditorState.sections
      );
      renderDocEditorIssues();
      renderDocEditorSections();
      updateDocPanelControls();
      renderStats();
      refreshDisciplineExportRow(docEditorState.disciplineId);
      await refreshExportSummary();
    }

    async function waiveValidationRule(ruleId) {
      if (!docEditorState.disciplineId || !docEditorState.kind || !ruleId) return;
      try {
        const item = await api(
          `/study-plans/${selectedPlanId}/disciplines/${docEditorState.disciplineId}/validation-waivers/`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rule_id: ruleId, kind: docEditorState.kind }),
          }
        );
        await applyValidationResult(item);
        if (!failedRules(item).length) {
          docEditorState.issuesCollapsed = true;
          updateDocPanelControls();
        }
        const remaining = failedRules(item).length;
        toast(
          remaining
            ? `${ruleId} снят с контроля · осталось критических: ${remaining}`
            : `${ruleId} снят · сверка без критических ошибок. Можно скачать DOCX/PDF в таблице.`,
          false
        );
      } catch (err) {
        toast(err.message, true);
      }
    }

    async function restoreValidationRule(ruleId) {
      if (!docEditorState.disciplineId || !docEditorState.kind || !ruleId) return;
      try {
        const item = await api(
          `/study-plans/${selectedPlanId}/disciplines/${docEditorState.disciplineId}/validation-waivers/${encodeURIComponent(ruleId)}/?kind=${docEditorState.kind}`,
          { method: "DELETE" }
        );
        await applyValidationResult(item);
        toast(`${ruleId} снова в контроле`, false);
      } catch (err) {
        toast(err.message, true);
      }
    }

    function pickFirstErrorSection() {
      const candidates = docEditorState.sections.filter(
        s => docEditorState.sectionRuleMap.has(s.id)
      );
      if (!candidates.length) return null;
      const withTable = candidates.find(s => /<table[\s>]/i.test(s.content || ""));
      if (withTable) return withTable.id;
      const withContent = candidates.find(s => sectionHasEditorContent(s));
      return (withContent || candidates[0]).id;
    }

    function selectDocSection(sectionId, ruleId = null) {
      if (docEditorState.selectedSectionId && docEditorState.selectedSectionId !== sectionId) {
        flushDocEditor();
      }
      const resolvedRuleId = ruleId || docEditorState.activeRuleId;
      if (resolvedRuleId) {
        const better = pickBestSectionForRule(
          resolvedRuleId,
          docEditorState.kind,
          docEditorState.sections,
          sectionId
        );
        if (better) sectionId = better.id;
      }
      docEditorState.selectedSectionId = sectionId;
      if (ruleId) {
        docEditorState.activeRuleId = ruleId;
      } else {
        const sectionRules = docEditorState.sectionRuleMap.get(sectionId) || [];
        const stillRelevant = sectionRules.some(r => r.rule_id === docEditorState.activeRuleId);
        if (!stillRelevant) docEditorState.activeRuleId = sectionRules[0]?.rule_id || null;
      }

      const section = docEditorState.sections.find(s => s.id === sectionId);
      if (!section) return;

      const activeRule = docEditorState.activeRuleId
        ? (failedRules(docEditorState.validation).find(r => r.rule_id === docEditorState.activeRuleId)
          || warningRules(docEditorState.validation).find(r => r.rule_id === docEditorState.activeRuleId))
        : null;

      document.getElementById("docEditorSectionTitle").textContent = section.section_name;

      let content = ensureDocHtml(section.content || "");
      if (activeRule) {
        const highlightOpts = {};
        if (NUMERIC_COMPARE_RULES.has(activeRule.rule_id) && isPlainNumber(activeRule.expected)) {
          highlightOpts.referenceValue = activeRule.expected;
        }
        content = highlightContentHtml(
          content,
          getHighlightTerms(activeRule, docEditorState.kind),
          highlightOpts
        );
      }

      const editor = tinymce.get("docEditor");
      if (editor) editor.setContent(content);
      renderDocEditorRuleHint(docEditorState.activeRuleId);
      renderDocEditorSections();
      requestAnimationFrame(resizeDocEditor);
    }

    async function openDocumentEditor({ docId, kind, disciplineId, disciplineCode, programId }) {
      if (!selectedPlanId) return;
      const discipline = disciplines.find(d => d.id === disciplineId);
      const pid = programId || discipline?.program_id;
      if (pid && window.SyllabusEditLock) {
        try {
          await SyllabusEditLock.acquire(pid);
        } catch (err) {
          toast(err.message || "Документ занят", true);
          return;
        }
      }
      await ensureDocEditorReady();
      docEditorState.docId = docId;
      docEditorState.programId = pid || null;
      docEditorState.kind = kind;
      docEditorState.disciplineId = disciplineId;
      docEditorState.disciplineCode = disciplineCode;
      window.ValidationStructured?.prepareForDocumentOpen();

      document.getElementById("docEditorModal").classList.add("open");
      document.getElementById("docEditorModal").setAttribute("aria-hidden", "false");
      document.getElementById("docEditorTitle").textContent =
        `${kind === "rpd" ? "РПД" : "ФОС"} · ${disciplineCode}`;

      const doc = await api(`/documents/${docId}/`);
      docEditorState.sections = doc.sections || [];
      docEditorState.selectedSectionId = null;
      docEditorState.validation = await getDisciplineValidation(disciplineId, kind);
      docEditorState.activeRuleId = null;
      const errCount = failedRules(docEditorState.validation).length
        + warningRules(docEditorState.validation).length;
      docEditorState.issuesCollapsed = errCount > 0;
      docEditorState.sectionsCollapsed = false;
      docEditorState.focusMode = false;
      docEditorState.sectionRuleMap = buildSectionRuleMap(
        docEditorState.validation, kind, docEditorState.sections
      );

      renderDocEditorIssues();
      renderDocEditorSections();
      updateDocPanelControls();

      const firstError = pickFirstErrorSection();
      const firstContent = docEditorState.sections.find(s => s.content && s.content.trim());
      const firstErrorRule = firstError
        ? (docEditorState.sectionRuleMap.get(firstError) || [])[0]?.rule_id
        : null;
      const targetId = firstError || firstContent?.id || docEditorState.sections[0]?.id;
      if (targetId) selectDocSection(targetId, firstErrorRule);
      else document.getElementById("docEditorSectionTitle").textContent = "Нет разделов";
      window.ValidationAssistant?.onEditorOpen();
      window.ValidationFix?.refreshConfig?.();
    }

    async function persistAllDocumentSections() {
      const modal = document.getElementById("docEditorModal");
      if (!modal?.classList.contains("open") || !docEditorState.sections.length) {
        return { saved: 0 };
      }
      flushDocEditor();
      const programQuery = docEditorState.programId
        ? `?program_id=${encodeURIComponent(docEditorState.programId)}`
        : "";
      let saved = 0;
      for (const section of docEditorState.sections) {
        await api(`/sections/${section.id}/${programQuery}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: section.content || "" }),
        });
        saved += 1;
      }
      return { saved };
    }

    function isEditorOpenForDiscipline(disciplineId) {
      const modal = document.getElementById("docEditorModal");
      return Boolean(
        modal?.classList.contains("open") &&
          docEditorState.disciplineId &&
          String(docEditorState.disciplineId) === String(disciplineId)
      );
    }

    async function saveDocSection() {
      if (!docEditorState.selectedSectionId) {
        toast("Выберите раздел", true);
        return;
      }
      flushDocEditor();
      const section = docEditorState.sections.find(s => s.id === docEditorState.selectedSectionId);
      if (!section) return;
      try {
        await api(`/sections/${section.id}/?program_id=${encodeURIComponent(docEditorState.programId || "")}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: section.content || "" }),
        });
        toast("Раздел сохранён");
        if (
          docEditorState.programId &&
          docEditorState.kind === "rpd" &&
          appConfig?.structured_rpd_enabled !== false
        ) {
          api(`/documents/${docEditorState.docId}/refresh-extract/`, { method: "POST" })
            .then(() => window.ValidationStructured?.loadStructuredData?.(true))
            .catch(() => {});
        }
      } catch (err) {
        toast(err.message, true);
      }
    }

    async function revalidateOpenDocument() {
      if (!docEditorState.disciplineId || !docEditorState.kind || !docEditorState.docId) return;
      flushDocEditor();
      try {
        if (docEditorState.selectedSectionId) {
          const section = docEditorState.sections.find(
            s => s.id === docEditorState.selectedSectionId
          );
          if (section) {
            await api(`/sections/${section.id}/?program_id=${encodeURIComponent(docEditorState.programId || "")}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ content: section.content || "" }),
            });
          }
        }
        await api(`/documents/${docEditorState.docId}/refresh-extract/`, { method: "POST" });
        const path = docEditorState.kind === "rpd"
          ? `/study-plans/${selectedPlanId}/disciplines/${docEditorState.disciplineId}/validate/`
          : `/study-plans/${selectedPlanId}/disciplines/${docEditorState.disciplineId}/validate-fos/`;
        const item = await api(path);
        await applyValidationResult(item);
        toast(item.passed ? "Сверка: без ошибок" : `Сверка: ${failedRules(item).length} ошибок`, !item.passed);
      } catch (err) {
        toast(err.message, true);
      }
    }

    function teardownDocEditorInstance() {
      const editor = tinymce.get("docEditor");
      if (editor) tinymce.remove(editor);
      docEditorReady = false;
      docEditorInitPromise = null;
    }

    function closeDocumentEditor() {
      flushDocEditor();
      teardownDocEditorInstance();
      if (window.SyllabusEditLock) SyllabusEditLock.release();
      window.ValidationStructured?.resetStructuredEditor();
      window.ValidationAssistant?.onEditorClose();
      document.getElementById("docEditorModal").classList.remove("open");
      document.getElementById("docEditorModal").setAttribute("aria-hidden", "true");
    }

    document.getElementById("docEditorSave").onclick = () => {
      if (docEditorState.editorMode === "structured") {
        window.ValidationStructured?.saveStructuredData();
      } else {
        saveDocSection();
      }
    };
    document.getElementById("docEditorRevalidate").onclick = () => revalidateOpenDocument();
    document.getElementById("docEditorExportDocx")?.addEventListener("click", async () => {
      if (!docEditorState.disciplineId || !docEditorState.kind) return;
      try {
        toast("Сохраняем правки и формируем DOCX по шаблону…");
        await persistAllDocumentSections();
        await window.ValidationExport?.downloadDocx(
          docEditorState.disciplineId,
          docEditorState.kind,
          true
        );
      } catch (err) {
        toast(err.message, true);
      }
    });
    document.getElementById("docEditorExportPdf")?.addEventListener("click", async () => {
      if (!docEditorState.disciplineId || !docEditorState.kind) return;
      try {
        toast("Сохраняем правки и формируем PDF…");
        await persistAllDocumentSections();
        await window.ValidationExport?.downloadPdf(
          docEditorState.disciplineId,
          docEditorState.kind,
          true
        );
      } catch (err) {
        toast(err.message, true);
      }
    });
    document.getElementById("docEditorClose").onclick = () => closeDocumentEditor();
    document.getElementById("docEditorFocus").onclick = () => toggleDocFocusMode();
    document.getElementById("docIssuesToggle").onclick = e => {
      e.stopPropagation();
      toggleDocIssuesPanel();
    };
    document.getElementById("docIssuesHead")?.addEventListener("click", e => {
      if (e.target.closest("#docIssuesToggle")) return;
      toggleDocIssuesPanel();
    });
    document.getElementById("docSectionsToggle").onclick = e => {
      e.stopPropagation();
      toggleDocSectionsPanel();
    };
    const onDocEditorResize = (window.SyllabusUi?.throttle || (fn => fn))(() => {
      if (document.getElementById("docEditorModal").classList.contains("open")) {
        resizeDocEditor();
      }
    }, 150);
    window.addEventListener("resize", onDocEditorResize);
    document.getElementById("docEditorModal").addEventListener("click", e => {
      if (e.target.id === "docEditorModal") closeDocumentEditor();
    });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && document.getElementById("docEditorModal").classList.contains("open")) {
        closeDocumentEditor();
      }
    });

    window.ValidationEditor = {
      persistAllDocumentSections,
      isEditorOpenForDiscipline,
    };