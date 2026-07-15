/** Метаданные правил свerки R/F и форматирование ошибок. */
    /**
     * К каким разделам привязать ошибку — по номеру в заголовке («1.3», «3.5» …).
     * Без цифры — ключевое слово в названии. [] — не подсвечивать раздел в боковой панели.
     */
    const RULE_SECTION_NUMS = {
      rpd: {
        R001: ["1.1", "паспорт"],
        R002: ["1.1", "паспорт"],
        R003: ["1.1", "паспорт"],
        R004: ["1.1", "паспорт"],
        R005: ["1.3"],
        R006: [],
        R007: ["2.1", "2.2", "2"],
        R008: ["подпис", "утвержд"],
        R009: ["1.1", "паспорт", "руковод"],
        R010: ["2"],
        R011: ["2", "2.1"],
        R012: ["2.1", "2.2", "планируемых результат", "компетенц"],
        R013: ["1.3", "3.5"],
        R014: ["1.3", "3.1", "3.2"],
        R015: ["2", "2.1", "3.1"],
        R016: ["3.5"],
        R017: ["3.1"],
        R018: ["3.5"],
        R019: ["3.6"],
        R020: ["1.3"],
        R021: ["1.3"],
        R022: ["1.3"],
        R023: ["1.3", "3.5"],
        R024: ["2"],
        R025: ["1.3"],
        R026: ["3.1", "3.2"],
        R027: ["3.5"],
        R028: ["3.1"],
        R029: ["3.1", "3.2"],
        R030: ["переутвержд", "сведения"],
        R032: ["2", "2.1", "3.1"],
      },
      fos: {
        F001: ["1", "паспорт"],
        F002: ["1", "паспорт"],
        F003: ["1", "паспорт"],
        F004: ["1", "паспорт"],
        F005: ["1", "паспорт"],
        F006: ["2", "3"],
        F007: ["2", "3"],
        F008: ["2", "3"],
        F009: ["2", "3"],
        F010: ["2", "3"],
        F011: ["2", "3"],
        F012: ["2", "3"],
        F013: ["2", "3"],
        F014: ["2", "3"],
      },
    };

    function sectionNumberPrefix(sectionName) {
      const m = String(sectionName || "").trim().match(/^(\d+(?:\.\d+)*)/);
      return m ? m[1] : null;
    }

    const EXAM_QUESTION_SECTION_RE = /^\d+[\.\)]\s+(?:объясните|перечислите|опишите|раскройте|сформулируйте|назовите|дайте|приведите|сравните|определите|решите|вычислите|постройте|найдите|докажите|разработайте|составьте|проанализируйте|охарактеризуйте|укажите|рассмотрите|оцените|выберите|какие|каков|что\s+такое|в\s+ч[её]м|почему|как\s+)/i;

    function isExamQuestionSection(sectionName) {
      const name = String(sectionName || "").trim();
      if (!name) return false;
      if (EXAM_QUESTION_SECTION_RE.test(name)) return true;
      const body = name.replace(/^\d+(?:\.\d+)*[\.\)]?\s+/, "");
      return body.length > 0 && body.length < 160 && body.endsWith("?");
    }

    function isCompetencySection(sectionName) {
      const name = String(sectionName || "").trim();
      const lower = name.toLowerCase();
      if (isExamQuestionSection(name)) return false;
      const prefix = sectionNumberPrefix(name);
      if (prefix && /^2\.\d+/.test(prefix)) return true;
      return /компетенц|планируемых результат|индикатор|универсальн|общепроф|профессиональн/.test(lower);
    }

    function prefixMatchesSection(prefix, targetNum) {
      if (!prefix || !targetNum) return false;
      const target = String(targetNum);
      if (!/^\d/.test(target)) return false;
      return prefix === target || prefix.startsWith(`${target}.`);
    }

    const COMPETENCY_SECTION_RULES = new Set(["R007", "R010", "R011", "R012", "R024", "R032"]);

    function sectionHasEditorContent(section) {
      const html = String(section?.content || "").trim();
      if (!html) return false;
      if (/<table[\s>]/i.test(html)) return true;
      return html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim().length > 0;
    }

    function sectionContentScore(section) {
      const html = String(section?.content || "").trim();
      if (!html) return 200;
      if (/<table[\s>]/i.test(html)) return 0;
      const textLen = html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim().length;
      if (textLen < 40) return 80;
      return 20;
    }

    function matrixSectionScore(section) {
      const prefix = sectionNumberPrefix(section.section_name);
      let score = sectionContentScore(section);
      if (prefix === "3.6.1") score -= 3;
      else if (prefix === "3.6.2") score -= 2;
      else if (prefix === "3.6") score += 10;
      return score;
    }

    const TABLE_SECTION_RULES = new Set(["R013", "R014", "R016", "R018", "R019", "R026", "R027"]);

    function sortSectionsForRule(ruleId, sections) {
      if (ruleId === "R019") {
        return sections.slice().sort((a, b) => matrixSectionScore(a) - matrixSectionScore(b));
      }
      if (COMPETENCY_SECTION_RULES.has(ruleId)) {
        return sections.slice().sort((a, b) => {
          const byContent = sectionContentScore(a) - sectionContentScore(b);
          if (byContent !== 0) return byContent;
          return competencySectionScore(a.section_name) - competencySectionScore(b.section_name);
        });
      }
      if (TABLE_SECTION_RULES.has(ruleId)) {
        return sections.slice().sort((a, b) => sectionContentScore(a) - sectionContentScore(b));
      }
      return sections;
    }

    function pickBestSectionForRule(ruleId, kind, sections, preferredSectionId = null) {
      const ranked = findSectionsForRule(ruleId, kind, sections);
      if (!ranked.length) return null;
      if (preferredSectionId) {
        const preferred = ranked.find(s => s.id === preferredSectionId);
        if (preferred && sectionHasEditorContent(preferred)) return preferred;
      }
      return ranked.find(s => sectionHasEditorContent(s)) || ranked[0];
    }

    function competencySectionScore(sectionName) {
      const name = String(sectionName || "");
      const prefix = sectionNumberPrefix(name);
      if (prefix === "2.1") return 0;
      if (prefix && /^2\.\d+/.test(prefix)) return 1;
      if (/компетенц|индикатор|планируемых результат/i.test(name)) return 2;
      if (prefix === "2") return 3;
      return 4;
    }

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
        R012: { where: "Раздел 2 → таблицы компетенций (З/У/В по индикаторам)", fix: "Уберите повторяющиеся формулировки З/У/В у разных индикаторов" },
        R013: { where: "Таблица 1.3 (часы СР) ↔ таблица 3.5", fix: "СР в 1.3 должно равняться итогу таблицы 3.5" },
        R014: { where: "Таблица 1.3 (контакт) ↔ темы 3.1 / 3.2", fix: "Согласуйте контактные часы между разделами" },
        R015: { where: "Таблица 3.1 ↔ раздел 2 (З/У/В)", fix: "Скопируйте формулировки из п.2 буквально, без перефразирования" },
        R016: { where: "Таблица 3.5 → виды СР и часы контроля (не таблица 3.1!)", fix: "«Подготовка к текущему контролю»; часы контроля = плану; КР≥30, КП≥40, контрольная≥10" },
        R017: { where: "Таблица 3.1 → колонки КР/КП/контрольные", fix: "Только +/- или «Есть/Нет», без часов" },
        R018: { where: "Таблица 3.5 → вопросы самостоятельного изучения (X.Y)", fix: "X.Y привязаны к темам 3.1; сумма часов = итог 3.5" },
        R019: { where: "Матрица 3.6 распределения часов", fix: "Темы = 3.1; суммы сходятся; СР темы ≥ сумма вопросов X.Y" },
        R020: { where: "Таблица 1.3 → всего часов и СР", fix: "Часы (кол. L) и СР (кол. O) как в УП" },
        R021: { where: "Таблица 1.3 → курсовая работа / проект", fix: "Не менее 30 ч (КР) или 40 ч (КП)" },
        R022: { where: "Таблица 1.3 → строка «Контактная работа», колонка очной формы (не таблицы тем 3.1/3.2 и не раздел 7)", fix: "Как hours_contact или hours_aud в УП" },
        R023: { where: "Таблица 3.5 → итог самостоятельной работы", fix: "Итог СР = hours_sr + hours_control в УП" },
        R024: { where: "Раздел 2 → таблица ПК", fix: "У каждой ПК должна быть группа (внутренняя группа вуза)" },
        R025: { where: "Таблица 1.3 (не текст § 3.3): лек + практ + лаб = строка «Контактная работа»", fix: "Согласуйте часы в табл. 1.3; «Не предусмотрены…» в разделе 3.3 — только описание" },
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

    function isPlainNumber(value) {
      const s = String(value || "").trim();
      return /^\d+(\.\d+)?$/.test(s) || /^≥\d+(\.\d+)?$/.test(s);
    }

    function looksLikeCodeList(expected, actual) {
      const parts = [...splitCodeList(expected), ...splitCodeList(actual)];
      if (!parts.length) return false;
      if (parts.every(isPlainNumber)) return false;
      return parts.some(p => /(?:УК|ОПК|ПК|ПСК|UK|OPK|PK)-/i.test(p))
        || String(expected || "").includes(";")
        || String(actual || "").includes(";");
    }

    function missingFromLists(expected, actual) {
      if (!looksLikeCodeList(expected, actual)) return [];
      const exp = new Set(splitCodeList(expected).map(normCompetencyCode));
      const act = new Set(splitCodeList(actual).map(normCompetencyCode));
      return [...exp].filter(c => !act.has(c));
    }

    const UP_HOUR_RULES = new Set(["R005", "R020", "R021", "R022", "R023"]);
    const NUMERIC_COMPARE_RULES = new Set([
      ...UP_HOUR_RULES,
      "R013", "R014", "R018", "R019", "R025", "R026", "R027",
    ]);

    const R016_NUMERIC_HINTS = new Set([
      "часы контрольной",
      "контрольная работа",
      "курсовая работа",
      "курсовой проект",
    ]);

    function ruleUsesNumericLabels(rule) {
      if (!NUMERIC_COMPARE_RULES.has(rule.rule_id)) return false;
      if (rule.rule_id === "R016") {
        const msg = String(rule.message || "").toLowerCase();
        return R016_NUMERIC_HINTS.some(h => msg.includes(h));
      }
      return Boolean(rule.expected && rule.actual && isPlainNumber(rule.expected) && isPlainNumber(rule.actual));
    }

    function valueShowsAsHours(ruleId, value) {
      return NUMERIC_COMPARE_RULES.has(ruleId) && isPlainNumber(value);
    }

    function numericRuleLabels(ruleId, rule) {
      if (ruleId === "R016" && rule && !ruleUsesNumericLabels(rule)) {
        return { expected: "Требование", actual: "В документе (§ 3.5)" };
      }
      const labels = {
        R013: ["СР в табл. 1.3", "Итого в § 3.5"],
        R014: ["Контакт в табл. 1.3", "Сумма по темам 3.1/3.2"],
        R016: ["Часы контроля в УП", "Часы контроля в § 3.5"],
        R018: ["Итого в § 3.5", "Сумма по вопросам"],
        R019: ["Итог в матрице", "Сумма в документе"],
        R025: ["Контакт в табл. 1.3", "Сумма лек+практ+лаб"],
        R026: ["Контакт (УП / 1.3)", "Сумма по темам"],
        R027: ["Итог СР в § 3.5", "Сумма строк"],
      };
      if (labels[ruleId]) {
        return { expected: labels[ruleId][0], actual: labels[ruleId][1] };
      }
      if (UP_HOUR_RULES.has(ruleId)) {
        return { expected: "Эталон (УП)", actual: "В документе (табл. 1.3)" };
      }
      return { expected: "Ожидается", actual: "В документе" };
    }

    function numericDeltaLine(rule) {
      if (!ruleUsesNumericLabels(rule) || !rule.expected || !rule.actual || rule.passed) {
        return "";
      }
      if (rule.rule_id === "R025") {
        return `<strong>Разница:</strong> контакт ${esc(rule.expected)} ч, сумма видов ${esc(rule.actual)} ч<br>`;
      }
      if (rule.rule_id === "R018") {
        return `<strong>Разница:</strong> в § 3.5 — ${esc(rule.expected)} ч, по вопросам — ${esc(rule.actual)} ч<br>`;
      }
      if (UP_HOUR_RULES.has(rule.rule_id)) {
        return `<strong>Разница:</strong> в УП ${esc(rule.expected)} ч, в документе ${esc(rule.actual)} ч<br>`;
      }
      if (isPlainNumber(rule.expected) && isPlainNumber(rule.actual)) {
        return `<strong>Разница:</strong> ${esc(rule.expected)} → ${esc(rule.actual)} ч<br>`;
      }
      return "";
    }

    function getHighlightTerms(rule, kind) {
      const terms = [];
      const meta = getRuleMeta(rule.rule_id, kind);
      if (rule.rule_id === "R012" && rule.actual) {
        const phrase = String(rule.actual).replace(/\s*\[[^\]]+\]\s*$/, "").trim();
        if (phrase.length >= 12) terms.push(phrase.slice(0, 80));
        const codes = String(rule.actual).match(/\[(.+)\]$/);
        if (codes) {
          codes[1].split(/,\s*/).forEach(code => {
            const trimmed = code.replace(/…$/, "").trim();
            if (trimmed) terms.push(trimmed);
          });
        }
        return [...new Set(terms.filter(t => t && String(t).length >= 3))].slice(0, 6);
      }
      if (rule.rule_id === "R019") {
        const topicM = String(rule.message || "").match(/Тема\s+(\d+)/i);
        if (topicM) {
          terms.push(`${topicM[1]}.`, topicM[1]);
        }
      }
      if (NUMERIC_COMPARE_RULES.has(rule.rule_id)) {
        if (rule.actual && String(rule.actual).length <= 120) {
          terms.push(String(rule.actual));
        }
        // Эталон (expected) не подсвечиваем: в § 3.5 это часто строка «итого», ошибка — в детализации
        if (/1\.3/i.test(meta.where)) terms.push("1.3", "Контактная работа");
        if (/3\.5/i.test(meta.where)) terms.push("3.5");
        return [...new Set(terms.filter(t => t && String(t).length >= 2))].slice(0, 6);
      }
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

    function isTotalRowHtml(rowHtml) {
      const text = String(rowHtml || "").replace(/<[^>]+>/g, " ").toLowerCase();
      return /\b(?:итог(?:о)?|всего)\b/.test(text)
        || /самостоятельн/.test(text) && /\b(?:изучен|работ)\b/.test(text);
    }

    function highlightTermPattern(term) {
      const raw = String(term).trim();
      const escaped = raw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (isPlainNumber(raw)) {
        return `(?<![\\d.,])(${escaped})(?![\\d.,])`;
      }
      return `(${escaped})`;
    }

    function highlightContentHtml(html, terms, options = {}) {
      if (!html || !terms.length) return html;
      const referenceValue = options.referenceValue != null
        ? String(options.referenceValue).trim()
        : null;
      let result = html;
      terms.forEach(term => {
        const raw = String(term).trim();
        if (raw.length < 2) return;
        if (referenceValue && raw === referenceValue) return;
        const pattern = highlightTermPattern(raw);
        const mark = '<mark class="val-err-mark" title="Возможное место ошибки">$1</mark>';
        if (/<tr[\s>]/i.test(result)) {
          result = result.replace(/(<tr[\s\S]*?<\/tr>)/gi, rowHtml => {
            if (referenceValue && isTotalRowHtml(rowHtml) && rowHtml.includes(referenceValue)) {
              return rowHtml;
            }
            return rowHtml.replace(
              new RegExp(`(?![^<]*>)${pattern}`, "gi"),
              mark
            );
          });
          return;
        }
        result = result.replace(
          new RegExp(`(?![^<]*>)${pattern}`, "gi"),
          mark
        );
      });
      return result;
    }

    function formatRuleSectionsLabel(sections, ruleId, kind) {
      if (!sections.length) {
        const meta = getRuleMeta(ruleId, kind);
        return meta.where ? `Откройте: ${meta.where}` : "Раздел не определён — см. подсказку «Где»";
      }
      if (sections.length === 1) return `Раздел: «${sections[0].section_name}»`;
      const names = sections.slice(0, 3).map(s => `«${s.section_name}»`).join(", ");
      return sections.length > 3
        ? `Разделы: ${names} и ещё ${sections.length - 3}`
        : `Разделы: ${names}`;
    }

    function formatRuleIssueCompact(rule, kind, sections, isActive, isWarning = false) {
      const primary = pickBestSectionForRule(rule.rule_id, kind, sections) || sections[0];
      const sectionId = primary?.id || "";
      const activeClass = isActive ? " active" : "";
      const warnClass = isWarning ? " warning" : "";
      const brief = (rule.message || "").replace(/\s+/g, " ").trim();
      const short = brief.length > 72 ? `${brief.slice(0, 69)}…` : brief;
      return `<div class="doc-issue-compact${activeClass}${warnClass}" role="button" tabindex="0"
        data-section-id="${sectionId}" data-rule-id="${esc(rule.rule_id)}">
        <span class="rule-id">${esc(rule.rule_id)}</span>
        <span class="rule-brief" title="${esc(brief)}">${esc(short)}</span>
        <button type="button" class="doc-issue-waive-btn" data-rule-id="${esc(rule.rule_id)}"
          title="Снять с контроля">Снять</button>
      </div>`;
    }

    function findValidationRule(ruleId) {
      if (!docEditorState.validation?.results) return null;
      return docEditorState.validation.results.find(r => r.rule_id === ruleId && !r.passed && !r.skipped)
        || null;
    }

    function renderDocEditorRuleHint(ruleId) {
      const el = document.getElementById("docEditorRuleHint");
      if (!el) return;
      if (!ruleId || !docEditorState.validation) {
        el.classList.remove("visible");
        el.innerHTML = "";
        return;
      }
      const rule = findValidationRule(ruleId);
      if (!rule) {
        el.classList.remove("visible");
        return;
      }
      const meta = getRuleMeta(ruleId, docEditorState.kind);
      const sections = findSectionsForRule(ruleId, docEditorState.kind, docEditorState.sections);
      const missing = missingFromLists(rule.expected, rule.actual);
      const labels = numericRuleLabels(ruleId, rule);
      const numericDelta = numericDeltaLine(rule);
      const missingLine = missing.length && !rule.passed
        ? `<strong>Не хватает кодов:</strong> <span style="color:var(--fail)">${esc(missing.join(", "))}</span><br>`
        : "";
      const expUnit = valueShowsAsHours(ruleId, rule.expected) ? " ч" : "";
      const actUnit = valueShowsAsHours(ruleId, rule.actual) ? " ч" : "";
      el.classList.add("visible");
      el.innerHTML = `
        <strong>${esc(rule.rule_id)}</strong> — ${esc(rule.name || rule.message)}<br>
        <strong>Где:</strong> ${esc(meta.where)}<br>
        <strong>Что сделать:</strong> ${esc(meta.fix)}<br>
        ${rule.expected ? `<strong>${labels.expected}:</strong> <span style="color:var(--ok)">${esc(rule.expected)}</span>${expUnit}<br>` : ""}
        ${rule.actual ? `<strong>${labels.actual}:</strong> <span style="color:var(--fail)">${esc(rule.actual)}</span>${actUnit}<br>` : ""}
        ${numericDelta}
        ${rule.rule_id === "R025" && !rule.passed ? `<span style="color:var(--muted);font-size:12px">Текст «Не предусмотрены…» в § 3.3 не отменяет эту проверку — смотрите <strong>таблицу 1.3</strong> (строки лекции / практика / лабораторные / контакт).<br></span>` : ""}
        ${missingLine}
        <span style="color:var(--accent)">${esc(formatRuleSectionsLabel(sections, ruleId, docEditorState.kind))}</span>
        · ${NUMERIC_COMPARE_RULES.has(ruleId) && rule.expected && rule.actual
          ? "ниже подсвечены строки с расхождением (эталонное «итого» не помечается)"
          : "в тексте ниже подсвечены возможные места ошибки"}
        <div class="doc-rule-hint-actions">
          <button type="button" class="btn sm doc-assist-inline" id="docRuleAssistBtn">🤖 Спросить помощника</button>
          ${window.ValidationFix?.isFixableRule(ruleId) ? `<button type="button" class="btn sm doc-fix-inline" id="docRuleFixBtn">✎ Предложить исправление</button>` : ""}
          ${window.ValidationFix?.canSuggestLlmFix?.(ruleId) ? `<button type="button" class="btn sm doc-fix-llm-inline" id="docRuleFixLlmBtn">✨ Правка (ИИ)</button>` : ""}
        </div>
      `;
      document.getElementById("docRuleAssistBtn")?.addEventListener("click", () => {
        window.ValidationAssistant?.expand?.();
        window.ValidationAssistant?.ask("Объясни эту ошибку и что исправить.");
      });
      document.getElementById("docRuleFixBtn")?.addEventListener("click", () => {
        window.ValidationFix?.suggestFix();
      });
      document.getElementById("docRuleFixLlmBtn")?.addEventListener("click", () => {
        window.ValidationFix?.suggestFixLlm();
      });
      window.ValidationAssistant?.onRuleFocus();
    }

    function sectionMatchesRule(sectionName, ruleId, kind) {
      const targets = RULE_SECTION_NUMS[kind]?.[ruleId];
      if (targets === undefined || !targets.length) return false;
      const name = String(sectionName || "").trim();
      const lower = name.toLowerCase();
      const prefix = sectionNumberPrefix(name);
      if (COMPETENCY_SECTION_RULES.has(ruleId) && !isCompetencySection(name)) {
        return false;
      }
      const matched = targets.some(target => {
        const t = String(target);
        if (/^\d/.test(t)) return prefixMatchesSection(prefix, t);
        return lower.includes(t.toLowerCase());
      });
      if (!matched) return false;
      if (isExamQuestionSection(name) && targets.some(t => /^\d/.test(String(t)))) {
        return false;
      }
      return true;
    }

    function findSectionsForRule(ruleId, kind, sections) {
      const matched = sections.filter(s => sectionMatchesRule(s.section_name, ruleId, kind));
      return sortSectionsForRule(ruleId, matched);
    }

    function buildSectionRuleMap(validation, kind, sections) {
      const map = new Map();
      if (!validation || !validation.results) return map;
      const issues = validation.results.filter(
        r => !r.skipped && !r.passed && !r.waived && (r.severity === "critical" || r.severity === "warning")
      );
      issues.forEach(rule => {
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
        r => !r.skipped && r.severity === "critical" && !r.passed && !r.waived
      );
    }

    function warningRules(validation) {
      if (!validation || !validation.results) return [];
      return validation.results.filter(
        r => !r.skipped && r.severity === "warning" && !r.passed && !r.waived
      );
    }

    function waivedRules(validation) {
      if (!validation || !validation.results) return [];
      return validation.results.filter(r => r.waived);
    }

    function formatWaivedRuleCard(rule, kind) {
      return `<div class="doc-waived-compact">
        <span class="rule-id waived">${esc(rule.rule_id)}</span>
        <button type="button" class="doc-issue-restore-btn" data-rule-id="${esc(rule.rule_id)}"
          title="Вернуть в контроль">↩</button>
      </div>`;
    }

