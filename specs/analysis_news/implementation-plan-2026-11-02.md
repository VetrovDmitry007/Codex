# BondNavigator — AI-агент анализа новостей: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать независимый асинхронный LangGraph-агент анализа одной новости эмитента облигаций и сохранения только проверенного результата в `public.news_analysis`.

**Architecture:** Один `StateGraph` с 10 согласованными узлами; ReAct-управление веб-инструментами; отдельные суммаризация, предварительный финансовый анализ, проверка анализа и детерминированная валидация. Три готовых экземпляра LLM, четыре системных промпта и существующий `PostgresStorage` с общим пулом `asyncpg`.

**Tech Stack:** Python, LangGraph/LangChain, TypedDict, asyncpg, PostgreSQL, Decimal, asyncio, logging, pytest.

**Spec:** [issuer-news-agent-2026-11-02.md](issuer-news-agent-2026-11-02.md). **Источник истины — спецификация**; при расхождении приостановить реализацию соответствующего шага и согласовать, не заменять требования догадками.

## Global Constraints

- Модуль `agents/analysis_news/`: `agent.py`, `models.py`, `nodes.py`, `tools.py`, `prompts.py`, `validation.py` и `__init__.py`. Узлы не раскладывать по дополнительным файлам.
- Хранилище — новый mixin `NewsAnalysisStorage` в `db/extensions/news_analysis.py` с подключением к существующему `db/postgres.py`. Не создавать отдельный пул.
- Только 10 узлов: `check_existing`, `assistant`, `route_assistant`, `tools`, `summarize`, `validate_summary`, `analyze_result`, `verify_analysis`, `validate_result`, `save_result`.
- Три экземпляра LLM на входе `get_graph(agent_model, summary_model, analysis_model, storage)`; два структурированных вывода из одного `analysis_model`. Четыре `SystemMessage` копировать из спецификации без смысловых правок.
- Доступные агенту инструменты только `fetch_web_page(url)` и `find_additional_sources(query)`, read-only, таймаут по умолчанию 20 секунд на вызов.
- `AgentState` содержит строго девять согласованных полей; история `messages` с редьюсером `add_messages`. Не добавлять checkpointer, Pydantic, CLI или вспомогательные LangGraph-узлы.
- `max_iterations = 8` по умолчанию: единый бюджет поисковых действий и повторов анализа, корректировок формата и ответа проверки; `correction_used` ограничивает один повтор для `NewsAnalysisResult` за запуск.
- Финальный результат — плоский `NewsAnalysisResult`. В PostgreSQL пишется только `status="success"` после `verify_analysis` и `validate_result`. Для `skipped`, `impact_unknown`, `error` запись не создаётся.
- Повторный анализ — `force_reanalysis: bool = False` и UPSERT по `news_id`; `created_at` не изменяется, `update_at` обновляется при повторном анализе.
- Ручной запуск — `run_graph()` без параметров и CLI, локальный `news_id` в функции, `asyncio.run(...)`, итоговый JSON через `logger.info`.
- **Прямое решение пользователя:** предварительную проверку совместимости утверждённого DDL с фактической схемой PostgreSQL **не выполнять**. При ошибке выполнения миграции сообщить о фактической причине; не менять согласованный DDL самостоятельно.
- Код по PEP 8 с аннотациями типов; модули, классы и функции — с содержательными русскими docstring по правилам проекта. Каждая готовая часть проверяется `pytest`. Никаких реальных внешних запросов в unit-тестах.

## Review Focus

