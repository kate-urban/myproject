/** Дерево папки «УЧЕБНЫЕ ПЛАНЫ» — общая логика для / и /validation */
window.SyllabusPlansNav = {
  filterTree(node, query) {
    if (!node) return null;
    const q = String(query || "").trim().toLowerCase();
    if (!q) return node;

    const plans = (node.plans || []).filter(p =>
      `${p.direction_code} ${p.profile_name} ${p.source_file}`.toLowerCase().includes(q)
    );
    const files = (node.files || []).filter(f => f.name.toLowerCase().includes(q));
    const children = (node.children || [])
      .map(ch => this.filterTree(ch, q))
      .filter(Boolean);
    const nameMatch = String(node.name || "").toLowerCase().includes(q);

    if (nameMatch || plans.length || files.length || children.length) {
      return {
        ...node,
        plans: nameMatch ? (node.plans || []) : plans,
        files: nameMatch ? (node.files || []) : files,
        children,
      };
    }
    return null;
  },

  flattenPlans(node) {
    if (!node) return [];
    const items = [...(node.plans || [])];
    for (const child of node.children || []) {
      items.push(...this.flattenPlans(child));
    }
    return items;
  },

  classifyBucket(discipline) {
    const code = String(discipline.code || "").toUpperCase();
    const name = String(discipline.name || "").toUpperCase();
    const objectType = String(discipline.object_type ?? discipline.objectType ?? "");
    if (objectType === "3" || code.includes("(П)") || code.startsWith("Б2")) return "practices";
    if (code.startsWith("Б3") || /ГИА|ВКР|ГОС\.?\s*ЭКЗ|ИТОГОВ/.test(name)) return "gia";
    return "disciplines";
  },

  groupDisciplines(items) {
    const groups = { disciplines: [], practices: [], gia: [] };
    for (const item of items || []) {
      groups[this.classifyBucket(item)].push(item);
    }
    return groups;
  },

  esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  },

  createExpandedState(storageKey) {
    const state = {
      storageKey: storageKey || null,
      nodes: new Set(),
      load() {
        if (!state.storageKey) return;
        try {
          state.nodes = new Set(JSON.parse(localStorage.getItem(state.storageKey) || "[]"));
        } catch (_) {
          state.nodes = new Set();
        }
      },
      save() {
        if (!state.storageKey) return;
        localStorage.setItem(state.storageKey, JSON.stringify([...state.nodes]));
      },
      toggle(id) {
        if (!id) return;
        if (state.nodes.has(id)) state.nodes.delete(id);
        else state.nodes.add(id);
        state.save();
      },
      isExpanded(id) {
        return state.nodes.has(id);
      },
    };
    state.load();
    return state;
  },

  planMatches(p, q) {
    return `${p.direction_code} ${p.profile_name} ${p.source_file}`.toLowerCase().includes(q);
  },

  nodeDirectMatch(node, q) {
    if (String(node.name || "").toLowerCase().includes(q)) return true;
    if ((node.plans || []).some(p => this.planMatches(p, q))) return true;
    if ((node.files || []).some(f => f.name.toLowerCase().includes(q))) return true;
    return false;
  },

  expandForSearch(node, query, expandedState) {
    const q = String(query || "").trim().toLowerCase();
    if (!node || !q) return;
    this._markExpandedForSearch(node, q, expandedState);
  },

  _markExpandedForSearch(node, q, expandedState) {
    let childMatched = false;
    for (const ch of node.children || []) {
      if (this._markExpandedForSearch(ch, q, expandedState)) childMatched = true;
    }
    const matched = childMatched || this.nodeDirectMatch(node, q);
    if (matched && node.id && node.id !== ".") {
      expandedState.nodes.add(node.id);
    }
    return matched;
  },

  renderPlanItemHtml(p, selectedPlanId, { planExpandable = false, expandedState = null } = {}) {
    const active = String(p.id) === String(selectedPlanId) ? " active" : "";
    const planKey = `plan:${p.id}`;
    const expanded = planExpandable && expandedState?.isExpanded(planKey);
    const toggle = planExpandable
      ? `<span class="toggle" data-action="plan-expand" data-plan-id="${this.esc(p.id)}" title="Показать дисциплины">${expanded ? "▼" : "▶"}</span>`
      : "";
    const body = `<div class="plan-label">
        <div class="code">${this.esc(p.direction_code)} · ${this.esc(p.profile_name)}</div>
        <div class="meta">${this.esc(p.source_file)} · ${p.disciplines_count} дисц.${p.year ? ` · ${p.year}` : ""}</div>
      </div>`;
    if (!planExpandable) {
      return `<div class="tree-plan${active}" data-id="${this.esc(p.id)}">${body}</div>`;
    }
    return `<div class="tree-plan-wrap">
      <div class="tree-plan${active}" data-id="${this.esc(p.id)}">${toggle}${body}</div>
      <div class="tree-children${expanded ? "" : " collapsed"}" data-plan-body="${this.esc(p.id)}"></div>
    </div>`;
  },

  renderFlatListHtml(allPlans, selectedPlanId, options = {}) {
    return (allPlans || []).map(p => this.renderPlanItemHtml(p, selectedPlanId, options)).join("");
  },

  renderMissingRootHtml(planNavData, allPlans, selectedPlanId, options = {}) {
    let html = `<div class="tree-missing">Папка «${this.esc(planNavData?.root || "УЧЕБНЫЕ ПЛАНЫ")}» не найдена в корне проекта.<br>Импорт через «＋ Импорт УП» по-прежнему доступен.</div>`;
    if (allPlans?.length) {
      html += this.renderFlatListHtml(allPlans, selectedPlanId, options);
    }
    return html;
  },

  renderTreeHtml(tree, expandedState, options = {}) {
    const {
      rootTitle = "",
      selectedPlanId = null,
      query = "",
      planExpandable = false,
    } = options;
    if (query) this.expandForSearch(tree, query, expandedState);
    const inner = this.renderNode(tree, 0, expandedState, { selectedPlanId, planExpandable });
    const title = rootTitle ? `<div class="tree-root-title">${this.esc(rootTitle)}</div>` : "";
    return `<div class="plan-tree">${title}${inner}</div>`;
  },

  renderNode(node, depth, expandedState, options) {
    if (!node) return "";
    const { selectedPlanId, planExpandable } = options;
    let html = "";

    const hasChildren = (node.children || []).length > 0;
    const planCount = (node.plans || []).length;
    const fileCount = (node.files || []).length;
    const hasBody = hasChildren || planCount || fileCount;
    const isExpanded = expandedState.isExpanded(node.id);

    if (node.type === "orphan") {
      html += `<div class="tree-root-title">${this.esc(node.name)}</div>`;
    } else if (node.id !== ".") {
      const toggleMark = hasBody ? (isExpanded ? "▼" : "▶") : "·";
      html += `<div class="tree-folder" data-folder-id="${this.esc(node.id)}" data-depth="${depth}">
        <span class="toggle" data-action="expand" title="Раскрыть папку">${toggleMark}</span>
        <span class="label">${this.esc(node.name)}${planCount ? `<span class="count">(${planCount})</span>` : ""}</span>
      </div>`;
    }

    const bodyParts = [];
    for (const p of node.plans || []) {
      bodyParts.push(this.renderPlanItemHtml(p, selectedPlanId, { planExpandable, expandedState }));
    }
    for (const f of node.files || []) {
      if (options.hideFiles) continue;
      bodyParts.push(
        `<div class="tree-file" data-import-path="${this.esc(f.relative_path)}" title="Импортировать в БД">${this.esc(f.name)}</div>`
      );
    }
    for (const child of node.children || []) {
      bodyParts.push(this.renderNode(child, depth + 1, expandedState, options));
    }

    if (bodyParts.length) {
      const collapsed = node.id !== "." && !isExpanded;
      html += `<div class="tree-children${collapsed ? " collapsed" : ""}" data-parent="${this.esc(node.id)}">${bodyParts.join("")}</div>`;
    }
    return html;
  },

  bindTree(container, expandedState, callbacks = {}) {
    const { onPlanSelect, onFileImport, onPlanExpand, onRerender } = callbacks;
    const root = container || document;

    root.querySelectorAll(".tree-folder[data-folder-id]").forEach(folder => {
      const toggleEl = folder.querySelector('.toggle[data-action="expand"]');
      if (!toggleEl || toggleEl.textContent.trim() === "·") return;
      const toggleFolder = e => {
        e.stopPropagation();
        expandedState.toggle(folder.dataset.folderId);
        onRerender?.();
      };
      folder.onclick = toggleFolder;
    });

    root.querySelectorAll(".tree-plan[data-id]").forEach(el => {
      const planId = el.dataset.id;
      const hasExpand = !!el.querySelector('[data-action="plan-expand"]');

      if (hasExpand && onPlanExpand) {
        el.onclick = e => {
          e.stopPropagation();
          onPlanSelect?.(planId);
          onPlanExpand?.(planId, el.querySelector('[data-action="plan-expand"]'));
        };
        return;
      }

      el.onclick = e => {
        e.stopPropagation();
        onPlanSelect?.(planId);
      };
    });

    root.querySelectorAll(".tree-file[data-import-path]").forEach(el => {
      el.onclick = e => {
        e.stopPropagation();
        onFileImport?.(el.dataset.importPath);
      };
    });
  },
};
