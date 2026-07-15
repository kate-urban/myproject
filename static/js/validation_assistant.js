/** Панель ИИ-помощника в редакторе сверки. */
(function () {
  const PROMPTS = {
    explain: "Объясни эту ошибку сверки простыми словами и почему она возникла.",
    where: "Где именно в документе нужно править эту ошибку?",
    steps: "Дай пошаговый план исправления этой ошибки для методиста.",
  };

  const state = {
    open: true,
    llmConfigured: false,
    enabled: true,
    busy: false,
    messages: [],
  };

  function esc(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function mdLite(text) {
    return esc(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\_(.+?)\_/g, "<em>$1</em>")
      .replace(/\n/g, "<br>");
  }

  function getActiveRule() {
    if (!docEditorState.activeRuleId || !docEditorState.validation) return null;
    return failedRules(docEditorState.validation).find(
      r => r.rule_id === docEditorState.activeRuleId
    ) || null;
  }

  function getSectionSnippet() {
    const section = docEditorState.sections.find(
      s => s.id === docEditorState.selectedSectionId
    );
    if (!section) return { title: null, snippet: null };
    const editor = window.tinymce?.get("docEditor");
    const content = editor ? editor.getContent() : section.content;
    return { title: section.section_name, snippet: content || section.content };
  }

  function buildPayload(question) {
    const rule = getActiveRule();
    const section = getSectionSnippet();
    return {
      question,
      rule_id: rule?.rule_id || docEditorState.activeRuleId,
      kind: docEditorState.kind || "rpd",
      discipline_code: docEditorState.disciplineCode || null,
      rule_name: rule?.name || null,
      message: rule?.message || null,
      expected: rule?.expected || null,
      actual: rule?.actual || null,
      section_title: section.title,
      section_snippet: section.snippet,
    };
  }

  function renderMessages() {
    const host = document.getElementById("docAssistantMessages");
    if (!host) return;
    host.innerHTML = state.messages.map(msg => `
      <div class="doc-assist-msg ${msg.role}">
        <div class="doc-assist-msg-label">${msg.role === "user" ? "Вы" : "Помощник"}</div>
        <div class="doc-assist-msg-body">${msg.role === "assistant" ? mdLite(msg.text) : esc(msg.text)}</div>
      </div>
    `).join("");
    host.scrollTop = host.scrollHeight;
  }

  function updateContextBanner() {
    const el = document.getElementById("docAssistantContext");
    if (!el) return;
    const rule = getActiveRule();
    if (!rule) {
      el.textContent = "Выберите ошибку сверки — помощник подскажет, где править.";
      return;
    }
    el.innerHTML = `<strong>${esc(rule.rule_id)}</strong> — ${esc(rule.name || rule.message)}`;
  }

  function updateBadge() {
    const badge = document.getElementById("docAssistantBadge");
    if (!badge) return;
    if (!state.enabled) {
      badge.textContent = "выкл";
      badge.className = "doc-assistant-badge off";
      return;
    }
    if (state.llmConfigured) {
      badge.textContent = "ИИ";
      badge.className = "doc-assistant-badge llm";
      badge.title = "Ответы через LLM (AI_API_KEY)";
    } else {
      badge.textContent = "справка";
      badge.className = "doc-assistant-badge local";
      badge.title = "Локальные подсказки по методичке (без API-ключа)";
    }
  }

  function updateToggleButton() {
    const btn = document.getElementById("docAssistantToggle");
    if (!btn) return;
    if (state.open) {
      btn.textContent = "Свернуть";
      btn.title = "Свернуть панель";
    } else {
      btn.textContent = "Развернуть";
      btn.title = "Развернуть панель";
    }
  }

  function syncPanelLayout() {
    const body = document.getElementById("docEditorBody");
    const panel = document.getElementById("docAssistant");
    if (!body || !panel) return;
    body.classList.toggle("assistant-open", state.open && state.enabled);
    body.classList.toggle("assistant-collapsed", !state.open && state.enabled);
    panel.classList.toggle("collapsed", !state.open);
    panel.setAttribute("aria-hidden", state.open ? "false" : "true");
    updateToggleButton();
  }

  function expandPanel() {
    if (state.open) return;
    state.open = true;
    syncPanelLayout();
  }

  async function sendQuestion(question) {
    const q = (question || "").trim();
    if (!q || state.busy || !state.enabled) return;
    state.busy = true;
    state.messages.push({ role: "user", text: q });
    renderMessages();
    const input = document.getElementById("docAssistantInput");
    if (input) input.value = "";

    try {
      const res = await api("/assist/validation/", {
        method: "POST",
        body: JSON.stringify(buildPayload(q)),
      });
      state.messages.push({
        role: "assistant",
        text: res.answer || "Нет ответа.",
      });
    } catch (err) {
      state.messages.push({
        role: "assistant",
        text: `Не удалось получить ответ: ${err.message || err}`,
      });
    } finally {
      state.busy = false;
      renderMessages();
    }
  }

  function bindEvents() {
    document.getElementById("docAssistantForm")?.addEventListener("submit", e => {
      e.preventDefault();
      const input = document.getElementById("docAssistantInput");
      sendQuestion(input?.value || "");
    });

    document.getElementById("docAssistantToggle")?.addEventListener("click", e => {
      e.stopPropagation();
      state.open = !state.open;
      syncPanelLayout();
    });

    document.getElementById("docAssistant")?.addEventListener("click", e => {
      if (state.open || state.enabled === false) return;
      if (e.target.closest("#docAssistantToggle")) return;
      expandPanel();
    });

    document.querySelectorAll("[data-assist-prompt]").forEach(btn => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-assist-prompt");
        sendQuestion(PROMPTS[key] || PROMPTS.explain);
      });
    });
  }

  async function loadConfig() {
    try {
      const res = await fetch("/api/v1/workspace/config/");
      if (res.ok) {
        const cfg = await res.json();
        state.enabled = cfg.ai_assistant_enabled !== false;
        state.llmConfigured = !!cfg.ai_llm_configured;
      }
    } catch (_) {
      /* локальный режим */
    }
    updateBadge();
    syncPanelLayout();
  }

  window.ValidationAssistant = {
    onRuleFocus() {
      updateContextBanner();
    },
    onEditorOpen() {
      state.messages = [];
      renderMessages();
      updateContextBanner();
      syncPanelLayout();
    },
    onEditorClose() {
      state.messages = [];
      renderMessages();
    },
    ask(question) {
      expandPanel();
      sendQuestion(question);
    },
    expand() {
      expandPanel();
    },
  };

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadConfig();
  });
})();