1. `summary_value=True` либо `"15"` вместо целого числа: `validate_result` должен отклонять; тест `test_reject_bool_and_string_score` в Task 1.
2. `500 млн ₽` превращается в `500 млрд ₽`, либо `I полугодие 2026` — в 2025: `validate_summary` отклоняет черновик и возвращает исходный текст; тест `test_reject_wrong_scale_sign_or_period` в Task 4.
3. `find_additional_sources` вернул пустой список, timeout или ошибку: различать `сомнительная` и `null`, не выводить `passed` из сниппета; тест `test_search_empty_vs_failure_and_snippet` в Task 8.
4. Повторный URL, циклическое `continue_search` и два разных вида исправления JSON: не удваивать источники и не выходить за `max_iterations`/`correction_used`; тест `test_shared_budget_and_no_duplicate_sources` в Task 9.
5. Повторная обработка `news_id` при `force_reanalysis=False/True`: корректные `skipped` и UPSERT, сохранение `created_at`, обновление `update_at`; тест `test_skip_and_force_upsert_timestamps` в Task 2.

---

## Порядок и карта файлов

Сначала Codex изучает реальные файлы и зависимости BondNavigator (`db/postgres.py`, `db/extensions/issuer_news.py`, `db/extensions/issuer_score.py` или фактические аналоги, адаптеры LLM, `pyproject.toml`/тестовую конфигурацию). Показанная ниже структура — утверждённый целевой интерфейс, а не утверждение, что эти файлы уже существуют. В репозитории документации `Codex` исходный код BondNavigator может отсутствовать: выполнять план в рабочем репозитории проекта.

План реализуется последовательно. Для **каждой** задачи: красный `pytest` → минимальная реализация → зелёный `pytest` → просмотр диффа → отдельный коммит. Тесты входят в рабочий проект Codex по его правилам; временные тесты ChatGPT не относятся к этому плану.

### Task 1: Контракты данных и детерминированная проверка результата

**Files:**
- Create: `agents/analysis_news/models.py`, `agents/analysis_news/validation.py`, `agents/analysis_news/__init__.py`
- Test: `tests/agents/analysis_news/test_validation.py`

**Interfaces:**
- Типы `NewsFact`, `NewsContext`, `NewsAnalysisResult`, `VerifyAnalysisResult`, `SourceData` и `AgentState` — **строго из спецификации**, включая девять ключей состояния.
- Предлагаемые функции в `validation.py`: `validate_news_analysis_result(value: object) -> list[str]` и `validate_verification_result(value: object) -> list[str]`. Пустой список — валидно.
- Детерминированно проверять статусы, обязательные/недопустимые по статусу поля, типы, границы `[-50, 50]`, `news_context.facts[].verification` и условную обязательность `task`/`issues`/`result`/`reason` в `VerifyAnalysisResult`.

