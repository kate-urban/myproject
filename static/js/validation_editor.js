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
        issuesToggle.textContent = docEditorState.issuesCollapsed ? "Развернуть ▼" : "Свернуть ▲";
        issuesToggle.classList.toggle("active", docEditorState.issuesCollapsed);
      }
      if (body) {
        body.classList.toggle("sections-collapsed", docEditorState.sectionsCollapsed);
      }
      if (sectionsToggle) {
        sectionsToggle.textContent = docEditorState.sectionsCollapsed ? "▶" : "◀";
        sectionsToggle.title = docEditorState.sectionsCollapsed
          ? "Развернуть список разделов"
          : "Свернуть список разделов";
        sectionsToggle.classList.toggle("active", docEditorState.sectionsCollapsed);
      }
      if (focusBtn) {
        focusBtn.classList.toggle("active", docEditorState.focusMode);
        focusBtn.textContent = docEditorState.focusMode ? "↩ Панели" : "⛶ Редактор";
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
        const ruleTags = rules.length
          ? `<span class="section-rules">${rules.map(r => r.rule_id).join(", ")}</span>`
          : "";
        item.innerHTML = `${esc(section.section_name)}${errBadge}${ruleTags}`;
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
      if (!rules.length) {
        panel.classList.add("empty");
        body.innerHTML = "";
        if (title) title.textContent = "Ошибки сверки";
        return;
      }
      panel.classList.remove("empty");
      if (title) title.textContent = `Ошибки сверки (${rules.length})`;
      const issueHint = `<p style="font-size:11px;color:var(--muted);margin-bottom:6px">Нажмите на ошибку — откроется нужный раздел, проблемные значения подсветятся. После правки: «Сохранить» → «Сверка».</p>`;
      body.innerHTML = issueHint +
        rules.map(rule => {
          const sections = findSectionsForRule(
            rule.rule_id, docEditorState.kind, docEditorState.sections
          );
          return formatRuleIssueCard(
            rule, docEditorState.kind, sections,
            docEditorState.activeRuleId === rule.rule_id
          );
        }).join("");
      body.querySelectorAll(".doc-issue-item").forEach(btn => {
        btn.onclick = () => {
          if (btn.dataset.sectionId) {
            selectDocSection(btn.dataset.sectionId, btn.dataset.ruleId || null);
          }
          body.querySelectorAll(".doc-issue-item").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
        };
      });
    }

    function pickFirstErrorSection() {
      for (const section of docEditorState.sections) {
        if (docEditorState.sectionRuleMap.has(section.id)) return section.id;
      }
      return null;
    }

    function selectDocSection(sectionId, ruleId = null) {
      if (docEditorState.selectedSectionId && docEditorState.selectedSectionId !== sectionId) {
        flushDocEditor();
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
        ? failedRules(docEditorState.validation).find(r => r.rule_id === docEditorState.activeRuleId)
        : null;

      document.getElementById("docEditorSectionTitle").textContent = section.section_name;

      let content = ensureDocHtml(section.content || "");
      if (activeRule) {
        content = highlightContentHtml(content, getHighlightTerms(activeRule, docEditorState.kind));
      }

      const editor = tinymce.get("docEditor");
      if (editor) editor.setContent(content);
      renderDocEditorRuleHint(docEditorState.activeRuleId);
      renderDocEditorSections();
      renderDocEditorIssues();
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
      docEditorState.kind = kind;
      docEditorState.disciplineId = disciplineId;
      docEditorState.disciplineCode = disciplineCode;

      document.getElementById("docEditorModal").classList.add("open");
      document.getElementById("docEditorModal").setAttribute("aria-hidden", "false");
      document.getElementById("docEditorTitle").textContent =
        `${kind === "rpd" ? "РПД" : "ФОС"} · ${disciplineCode}`;

      const doc = await api(`/documents/${docId}/`);
      docEditorState.sections = doc.sections || [];
      docEditorState.selectedSectionId = null;
      docEditorState.validation = await getDisciplineValidation(disciplineId, kind);
      docEditorState.activeRuleId = null;
      docEditorState.issuesCollapsed = false;
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
        await api(`/sections/${section.id}/`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: section.content || "" }),
        });
        toast("Раздел сохранён");
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
            await api(`/sections/${section.id}/`, {
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
        docEditorState.validation = item;
        updateCachedValidationItem(docEditorState.disciplineId, docEditorState.kind, item);
        docEditorState.sectionRuleMap = buildSectionRuleMap(
          item, docEditorState.kind, docEditorState.sections
        );
        renderDocEditorIssues();
        renderDocEditorSections();
        updateDocPanelControls();
        renderStats();
        toast(item.passed ? "Сверка: OK" : `Сверка: ${failedRules(item).length} ошибок`, !item.passed);
      } catch (err) {
        toast(err.message, true);
      }
    }

    function closeDocumentEditor() {
      flushDocEditor();
      if (window.SyllabusEditLock) SyllabusEditLock.release();
      document.getElementById("docEditorModal").classList.remove("open");
      document.getElementById("docEditorModal").setAttribute("aria-hidden", "true");
    }

    document.getElementById("docEditorSave").onclick = () => saveDocSection();
    document.getElementById("docEditorRevalidate").onclick = () => revalidateOpenDocument();
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
    window.addEventListener("resize", () => {
      if (document.getElementById("docEditorModal").classList.contains("open")) {
        resizeDocEditor();
      }
    });
    document.getElementById("docEditorModal").addEventListener("click", e => {
      if (e.target.id === "docEditorModal") closeDocumentEditor();
    });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && document.getElementById("docEditorModal").classList.contains("open")) {
        closeDocumentEditor();
      }
    });