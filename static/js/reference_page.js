(function () {
  const API = "/api/v1";
  let currentSection = "phrases";
  let modalState = null;

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
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

  function openModal(title, fields, onSubmit) {
    modalState = { onSubmit };
    document.getElementById("modalTitle").textContent = title;
    const form = document.getElementById("modalForm");
    form.innerHTML = fields.map(f => {
      if (f.type === "textarea") {
        return `<div class="field"><label>${esc(f.label)}</label><textarea name="${esc(f.name)}" ${f.required ? "required" : ""}>${esc(f.value || "")}</textarea></div>`;
      }
      if (f.type === "checkbox") {
        return `<div class="field"><label><input type="checkbox" name="${esc(f.name)}" ${f.value ? "checked" : ""}> ${esc(f.label)}</label></div>`;
      }
      return `<div class="field"><label>${esc(f.label)}</label><input name="${esc(f.name)}" value="${esc(f.value || "")}" ${f.required ? "required" : ""}></div>`;
    }).join("");
    document.getElementById("refModal").classList.add("open");
  }

  function closeModal() {
    modalState = null;
    document.getElementById("refModal").classList.remove("open");
  }

  document.getElementById("modalCancel").onclick = closeModal;
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
    const items = await api("/reference/phrases/?active_only=false");
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
      if (delId) {
        if (!confirm("Деактивировать фразу?")) return;
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
        <table><thead><tr><th>Шаблон</th><th>Замена</th><th>Приоритет</th><th>Regex</th><th></th></tr></thead>
        <tbody>${items.map(r => `<tr>
          <td><code>${esc(r.pattern)}</code></td><td>${esc(r.replacement)}</td><td>${r.priority}</td><td>${r.is_regex ? "да" : ""}</td>
          <td><button class="btn danger" data-del="${esc(r.id)}" type="button">×</button></td></tr>`).join("") || `<tr><td colspan="5" class="empty-state">Нет записей</td></tr>`}
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
    document.querySelector("#refMain tbody")?.addEventListener("click", async e => {
      const id = e.target.closest("[data-del]")?.dataset.del;
      if (!id) return;
      await api(`/reference/abbreviations/${id}/`, { method: "DELETE" });
      renderSection("abbreviations");
    });
  }

  async function renderSimpleList(title, lead, path, columns, addFields, createBody) {
    const items = await api(path);
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card"><h2>${esc(title)}</h2><p class="lead">${esc(lead)}</p>
      <div class="toolbar"><button class="btn primary" type="button" id="btnAdd">＋ Добавить</button></div>
      <table><thead><tr>${columns.map(c => `<th>${esc(c.label)}</th>`).join("")}</tr></thead>
      <tbody>${items.map(row => `<tr>${columns.map(c => `<td>${esc(row[c.key] ?? "—")}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${columns.length}" class="empty-state">Нет записей</td></tr>`}
      </tbody></table></div>`;
    document.getElementById("btnAdd").onclick = () => openModal(`Новая запись: ${title}`, addFields, async data => {
      await api(path.replace(/\/$/, "") + "/", { method: "POST", body: JSON.stringify(createBody(data)) });
    });
  }

  async function renderSignatures() {
    const items = await api("/reference/signatures/");
    document.getElementById("refMain").innerHTML = `
      <div class="panel-card">
        <h2>Подписи (PDF / Word)</h2>
        <p class="lead">PNG накладываются при экспорте PDF. Роли: director, dept_head, discipline_head.</p>
        <div class="toolbar"><button class="btn primary" type="button" id="btnAddSig">＋ Добавить</button></div>
        <table><thead><tr><th>Роль</th><th>ФИО</th><th>PNG</th><th>Загрузка</th></tr></thead>
        <tbody id="sigRows"></tbody></table>
      </div>`;
    const tbody = document.getElementById("sigRows");
    tbody.innerHTML = items.map(r => `<tr>
      <td><code>${esc(r.role)}</code></td><td>${esc(r.full_name)}</td>
      <td>${r.png_path ? esc(r.png_path) : "—"}</td>
      <td><input type="file" accept="image/*" data-upload="${esc(r.id)}"></td></tr>`).join("") || `<tr><td colspan="4" class="empty-state">Нет записей</td></tr>`;
    document.getElementById("btnAddSig").onclick = () => openModal("Новая подпись", [
      { name: "role", label: "Роль", value: "director", required: true },
      { name: "full_name", label: "ФИО", required: true },
    ], async data => {
      await api("/reference/signatures/", { method: "POST", body: JSON.stringify(data) });
    });
    tbody.onchange = async e => {
      const input = e.target.closest("[data-upload]");
      if (!input?.files?.[0]) return;
      const fd = new FormData();
      fd.append("file", input.files[0]);
      const res = await fetch(`${API}/reference/signatures/${input.dataset.upload}/png/`, {
        method: "POST",
        body: fd,
        headers: SyllabusAuth.authHeaders(),
      });
      if (!res.ok) alert("Ошибка загрузки PNG");
      else renderSection("signatures");
    };
  }

  async function renderSection(name) {
    currentSection = name;
    document.querySelectorAll(".ref-tab").forEach(t => t.classList.toggle("active", t.dataset.ref === name));
    try {
      if (name === "phrases") await renderPhrases();
      else if (name === "abbreviations") await renderAbbreviations();
      else if (name === "departments") await renderSimpleList("Кафедры", "Справочник кафедр.", "/reference/departments/", [
        { key: "code", label: "Код" }, { key: "name", label: "Название" },
      ], [{ name: "code", label: "Код", required: true }, { name: "name", label: "Название", required: true }], d => d);
      else if (name === "signatures") await renderSignatures();
      else if (name === "fgos") {
        const items = await api("/reference/fgos/competencies/");
        document.getElementById("refMain").innerHTML = `<div class="panel-card"><h2>ФГОС</h2><p class="lead">Компетенции УК/ОПК/ПК.</p>
        <div class="toolbar"><button class="btn primary" id="btnAddFgos" type="button">＋ Компетенция</button></div>
        <table><thead><tr><th>Код</th><th>Тип</th><th>Название</th></tr></thead>
        <tbody>${items.map(r => `<tr><td><code>${esc(r.code)}</code></td><td>${esc(r.kind)}</td><td>${esc(r.title)}</td></tr>`).join("")}</tbody></table></div>`;
        document.getElementById("btnAddFgos").onclick = () => openModal("Новая компетенция", [
          { name: "kind", label: "Тип (UK/OPK/PK)", value: "OPK", required: true },
          { name: "code", label: "Код", required: true },
          { name: "title", label: "Название", type: "textarea", required: true },
        ], async data => {
          await api("/reference/fgos/competencies/", { method: "POST", body: JSON.stringify(data) });
        });
      } else if (name === "mto") {
        await renderSimpleList("МТО", "Аудитории и оборудование.", "/reference/mto/rooms/", [
          { key: "code", label: "Код" }, { key: "name", label: "Название" }, { key: "equipment", label: "Оборудование" },
        ], [
          { name: "code", label: "Код", required: true },
          { name: "name", label: "Название", required: true },
          { name: "equipment", label: "Оборудование", type: "textarea" },
        ], d => ({ code: d.code, name: d.name, equipment: d.equipment || null }));
      }
    } catch (err) {
      document.getElementById("refMain").innerHTML = `<div class="panel-card"><p class="empty-state">${esc(err.message)}</p></div>`;
    }
  }

  document.querySelectorAll(".ref-tab").forEach(tab => {
    tab.onclick = () => renderSection(tab.dataset.ref);
  });

  SyllabusAuth.requireAuth("/").then(ok => {
    if (ok !== false) renderSection("phrases");
  }).catch(err => {
    document.getElementById("refMain").innerHTML = `<div class="panel-card"><p class="empty-state">${esc(err.message)}</p></div>`;
  });
})();
