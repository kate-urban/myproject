/** Предложение и применение автоправок сверки (детерминированные + LLM). */
(function () {
  const FIXABLE_RULES = new Set([
    "R001", "R002", "R003", "R004", "R005",
    "R020", "R021", "R022", "R025",
  ]);

  const state = {
    busy: false,
    llmConfigured: false,
    assistantEnabled: true,
    lastResult: null,
  };

  function esc(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function isFixableRule(ruleId) {
    return FIXABLE_RULES.has(String(ruleId || "").toUpperCase());
  }

  function canSuggestLlmFix(ruleId) {
    if (!state.llmConfigured || !state.assistantEnabled) return false;
    return Boolean(ruleId && docEditorState.activeRuleId);
  }

  function getEditorHtml() {
    const editor = window.tinymce?.get("docEditor");
    const section = docEditorState.sections.find(
      s => s.id === docEditorState.selectedSectionId
    );
    let content = editor ? editor.getContent() : section?.content;
    if (content) {
      content = content.replace(/<mark class="val-err-mark"[^>]*>/g, "").replace(/<\/mark>/g, "");
    }
    return content || "";
  }

  function buildFixPayload() {
    return {
      rule_id: docEditorState.activeRuleId,
      study_plan_id: selectedPlanId,
      discipline_id: docEditorState.disciplineId,
      section_id: docEditorState.selectedSectionId,
      section_html: getEditorHtml(),
    };
  }

  function ensureModal() {
    if (document.getElementById("docFixModal")) return;
    const modal = document.createElement("div");
    modal.id = "docFixModal";
    modal.className = "doc-fix-modal";
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
      <div class="doc-fix-modal-inner" role="dialog" aria-labelledby="docFixModalTitle">
        <div class="doc-fix-modal-head">
          <h4 id="docFixModalTitle">Предложенная правка</h4>
          <span class="doc-fix-source-badge" id="docFixSourceBadge"></span>
          <button type="button" class="btn ghost sm" id="docFixModalClose">Закрыть</button>
        </div>
        <div class="doc-fix-modal-body" id="docFixModalBody"></div>
        <div class="doc-fix-modal-actions">
          <button type="button" class="btn" id="docFixModalCancel">Отмена</button>
          <button type="button" class="btn primary" id="docFixModalApply">Применить и сверить</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener("click", e => {
      if (e.target.id === "docFixModal") closeModal();
    });
    document.getElementById("docFixModalClose").onclick = closeModal;
    document.getElementById("docFixModalCancel").onclick = closeModal;
    document.getElementById("docFixModalApply").onclick = () => applyAndRevalidate();
  }

  function renderDiff(result) {
    if (!result?.changes?.length) {
      return `<p class="doc-fix-empty">${esc(result?.message || "Нет изменений")}</p>`;
    }
    const explain = result.explanation
      ? `<p class="doc-fix-explanation">${esc(result.explanation)}</p>`
      : "";
    const safeNote = result.apply_safe
      ? `<p class="doc-fix-safe">Эталон из сверки совпадает — правка проверена автоматически.</p>`
      : `<p class="doc-fix-warn">Проверьте diff: ИИ мог предложить неточную формулировку.</p>`;
    const rows = result.changes.map(ch => `
      <div class="doc-fix-change">
        <div class="doc-fix-change-label">${esc(ch.row_label || ch.field)}</div>
        <div class="doc-fix-diff">
          <span class="doc-fix-old">${esc(ch.old)}</span>
          <span class="doc-fix-arrow">→</span>
          <span class="doc-fix-new">${esc(ch.new)}</span>
        </div>
      </div>
    `).join("");
    return `
      ${explain}
      ${safeNote}
      <p class="doc-fix-msg">${esc(result.message)}</p>
      ${rows}
      <p class="doc-fix-note">После применения раздел будет сохранён и запущена повторная сверка.</p>
    `;
  }

  function updateSourceBadge(result) {
    const badge = document.getElementById("docFixSourceBadge");
    if (!badge) return;
    if (result?.source === "llm") {
      badge.textContent = "ИИ";
      badge.className = "doc-fix-source-badge llm";
      badge.title = "Правка сгенерирована LLM";
    } else {
      badge.textContent = "авто";
      badge.className = "doc-fix-source-badge auto";
      badge.title = "Детерминированная правка по УП";
    }
  }

  function openModal(result) {
    ensureModal();
    state.lastResult = result;
    const modal = document.getElementById("docFixModal");
    document.getElementById("docFixModalTitle").textContent =
      result?.source === "llm" ? "Правка от ИИ" : "Предложенная правка";
    document.getElementById("docFixModalBody").innerHTML = renderDiff(result);
    updateSourceBadge(result);
    document.getElementById("docFixModalApply").disabled = !result?.patched_html;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    const modal = document.getElementById("docFixModal");
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    state.lastResult = null;
  }

  async function requestFix(endpoint) {
    if (state.busy) return;
    const ruleId = docEditorState.activeRuleId;
    if (!ruleId) {
      toast("Выберите ошибку сверки", true);
      return;
    }
    if (!selectedPlanId || !docEditorState.disciplineId || !docEditorState.selectedSectionId) {
      toast("Выберите дисциплину и раздел с ошибкой", true);
      return;
    }
    state.busy = true;
    try {
      const result = await api(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildFixPayload()),
      });
      if (!result.supported) {
        toast(result.message || "Не удалось сформировать правку", true);
        return;
      }
      if (!result.patched_html) {
        toast(result.message || "ИИ не предложил правок для этого раздела", true);
        return;
      }
      openModal(result);
    } catch (err) {
      toast(err.message || "Ошибка запроса правки", true);
    } finally {
      state.busy = false;
    }
  }

  async function suggestFix() {
    const ruleId = docEditorState.activeRuleId;
    if (!isFixableRule(ruleId)) {
      toast("Для этого правила используйте «Правка (ИИ)»", true);
      return;
    }
    await requestFix("/assist/suggest-fix/");
  }

  async function suggestFixLlm() {
    if (!canSuggestLlmFix(docEditorState.activeRuleId)) {
      toast("Настройте AI_API_KEY в .env для правок через ИИ", true);
      return;
    }
    await requestFix("/assist/suggest-fix-llm/");
  }

  async function applyAndRevalidate() {
    const result = state.lastResult;
    if (!result?.patched_html || !docEditorState.selectedSectionId) return;
    state.busy = true;
    const applyBtn = document.getElementById("docFixModalApply");
    if (applyBtn) applyBtn.disabled = true;
    try {
      const section = docEditorState.sections.find(
        s => s.id === docEditorState.selectedSectionId
      );
      if (!section) throw new Error("Раздел не найден");

      section.content = result.patched_html;
      const editor = window.tinymce?.get("docEditor");
      if (editor) editor.setContent(result.patched_html);

      await api(`/sections/${section.id}/?program_id=${encodeURIComponent(docEditorState.programId || "")}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: result.patched_html }),
      });

      if (docEditorState.docId) {
        await api(`/documents/${docEditorState.docId}/refresh-extract/`, { method: "POST" });
      }

      const path = docEditorState.kind === "rpd"
        ? `/study-plans/${selectedPlanId}/disciplines/${docEditorState.disciplineId}/validate/`
        : `/study-plans/${selectedPlanId}/disciplines/${docEditorState.disciplineId}/validate-fos/`;
      const item = await api(path);

      if (typeof applyValidationResult === "function") {
        await applyValidationResult(item);
      }

      const ruleStillFailed = failedRules(item).some(r => r.rule_id === docEditorState.activeRuleId)
        || warningRules(item).some(r => r.rule_id === docEditorState.activeRuleId);
      closeModal();
      if (item.passed) {
        toast("Сверка: без ошибок");
      } else if (ruleStillFailed) {
        toast(`Правка применена, но ${docEditorState.activeRuleId} всё ещё не проходит`, true);
      } else {
        toast(`Правка применена. Осталось замечаний: ${failedRules(item).length + warningRules(item).length}`);
      }
    } catch (err) {
      toast(err.message || "Не удалось применить правку", true);
    } finally {
      state.busy = false;
      if (applyBtn) applyBtn.disabled = false;
    }
  }

  async function loadConfig() {
    try {
      const res = await fetch("/api/v1/workspace/config/");
      if (res.ok) {
        const cfg = await res.json();
        state.assistantEnabled = cfg.ai_assistant_enabled !== false;
        state.llmConfigured = !!cfg.ai_llm_configured;
      }
    } catch (_) {
      /* ignore */
    }
  }

  document.addEventListener("DOMContentLoaded", loadConfig);

  window.ValidationFix = {
    isFixableRule,
    canSuggestLlmFix,
    suggestFix,
    suggestFixLlm,
    closeModal,
    refreshConfig: loadConfig,
  };
})();
