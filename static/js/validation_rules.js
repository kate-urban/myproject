/** Метаданные правил свerки R/F и форматирование ошибок. */
    /** Подсказки: какие разделы документа связаны с правилом сверки */
    const RULE_SECTION_HINTS = {
      rpd: {
        R001: [/паспорт|шифр|индекс|дисциплин/i],
        R002: [/направлен|паспорт/i],
        R003: [/профил|паспорт/i],
        R004: [/дисциплин|паспорт|назван/i],
        R005: [/1\.3|объ[её]м|з\.?\s*е/i],
        R006: [/кафедр|паспорт|_k/i],
        R007: [/компетен|паспорт|1\./i],
        R008: [/директор|утвержд|подпис/i],
        R009: [/руковод|дисциплин|подпис/i],
        R010: [/компетен|индикатор/i],
        R011: [/индикатор|компетен|контрол/i],
        R012: [/3\.|задач|зув|умен/i],
        R013: [/1\.3|3\.5|самостоят/i],
        R014: [/1\.3|3\.1|3\.2|тем/i],
        R015: [/3\.1|2\.|зув|знать|уметь|владеть/i],
        R016: [/3\.5|самостоят|контрол/i],
        R017: [/3\.1|курсов|контрольн/i],
        R018: [/3\.5|3\.6|вопрос|самостоят/i],
        R019: [/3\.6|матриц|самостоят/i],
        R020: [/1\.3|объ[её]м|час/i],
        R021: [/1\.3|курсов|курсов/i],
        R022: [/1\.3|контакт|лекц|практ/i],
        R023: [/3\.5|самостоят|1\.3/i],
        R024: [/2\.|пк|компетен|групп/i],
        R025: [/1\.3|лекц|практ|лаб/i],
        R026: [/3\.1|3\.2|лекц|практ/i],
        R027: [/3\.5|самостоят/i],
        R028: [/3\.1|аттест|зач|экзам|семестр/i],
        R029: [/3\.1|3\.2|тем/i],
        R030: [/переутверж|протокол/i],
      },
      fos: {
        F001: [/паспорт|шифр|индекс|1\./i],
        F002: [/направлен|паспорт/i],
        F003: [/профил|паспорт/i],
        F004: [/дисциплин|паспорт/i],
        F005: [/дисциплин|паспорт/i],
        F006: [/компетен|2\.|3\./i],
        F007: [/индикатор|контрол|2\.|3\./i],
        F008: [/индикатор|контрол|2\.|3\./i],
        F009: [/критер|оценив|2\.|3\./i],
        F010: [/тем|контрол|2\.|3\./i],
        F011: [/оценив|форма|2\.|3\./i],
        F012: [/шкал|балл|оценк|2\.|3\./i],
        F013: [/2\.|3\.|таблиц/i],
        F014: [/2\.|3\.|таблиц/i],
      },
    };

    /** Где искать в документе и что исправлять (по методичке R/F) */
    const RULE_META = {
      rpd: {
        R001: { where: "Паспорт РПД → поле «Шифр дисциплины»", fix: "Шифр как в колонке «Индекс» учебного плана" },
        R002: { where: "Паспорт → «Направление подготовки» (код XX.XX.XX)", fix: "Код направления из титула УП" },
        R003: { where: "Паспорт → «Направленность (профиль)»", fix: "Текст профиля как в учебном плане" },
        R004: { where: "Паспорт → «Дисциплина» (наименование)", fix: "Название как в строке дисциплины УП" },
        R005: { where: "Таблица 1.3 «Объём дисциплины» → строка з.е.", fix: "Число зачётных единиц = колонка J УП" },
        R006: { where: "Имя файла РПД (суффикс _kNN)", fix: "Код кафедры в имени файла = код кафедры в УП" },
        R007: { where: "Таблица 2.1 → колонка «Индикаторы достижения компетенции»", fix: "Индикаторы УК/ОПК/ПК из УП (например УК-5.1), а не только группа УК-5" },
        R008: { where: "Блок подписей → директор института", fix: "ФИО директора (.env EXPECTED_DIRECTOR)" },
        R009: { where: "Паспорт / подписи → руководитель программы", fix: "ФИО руководителя (.env EXPECTED_DISCIPLINE_HEAD)" },
        R010: { where: "Таблицы компетенций (формат кодов)", fix: "Коды компетенций в УП соответствуют ФГОС" },
        R011: { where: "Таблица индикаторов оценивания компетенций", fix: "Индикаторы из УП есть в РПД" },
        R012: { where: "Раздел 3 → таблицы ЗУВ (задачи, умения, навыки)", fix: "Уберите повторяющиеся формулировки" },
        R013: { where: "Таблица 1.3 (часы СР) ↔ таблица 3.5", fix: "СР в 1.3 должно равняться итогу таблицы 3.5" },
        R014: { where: "Таблица 1.3 (контакт) ↔ темы 3.1 / 3.2", fix: "Согласуйте контактные часы между разделами" },
        R015: { where: "Таблица 3.1 ↔ раздел 2 (З/У/В)", fix: "Скопируйте формулировки из п.2 буквально, без перефразирования" },
        R016: { where: "Таблица 3.5 → виды СР и часы контроля", fix: "«Подготовка к текущему контролю»; часы контроля = плану; КР≥30, КП≥40, КР-10" },
        R017: { where: "Таблица 3.1 → колонки КР/КП/контрольные", fix: "Только +/- или «Есть/Нет», без часов" },
        R018: { where: "Таблица вопросов СР (нумерация X.Y)", fix: "X.Y привязаны к темам 3.1; сумма часов = итог 3.5" },
        R019: { where: "Матрица 3.6 распределения часов", fix: "Темы = 3.1; суммы сходятся; СР темы ≥ сумма вопросов" },
        R020: { where: "Таблица 1.3 → всего часов и СР", fix: "Часы (кол. L) и СР (кол. O) как в УП" },
        R021: { where: "Таблица 1.3 → курсовая работа / проект", fix: "Не менее 30 ч (КР) или 40 ч (КП)" },
        R022: { where: "Таблица 1.3 → аудиторные / контактные часы", fix: "Как hours_contact или hours_aud в УП" },
        R023: { where: "Таблица 3.5 → итог самостоятельной работы", fix: "Итог СР = hours_sr + hours_control в УП" },
        R024: { where: "Раздел 2 → таблица ПК", fix: "У каждой ПК должна быть группа (внутренняя группа вуза)" },
        R025: { where: "Таблица 1.3 → лекции + практики + лабораторные", fix: "Сумма видов занятий = контактные часы" },
        R026: { where: "Таблицы тем 3.1/3.2", fix: "Сумма лек+практ+лаб по темам = контакт УП и 1.3" },
        R027: { where: "Таблица 3.5 → строки видов СР", fix: "Сумма по строкам = итоговая строка СР" },
        R028: { where: "Таблица 3.1 → формы аттестации по семестрам", fix: "Зачёты/экзамены как в учебном плане, с указанием семестра" },
        R029: { where: "Таблицы тем 3.1 / 3.2", fix: "Название темы — жирным, детализация — обычным текстом" },
        R030: { where: "Лист «Сведения о переутверждении»", fix: "Заполните годы и протоколы переутверждения" },
      },
      fos: {
        F001: { where: "Паспорт ФОС → шифр дисциплины", fix: "Шифр как в учебном плане" },
        F002: { where: "Паспорт ФОС → направление подготовки", fix: "Код направления из УП" },
        F003: { where: "Паспорт ФОС → профиль", fix: "Профиль как в УП" },
        F004: { where: "Паспорт ФОС ↔ паспорт РПД", fix: "Шифр в ФОС = шифр в РПД" },
        F005: { where: "Паспорт ФОС ↔ паспорт РПД", fix: "Направление в ФОС = направление в РПД" },
        F006: { where: "Таблица компетенций в ФОС", fix: "Все компетенции УП должны быть в ФОС" },
        F007: { where: "Таблица контроля → столбец индикаторов", fix: "Каждый индикатор из контроля есть среди кодов ФОС" },
        F008: { where: "Таблица контроля ↔ индикаторы РПД", fix: "Индикаторы контроля должны быть в РПД" },
        F009: { where: "Таблица критериев оценивания", fix: "Добавьте строки с критериями (≥1)" },
        F010: { where: "Таблица контролируемых тем / вопросов", fix: "Должна быть хотя бы одна тема" },
        F011: { where: "Таблица контроля → «Форма оценивания»", fix: "Заполните форму оценивания ≥50% строк" },
        F012: { where: "Шкала оценивания (оценка + баллы)", fix: "Не менее 2 строк шкалы" },
        F013: { where: "Таблицы фонда оценочных средств", fix: "Проверьте структуру таблиц ФОС" },
        F014: { where: "Таблицы фонда оценочных средств", fix: "Проверьте полноту таблиц ФОС" },
      },
    };

    function getRuleMeta(ruleId, kind) {
      return RULE_META[kind]?.[ruleId] || {
        where: "См. соответствующий раздел документа",
        fix: "Исправьте значение согласно учебному плану",
      };
    }

    function normCompetencyCode(code) {
      return String(code || "")
        .trim()
        .toUpperCase()
        .replace(/[\u2013\u2014\u2212\u2011]/g, "-")
        .replace(/^UK-/, "УК-")
        .replace(/^OPK-/, "ОПК-")
        .replace(/^PK-/, "ПК-")
        .replace(/^PSK-/, "ПСК-");
    }

    function splitCodeList(value) {
      if (!value) return [];
      return String(value).split(/[;,]+/).map(s => s.trim()).filter(Boolean);
    }

    function missingFromLists(expected, actual) {
      const exp = new Set(splitCodeList(expected).map(normCompetencyCode));
      const act = new Set(splitCodeList(actual).map(normCompetencyCode));
      return [...exp].filter(c => !act.has(c));
    }

    function getHighlightTerms(rule, kind) {
      const terms = [];
      const meta = getRuleMeta(rule.rule_id, kind);
      if (rule.actual && String(rule.actual).length <= 120) terms.push(String(rule.actual));
      if (rule.expected && String(rule.expected).length <= 120) terms.push(String(rule.expected));
      missingFromLists(rule.expected, rule.actual).forEach(code => terms.push(code));
      const codesInMsg = String(rule.message || "").match(/(?:УК|ОПК|ПК|ПСК)-[\d.]+/gi);
      if (codesInMsg) terms.push(...codesInMsg);
      if (/з\.?\s*е|зет|трудо/i.test(meta.where)) terms.push("з.е", "З.е", "з e");
      if (/1\.3/i.test(meta.where)) terms.push("1.3");
      if (/3\.5/i.test(meta.where)) terms.push("3.5");
      return [...new Set(terms.filter(t => t && String(t).length >= 2))].slice(0, 10);
    }

    function stripHighlightMarks(html) {
      return String(html || "").replace(/<mark class="val-err-mark"[^>]*>([\s\S]*?)<\/mark>/gi, "$1");
    }

    function highlightContentHtml(html, terms) {
      if (!html || !terms.length) return html;
      let result = html;
      terms.forEach(term => {
        const raw = String(term).trim();
        if (raw.length < 2) return;
        const escaped = raw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        result = result.replace(
          new RegExp(`(?![^<]*>)(${escaped})`, "gi"),
          '<mark class="val-err-mark" title="Возможное место ошибки">$1</mark>'
        );
      });
      return result;
    }

    function formatRuleSectionsLabel(sections) {
      if (!sections.length) return "Раздел не определён — откройте паспорт или таблицу 1.3";
      if (sections.length === 1) return `Раздел: «${sections[0].section_name}»`;
      const names = sections.slice(0, 3).map(s => `«${s.section_name}»`).join(", ");
      return sections.length > 3
        ? `Разделы: ${names} и ещё ${sections.length - 3}`
        : `Разделы: ${names}`;
    }

    function formatRuleIssueCard(rule, kind, sections, isActive) {
      const meta = getRuleMeta(rule.rule_id, kind);
      const missing = missingFromLists(rule.expected, rule.actual);
      const sectionId = sections[0]?.id || "";
      const activeClass = isActive ? " active" : "";
      return `<button type="button" class="doc-issue-item${activeClass}"
        data-section-id="${sectionId}" data-rule-id="${esc(rule.rule_id)}">
        <div class="rule-head">
          <span class="rule-id">${esc(rule.rule_id)}</span>
          <span class="rule-name">${esc(rule.name || meta.fix)}</span>
        </div>
        <div class="rule-where">📍 ${esc(meta.where)}</div>
        <div>${esc(rule.message)}</div>
        <div class="rule-fix">✎ ${esc(meta.fix)}</div>
        ${rule.rule_id === "R015" && !rule.passed ? `<div class="rule-fix" style="margin-top:4px;color:var(--accent)">💡 Скопируйте формулировки З/У/В из п.2 в таблицу 3.1 без перефразирования</div>` : ""}
        ${rule.expected || rule.actual ? `
          <div class="rule-compare">
            ${rule.expected ? `<div><span class="lbl">В учебном плане (эталон): </span><span class="exp">${esc(rule.expected)}</span></div>` : ""}
            ${rule.actual ? `<div><span class="lbl">В документе сейчас: </span><span class="act">${esc(rule.actual)}</span></div>` : ""}
          </div>` : ""}
        ${missing.length && !rule.passed ? `<div class="missing-codes">Не хватает: ${esc(missing.join(", "))}</div>` : ""}
        <div class="rule-sections">→ ${esc(formatRuleSectionsLabel(sections))}</div>
      </button>`;
    }

    function formatReportRuleDetail(rule, kind) {
      const meta = getRuleMeta(rule.rule_id, kind);
      const missing = missingFromLists(rule.expected, rule.actual);
      return `<div class="report-rule-detail">
        <div><strong>${esc(rule.rule_id)}</strong> ${esc(rule.name || rule.message)}</div>
        <div class="where">📍 ${esc(meta.where)} · ✎ ${esc(meta.fix)}</div>
        ${rule.expected ? `<div style="font-size:11px"><span style="color:var(--muted)">Эталон: </span><span style="color:var(--ok)">${esc(rule.expected)}</span></div>` : ""}
        ${rule.actual ? `<div style="font-size:11px"><span style="color:var(--muted)">В документе: </span><span style="color:var(--fail)">${esc(rule.actual)}</span></div>` : ""}
        ${missing.length && !rule.passed ? `<div style="font-size:11px;color:var(--fail)">Не хватает: ${esc(missing.join(", "))}</div>` : ""}
      </div>`;
    }

    function renderDocEditorRuleHint(ruleId) {
      const el = document.getElementById("docEditorRuleHint");
      if (!el) return;
      if (!ruleId || !docEditorState.validation) {
        el.classList.remove("visible");
        el.innerHTML = "";
        return;
      }
      const rule = failedRules(docEditorState.validation).find(r => r.rule_id === ruleId);
      if (!rule) {
        el.classList.remove("visible");
        return;
      }
      const meta = getRuleMeta(ruleId, docEditorState.kind);
      const sections = findSectionsForRule(ruleId, docEditorState.kind, docEditorState.sections);
      const missing = missingFromLists(rule.expected, rule.actual);
      el.classList.add("visible");
      el.innerHTML = `
        <strong>${esc(rule.rule_id)}</strong> — ${esc(rule.name || rule.message)}<br>
        <strong>Где:</strong> ${esc(meta.where)}<br>
        <strong>Что сделать:</strong> ${esc(meta.fix)}<br>
        ${rule.expected ? `<strong>Эталон (УП):</strong> <span style="color:var(--ok)">${esc(rule.expected)}</span><br>` : ""}
        ${rule.actual ? `<strong>Сейчас в документе:</strong> <span style="color:var(--fail)">${esc(rule.actual)}</span><br>` : ""}
        ${missing.length && !rule.passed ? `<strong>Не хватает кодов:</strong> <span style="color:var(--fail)">${esc(missing.join(", "))}</span><br>` : ""}
        <span style="color:var(--accent)">${esc(formatRuleSectionsLabel(sections))}</span>
        · в тексте ниже подсвечены возможные места ошибки
      `;
    }

    function sectionMatchesRule(sectionName, ruleId, kind) {
      const hints = RULE_SECTION_HINTS[kind]?.[ruleId];
      if (!hints || !hints.length) return false;
      const name = String(sectionName || "").toLowerCase();
      return hints.some(rx => rx.test(name));
    }

    function findSectionsForRule(ruleId, kind, sections) {
      const matched = sections.filter(s => sectionMatchesRule(s.section_name, ruleId, kind));
      if (matched.length) return matched;
      if (sections.length) return [sections[0]];
      return [];
    }

    function buildSectionRuleMap(validation, kind, sections) {
      const map = new Map();
      if (!validation || !validation.results) return map;
      const failed = validation.results.filter(
        r => !r.skipped && r.severity === "critical" && !r.passed
      );
      failed.forEach(rule => {
        findSectionsForRule(rule.rule_id, kind, sections).forEach(section => {
          if (!map.has(section.id)) map.set(section.id, []);
          map.get(section.id).push(rule);
        });
      });
      return map;
    }

    function failedRules(validation) {
      if (!validation || !validation.results) return [];
      return validation.results.filter(
        r => !r.skipped && r.severity === "critical" && !r.passed
      );
    }

