/** Редактор relational CRUD: topics / zuv / literature (ТЗ P2). */
(function () {
  const ZUV_TYPES = [
    { value: "know", label: "Знать" },
    { value: "skill", label: "Уметь" },
    { value: "ability", label: "Владеть" },
  ];

  function numOrNull(value) {
    const raw = String(value ?? "").trim();
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }

  function emptyTopicsRow(order = 0) {
    return {
      topic_number: String(order + 1),
      title: "",
      semester: null,
      hours_lecture: null,
      hours_practical: null,
      hours_lab: null,
      hours_sr: null,
      is_bold: false,
      row_order: order,
    };
  }

  function emptyZuvRow() {
    return { indicator_code: "", zuv_type: "know", text: "", topic_ref: "" };
  }

  function emptyLitRow(order = 0) {
    return { citation: "", lit_type: "main", row_order: order };
  }

  function ensureStructuredState() {
    if (!docEditorState.structured) {
      docEditorState.structured = {
        loaded: false,
        loading: false,
        activeTab: "topics",
        data: { topics: [], zuv: [], literature: [] },
      };
    }
    return docEditorState.structured;
  }

  function structuredEnabled() {
    return (
      docEditorState.kind === "rpd" &&
      docEditorState.programId &&
      appConfig?.structured_rpd_enabled !== false
    );
  }

  function updateStructuredTabVisibility() {
    const tab = document.getElementById("docTabStructured");
    if (!tab) return;
    tab.classList.toggle("hidden", !structuredEnabled());
  }

  function setDocEditorMode(mode) {
    docEditorState.editorMode = mode;
    const body = document.getElementById("docEditorBody");
    const structured = document.getElementById("docStructuredPanel");
    const tabSections = document.getElementById("docTabSections");
    const tabStructured = document.getElementById("docTabStructured");
    const saveBtn = document.getElementById("docEditorSave");

    if (body) body.classList.toggle("hidden", mode !== "sections");
    if (structured) structured.classList.toggle("hidden", mode !== "structured");
    tabSections?.classList.toggle("active", mode === "sections");
    tabStructured?.classList.toggle("active", mode === "structured");
    if (saveBtn) {
      saveBtn.textContent = mode === "structured" ? "Сохранить структуру" : "Сохранить";
    }
    if (mode === "structured") {
      loadStructuredData().catch(err => toast(err.message, true));
    } else {
      requestAnimationFrame(resizeDocEditor);
    }
  }

  async function loadStructuredData(force = false) {
    const st = ensureStructuredState();
    if (!structuredEnabled()) return;
    if (st.loaded && !force) {
      renderStructuredEditor();
      return;
    }
    st.loading = true;
    renderStructuredEditor();
    try {
      const payload = await api(`/programs/${docEditorState.programId}/structured/`);
      st.data = {
        topics: payload.topics || [],
        zuv: payload.zuv || [],
        literature: payload.literature || [],
      };
      st.loaded = true;
    } finally {
      st.loading = false;
      renderStructuredEditor();
    }
  }

  function renderStructuredEditor() {
    const host = document.getElementById("structEditorHost");
    const st = ensureStructuredState();
    if (!host) return;

    document.querySelectorAll(".struct-tab").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.struct === st.activeTab);
    });

    if (st.loading) {
      host.innerHTML = '<p class="struct-empty">Загрузка структуры…</p>';
      return;
    }

    if (st.activeTab === "topics") {
      host.innerHTML = renderTopicsTable(st.data.topics);
    } else if (st.activeTab === "zuv") {
      host.innerHTML = renderZuvTable(st.data.zuv);
    } else {
      host.innerHTML = renderLiteratureTable(st.data.literature);
    }

    host.querySelectorAll("[data-remove-row]").forEach(btn => {
      btn.onclick = () => {
        const idx = Number(btn.dataset.removeRow);
        if (st.activeTab === "topics") st.data.topics.splice(idx, 1);
        else if (st.activeTab === "zuv") st.data.zuv.splice(idx, 1);
        else st.data.literature.splice(idx, 1);
        renderStructuredEditor();
      };
    });
  }

  function renderTopicsTable(rows) {
    const body = (rows.length ? rows : [emptyTopicsRow()])
      .map((row, idx) => `
        <tr>
          <td><input class="struct-input sm" data-field="topic_number" data-row="${idx}" value="${esc(row.topic_number || "")}"></td>
          <td><input class="struct-input" data-field="title" data-row="${idx}" value="${esc(row.title || "")}"></td>
          <td><input class="struct-input sm" data-field="semester" data-row="${idx}" value="${row.semester ?? ""}"></td>
          <td><input class="struct-input xs" data-field="hours_lecture" data-row="${idx}" value="${row.hours_lecture ?? ""}"></td>
          <td><input class="struct-input xs" data-field="hours_practical" data-row="${idx}" value="${row.hours_practical ?? ""}"></td>
          <td><input class="struct-input xs" data-field="hours_lab" data-row="${idx}" value="${row.hours_lab ?? ""}"></td>
          <td><input class="struct-input xs" data-field="hours_sr" data-row="${idx}" value="${row.hours_sr ?? ""}"></td>
          <td><button type="button" class="btn sm ghost" data-remove-row="${idx}">Удалить</button></td>
        </tr>`).join("");
    return `
      <div class="struct-table-wrap">
        <table class="struct-table">
          <thead>
            <tr>
              <th>№</th><th>Название темы</th><th>Сем.</th>
              <th>Лек</th><th>Пр</th><th>Лаб</th><th>СР</th><th></th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderZuvTable(rows) {
    const body = (rows.length ? rows : [emptyZuvRow()])
      .map((row, idx) => {
        const options = ZUV_TYPES.map(t =>
          `<option value="${t.value}" ${row.zuv_type === t.value ? "selected" : ""}>${t.label}</option>`
        ).join("");
        return `
        <tr>
          <td><input class="struct-input sm" data-field="indicator_code" data-row="${idx}" value="${esc(row.indicator_code || "")}"></td>
          <td><select class="struct-input sm" data-field="zuv_type" data-row="${idx}">${options}</select></td>
          <td><input class="struct-input" data-field="text" data-row="${idx}" value="${esc(row.text || "")}"></td>
          <td><input class="struct-input xs" data-field="topic_ref" data-row="${idx}" value="${esc(row.topic_ref || "")}"></td>
          <td><button type="button" class="btn sm ghost" data-remove-row="${idx}">Удалить</button></td>
        </tr>`;
      }).join("");
    return `
      <div class="struct-table-wrap">
        <table class="struct-table">
          <thead>
            <tr><th>Индикатор</th><th>Тип</th><th>Формулировка</th><th>Тема</th><th></th></tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderLiteratureTable(rows) {
    const body = (rows.length ? rows : [emptyLitRow()])
      .map((row, idx) => `
        <tr>
          <td>
            <select class="struct-input sm" data-field="lit_type" data-row="${idx}">
              <option value="main" ${row.lit_type === "main" ? "selected" : ""}>Основная</option>
              <option value="add" ${row.lit_type === "add" ? "selected" : ""}>Доп.</option>
              <option value="electronic" ${row.lit_type === "electronic" ? "selected" : ""}>Электронная</option>
            </select>
          </td>
          <td><input class="struct-input" data-field="citation" data-row="${idx}" value="${esc(row.citation || "")}"></td>
          <td><button type="button" class="btn sm ghost" data-remove-row="${idx}">Удалить</button></td>
        </tr>`).join("");
    return `
      <div class="struct-table-wrap">
        <table class="struct-table">
          <thead><tr><th>Тип</th><th>Библиографическое описание</th><th></th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function collectStructuredFromDom() {
    const st = ensureStructuredState();
    const host = document.getElementById("structEditorHost");
    if (!host) return st.data;

    const rows = host.querySelectorAll("[data-row]");
    const grouped = new Map();
    rows.forEach(el => {
      const idx = Number(el.dataset.row);
      if (!grouped.has(idx)) grouped.set(idx, {});
      grouped.get(idx)[el.dataset.field] = el.value;
    });

    if (st.activeTab === "topics") {
      st.data.topics = [...grouped.keys()].sort((a, b) => a - b).map((idx, order) => {
        const row = grouped.get(idx);
        return {
          topic_number: row.topic_number || String(order + 1),
          title: row.title || "",
          semester: numOrNull(row.semester),
          hours_lecture: numOrNull(row.hours_lecture),
          hours_practical: numOrNull(row.hours_practical),
          hours_lab: numOrNull(row.hours_lab),
          hours_sr: numOrNull(row.hours_sr),
          is_bold: false,
          row_order: order,
        };
      });
    } else if (st.activeTab === "zuv") {
      st.data.zuv = [...grouped.keys()].sort((a, b) => a - b).map(idx => {
        const row = grouped.get(idx);
        return {
          indicator_code: row.indicator_code || "",
          zuv_type: row.zuv_type || "know",
          text: row.text || "",
          topic_ref: row.topic_ref || null,
        };
      });
    } else {
      st.data.literature = [...grouped.keys()].sort((a, b) => a - b).map((idx, order) => {
        const row = grouped.get(idx);
        return {
          citation: row.citation || "",
          lit_type: row.lit_type || null,
          row_order: order,
        };
      });
    }
    return st.data;
  }

  function addStructuredRow() {
    const st = ensureStructuredState();
    collectStructuredFromDom();
    if (st.activeTab === "topics") {
      st.data.topics.push(emptyTopicsRow(st.data.topics.length));
    } else if (st.activeTab === "zuv") {
      st.data.zuv.push(emptyZuvRow());
    } else {
      st.data.literature.push(emptyLitRow(st.data.literature.length));
    }
    renderStructuredEditor();
  }

  async function saveStructuredData() {
    if (!docEditorState.programId) {
      toast("Не указан идентификатор программы для сохранения", true);
      return;
    }
    collectStructuredFromDom();
    const st = ensureStructuredState();
    const pid = docEditorState.programId;
    try {
      await api(`/programs/${pid}/topics/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: st.data.topics }),
      });
      await api(`/programs/${pid}/zuv/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: st.data.zuv }),
      });
      await api(`/programs/${pid}/literature/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: st.data.literature }),
      });
      toast("Структура сохранена");
      st.loaded = true;
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function refreshStructuredFromDocument() {
    if (!docEditorState.programId) return;
    flushDocEditor();
    try {
      if (docEditorState.selectedSectionId) {
        const section = docEditorState.sections.find(s => s.id === docEditorState.selectedSectionId);
        if (section) {
          await api(`/sections/${section.id}/`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: section.content || "" }),
          });
        }
      }
      const payload = await api(
        `/programs/${docEditorState.programId}/structured/refresh-from-document/`,
        { method: "POST" }
      );
      const st = ensureStructuredState();
      st.data = {
        topics: payload.topics || [],
        zuv: payload.zuv || [],
        literature: payload.literature || [],
      };
      st.loaded = true;
      renderStructuredEditor();
      toast("Структура обновлена из документа");
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function applyStructuredToDocument() {
    if (!docEditorState.programId) return;
    collectStructuredFromDom();
    await saveStructuredData();
    try {
      const result = await api(
        `/programs/${docEditorState.programId}/structured/apply-to-document/`,
        { method: "POST" }
      );
      toast(`Обновлены разделы: ${(result.updated_sections || []).join(", ")}`);
      if (docEditorState.docId) {
        const doc = await api(`/documents/${docEditorState.docId}/`);
        docEditorState.sections = doc.sections || [];
        if (docEditorState.editorMode === "sections") {
          renderDocEditorSections();
          if (docEditorState.selectedSectionId) {
            selectDocSection(docEditorState.selectedSectionId);
          }
        }
      }
    } catch (err) {
      toast(err.message, true);
    }
  }

  function prepareForDocumentOpen() {
    docEditorState.structured = null;
    docEditorState.editorMode = "sections";
    updateStructuredTabVisibility();
    document.getElementById("docEditorBody")?.classList.remove("hidden");
    document.getElementById("docStructuredPanel")?.classList.add("hidden");
    document.getElementById("docTabSections")?.classList.add("active");
    document.getElementById("docTabStructured")?.classList.remove("active");
    const saveBtn = document.getElementById("docEditorSave");
    if (saveBtn) saveBtn.textContent = "Сохранить";
  }

  function resetStructuredEditor() {
    prepareForDocumentOpen();
  }

  window.ValidationStructured = {
    structuredEnabled,
    updateStructuredTabVisibility,
    prepareForDocumentOpen,
    resetStructuredEditor,
    saveStructuredData,
    loadStructuredData,
    initStructuredEditorUi,
    setDocEditorMode,
  };

  function initStructuredEditorUi() {
    document.getElementById("docTabSections")?.addEventListener("click", () => setDocEditorMode("sections"));
    document.getElementById("docTabStructured")?.addEventListener("click", () => setDocEditorMode("structured"));
    document.querySelectorAll(".struct-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        collectStructuredFromDom();
        ensureStructuredState().activeTab = btn.dataset.struct;
        renderStructuredEditor();
      });
    });
    document.getElementById("structAddRow")?.addEventListener("click", addStructuredRow);
    document.getElementById("structRefreshFromDoc")?.addEventListener("click", () => {
      refreshStructuredFromDocument().catch(err => toast(err.message, true));
    });
    document.getElementById("structApplyToDoc")?.addEventListener("click", () => {
      applyStructuredToDocument().catch(err => toast(err.message, true));
    });
  }

  initStructuredEditorUi();
})();