- [ ] **Step 1: Написать падающие тесты** `test_valid_success_and_terminal_statuses`, `test_reject_bool_and_string_score`, `test_invalid_nested_fact_and_range`, `test_verify_decision_required_fields`. Примеры: `summary_value=15` проходит; `summary_value=51`, `True`, `"15"` — ошибки; `verification="passed"` допустимо; `verification="unknown"` — ошибка; `continue_search` без `task.question` — ошибка.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_validation.py -q`; ожидаемо FAIL до реализации.
- [ ] **Step 3: Реализовать** типы и обе проверки, без Pydantic и повторного `json.loads()`. Тип `int` проверять без неявного принятия `bool`.
- [ ] **Step 4: Запустить** тот же `pytest`; ожидаемо PASS, проверить аннотации и русские docstring.
- [ ] **Step 5: Зафиксировать** отдельный коммит `feat: add news analysis contracts and validators`.

### Task 2: DDL, хранилище и политика повторной обработки

**Files:**
- Create: `db/extensions/news_analysis.py`; SQL-миграцию — в **существующем каталоге миграций проекта** (определить при изучении репозитория, не создавать новую систему миграций).
- Modify: `db/postgres.py` (подключить mixin по действующему образцу).
- Test: `tests/db/test_news_analysis_storage.py`

**Interfaces:**
- `NewsAnalysisStorage`: асинхронные операции загрузки исходной новости по `news_id`, проверки наличия анализа по `news_id` и записи успешного результата. Конкретные имена методов выбрать **по стилю существующих `*Storage`**, зафиксировать в тесте и использовать одинаково во всех узлах.
- Единственный утверждённый SQL — `CREATE TABLE public.news_analysis` из спецификации. Уникальный ключ `news_id`; `issuer_id` с внешним ключом на `public.issuers(id)`; `reporting_period TEXT NULL`; категории и диапазон с `CHECK`.

- [ ] **Step 1: Изучить** существующее устройство `PostgresStorage`/`asyncpg.Pool` и механизм миграций. **Не выполнять предварительную проверку совместимости DDL**.
- [ ] **Step 2: Написать падающие тесты** `test_get_existing_analysis`, `test_skip_and_force_upsert_timestamps`, `test_rollback_on_save_failure`, `test_get_missing_news`. Мокать asyncpg; проверить, что при `force_reanalysis=True` используется `ON CONFLICT (news_id) DO UPDATE` и не перезаписывается `created_at`.
- [ ] **Step 3: Запустить** `pytest tests/db/test_news_analysis_storage.py -q`; ожидаемо FAIL.
- [ ] **Step 4: Добавить** SQL и mixin, подключить его к `PostgresStorage` без нового пула; запрещать запись неуспешных статусов.
- [ ] **Step 5: Запустить** тот же `pytest`; ожидаемо PASS. Проверить, что SQL совпадает со спецификацией буквально по схеме и ограничениям; **не применять миграцию в рамках этого шага без разрешения владельца БД**.
- [ ] **Step 6: Коммит** `feat: add news analysis storage and migration`.

### Task 3: Веб-инструменты ReAct и корректное обновление `sources`

**Files:**
- Create: `agents/analysis_news/tools.py`
- Test: `tests/agents/analysis_news/test_tools.py`

**Interfaces:**
- Вход LLM: `fetch_web_page(url: str)`, `find_additional_sources(query: str)`. Внутренний доступ к состоянию/`tool_call_id` — через поддерживаемую версией LangGraph инъекцию.
- Результат `fetch_web_page`: `{"url": ..., "title": ..., "text": ..., "status": "success"}` либо `{"url": ..., "status": "error", "msg": ...}`. Успешный полный текст хранится в `sources[url]`, для `ToolNode` возвращается `Command(update=...)` с коротким `ToolMessage` и сохранением остальных URL.
- Результат поиска: `{"status": "success", "sources": [{"title", "url", "description"}]}` либо `{"status": "error", "msg": ...}`. Пустой список — успех; сниппет не подтверждает факт.

- [ ] **Step 1: Написать падающие тесты** `test_fetch_success_updates_complete_sources`, `test_fetch_error_has_no_text`, `test_search_empty_success`, `test_timeout_20_seconds_error`, `test_source_tool_message_matches_tool_call_id`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_tools.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** два read-only инструмента, настраиваемый 20-секундный таймаут, статусы и совместимый `Command`; не вкладывать полный текст статьи в `ToolMessage`. Реальное HTTP/search-API выбрать из уже используемых проектом решений; не создавать без необходимости собственный веб-стек.
- [ ] **Step 4: Запустить** тот же `pytest` с mocked network; ожидаемо PASS.
- [ ] **Step 5: Коммит** `feat: add read-only news web tools`.

### Task 4: Суммаризация статьи и безопасная проверка фактов

**Files:**
- Create: `agents/analysis_news/prompts.py` (четыре утверждённых `SystemMessage`), `agents/analysis_news/nodes.py` (начать узлы `summarize` и `validate_summary`).
- Modify: `agents/analysis_news/validation.py`
- Test: `tests/agents/analysis_news/test_summary.py`

**Interfaces:**
- `summary_llm` обрабатывает только `sources[url].text`. На выходе текст черновика `sources[url].draft`; после `validate_summary` — `summary_status="validated"` и `summary` либо `summary_status="rejected"` с отправкой оригинала.
- Предлагаемая чистая функция: `validate_summary_content(original: str, draft: str) -> list[str]`. Проверка `Decimal` для чисел, единиц, масштаба, знака, даты и отчётного периода **по связи с показателем**, без произвольного пересчёта.

- [ ] **Step 1: Написать падающие тесты** `test_preserve_numbers_currency_dates`, `test_reject_wrong_scale_sign_or_period`, `test_reject_added_number`, `test_valid_summary_or_fallback_added_once`, `test_repeated_source_avoids_resummary`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_summary.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Добавить** тексты промптов из спецификации без новых инструкций; реализовать узлы и проверку. Например, `1 250,5` и `1250.5` допустимо нормализовать, `500 млн ₽` и `500 млрд ₽` — нет; при расхождении сообщить причину через `logging` и передать исходник.
- [ ] **Step 4: Запустить** тот же `pytest`; ожидаемо PASS. Проверить, что черновик не попадает в `messages` до валидации.
- [ ] **Step 5: Коммит** `feat: add verified news summarization`.

### Task 5: Каркас графа, роутер и проверка существующего анализа

**Files:**
- Create: `agents/analysis_news/agent.py`
- Modify: `agents/analysis_news/nodes.py`
- Test: `tests/agents/analysis_news/test_graph_routing.py`

**Interfaces:**
- `get_graph(agent_model, summary_model, analysis_model, storage)` — принимает готовые зависимости и возвращает скомпилированный `StateGraph`.
- `check_existing`: `screening` или сохранённый `news_id` при `force_reanalysis=False` → `skipped`; ошибка БД → `error`; иначе к `assistant`.
- `route_assistant`: приоритет `result.status=="error"` → `END`; иначе `tool_calls` → `tools`; иначе → `analyze_result`. После успешной страницы `tools → summarize → validate_summary → assistant`, после поиска/ошибки `tools → assistant`.

- [ ] **Step 1: Написать падающие тесты** `test_graph_contains_exactly_ten_nodes`, `test_check_existing_skip_and_db_error`, `test_route_priority_error_tools_analysis`, `test_loaded_page_passes_summary`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_graph_routing.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** узлы и маршруты, подключить `ToolNode` с двумя инструментами, динамический `Command.goto` из `verify_analysis` без параллельных статических исходящих рёбер. Нереализованные пока узлы подключать только через минимальные тестовые подстановки; не объявлять граф готовым до Task 9.
- [ ] **Step 4: Запустить** тот же `pytest`; ожидаемо PASS.
- [ ] **Step 5: Коммит** `feat: add news agent graph routing`.

### Task 6: `assistant`, накопление сообщений и единый бюджет шагов

**Files:**
- Modify: `agents/analysis_news/nodes.py`, `agents/analysis_news/agent.py`
- Test: `tests/agents/analysis_news/test_react.py`

**Interfaces:**
- Модель `agent_model.bind_tools(tools, parallel_tool_calls=False)`; исходный `HumanMessage` — один раз при создании состояния; источники добавлять по одному `HumanMessage` только после `validate_summary`.
- `continue_search` передаётся через новое адресованное сообщение `messages`, без дублей исходной новости. `AgentState.iterations` — один шаг на поисковое действие, не два за `assistant+tool`. Лимит по умолчанию 8.

- [ ] **Step 1: Написать падающие тесты** `test_initial_news_added_once`, `test_search_task_delivered_without_duplicate_news`, `test_no_tool_search_still_consumes_budget`, `test_tool_call_counts_once`, `test_limit_stops_new_search`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_react.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** `assistant`, правило подсчёта шагов и отсечение бесконечных циклов, сохраняя терминальные статусы `impact_unknown` (нехватка сведений) и `error` (неустранимый сбой). Не создавать полей `AgentState` и не дублировать историю.
- [ ] **Step 4: Запустить** тот же `pytest`; ожидаемо PASS.
- [ ] **Step 5: Коммит** `feat: add bounded news ReAct assistant`.

### Task 7: `analyze_result` и общий флаг исправления

**Files:**
- Modify: `agents/analysis_news/nodes.py`
- Test: `tests/agents/analysis_news/test_analysis_node.py`

**Interfaces:**
- `analysis_llm = analysis_model.with_structured_output(NewsAnalysisResult, include_raw=True)`; использовать собственный `SystemMessage`, `news`, `sources`, а из `messages` — только замечания `revise_analysis`; `raw_result` и `parsed_result` сохраняются в состоянии.
- При `parsed=None`/`parsing_error` разрешена **одна** локальная попытка исправления с `correction_used=True` и расходом одного `iterations`. Неудача → терминальный `result.status="error"`, который `verify_analysis` пропускает без LLM.
- При `revise_analysis` новый финансовый вывод учитывает `issues`, не ищет источники, расходует шаг общего бюджета.

- [ ] **Step 1: Написать падающие тесты** `test_preliminary_verification_is_null`, `test_revision_uses_only_addressed_issues`, `test_local_parsing_retry_once`, `test_parsing_error_skips_verification_llm`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_analysis_node.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** вызов анализа, обработку структурированного вывода и терминальных ошибок; сохранить `verification=null` только как предварительный заполнитель без выводов о достоверности.
- [ ] **Step 4: Запустить** тот же `pytest`; ожидаемо PASS.
- [ ] **Step 5: Коммит** `feat: add structured preliminary news analysis`.

### Task 8: `verify_analysis` и четыре исхода проверки

**Files:**
- Modify: `agents/analysis_news/nodes.py`
- Test: `tests/agents/analysis_news/test_verification_node.py`

**Interfaces:**
- `verification_llm = analysis_model.with_structured_output(VerifyAnalysisResult, include_raw=True)` с отдельным `SystemMessage`, без веб-инструментов.
- `continue_search` → `assistant` с `task.fact`/`task.question`; `revise_analysis` → `analyze_result` с `issues`; `complete` → `validate_result` с `parsed_result=result`; `impact_unknown` → `END` с причиной.
- Одна повторная попытка некорректного `VerifyAnalysisResult` в пределах `max_iterations`; локальный счётчик повторов, `correction_used` не расходовать.

- [ ] **Step 1: Написать падающие тесты** `test_four_verification_decisions`, `test_search_empty_vs_failure_and_snippet`, `test_validation_retry_then_error`, `test_complete_passes_candidate_not_saved_result`. Проверить, что `passed` требует **полного независимого источника**, успешный пустой поиск даёт `сомнительная` проверяемому факту, технический сбой — `null`, одно лишь описание поисковой выдачи не даёт `passed`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_verification_node.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** четыре ветки с `Command(update=..., goto=...)`, проверку контракта `VerifyAnalysisResult` и один повтор при его ошибке. Не пересчитывать `summary_value`/`summary_category` в проверяющем узле.
- [ ] **Step 4: Запустить** тот же `pytest`; ожидаемо PASS.
- [ ] **Step 5: Коммит** `feat: add financial analysis verification and retries`.

### Task 9: `validate_result`, `save_result` и полные маршруты

**Files:**
- Modify: `agents/analysis_news/nodes.py`, `agents/analysis_news/agent.py`
- Test: `tests/agents/analysis_news/test_pipeline.py`

**Interfaces:**
- `validate_result` проверяет `AgentState.parsed_result` (результат `verify_analysis`), лишь при успехе переносит в `AgentState.result`.
- При структурной ошибке — один возврат в `analyze_result`, **только если** `correction_used=False` и есть бюджет; исправление снова проходит узел 8. `save_result` принимает **только** проверенный `status="success"`, пишет через `PostgresStorage` и использует транзакцию.
- При сбое сохранения → rollback и терминальный `error` без дополнительной LLM.

- [ ] **Step 1: Написать падающие тесты** `test_complete_validate_then_save_only`, `test_shared_budget_and_no_duplicate_sources`, `test_never_save_skipped_unknown_or_error`, `test_invalid_json_corrected_once`, `test_save_failure_rolls_back`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_pipeline.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** заключительные узлы и полное выполнение графа через `ainvoke`; проверить отсутствие обходного сохранения из `analyze_result` либо `verify_analysis`.
- [ ] **Step 4: Запустить** `pytest tests/agents/analysis_news/test_pipeline.py -q`; ожидаемо PASS. Далее `pytest tests/agents/analysis_news tests/db/test_news_analysis_storage.py -q`; исправить регрессии.
- [ ] **Step 5: Коммит** `feat: validate and persist verified news analysis`.

### Task 10: Ручной запуск, диагностика и приёмочные проверки

**Files:**
- Modify: `agents/analysis_news/agent.py`
- Test: `tests/agents/analysis_news/test_runner.py`

**Interfaces:**
- `run_graph() -> None`: локальный `news_id`, создание зависимостей по действующим адаптерам проекта, загрузка `issuer_news` **до графа**, `asyncio.run` и `graph.ainvoke`; без CLI. Отсутствующая новость → `error` без LLM.
- Итоговый JSON через `logger.info(json.dumps(result, ensure_ascii=False, indent=2))`; `debug=False` по умолчанию; отладочные сообщения узлов — только при включённой диагностике, без секретов.

- [ ] **Step 1: Написать падающие тесты** `test_missing_news_returns_error_without_llm`, `test_runner_logs_result_at_info_without_debug`, `test_debug_does_not_log_secrets`, `test_run_graph_requires_no_arguments`.
- [ ] **Step 2: Запустить** `pytest tests/agents/analysis_news/test_runner.py -q`; ожидаемо FAIL.
- [ ] **Step 3: Реализовать** минимальную ручную обёртку, переиспользовать существующую конфигурацию адаптеров, не создавать новых провайдеров и CLI-аргументов.
- [ ] **Step 4: Запустить** `pytest tests/agents/analysis_news tests/db/test_news_analysis_storage.py -q`; ожидаемо PASS. Затем — `pytest -q` для регрессий затронутого проекта, если среда позволяет.
- [ ] **Step 5: Прочитать** изменённые файлы, проверить docstring, PEP 8, SQL, маршруты, бюджет, отсутствие секретов в логах и дублирования источников. Коммит `feat: finalize news analysis agent runner`.

## Acceptance Criteria

- В графе ровно 10 согласованных узлов и 4 `SystemMessage`; три переданные модели, один общий `analysis_model` для двух структурированных ответов.
- Поиск и загрузка работают как отдельные read-only инструменты; обязательная проверка суммаризации не допускает искажений чисел, масштаба и периодов.
- Терминальные статусы и ошибки возвращаются плоским JSON; только `success` попадает в `news_analysis` после **обеих** проверок.
- При повторном запуске `news_id` без `force_reanalysis` получаем `skipped`; с ним — UPSERT без потери `created_at`.
- Подсчёт `iterations` и единый `correction_used` исключают бесконечный цикл и более одной коррекции `NewsAnalysisResult`.
- Unit-тесты основных и граничных случаев проходят; результаты `pytest` и ограничения среды отмечены в отчёте Codex. Наличие согласованного DDL **не означает**, что миграция была применена.
- Не реализуются дополнительные сервисы: обработка исторических новостей, автоматический scheduler, новое скоринговое API, дополнительные таблицы и произвольные поля результата.

## Execution Handoff

Этот документ — план, **не отчёт о выполненной реализации**: все флажки изначально пусты, код и миграция настоящим изменением не создавались. Перед началом Codex должен прочесть всю спецификацию, сверить реальные зависимости рабочего репозитория BondNavigator и реализовывать задачи с независимыми тестовыми циклами и коммитами. Любое расхождение утверждённых контрактов с фактическим API требует остановки и согласования, а не молчаливого изменения спецификации.
