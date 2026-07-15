(function () {
  const API = "/api/v1";
  let currentSection = "phrases";
  let modalState = null;

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }

  function compareText(a, b) {
    return String(a ?? "").localeCompare(String(b ?? ""), "ru", { numeric: true, sensitivity: "base" });
  }

  function deptSortButton(key, activeKey, dir) {
    const label = key === "code" ? "Код" : "Название";
    const active = key === activeKey;
    const arrow = active ? (dir > 0 ? " ↑" : " ↓") : "";
    return `<button type="button" class="th-sort${active ? " active" : ""}" data-dept-sort="${key}">${label}${arrow}</button>`;
  }

  function sigSortButton(key, activeKey, dir) {
    const label = key === "role" ? "Роль" : "ФИО";
    const active = key === activeKey;
    const arrow = active ? (dir > 0 ? " ↑" : " ↓") : "";
    return `<button type="button" class="th-sort${active ? " active" : ""}" data-sig-sort="${key}">${label}${arrow}</button>`;
  }

  function signatureHasPng(row) {
    if (typeof row?.has_png === "boolean") return row.has_png;
    return Boolean(row?.png_path);
  }

  function signatureStatusHtml(hasPng) {
    if (hasPng) {
      return '<span class="badge ok" title="PNG загружен — подпись будет в новом PDF">Загружена</span>';
    }
    return '<span class="badge fail" title="PNG не загружен — при экспорте подпись не появится">Нет PNG</span>';
  }

  function signatureUploadCellHtml(id, hasPng) {
    const action = hasPng ? "Заменить" : "Загрузить";
    const title = hasPng
      ? "Заменить PNG/JPG для этой подписи"
      : "Загрузить PNG/JPG для этой подписи";
    return `<label class="btn sm file-pick-btn" title="${esc(title)}">
      ${action}<input type="file" class="sr-only" accept="image/png,image/jpeg,image/jpg,image/webp" data-upload="${esc(id)}">
    </label>`;
  }

  async function api(path, opts = {}) {
    const res = await fetch(`${API}${path}`, {
      ...opts,
      headers: SyllabusAuth.authHeaders({ "Content-Type": "application/json", ...(opts.headers || {}) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(SyllabusApi.errorFromResponse(res.statusText, err));
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    return ct.includes("json") ? res.json() : res.text();
  }

  async function deleteRefItem(path, message = "Удалить запись?") {
    if (!confirm(message)) return false;
    await api(path, { method: "DELETE" });
    return true;
  }

  function deleteBtn(id, title = "Удалить") {
    return `<button class="btn danger" type="button" data-del="${esc(id)}" title="${esc(title)}">×</button>`;
  }

  function editBtn(id, title = "Изменить", kind = "") {
    const kindAttr = kind ? ` data-edit-kind="${esc(kind)}"` : "";
    return `<button class="btn" type="button" data-edit="${esc(id)}"${kindAttr} title="${esc(title)}">Изм.</button>`;
  }

  function rowActions(id, { editTitle, deleteTitle, editKind = "" } = {}) {
    return `${editBtn(id, editTitle || "Изменить", editKind)} ${deleteBtn(id, deleteTitle || "Удалить")}`;
  }

  function renderSelectOptions(options, selectedValue) {
    if (typeof options === "string") return options;
    if (!Array.isArray(options)) return "";
    return options.map(opt => {
      if (typeof opt === "string") {
        const sel = opt === selectedValue ? " selected" : "";
        return `<option value="${esc(opt)}"${sel}>${esc(opt)}</option>`;
      }
      const val = opt.value ?? "";
      const sel = String(val) === String(selectedValue ?? "") ? " selected" : "";
      return `<option value="${esc(val)}"${sel}>${esc(opt.label ?? val)}</option>`;
    }).join("");
  }

  function openModal(title, fields, onSubmit) {
    modalState = { onSubmit };
    document.getElementById("modalTitle").textContent = title;
    const form = document.getElementById("modalForm");
    form.innerHTML = fields.map(f => {
      if (f.type === "textarea") {
        return `<div class="field"><label for="modal-${esc(f.name)}">${esc(f.label)}</label><textarea id="modal-${esc(f.name)}" name="${esc(f.name)}" ${f.required ? "required" : ""}>${esc(f.value || "")}</textarea></div>`;
      }
      if (f.type === "checkbox") {
        return `<div class="field"><label><input type="checkbox" id="modal-${esc(f.name)}" name="${esc(f.name)}" ${f.value ? "checked" : ""}> ${esc(f.label)}</label></div>`;
      }
      if (f.type === "select") {
        const opts = renderSelectOptions(f.options, f.value);
        return `<div class="field"><label for="modal-${esc(f.name)}">${esc(f.label)}</label><select id="modal-${esc(f.name)}" name="${esc(f.name)}" ${f.required ? "required" : ""}>${opts}</select></div>`;
      }
      const inputType = f.inputType || "text";
      return `<div class="field"><label for="modal-${esc(f.name)}">${esc(f.label)}</label><input id="modal-${esc(f.name)}" type="${esc(inputType)}" name="${esc(f.name)}" value="${esc(f.value || "")}" ${f.required ? "required" : ""}></div>`;
    }).join("") + `<div class="modal-actions" style="display:flex;gap:8px;margin-top:16px">
      <button class="btn primary" type="submit">Сохранить</button>
      <button class="btn" type="button" data-action="modal-cancel">Отмена</button>
    </div>`;
    form.querySelector("[data-action=modal-cancel]")?.addEventListener("click", closeModal);
    document.getElementById("refModal").classList.add("open");
    const firstField = form.querySelector("input, select, textarea");
    if (firstField) firstField.focus();
  }

  function closeModal() {
    modalState = null;
    document.getElementById("refModal").classList.remove("open");
  }

  document.getElementById("modalCancel")?.addEventListener("click", closeModal);
  document.getElementById("modalForm").onsubmit = async e => {
    e.preventDefault();
    if (!modalState) return;
    const fd = new FormData(e.target);
    const data = {};
    for (const [k, v] of fd.entries()) data[k] = v;
    const checkbox = e.target.querySelector('input[type="checkbox"]');
    if (checkbox) data[checkbox.name] = checkbox.checked;
    try {
      await modalState.onSubmit(data);
      closeModal();
      renderSection(currentSection);
    } catch (err) {
      alert(err.message);
    }
  };

  async function renderPhrases() {
    const items = await api("/reference/phrases/?active_only=true");
    const main = document.getElementById("refMain");
    main.innerHTML = `
      <div class="panel-card">
        <h2>Стандартные фразы</h2>
        <p class="lead">Версионные тексты для аннотаций, МТО, практик. Используются в конструкторе и экспорте.</p>
        <div class="toolbar">
          <button class="btn primary" type="button" id="btnAddPhrase">＋ Добавить фразу</button>
          <select id="phraseCategoryFilter"><option value="">Все категории</option></select>
        </div>
        <table>
          <thead><tr><th>Категория</th><th>Версия</th><th>Текст</th><th>Активна</th><th></th></tr></thead>
          <tbody id="phraseRows"></tbody>
        </table>
      </div>`;
    const categories = [...new Set(items.map(i => i.category))].sort();
    const filter = document.getElementById("phraseCategoryFilter");
    categories.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      filter.appendChild(opt);
    });
    const tbody = document.getElementById("phraseRows");
    function draw(list) {
      tbody.innerHTML = list.length ? list.map(row => `<tr>
        <td><code>${esc(row.category)}</code></td>
        <td>${row.version}</td>
        <td>${esc(row.text.slice(0, 160))}${row.text.length > 160 ? "…" : ""}</td>
        <td>${row.is_active ? "да" : "—"}</td>
        <td>
          <button class="btn" data-edit="${esc(row.id)}" type="button">Изм.</button>
          <button class="btn" data-propagate="${esc(row.id)}" type="button" title="Заменить текст в программах">↻</button>
          <button class="btn" data-newver="${esc(row.id)}" type="button" title="Новая версия">v+</button>
          <button class="btn danger" data-del="${esc(row.id)}" type="button">×</button>
        </td></tr>`).join("") : `<tr><td colspan="5" class="empty-state">Нет записей</td></tr>`;
    }
    draw(items);
    filter.onchange = () => {
      const cat = filter.value;
      draw(cat ? items.filter(i => i.category === cat) : items);
    };
    document.getElementById("btnAddPhrase").onclick = () => openModal("Новая фраза", [
      { name: "category", label: "Категория", required: true, value: "mto" },
      { name: "version", label: "Версия", value: "1" },
      { name: "text", label: "Текст", type: "textarea", required: true },
    ], async data => {
      await api("/reference/phrases/", {
        method: "POST",
        body: JSON.stringify({
          category: data.category,
          version: Number(data.version || 1),
          text: data.text,
          is_active: true,
        }),
      });
    });
    tbody.onclick = async e => {
      const editId = e.target.closest("[data-edit]")?.dataset.edit;
      const delId = e.target.closest("[data-del]")?.dataset.del;
      const propId = e.target.closest("[data-propagate]")?.dataset.propagate;
      const newVerId = e.target.closest("[data-newver]")?.dataset.newver;
      if (propId) {
        if (!confirm("Заменить текст фразы во всех разделах и конструкторах?")) return;
        const res = await api(`/reference/phrases/${propId}/propagate/`, {
          method: "POST",
          body: JSON.stringify({ mode: "replace_active" }),
        });
        alert(`Обновлено: разделов ${res.sections_updated}, программ ${res.programs_updated}`);
        renderSection("phrases");
        return;
      }
      if (newVerId) {
        const row = items.find(i => i.id === newVerId);
        if (!row) return;
        const text = prompt("Новый текст фразы (новая версия):", row.text);
        if (text === null) return;
        const res = await api(`/reference/phrases/${newVerId}/propagate/`, {
          method: "POST",
          body: JSON.stringify({ mode: "new_version", new_text: text }),
        });
        alert(`Создана версия, обновлено: разделов ${res.sections_updated}, программ ${res.programs_updated}`);
        renderSection("phrases");
        return;
      }
      if (delId) {
        if (!confirm("Удалить фразу из справочника?")) return;
        await api(`/reference/phrases/${delId}/`, { method: "DELETE" });
        renderSection("phrases");
        return;
      }
      if (editId) {
        const row = items.find(i => i.id === editId);
        if (!row) return;
        openModal("Редактировать фразу", [
          { name: "category", label: "Категория", value: row.category, required: true },
          { name: "version", label: "Версия", value: String(row.version) },
          { name: "text", label: "Текст", type: "textarea", value: row.text, required: true },
          { name: "is_active", label: "Активна", type: "checkbox", value: row.is_active },
        ], async data => {
          await api(`/reference/phrases/${editId}/`, {
            method: "PUT",
            body: JSON.stringify({
              category: data.category,
              version: Number(data.version || 1),
              text: data.text,
              is_active: Boolean(data.is_active),
            }),
          });
        });
      }
    };
  }

  async function renderAbbreviations() {
    const items = await api("/reference/abbreviations/");
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Сокращения</h2>
        <p class="lead">Применяются при импорте учебного плана (ОПР-1 → ОПР).</p>
        <div class="toolbar"><button class="btn primary" type="button" id="btnAddAbbr">＋ Добавить</button></div>
        <table><thead><tr><th>Шаблон</th><th>Замена</th><th>Приоритет</th><th>Рег. выражение</th><th></th></tr></thead>
        <tbody id="abbrRows">${items.map(r => `<tr>
          <td><code>${esc(r.pattern)}</code></td><td>${esc(r.replacement)}</td><td>${r.priority}</td><td>${r.is_regex ? "да" : ""}</td>
          <td>${rowActions(r.id, { deleteTitle: "Удалить сокращение" })}</td></tr>`).join("") || `<tr><td colspan="5" class="empty-state">Нет записей</td></tr>`}
        </tbody></table>
      </div>`;
    document.getElementById("btnAddAbbr").onclick = () => openModal("Новое сокращение", [
      { name: "pattern", label: "Шаблон", required: true },
      { name: "replacement", label: "Замена", required: true },
      { name: "priority", label: "Приоритет", value: "0" },
      { name: "is_regex", label: "Регулярное выражение", type: "checkbox" },
    ], async data => {
      await api("/reference/abbreviations/", {
        method: "POST",
        body: JSON.stringify({
          pattern: data.pattern,
          replacement: data.replacement,
          priority: Number(data.priority || 0),
          is_regex: Boolean(data.is_regex),
        }),
      });
    });
    document.getElementById("abbrRows")?.addEventListener("click", async e => {
      const editId = e.target.closest("[data-edit]")?.dataset.edit;
      const delId = e.target.closest("[data-del]")?.dataset.del;
      if (editId) {
        const row = items.find(i => i.id === editId);
        if (!row) return;
        openModal("Редактировать сокращение", [
          { name: "pattern", label: "Шаблон", value: row.pattern, required: true },
          { name: "replacement", label: "Замена", value: row.replacement, required: true },
          { name: "priority", label: "Приоритет", value: String(row.priority ?? 0) },
          { name: "is_regex", label: "Регулярное выражение", type: "checkbox", value: row.is_regex },
        ], async data => {
          await api(`/reference/abbreviations/${editId}/`, {
            method: "PUT",
            body: JSON.stringify({
              pattern: data.pattern,
              replacement: data.replacement,
              priority: Number(data.priority || 0),
              is_regex: Boolean(data.is_regex),
            }),
          });
        });
        return;
      }
      if (!delId) return;
      if (await deleteRefItem(`/reference/abbreviations/${delId}/`, "Удалить сокращение?")) {
      renderSection("abbreviations");
      }
    });
  }

  async function renderDepartments() {
    const items = await api("/reference/departments/");
    let deptSortKey = "code";
    let deptSortDir = 1;

    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Кафедры</h2>
        <p class="lead">Справочник: код кафедры из учебного плана → полное название в отчётах 7.1/7.2 и PDF переутверждения. Импорт: Excel с колонками «Код/Шифр кафедры» и «Название кафедры» (свод УП FGOS3, лист «Справочник» отчёта 7.2).</p>
        <div class="toolbar form-grid" style="margin-bottom:16px;align-items:end">
          <div class="field" style="margin:0"><label>Код кафедры</label><input id="deptResolveCode" placeholder="52"></div>
          <div class="field" style="margin:0"><label>Год набора</label><input id="deptResolveYear" type="number" placeholder="2024"></div>
          <button class="btn" type="button" id="btnResolveDept">Проверить название</button>
        </div>
        <p id="deptResolveOut" style="font-size:13px;color:var(--muted);margin-bottom:12px"></p>
        <div class="toolbar" style="margin-bottom:12px;align-items:center">
          <button class="btn primary" type="button" id="btnAddDept">＋ Добавить</button>
          <label class="btn file-pick-btn" title="Импорт из Excel (.xlsx)">
            Импорт из Excel
            <input type="file" class="sr-only" id="deptImportFile" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
          </label>
        </div>
        <p id="deptImportStatus" style="font-size:13px;min-height:18px;margin:0 0 12px;color:var(--muted)"></p>
        <table id="deptTable">
          <thead><tr id="deptHeadRow"></tr></thead>
          <tbody id="deptRows"></tbody>
        </table>
      </div>`;

    function sortedDepartments() {
      return [...items].sort((a, b) => {
        let cmp = deptSortKey === "code"
          ? compareText(a.code, b.code)
          : compareText(a.name, b.name);
        if (cmp === 0) {
          cmp = deptSortKey === "code"
            ? compareText(a.name, b.name)
            : compareText(a.code, b.code);
        }
        return cmp * deptSortDir;
      });
    }

    function paintDeptTable() {
      const headRow = document.getElementById("deptHeadRow");
      const tbody = document.getElementById("deptRows");
      if (headRow) {
        headRow.innerHTML = `
          <th>${deptSortButton("code", deptSortKey, deptSortDir)}</th>
          <th>${deptSortButton("name", deptSortKey, deptSortDir)}</th>
          <th>Открыта</th><th>Закрыта</th><th>Родитель</th><th></th>`;
      }
      const rows = sortedDepartments();
      tbody.innerHTML = rows.length
        ? rows.map(row => `<tr>
            <td><code>${esc(row.code)}</code></td>
            <td>${esc(row.name)}</td>
            <td>${esc(row.opened_on || "—")}</td>
            <td>${esc(row.closed_on || "—")}</td>
            <td>${esc(row.parent_id || "—")}</td>
            <td>${rowActions(row.id, { deleteTitle: "Удалить кафедру" })}</td>
          </tr>`).join("")
        : `<tr><td colspan="6" class="empty-state">Нет записей</td></tr>`;
    }

    paintDeptTable();
    document.getElementById("deptTable")?.addEventListener("click", e => {
      const sortKey = e.target.closest("[data-dept-sort]")?.dataset.deptSort;
      if (!sortKey) return;
      if (deptSortKey === sortKey) deptSortDir *= -1;
      else {
        deptSortKey = sortKey;
        deptSortDir = 1;
      }
      paintDeptTable();
    });
    document.getElementById("btnAddDept").onclick = () => openModal("Новая кафедра", [
      { name: "code", label: "Код", required: true },
      { name: "name", label: "Название", required: true },
      { name: "opened_on", label: "Открыта (ГГГГ-ММ-ДД)" },
      { name: "closed_on", label: "Закрыта (ГГГГ-ММ-ДД)" },
    ], async data => {
      const body = {
        code: data.code,
        name: data.name,
        opened_on: data.opened_on || null,
        closed_on: data.closed_on || null,
      };
      await api("/reference/departments/", { method: "POST", body: JSON.stringify(body) });
      renderSection("departments");
    });
    document.getElementById("deptImportFile")?.addEventListener("change", async e => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      const statusEl = document.getElementById("deptImportStatus");
      if (statusEl) {
        statusEl.textContent = `Импорт «${file.name}»…`;
        statusEl.style.color = "var(--muted)";
      }
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/reference/departments/import/`, {
        method: "POST",
        body: fd,
        headers: SyllabusAuth.authHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = SyllabusApi.errorFromResponse(res.statusText, err);
        if (statusEl) {
          statusEl.textContent = msg;
          statusEl.style.color = "var(--danger, #d13438)";
        } else {
          alert(msg);
        }
        return;
      }
      const data = await res.json();
      const warn = (data.warnings || []).length ? ` ${data.warnings[0]}` : "";
      if (statusEl) {
        statusEl.textContent = `Добавлено: ${data.added}, уже было: ${data.skipped}, в файле: ${data.total}.${warn}`;
        statusEl.style.color = "var(--ok, #107c10)";
      }
      await renderDepartments();
    });
    document.getElementById("btnResolveDept").onclick = async () => {
      const code = document.getElementById("deptResolveCode").value.trim();
      const yearRaw = document.getElementById("deptResolveYear").value.trim();
      if (!code) return;
      const q = new URLSearchParams({ code });
      if (yearRaw) q.set("year", yearRaw);
      const res = await api(`/reference/departments/resolve/?${q}`);
      document.getElementById("deptResolveOut").textContent = res.found
        ? `→ ${res.name}`
        : "Кафедра не найдена для указанного кода/года";
    };
    document.getElementById("deptRows")?.addEventListener("click", async e => {
      const editId = e.target.closest("[data-edit]")?.dataset.edit;
      const delId = e.target.closest("[data-del]")?.dataset.del;
      if (editId) {
        const row = items.find(i => i.id === editId);
        if (!row) return;
        openModal("Редактировать кафедру", [
          { name: "code", label: "Код", value: row.code, required: true },
          { name: "name", label: "Название", value: row.name, required: true },
          { name: "opened_on", label: "Открыта (ГГГГ-ММ-ДД)", value: row.opened_on || "" },
          { name: "closed_on", label: "Закрыта (ГГГГ-ММ-ДД)", value: row.closed_on || "" },
        ], async data => {
          await api(`/reference/departments/${editId}/`, {
            method: "PUT",
            body: JSON.stringify({
              code: data.code,
              name: data.name,
              opened_on: data.opened_on || null,
              closed_on: data.closed_on || null,
            }),
          });
        });
        return;
      }
      if (!delId) return;
      if (await deleteRefItem(`/reference/departments/${delId}/`, "Удалить кафедру из справочника?")) {
        renderSection("departments");
      }
    });
  }

  async function renderLayout() {
    const data = await api("/reference/layout-templates/");
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Макеты документов</h2>
        <p class="lead">Папка: <code>${esc(data.layout_dir)}</code>. Конструктор ГИА/РПп экспортирует через эти файлы (.docx или .doc).</p>
        <div class="toolbar">
          <button class="btn primary" type="button" id="btnReseedLayout">↻ Перечитать папку макетов</button>
        </div>
        <table>
          <thead><tr><th>Макет</th><th>Ожидаемый файл</th><th>Найден</th></tr></thead>
          <tbody>${(data.templates || []).map(row => `<tr>
            <td>${esc(row.name)}</td>
            <td><code>${esc(row.preferred)}</code></td>
            <td>${row.found ? `<span class="badge ok">да</span> <code>${esc(row.found)}</code>` : '<span class="badge no">нет</span>'}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
    document.getElementById("btnReseedLayout").onclick = async () => {
      const res = await api("/reference/layout-templates/reseed/", { method: "POST" });
      alert(`Зарегистрировано: ${(res.registered || []).join(", ") || "ничего — положите файлы в папку «Макеты»"}`);
      renderLayout();
    };
  }

  async function renderArchive() {
    const [volumes, plans] = await Promise.all([
      api("/archive/volumes/"),
      api("/study-plans/"),
    ]);
    const planMap = Object.fromEntries(plans.map(p => [p.id, p]));
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Архивные тома</h2>
        <p class="lead">Опись, лист-заверитель и PDF с левым полем 30 мм.</p>
        <div class="toolbar">
          <button class="btn primary" type="button" id="btnAddVolume">＋ Новый том</button>
        </div>
        <table>
          <thead><tr><th>Название</th><th>Учебный план</th><th>Статус</th><th>Опись</th><th></th></tr></thead>
          <tbody id="archiveRows">${volumes.length ? volumes.map(v => {
            const plan = planMap[v.study_plan_id];
            const planLabel = plan ? `${plan.direction_code} · ${plan.year}` : v.study_plan_id;
            return `<tr data-vol="${esc(v.id)}">
              <td>${esc(v.title)}</td>
              <td>${esc(planLabel)}</td>
              <td><code>${esc(v.status)}</code></td>
              <td>${v.has_inventory ? "да" : "—"}</td>
              <td><button class="btn" type="button" data-open="${esc(v.id)}">Открыть</button> ${deleteBtn(v.id, "Удалить том")}</td>
            </tr>`;
          }).join("") : `<tr><td colspan="5" class="empty-state">Нет томов</td></tr>`}
          </tbody>
        </table>
      </div>
      <div id="archiveDetail"></div>`;

    document.getElementById("btnAddVolume").onclick = () => {
      const planOptions = plans.map(p =>
        `<option value="${esc(p.id)}">${esc(p.direction_code || "?")} · ${esc(p.profile_name || p.source_file || p.id)} · ${p.year || ""}</option>`
      ).join("");
      openModal("Новый архивный том", [
        { name: "title", label: "Название тома", value: "Архивный том", required: true },
        { name: "study_plan_id", label: "Учебный план", type: "select", options: planOptions, value: plans[0]?.id || "", required: true },
        { name: "cover_text", label: "Лист-заверитель (оставьте пустым — шаблон)", type: "textarea" },
      ], async data => {
        let cover = data.cover_text || null;
        if (!cover && data.study_plan_id) {
          const tpl = await api(`/archive/certification-template/?study_plan_id=${encodeURIComponent(data.study_plan_id)}&title=${encodeURIComponent(data.title)}`);
          cover = tpl.text;
        }
        await api("/archive/volumes/", {
          method: "POST",
          body: JSON.stringify({
            title: data.title,
            study_plan_id: data.study_plan_id,
            cover_text: cover,
          }),
        });
        renderSection("archive");
      });
    };

    document.getElementById("archiveRows").onclick = async e => {
      const delId = e.target.closest("[data-del]")?.dataset.del;
      if (delId) {
        if (await deleteRefItem(`/archive/volumes/${delId}/`, "Удалить архивный том?")) {
          document.getElementById("archiveDetail").innerHTML = "";
          renderSection("archive");
        }
        return;
      }
      const id = e.target.closest("[data-open]")?.dataset.open;
      if (!id) return;
      await renderArchiveDetail(id);
    };
  }

  async function renderArchiveDetail(volumeId) {
    const volume = await api(`/archive/volumes/${volumeId}/`);
    const host = document.getElementById("archiveDetail");
    host.innerHTML = `
      <div class="panel-card" style="margin-top:16px">
        <h3>${esc(volume.title)}</h3>
        <p class="lead">Статус: <code>${esc(volume.status)}</code> · документов: ${volume.items.length}</p>
        <div class="toolbar" style="flex-wrap:wrap">
          <button class="btn" type="button" id="archPopulate">Заполнить из плана</button>
          <button class="btn" type="button" id="archRebuildInv">Пересобрать опись</button>
          <button class="btn" type="button" id="archTplCover">Шаблон листа-заверителя</button>
          <button class="btn primary" type="button" id="archExportPdf">Скачать PDF</button>
          <button class="btn" type="button" id="archExportZip">Скачать архив</button>
        </div>
        <div class="field" style="margin-top:12px">
          <label>Лист-заверитель / обложка</label>
          <textarea id="archCover" rows="3">${esc(volume.cover_text || "")}</textarea>
        </div>
        <div class="field">
          <label><input type="checkbox" id="archDuplex" ${volume.duplex_enabled !== false ? "checked" : ""}> Duplex (новый документ с нечётной страницы, номер с внешнего поля)</label>
        </div>
        <div class="field">
          <label>Опись</label>
          <textarea id="archInventory" rows="10">${esc(volume.inventory_text || "")}</textarea>
        </div>
        <button class="btn" type="button" id="archSaveMeta">Сохранить текст</button>
        <table style="margin-top:16px">
          <thead><tr><th>#</th><th>Шифр</th><th>Дисциплина</th><th>Листов</th><th>Страницы</th></tr></thead>
          <tbody>${volume.items.map(item => `<tr>
            <td>${item.row_order + 1}</td>
            <td><code>${esc(item.discipline?.code || "—")}</code></td>
            <td>${esc(item.discipline?.name || "—")}</td>
            <td>${item.sheet_count ?? "—"}</td>
            <td>${item.page_start && item.page_end ? (item.page_start === item.page_end ? item.page_start : `${item.page_start}–${item.page_end}`) : "—"}</td>
          </tr>`).join("") || `<tr><td colspan="5" class="empty-state">Пусто — нажмите «Заполнить из плана»</td></tr>`}
          </tbody>
        </table>
      </div>`;

    document.getElementById("archPopulate").onclick = async () => {
      await api(`/archive/volumes/${volumeId}/populate-from-plan/`, { method: "POST" });
      await renderArchiveDetail(volumeId);
    };
    document.getElementById("archRebuildInv").onclick = async () => {
      await api(`/archive/volumes/${volumeId}/build-inventory/`, { method: "POST" });
      await renderArchiveDetail(volumeId);
    };
    document.getElementById("archTplCover").onclick = async () => {
      const tpl = await api(
        `/archive/certification-template/?study_plan_id=${encodeURIComponent(volume.study_plan_id)}&title=${encodeURIComponent(volume.title)}`
      );
      document.getElementById("archCover").value = tpl.text;
    };
    document.getElementById("archSaveMeta").onclick = async () => {
      await api(`/archive/volumes/${volumeId}/`, {
        method: "PATCH",
        body: JSON.stringify({
          cover_text: document.getElementById("archCover").value,
          inventory_text: document.getElementById("archInventory").value,
          duplex_enabled: document.getElementById("archDuplex").checked,
        }),
      });
      alert("Сохранено");
    };
    document.getElementById("archExportPdf").onclick = () => {
      window.open(`${API}/archive/volumes/${volumeId}/export.pdf`, "_blank");
    };
    document.getElementById("archExportZip").onclick = () => {
      window.open(`${API}/archive/volumes/${volumeId}/export.zip`, "_blank");
    };
  }

  async function renderAuthorsLoad() {
    const plans = await api("/study-plans/");
    const planOptions = plans.map(p =>
      `<option value="${esc(p.id)}">${esc(p.direction_code || "?")} · ${esc(p.profile_name || p.source_file)} · ${p.year || ""}</option>`
    ).join("");
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Нагрузка авторов (отчёт 7.2)</h2>
        <p class="lead">Теневое закрепление, доля %, балл за з.е. По умолчанию авторы берутся из РПД.</p>
        <div class="toolbar form-grid" style="align-items:end">
          <div class="field" style="margin:0"><label>Учебный план</label>
            <select id="authorsPlan">${planOptions}</select></div>
          <button class="btn primary" type="button" id="btnLoadAuthors">Показать</button>
          <button class="btn" type="button" id="btnAddAuthorLoad">＋ Автор</button>
        </div>
        <table style="margin-top:16px">
          <thead><tr><th>Шифр</th><th>Автор</th><th>Тень</th><th>Доля %</th><th>Балл/з.е.</th><th>Фикс.</th><th></th></tr></thead>
          <tbody id="authorsLoadRows"><tr><td colspan="7" class="empty-state">Выберите план</td></tr></tbody>
        </table>
      </div>`;
    let currentDisciplines = [];
    let currentLoads = [];

    async function loadPlan(planId) {
      const [disciplines, loads] = await Promise.all([
        api(`/study-plans/${planId}/disciplines/`),
        api("/reference/authors-load/"),
      ]);
      currentDisciplines = disciplines;
      currentLoads = loads.filter(l => disciplines.some(d => d.id === l.plan_discipline_id));
      const discMap = Object.fromEntries(disciplines.map(d => [d.id, d]));
      const tbody = document.getElementById("authorsLoadRows");
      tbody.innerHTML = currentLoads.length ? currentLoads.map(row => {
        const d = discMap[row.plan_discipline_id] || {};
        return `<tr data-id="${esc(row.id)}">
          <td><code>${esc(d.code || "—")}</code></td>
          <td>${esc(row.author_name)}</td>
          <td>${row.is_shadow ? "да" : "—"}</td>
          <td>${row.share_percent ?? "—"}</td>
          <td>${row.points_per_credit ?? "—"}</td>
          <td>${row.fixed_points ?? "—"}</td>
          <td><button class="btn" type="button" data-edit-load="${esc(row.id)}">Изм.</button>
          <button class="btn danger" type="button" data-del-load="${esc(row.id)}">×</button></td></tr>`;
      }).join("") : `<tr><td colspan="7" class="empty-state">Нет записей — добавьте или используйте авторов из РПД</td></tr>`;
    }

    document.getElementById("btnLoadAuthors").onclick = () => {
      const planId = document.getElementById("authorsPlan").value;
      if (planId) loadPlan(planId);
    };
    if (plans[0]) loadPlan(plans[0].id);

    document.getElementById("btnAddAuthorLoad").onclick = () => {
      const planId = document.getElementById("authorsPlan").value;
      if (!planId) return alert("Выберите план");
      const discOptions = currentDisciplines.map(d =>
        `<option value="${esc(d.id)}">${esc(d.code)} — ${esc(d.name)}</option>`
      ).join("");
      openModal("Нагрузка автора", [
        { name: "plan_discipline_id", label: "Дисциплина", type: "select", options: discOptions, required: true },
        { name: "author_name", label: "ФИО", required: true },
        { name: "is_shadow", label: "Теневое закрепление", type: "checkbox" },
        { name: "share_percent", label: "Доля %", value: "100" },
        { name: "points_per_credit", label: "Балл за 1 з.е.", value: "20" },
        { name: "fixed_points", label: "Фикс. баллы (необяз.)" },
      ], async data => {
        await api("/reference/authors-load/", {
          method: "POST",
          body: JSON.stringify({
            plan_discipline_id: data.plan_discipline_id,
            author_name: data.author_name,
            is_shadow: Boolean(data.is_shadow),
            share_percent: data.share_percent ? Number(data.share_percent) : null,
            points_per_credit: data.points_per_credit ? Number(data.points_per_credit) : null,
            fixed_points: data.fixed_points ? Number(data.fixed_points) : null,
          }),
        });
        await loadPlan(planId);
      });
    };

    document.getElementById("authorsLoadRows").onclick = async e => {
      const editId = e.target.closest("[data-edit-load]")?.dataset.editLoad;
      const delId = e.target.closest("[data-del-load]")?.dataset.delLoad;
      const planId = document.getElementById("authorsPlan").value;
      if (delId) {
        if (!confirm("Удалить запись?")) return;
        await api(`/reference/authors-load/${delId}/`, { method: "DELETE" });
        await loadPlan(planId);
        return;
      }
      if (editId) {
        const row = currentLoads.find(r => r.id === editId);
        if (!row) return;
        openModal("Редактировать нагрузку", [
          { name: "author_name", label: "ФИО", value: row.author_name, required: true },
          { name: "is_shadow", label: "Теневое", type: "checkbox", value: row.is_shadow },
          { name: "share_percent", label: "Доля %", value: String(row.share_percent ?? "") },
          { name: "points_per_credit", label: "Балл/з.е.", value: String(row.points_per_credit ?? "") },
          { name: "fixed_points", label: "Фикс.", value: String(row.fixed_points ?? "") },
        ], async data => {
          await api(`/reference/authors-load/${editId}/`, {
            method: "PUT",
            body: JSON.stringify({
              author_name: data.author_name,
              is_shadow: Boolean(data.is_shadow),
              share_percent: data.share_percent ? Number(data.share_percent) : null,
              points_per_credit: data.points_per_credit ? Number(data.points_per_credit) : null,
              fixed_points: data.fixed_points ? Number(data.fixed_points) : null,
            }),
          });
          await loadPlan(planId);
        });
      }
    };
  }

  async function renderSimpleList(title, lead, path, columns, addFields, createBody, opts = {}) {
    const items = await api(path);
    const deleteBase = (opts.deleteBase || path).replace(/\/$/, "");
    const deleteMessage = opts.deleteMessage || "Удалить запись?";
    const updateBase = (opts.updateBase || deleteBase).replace(/\/$/, "");
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card"><h2>${esc(title)}</h2><p class="lead">${esc(lead)}</p>
      <div class="toolbar"><button class="btn primary" type="button" id="btnAdd">＋ Добавить</button></div>
      <table><thead><tr>${columns.map(c => `<th>${esc(c.label)}</th>`).join("")}<th></th></tr></thead>
      <tbody id="simpleListRows">${items.map(row => `<tr>${columns.map(c => `<td>${esc(row[c.key] ?? "—")}</td>`).join("")}<td>${rowActions(row.id)}</td></tr>`).join("") || `<tr><td colspan="${columns.length + 1}" class="empty-state">Нет записей</td></tr>`}
      </tbody></table></div>`;
    document.getElementById("btnAdd").onclick = () => openModal(`Новая запись: ${title}`, addFields, async data => {
      await api(path.replace(/\/$/, "") + "/", { method: "POST", body: JSON.stringify(createBody(data)) });
    });
    document.getElementById("simpleListRows")?.addEventListener("click", async e => {
      const editId = e.target.closest("[data-edit]")?.dataset.edit;
      const delId = e.target.closest("[data-del]")?.dataset.del;
      if (editId && opts.editFields) {
        const row = items.find(i => i.id === editId);
        if (!row) return;
        const fields = opts.editFields(row);
        openModal(`Редактировать: ${title}`, fields, async data => {
          const body = opts.updateBody ? opts.updateBody(data, row) : createBody(data);
          await api(`${updateBase}/${editId}/`, { method: "PUT", body: JSON.stringify(body) });
        });
        return;
      }
      if (!delId) return;
      if (await deleteRefItem(`${deleteBase}/${delId}/`, deleteMessage)) {
        renderSection(currentSection);
      }
    });
  }

  function signatureRoleOptions() {
    return window.SyllabusUiRu?.signatureRoleOptions || [
      { value: "director", label: "Директор института" },
      { value: "dept_head", label: "Заведующий кафедрой" },
      { value: "discipline_head", label: "Руководитель программы" },
    ];
  }

  async function saveSignatureEntry(role, fullName, statusEl) {
    const name = String(fullName || "").trim();
    if (!name) {
      throw new Error("Введите ФИО");
    }
    if (statusEl) {
      statusEl.textContent = "Сохранение…";
      statusEl.style.color = "var(--muted)";
    }
    await api("/reference/signatures/", {
      method: "POST",
      body: JSON.stringify({ role, full_name: name }),
    });
    if (statusEl) {
      statusEl.textContent = `Добавлено: ${name}`;
      statusEl.style.color = "var(--ok, #107c10)";
    }
  }

  async function renderSignatures() {
    const items = await api("/reference/signatures/");
    const roleLabel = role => (window.SyllabusUiRu?.signatureRoleLabel || (r => r))(role);
    const roleOptionsHtml = renderSelectOptions(signatureRoleOptions(), "director");
    const roleOrder = { director: 0, dept_head: 1, discipline_head: 2 };
    let sigSortKey = "role";
    let sigSortDir = 1;
    const loadedCount = items.filter(signatureHasPng).length;
    const missingCount = items.length - loadedCount;
    const roleSummary = (() => {
      const byRole = {};
      for (const r of items) {
        if (!byRole[r.role]) byRole[r.role] = { loaded: 0, total: 0 };
        byRole[r.role].total += 1;
        if (signatureHasPng(r)) byRole[r.role].loaded += 1;
      }
      return Object.keys(byRole)
        .sort((a, b) => (roleOrder[a] ?? 9) - (roleOrder[b] ?? 9))
        .map(role => `${roleLabel(role)} ${byRole[role].loaded}/${byRole[role].total}`)
        .join(" · ");
    })();
    const summaryHtml = items.length
      ? `<div class="sig-controls" style="display:flex;flex-direction:column;gap:16px;margin:18px 0 20px">
        <div class="sig-summary">
          <span><strong>${loadedCount}</strong> с PNG · ${missingCount
            ? `<strong class="sig-missing-count">${missingCount}</strong> без PNG · `
            : ""}всего <strong>${items.length}</strong></span>
          ${missingCount === 0
            ? '<span class="badge ok sig-all-ready">Все подписи готовы</span>'
            : `<span class="sig-role-breakdown">${esc(roleSummary)}</span>`}
        </div>
        <div class="sig-toolbar">
          <input type="search" id="sigSearch" class="sig-search" placeholder="Поиск по ФИО…" autocomplete="off">
          <div class="sig-filter-btns">
            <button type="button" class="btn sm active" data-sig-filter="all">Все (${items.length})</button>
            <button type="button" class="btn sm" data-sig-filter="missing">Без PNG (${missingCount})</button>
            <button type="button" class="btn sm" data-sig-filter="loaded">С PNG (${loadedCount})</button>
          </div>
        </div>
      </div>`
      : "";
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Подписи для PDF</h2>
        <p class="lead">PNG накладываются при <strong>новом</strong> экспорте PDF. Уже сохранённые файлы не меняются. Удаление скрывает подпись из справочника (запись остаётся в базе), для правки ФИО или роли используйте «Изм.»</p>
        <div class="form-grid" style="grid-template-columns:minmax(180px,1fr) minmax(220px,2fr) auto;align-items:end;margin-bottom:12px">
          <div class="field" style="margin:0">
            <label for="sigAddRole">Роль</label>
            <select id="sigAddRole">${roleOptionsHtml}</select>
          </div>
          <div class="field" style="margin:0">
            <label for="sigAddName">ФИО</label>
            <input id="sigAddName" type="text" placeholder="Иванова Мария Петровна" autocomplete="name">
          </div>
          <button type="button" class="btn primary" id="btnSaveSig">Сохранить</button>
        </div>
        <p id="sigStatus" style="font-size:13px;min-height:18px;margin:0 0 16px;color:var(--muted)"></p>
        ${summaryHtml}
        <div class="sig-table-wrap" style="margin-top:4px">
        <table id="sigTable">
          <thead><tr id="sigHeadRow"></tr></thead>
          <tbody id="sigRows"></tbody>
        </table>
        </div>
      </div>`;
    const tbody = document.getElementById("sigRows");
    let sigFilter = "all";

    function sortSignatures(list) {
      return [...list].sort((a, b) => {
        let cmp = 0;
        if (sigSortKey === "role") {
          cmp = (roleOrder[a.role] ?? 9) - (roleOrder[b.role] ?? 9);
          if (cmp === 0) cmp = compareText(a.full_name, b.full_name);
        } else {
          cmp = compareText(a.full_name, b.full_name);
          if (cmp === 0) cmp = (roleOrder[a.role] ?? 9) - (roleOrder[b.role] ?? 9);
        }
        return cmp * sigSortDir;
      });
    }

    function paintSigRows() {
      const headRow = document.getElementById("sigHeadRow");
      if (headRow) {
        headRow.innerHTML = `
          <th>${sigSortButton("role", sigSortKey, sigSortDir)}</th>
          <th>${sigSortButton("name", sigSortKey, sigSortDir)}</th>
          <th>Статус PNG</th><th>Действие</th><th></th>`;
      }
      const query = (document.getElementById("sigSearch")?.value || "").trim().toLowerCase();
      const visible = sortSignatures(items.filter(r => {
        if (sigFilter === "missing" && signatureHasPng(r)) return false;
        if (sigFilter === "loaded" && !signatureHasPng(r)) return false;
        if (query && !String(r.full_name || "").toLowerCase().includes(query)) return false;
        return true;
      }));
      tbody.innerHTML = visible.length
        ? visible.map(r => {
          const hasPng = signatureHasPng(r);
          const rowClass = hasPng ? "" : ' class="row-missing-png"';
          return `<tr${rowClass} data-sig-id="${esc(r.id)}">
      <td>${esc(roleLabel(r.role))}</td>
      <td>${esc(r.full_name)}</td>
      <td>${signatureStatusHtml(hasPng)}</td>
      <td>${signatureUploadCellHtml(r.id, hasPng)}</td>
      <td>${rowActions(r.id, { deleteTitle: "Скрыть подпись из справочника" })}</td></tr>`;
        }).join("")
        : `<tr><td colspan="5" class="empty-state">${
          items.length === 0
            ? "Пока нет подписей — заполните форму выше и нажмите «Сохранить»."
            : query
              ? "Никого не найдено по запросу."
              : "Нет записей для выбранного фильтра."
        }</td></tr>`;
    }

    paintSigRows();
    document.getElementById("sigTable")?.addEventListener("click", e => {
      const sortKey = e.target.closest("[data-sig-sort]")?.dataset.sigSort;
      if (!sortKey) return;
      if (sigSortKey === sortKey) sigSortDir *= -1;
      else {
        sigSortKey = sortKey;
        sigSortDir = 1;
      }
      paintSigRows();
    });
    document.getElementById("sigSearch")?.addEventListener(
      "input",
      SyllabusUi.debounce(paintSigRows, 250)
    );
    document.querySelectorAll("[data-sig-filter]").forEach(btn => {
      btn.onclick = () => {
        sigFilter = btn.dataset.sigFilter;
        document.querySelectorAll("[data-sig-filter]").forEach(b => b.classList.toggle("active", b === btn));
        paintSigRows();
      };
    });

    const statusEl = document.getElementById("sigStatus");
    const nameInput = document.getElementById("sigAddName");
    const roleInput = document.getElementById("sigAddRole");

    async function submitInlineSignature() {
      try {
        await saveSignatureEntry(roleInput.value, nameInput.value, statusEl);
        nameInput.value = "";
        nameInput.focus();
        await renderSignatures();
      } catch (err) {
        if (statusEl) {
          statusEl.textContent = err.message || "Ошибка сохранения";
          statusEl.style.color = "var(--danger, #d13438)";
        } else {
          alert(err.message);
        }
      }
    }

    document.getElementById("btnSaveSig").onclick = () => submitInlineSignature();
    nameInput.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitInlineSignature();
      }
    });

    tbody.onchange = async e => {
      const input = e.target.closest("[data-upload]");
      const file = input?.files?.[0];
      if (!file) return;
      const row = items.find(i => i.id === input.dataset.upload);
      const who = row ? `${roleLabel(row.role)} — ${row.full_name}` : "подпись";
      const fd = new FormData();
      fd.append("file", file);
      if (statusEl) {
        statusEl.textContent = `Загрузка для ${who}…`;
        statusEl.style.color = "var(--muted)";
      }
      const res = await fetch(`${API}/reference/signatures/${input.dataset.upload}/png/`, {
        method: "POST",
        body: fd,
        headers: SyllabusAuth.authHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = SyllabusApi.errorFromResponse(res.statusText, err);
        if (statusEl) {
          statusEl.textContent = msg;
          statusEl.style.color = "var(--danger, #d13438)";
        } else {
          alert(msg);
        }
        return;
      }
      const payload = await res.json().catch(() => ({}));
      if (!payload.has_png && !payload.png_path) {
        if (statusEl) {
          statusEl.textContent = "Сервер не подтвердил загрузку — обновите страницу";
          statusEl.style.color = "var(--danger, #d13438)";
        }
        return;
      }
      if (statusEl) {
        statusEl.textContent = `PNG загружен: ${who}`;
        statusEl.style.color = "var(--ok, #107c10)";
      }
      await renderSignatures();
      const freshRow = document.querySelector(`tr[data-sig-id="${input.dataset.upload}"]`);
      freshRow?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    tbody.addEventListener("click", async e => {
      const editId = e.target.closest("[data-edit]")?.dataset.edit;
      const delId = e.target.closest("[data-del]")?.dataset.del;
      if (editId) {
        const row = items.find(i => i.id === editId);
        if (!row) return;
        openModal("Редактировать подпись", [
          {
            name: "role",
            label: "Роль",
            type: "select",
            options: signatureRoleOptions(),
            value: row.role,
            required: true,
          },
          { name: "full_name", label: "ФИО", value: row.full_name, required: true },
        ], async data => {
          await api(`/reference/signatures/${editId}/`, {
            method: "PUT",
            body: JSON.stringify({ role: data.role, full_name: data.full_name }),
          });
        });
        return;
      }
      if (!delId) return;
      if (await deleteRefItem(
        `/reference/signatures/${delId}/`,
        "Скрыть подпись из справочника? Уже скачанные PDF не изменятся. При новом экспорте PDF эта подпись не будет использоваться."
      )) {
        await renderSignatures();
      }
    });
  }

  async function renderSection(name) {
    currentSection = name;
    try {
      sessionStorage.setItem("ref_tab", name);
    } catch (_) {}
    document.querySelectorAll(".ref-tab").forEach(t => t.classList.toggle("active", t.dataset.ref === name));
    try {
      if (name === "phrases") await renderPhrases();
      else if (name === "abbreviations") await renderAbbreviations();
      else if (name === "departments") await renderDepartments();
      else if (name === "signatures") await renderSignatures();
      else if (name === "authors-load") await renderAuthorsLoad();
      else if (name === "archive") await renderArchive();
      else if (name === "layout") await renderLayout();
      else if (name === "fgos") {
        const [items, indicators] = await Promise.all([
          api("/reference/fgos/competencies/"),
          api("/reference/fgos/indicators/"),
        ]);
        const indByComp = indicators.reduce((acc, row) => {
          (acc[row.competency_id] ||= []).push(row);
          return acc;
        }, {});
        document.getElementById("refMain").innerHTML = `<div class="panel-card"><h2>ФГОС</h2><p class="lead">Компетенции УК/ОПК/ПК и индикаторы. Проверка кодов перед вводом в РПД.</p>
        <div class="toolbar form-grid" style="margin-bottom:16px;align-items:end">
          <div class="field" style="margin:0"><label>Код компетенции</label><input id="fgosCheckComp" placeholder="ОПК-1"></div>
          <div class="field" style="margin:0"><label>Код индикатора</label><input id="fgosCheckInd" placeholder="ИОПК-1.1"></div>
          <button class="btn" type="button" id="btnCheckFgos">Проверить</button>
        </div>
        <p id="fgosCheckOut" style="font-size:13px;color:var(--muted);margin-bottom:12px"></p>
        <div class="toolbar"><button class="btn primary" id="btnAddFgos" type="button">＋ Компетенция</button>
        <button class="btn" id="btnAddIndicator" type="button">＋ Индикатор</button></div>
        <table><thead><tr><th>Код</th><th>Тип</th><th>Название</th><th>Индикаторы</th><th></th></tr></thead>
        <tbody id="fgosRows">${items.map(r => {
          const inds = indByComp[r.id] || [];
          const indHtml = inds.length
            ? `<ul style="margin:0;padding-left:18px">${inds.map(i => `<li style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap"><span><code>${esc(i.code)}</code> ${esc(i.title.slice(0, 80))}${i.title.length > 80 ? "…" : ""}</span>${editBtn(i.id, "Изм.", "indicator")} ${deleteBtn(i.id, "Удалить индикатор")}</li>`).join("")}</ul>`
            : "—";
          return `<tr><td><code>${esc(r.code)}</code></td><td>${esc(r.kind)}</td><td>${esc(r.title)}</td><td>${indHtml}</td><td>${editBtn(r.id, "Изм.", "competency")} ${deleteBtn(r.id, "Удалить компетенцию")}</td></tr>`;
        }).join("") || `<tr><td colspan="5" class="empty-state">Нет записей</td></tr>`}</tbody></table></div>`;
        document.getElementById("fgosRows")?.addEventListener("click", async e => {
          const editEl = e.target.closest("[data-edit]");
          const editId = editEl?.dataset.edit;
          const editKind = editEl?.dataset.editKind;
          const delId = e.target.closest("[data-del]")?.dataset.del;
          if (editId && editKind === "competency") {
            const row = items.find(i => i.id === editId);
            if (!row) return;
            openModal("Редактировать компетенцию", [
              { name: "kind", label: "Тип (UK/OPK/PK)", value: row.kind, required: true },
              { name: "code", label: "Код", value: row.code, required: true },
              { name: "title", label: "Название", type: "textarea", value: row.title, required: true },
            ], async data => {
              await api(`/reference/fgos/competencies/${editId}/`, { method: "PUT", body: JSON.stringify(data) });
            });
            return;
          }
          if (editId && editKind === "indicator") {
            const row = indicators.find(i => i.id === editId);
            if (!row) return;
            openModal("Редактировать индикатор", [
              { name: "competency_id", label: "ID компетенции", value: row.competency_id, required: true },
              { name: "code", label: "Код", value: row.code, required: true },
              { name: "title", label: "Название", type: "textarea", value: row.title, required: true },
            ], async data => {
              await api(`/reference/fgos/indicators/${editId}/`, { method: "PUT", body: JSON.stringify(data) });
            });
            return;
          }
          if (!delId) return;
          const isIndicator = indicators.some(i => i.id === delId);
          const msg = isIndicator
            ? "Удалить индикатор из справочника?"
            : "Удалить компетенцию и все её индикаторы?";
          const path = isIndicator
            ? `/reference/fgos/indicators/${delId}/`
            : `/reference/fgos/competencies/${delId}/`;
          if (await deleteRefItem(path, msg)) renderSection("fgos");
        });
        document.getElementById("btnCheckFgos").onclick = async () => {
          const competency = document.getElementById("fgosCheckComp").value.trim();
          const indicator = document.getElementById("fgosCheckInd").value.trim();
          if (!competency && !indicator) return;
          const q = new URLSearchParams();
          if (competency) q.set("competency", competency);
          if (indicator) q.set("indicator", indicator);
          const res = await api(`/reference/fgos/check/?${q}`);
          const parts = [];
          if (competency) parts.push(res.competency_ok ? `Компетенция найдена: ${res.competency_title || competency}` : `Компетенция «${competency}» не в справочнике`);
          if (indicator) parts.push(res.indicator_ok ? `Индикатор найден: ${res.indicator_title || indicator}` : `Индикатор «${indicator}» не в справочнике`);
          document.getElementById("fgosCheckOut").textContent = parts.join(" · ");
        };
        document.getElementById("btnAddFgos").onclick = () => openModal("Новая компетенция", [
          { name: "kind", label: "Тип (UK/OPK/PK)", value: "OPK", required: true },
          { name: "code", label: "Код", required: true },
          { name: "title", label: "Название", type: "textarea", required: true },
        ], async data => {
          await api("/reference/fgos/competencies/", { method: "POST", body: JSON.stringify(data) });
        });
        document.getElementById("btnAddIndicator").onclick = () => openModal("Новый индикатор", [
          { name: "competency_id", label: "ID компетенции", required: true },
          { name: "code", label: "Код индикатора", required: true },
          { name: "title", label: "Название", type: "textarea", required: true },
        ], async data => {
          await api("/reference/fgos/indicators/", { method: "POST", body: JSON.stringify(data) });
        });
      } else if (name === "mto") {
        await renderSimpleList("МТО", "Аудитории и оборудование. Привязка к программе — карточка дисциплины на рабочем столе (P3).", "/reference/mto/rooms/", [
          { key: "code", label: "Код" }, { key: "name", label: "Название" }, { key: "equipment", label: "Оборудование" },
        ], [
          { name: "code", label: "Код", required: true },
          { name: "name", label: "Название", required: true },
          { name: "equipment", label: "Оборудование", type: "textarea" },
        ], d => ({ code: d.code, name: d.name, equipment: d.equipment || null }), {
          deleteMessage: "Удалить аудиторию из справочника?",
          editFields: row => [
            { name: "code", label: "Код", value: row.code, required: true },
            { name: "name", label: "Название", value: row.name, required: true },
            { name: "equipment", label: "Оборудование", type: "textarea", value: row.equipment || "" },
          ],
          updateBody: d => ({ code: d.code, name: d.name, equipment: d.equipment || null }),
        });
      }
    } catch (err) {
      document.getElementById("refMain").innerHTML = `<div class="panel-card"><p class="empty-state">${esc(err.message)}</p></div>`;
    }
  }

  function refreshReferenceRibbon() {
    SyllabusShell.initPage("reference");
  }

  document.querySelectorAll(".ref-tab").forEach(tab => {
    tab.onclick = () => renderSection(tab.dataset.ref);
  });

  SyllabusAuth.requireAuth("/").then(ok => {
    if (ok === false) {
      if (SyllabusAuth.isEmbed()) {
        document.getElementById("refMain").innerHTML =
          '<div class="panel-card"><p class="empty-state">Войдите через главную страницу приложения.</p></div>';
      }
      return;
    }
    refreshReferenceRibbon();
    const hash = (location.hash || "").replace(/^#/, "");
    const sections = ["phrases", "abbreviations", "departments", "signatures", "fgos", "mto", "authors-load", "archive", "layout"];
    let initial = sections.includes(hash) ? hash : "";
    if (!initial) {
      try {
        initial = sessionStorage.getItem("ref_tab") || "phrases";
      } catch (_) {
        initial = "phrases";
      }
    }
    if (!sections.includes(initial)) initial = "phrases";
    renderSection(initial);
  }).catch(err => {
    document.getElementById("refMain").innerHTML = `<div class="panel-card"><p class="empty-state">${esc(err.message)}</p></div>`;
  });
})();
