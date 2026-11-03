# AI-агент анализа новостей эмитентов — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkboxes (`- [ ]`) for tracking.

**Goal:** реализовать в BondNavigator LangGraph-агента, который исследует одну новость эмитента, проверяет факты, формирует обоснованную оценку финансового влияния и сохраняет только проверенный результат.

**Architecture:** отдельный пакет `agents/analysis_news/` с 10 узлами `StateGraph`, двумя read-only веб-инструментами, тремя экземплярами LLM и четырьмя системными промптами. PostgreSQL используется через существующий `PostgresStorage` и новый mixin `NewsAnalysisStorage`; сохранение защищено session-level advisory lock. Публичный запуск — `run_news_analysis(...)`, внутреннее состояние не выходит наружу.

**Tech Stack:** Python, LangGraph, LangChain Core, asyncpg, PostgreSQL, pytest/pytest-asyncio (или эквивалентный уже установленный async pytest-режим), существующие адаптеры LLM BondNavigator.

**Spec:** [`specs/analysis_news/issuer-news-agent-2026-11-02.md`](../../../specs/analysis_news/issuer-news-agent-2026-11-02.md) — [GitHub](https://github.com/VetrovDmitry007/Codex/blob/main/specs/analysis_news/issuer-news-agent-2026-11-02.md), ветка `main`, редакция после коммита `6f0b0bfb`.

**Источники проверки:** утверждённая архитектурная спецификация; предоставленный пользователем снимок структуры `PROJECT_STRUCTURE.md` (в нём подтверждены общий `db/postgres.py` и `db/extensions/`, однако актуальные реализации `issuer_news`, LLM-адаптеров и миграций в этом ходе не открывались). Указанные ниже пути новых файлов — целевая структура из спецификации; фактические интерфейсы существующих файлов обязательно прочитать до изменений.

## Global Constraints

- Не менять согласованный граф из **10 узлов**: `check_existing`, `assistant`, `route_assistant`, `tools`, `summarize`, `validate_summary`, `analyze_result`, `verify_analysis`, `validate_result`, `save_result`.
- `AgentState` — `TypedDict` с полями `news, messages, sources, raw_result, parsed_result, result, validation_errors, iterations, correction_used`; только `messages` использует `add_messages`. Не применять Pydantic, checkpointer или новую таблицу для состояния.
- `get_graph(agent_model, summary_model, analysis_model, storage)` принимает три **готовых** экземпляра моделей и существующий `PostgresStorage`. Использовать **четыре** отдельных `SystemMessage` из спецификации, не создавать нового провайдера.
- `max_iterations=8`, `recursion_limit=128` — независимые пределы. Одна попытка сетевого повтора на логический вызов LLM при временном сбое, с расходом общей итерации; только одна общая коррекция окончательного `NewsAnalysisResult`.
- Веб-инструменты: таймаут **20 секунд** на вызов; `fetch_web_page` — только публичные HTTP(S), контролируемые DNS/IP и редиректы (не более **5**), разрешённый текстовый MIME, максимум **4 MiB** распакованного тела по умолчанию; защищаться от DNS rebinding.
- A7: после **двух успешных поисковых действий без новых URL/текста** запретить дальнейший поиск; `continue_search` при блокировке детерминированно переводить в `impact_unknown`, без нового LLM.
- A1/A2/A8: только проверенный `success` допускается к записи; идентификаторы строго из `AgentState.news`; `positive > 0`, `negative < 0`, `neutral == 0`, `mixed` допускает любой знак при наличии факторов обоих направлений.
- PostgreSQL: **одна** запись на `news_id`; `INSERT ... ON CONFLICT DO NOTHING RETURNING id` для обычного запуска; `UPSERT` для `force_reanalysis=True`; запись **на том же физическом соединении**, удерживающем advisory lock. Не держать транзакцию во время LLM/HTTP.
- При `news_type="screening"` → `skipped` до графа. При отсутствующей записи в `issuer_news` → **`NewsNotFoundError(news_id)` до создания графа**, без `NewsAnalysisResult`, без фиктивного `issuer_id`. Не путать отсутствие строки с технической ошибкой PostgreSQL.
- Публичный результат только `NewsAnalysisResult` через `run_news_analysis(...)`; `graph.ainvoke(...)` внутри возвращает полный `AgentState`, его нельзя отдавать наружу.
- Для всех модулей, классов и функций — содержательные docstring на русском языке, аннотации типов, PEP 8; сохранять публичные контракты и существующую функциональность.
- Утверждённый DDL перенести без самовольных изменений. Проверка его совместимости с реальной БД **предварительно пропущена по решению пользователя**; возможные проблемы миграции зафиксировать, не считать таблицу созданной до реального применения.
- Постоянные тесты реализации хранить в проекте; временные тесты, если создаются отдельно в среде ChatGPT, не передавать без запроса. Выполнение этого плана **не начато**, чисел прошедших тестов пока нет.

## Review Focus

Пять наиболее рискованных входных условий и их ожидаемое поведение:
1. `news_id` отсутствует при успешном SELECT: `NewsNotFoundError`, ноль LLM/SQL write/графовых узлов — тест задачи 9.
2. Публичный домен сначала разрешился в публичный IP, затем HTTP-клиент переподключился к приватному: запрос **запрещён**, валидация IP не обходится — тест задачи 4.
3. Сессия advisory lock потеряна непосредственно перед `UPSERT`: запись запрещена, новый `pool.acquire()` не допускается — тест задачи 3.
4. `verify_analysis` возвращает `continue_search` после порога A7: переход в `END/impact_unknown`, без инструмента и LLM-повтора — тест задачи 8.
5. Граф завершился с `result=success`, но транзакция `save_result` не закоммичена: публичный ответ **не success**, служебные поля не раскрываются — тест задачи 9.

---

## Этап 0. Предварительная сверка с живым кодом (без правок)

**Прочитать:** `db/postgres.py`, `db/extensions/__init__.py` и связанные mixin-классы, модуль работы с `issuer_news`, имеющиеся адаптеры LLM, `pyproject.toml`/`requirements.txt`, соглашения о миграциях и тестах. **Не** подменять исходники снимком `PROJECT_STRUCTURE.md`.

- [ ] Сверить реальные имена методов чтения новости, инициализацию `asyncpg.Pool`, конфигурацию адаптеров, тип `issuer_news.id`, наличие `news_type`.
- [ ] Проверить версии LangGraph/LangChain, поддержку `ToolNode + Command(update=...)`, асинхронного `ainvoke` и переноса `ContextVar` между его задачами на небольшом изолированном прототипе.
- [ ] Зафиксировать способ применения SQL-миграций в проекте. Предлагаемый путь нового DDL — `db/migrations/20261103_create_news_analysis.sql`; если в проекте уже есть иной миграционный механизм, использовать **его** без переноса остальных миграций.
- [ ] Выполнить исходную проверку `python -m pytest -q` и отдельно зафиксировать исходные ошибки/пропущенные тесты. Не изменять код ради несвязанных проблем.
- [ ] Если фактический интерфейс расходится с планом, остановить конкретный затронутый этап и согласовать только существенное расхождение. Не менять утверждённую спецификацию молча.

## Task 1. Предметные контракты и детерминированная проверка

**Files:** создать `agents/analysis_news/__init__.py`, `agents/analysis_news/models.py`, `agents/analysis_news/validation.py`; тест `tests/analysis_news/test_validation.py`.

**Interfaces:** `NewsFact`, `NewsContext`, `NewsAnalysisResult`, `VerifyAnalysisResult`, `SourceData` и `AgentState` — точно по спецификации. В `validation.py` выделить проверку конечного результата: `validate_news_result(candidate: dict[str, Any], news: dict[str, Any]) -> list[str]` и детерминированную проверку чисел суммаризации (интерфейс определить по фактическому текстовому формату, не вводя Pydantic).

- [ ] Написать тесты: допустимый `success`; отсутствие каждого обязательного поля; неверные типы (включая `bool` вместо `int`); чужие `news_id/issuer_id`; `summary_value` за пределами `[-50,50]`; несовместимые пары `positive/negative/neutral`; корректный `mixed`; пустые `facts[].fact` и недопустимые `verification`; неверные поля для терминальных статусов.
- [ ] Запустить `python -m pytest -q tests/analysis_news/test_validation.py`; убедиться, что новые проверки сначала не проходят (red).
- [ ] Реализовать минимальные модели и проверку; не исправлять результаты LLM автоматически, возвращать причины ошибок.
- [ ] Запустить тесты до PASS; затем `python -m pytest -q tests/analysis_news`; отдельный коммит `feat(analysis-news): add result contracts and validation`.

## Task 2. Миграция и чтение исходной новости

**Files:** создать SQL-миграцию выбранным на этапе 0 способом и `db/extensions/news_analysis.py`, изменить подключения mixin в `db/postgres.py`/фактическом файле импорта; тесты `tests/analysis_news/test_storage_read.py` и `tests/analysis_news/test_storage_schema.py`.

**Interfaces:** `NewsAnalysisStorage.load_news_for_analysis(news_id: int) -> dict[str, Any] | None`; `NewsAnalysisStorage.news_analysis_exists(news_id: int) -> bool`. Возвращаемые поля новости — исходные `id`, `issuer_id`, `news_type`, заголовок, URL, дата и необходимые метаданные.

- [ ] Написать тесты: найденная новость, отсутствие строки, ошибка SQL (не равна `None`), `screening`; существующая/отсутствующая запись анализа и ошибка проверки дубля.
- [ ] Запустить новые тесты до ожидаемого FAIL.
- [ ] Добавить методы чтения в существующий пул, подключить mixin без отдельного пула; перенести в миграцию согласованный `public.news_analysis`: `UNIQUE(news_id)`, FK только для `issuer_id`, `CHECK` категории и диапазона оценки, `created_at/update_at`.
- [ ] Проверить тесты и отдельной проверкой SQL на **тестовом PostgreSQL**, когда он доступен, убедиться в корректном создании схемы. Не утверждать, что миграция применена в рабочей БД.
- [ ] Коммит `feat(analysis-news): add news analysis storage and schema`.

## Task 3. Защищённая сессия A3 и атомарное сохранение

**Files:** изменить `db/extensions/news_analysis.py`; тесты `tests/analysis_news/test_storage_lock.py` и `tests/analysis_news/test_storage_write.py`.

**Interfaces:** асинхронный контекст защищённого запуска для `news_id` (сессия из существующего пула + `ContextVar`); сохранение `save_news_analysis(news: dict[str, Any], result: NewsAnalysisResult, *, force_reanalysis: bool) -> Literal["inserted", "updated", "skipped"]`, вызываемое только внутри защищённой сессии.

- [ ] Тестировать: два конкурирующих запуска **одного** `news_id` (второй не запускает анализ); независимые `news_id`; `pg_backend_pid()` совпадает при взятии lock и записи; пустой/потерянный `ContextVar`; чужой `news_id`; потеря сессии между проверкой и SQL; отмена задачи; SQL-rollback; повторное использование соединения после корректной разблокировки.
- [ ] Запустить тесты до FAIL; тесты реального advisory lock выполнять на **изолированной PostgreSQL**, не заменять их SQLite.
- [ ] Реализовать context manager, проверку владения и короткую транзакцию **на том же соединении**; `DO NOTHING` возвращает `skipped`, `UPSERT` при `force_reanalysis=True` сохраняет `created_at` и обновляет `update_at`.
- [ ] Проверить отсутствие транзакции на протяжении LLM/HTTP и отсутствие fallback `pool.acquire()` в сохранении. PASS тестов, отдельный коммит `feat(analysis-news): serialize news writes with advisory locks`.

## Task 4. `fetch_web_page`, SSRF и ограничение ресурсов

**Files:** создать `agents/analysis_news/tools.py`; тест `tests/analysis_news/test_fetch_web_page.py`.

**Interfaces:** tool `fetch_web_page(url: str)` с результатом `{url, status, title, text}` при успехе и `{url, status:"error", msg}` при отказе. Входящие URL — недоверенные.

- [ ] Тесты безопасной публичной HTML-страницы и обычного текста; `file:/ftp:/data:`, userinfo, внутренний hostname, IPv4/IPv6 loopback/private/link-local/special-use, нестандартный порт, некорректный URL, DNS с хотя бы одним запретным IP.
- [ ] Тесты DNS rebinding: соединение действительно использует **проверенный** адрес; в случае невозможности pinning — отказ. Проверить HTTPS SNI/Host и сертификат с тестовым transport/resolver.
- [ ] Тесты каждого редиректа, перенаправления на приватный адрес, более 5 редиректов, цикла; MIME вне списка `text/html/text/plain/application/xhtml+xml`, отсутствующего MIME, `Content-Length` и потокового размера >4 MiB, gzip/deflate decompression bomb, таймаута 20 секунд.
- [ ] Запустить тесты до FAIL; реализовать потоковую безопасную загрузку без неявных proxy/env-настроек, без автоматической загрузки `iframe`/ресурсов и без LLM/суммаризации.
- [ ] PASS; проверить отсутствие реальных внешних HTTP-запросов в тестах (fake transport); коммит `feat(analysis-news): add SSRF-safe page fetcher`.

## Task 5. `find_additional_sources` и учёт прогресса A7

**Files:** дополнить `agents/analysis_news/tools.py`, при необходимости вспомогательную детерминированную логику в `agents/analysis_news/validation.py`; тесты `tests/analysis_news/test_source_search.py` и `tests/analysis_news/test_search_progress.py`.

**Interfaces:** `find_additional_sources(query: str)` → `{status:"success",sources:[{title,url,description}]}` или `{status:"error",msg}`. Нормализация URL и поисковых запросов без потери значащих query-параметров. История инструмента хранится в `messages`, тексты — в `sources`.

- [ ] Тесты: успешный список, успешный **пустой** список, ошибка поиска, таймаут, повтор после ошибки, успешный повтор идентичного запроса без сетевого обращения, новый существенно иной запрос, ранее обработанный URL и новый изменённый текст.
- [ ] Тестировать два последовательных **успешных** действия без прогресса и сброс серии новым URL/текстом; техническую ошибку не классифицировать как успешный пустой поиск.
- [ ] Red → реализовать нормализацию/кэш только в рамках одного запуска (`messages/sources` без новых полей State) → Green.
- [ ] Проверить `ToolMessage` с актуальным `tool_call_id` и согласованность `add_messages`; коммит `feat(analysis-news): add source search and progress guard`.

## Task 6. Суммаризация и проверка точности

**Files:** создать `agents/analysis_news/prompts.py` (все четыре согласованных системных промпта), реализовать `summarize` и `validate_summary` в `agents/analysis_news/nodes.py`; тест `tests/analysis_news/test_summarization.py`.

**Interfaces:** вход `sources[url].text`; выход `sources[url].draft/summary/summary_status`; при успехе **одно** добавление проверенного текста в `messages`; при отклонении — **одно** добавление исходного полного текста.

- [ ] Red-тесты: `1 250,5 == 1250.5`, изменённое число/минус, дополнительное выдуманное число, потеря существенных чисел, расхождение отчётного периода и РСБУ/МСФО, пустой ответ, повтор одного текста, технические 429/503/timeout и постоянный 4xx.
- [ ] Реализовать числовую проверку с точным сравнением (без float и без изменения чисел), fallback на исходный текст, переиспользование валидированной/отклонённой суммаризации.
- [ ] Green; проверить отсутствие повторного добавления сообщений или второго `summary_llm` для неизменённого текста; коммит `feat(analysis-news): add checked financial summaries`.

## Task 7. Аналитическая LLM и независимая содержательная проверка

**Files:** `agents/analysis_news/nodes.py`, `agents/analysis_news/prompts.py`, `agents/analysis_news/validation.py`; тесты `tests/analysis_news/test_analysis_nodes.py` и `tests/analysis_news/test_verification_nodes.py`.

**Interfaces:** `analysis_model.with_structured_output(NewsAnalysisResult, include_raw=True)` и `analysis_model.with_structured_output(VerifyAnalysisResult, include_raw=True)`; `raw_result` сохраняет сырой ответ, `parsed_result` — непроверенный кандидат, `result` — только проверенный или терминальный результат.

- [ ] Red-тесты 4 решений `verify_analysis`: `continue_search`, `revise_analysis`, `complete`, `impact_unknown`; проверка полноты существенных фактов исходного события и наличия обоих направлений для `mixed`.
- [ ] Тестировать `parsed=None`, `parsing_error`, неверный тип, `complete` с `result.status != "success"`, подмену `issuer_id/news_id`, неверные пары категории/знака; исправление конечного результата **одно на запуск**, вторая ошибка → `error` без записи.
- [ ] Тестировать ограниченный сетевой retry для 429/5xx/timeout, отсутствие retry для постоянных 4xx, расход `iterations` каждым повтором и запрет исправления при исчерпанном `max_iterations`.
- [ ] Red → реализовать узлы и A1/A2/A4/A8-guard без новых полей/узлов → Green; коммит `feat(analysis-news): analyze and verify issuer news`.

## Task 8. Сборка `StateGraph`, ReAct и маршрутизация

**Files:** `agents/analysis_news/agent.py`, `agents/analysis_news/nodes.py`; тесты `tests/analysis_news/test_graph_routes.py` и `tests/analysis_news/test_graph_limits.py`.

**Interfaces:** `get_graph(agent_model, summary_model, analysis_model, storage)`; ровно 10 узлов, маршруты строго по Mermaid спецификации. `max_iterations=8` и верхнеуровневый `config={"recursion_limit":128}`.

- [ ] Red-тесты: `check_existing → END` для `skipped/error`; `assistant → tools` по tool calls; `assistant → analyze_result` без calls; результат `fetch_web_page` → `summarize → validate_summary → assistant`; `find_additional_sources`/ошибка инструмента → `assistant`.
- [ ] Проверить `verify_analysis`: `continue_search → assistant` только при разрешённом поиске; `revise_analysis → analyze_result` с замечаниями; `complete → validate_result`; `impact_unknown → END`. Не добавлять статическое исходящее ребро к узлу, использующему `Command.goto`.
- [ ] Проверить A7: после двух поисков без прогресса `assistant` не вызывает LLM; если `verify_analysis` вернул `continue_search`, использовать принудительный `END/impact_unknown`, без нового tool/LLM. Отдельно проверить, что новый источник позволяет продолжить поиск.
- [ ] Проверить A6: ни один расход не происходит при `iterations >= max_iterations`; сверхлимитные LLM retries/`revise_analysis`/коррекция не выполняются; `GraphRecursionError` перехватывает **внешняя** обёртка, не граф.
- [ ] Red → собрать маршруты, привязать инструменты с `parallel_tool_calls=False`, проверить `ToolNode Command(update=...)` и сохранение `sources` → Green; коммит `feat(analysis-news): assemble bounded LangGraph workflow`.

## Task 9. Публичный запуск, исключение `NewsNotFoundError` и логирование

**Files:** `agents/analysis_news/agent.py`; тесты `tests/analysis_news/test_runner.py` и `tests/analysis_news/test_public_result.py`.

**Interfaces:** `class NewsNotFoundError(LookupError)` с `news_id`; `async def run_news_analysis(...) -> NewsAnalysisResult` для **найденной** новости; существующая `def run_graph() -> None` без CLI-аргументов. Точную сигнатуру параметров `run_news_analysis` зафиксировать по уже имеющимся адаптерам при этапе 0; не вводить второй путь запуска.

- [ ] Red-тесты: отсутствие `news_id` после успешного чтения → `NewsNotFoundError`, без создания графа, lock и LLM; ошибка SQL чтения → **не** `NewsNotFoundError`; `screening` → `skipped` без LLM; занятая блокировка → `error`; повтор при `force_reanalysis=False` → `skipped`; принудительный повтор → проверенный `success`.
- [ ] Red-тесты: наружу выходят **только** допустимые поля `NewsAnalysisResult`; не выходят `messages, sources, raw_result, parsed_result, validation_errors, iterations, correction_used`; отсутствующий/невалидный `state["result"]` → `error`; `success` до `commit` запрещён; SQL conflict меняет итог на `skipped`; сбой commit → `error`.
- [ ] Проверить `GraphRecursionError`, отказ при потере lock, ошибки LLM, чистоту `reason` (без секретов/traceback), `logger.info` для нормального запуска и `logger.error` + ненулевой exit-код для `NewsNotFoundError`.
- [ ] Red → реализовать единую обёртку и ручную точку входа; `run_graph()` вызывает обёртку через `asyncio.run`, для `NewsNotFoundError` не придумывает `issuer_id` → Green.
- [ ] Коммит `feat(analysis-news): expose guarded public news runner`.

## Task 10. Сквозные тесты, регрессия, выпуск

**Files:** `tests/analysis_news/conftest.py`, `tests/analysis_news/test_end_to_end.py`, `tests/analysis_news/test_postgres_integration.py`; при необходимости файлы конфигурации pytest и документация запуска.

**Interfaces:** управляемые фейковые LLM и веб-транспорты; только тестовая БД PostgreSQL для тестов физического advisory lock и транзакций. Продакшен-доступ в тестах запрещён.

- [ ] Сквозной успех: новость → один/несколько источников → валидная суммаризация → анализ → проверка фактов → `validate_result` → commit в БД → плоский `success` с правильными `news_id/issuer_id`.
- [ ] Сквозной недостаток сведений: недоступен источник + нет обоснованной оценки → `impact_unknown`, **0** записей; технический сбой инструмента ≠ отметка «сомнительная»; успешный поиск без подтверждений ≠ опровержение новости.
- [ ] Сквозной отказ анализа: некорректный JSON дважды, конфликт идентификаторов, неверный `summary_category/summary_value`, неисправимая ошибка LLM, таймаут; убедиться в терминальном `error` и отсутствии записи.
- [ ] Сквозная конкуренция: два job на один `news_id`, освобождение lock при исключении/отмене, идентичное соединение для `UPSERT`; повторное выполнение без `force` не изменяет данные; `force` обновляет данные и `update_at` с сохранением `created_at`.
- [ ] Проверить `max_iterations=8`, `recursion_limit=128`, остановку A7, запрет SSRF через 3xx/смену DNS, кэш суммаризации, idempotency `news_id` и отсутствие утечки секретов в логах.
- [ ] Выполнить команды:
  - `python -m pytest -q tests/analysis_news` — все тесты агента, включая быстрые unit/fake.
  - `python -m pytest -q tests/analysis_news -m postgres` — реальные PostgreSQL-тесты при наличии **изолированного** тестового подключения и соответствующей маркировки; если среды нет, явно отметить `SKIPPED/не выполнялись`.
  - `python -m pytest -q` — регрессия затронутых модулей проекта.
- [ ] Применить SQL-миграцию сначала к **тестовой** БД, проверить ограничения `UNIQUE/FK/CHECK`; в боевой среде — только после отдельного разрешения. До миграции рабочий запуск не включать.
- [ ] Провести итоговое ревью: охват A1–A8, 10 узлов, 4 промпта, 2 инструмента, все терминальные статусы, отсутствие API/DDL-изменений вне спецификации. Зафиксировать фактические команды, количество PASS/FAIL/SKIP и ограничения; коммит `test(analysis-news): cover workflow and failure paths`.

## Критерии готовности

1. Все тесты, относящиеся к изменённым модулям, успешно проходят. Не утверждать это до реального `pytest`.
2. Ни одно выполнение с `status != "success"` не создаёт и не обновляет `news_analysis`; `success` возможен только после commit.
3. Все записи используют lock-соединение для того же `news_id`; конкурентный повтор безопасен.
4. Веб-инструмент не может обратиться к непубличному IP даже через DNS/редиректы; ограничения времени и размера реально исполняются.
5. А7 и А6 ограничивают циклы и расход ресурсов, не создавая непроверенный `success`.
6. Публичный результат точно соответствует `NewsAnalysisResult`, а отсутствующая новость вызывает `NewsNotFoundError` до графа.
7. Документация запуска и диагностические логи готовы, рабочая БД не изменена без отдельного согласования.

## Передача на реализацию

**Рекомендуемый способ:** `superpowers:subagent-driven-development` — отдельный исполнитель и отдельная проверка каждого этапа, затем сквозное ревью ветки. Сначала утвердить этот план, после чего выполнять задачи последовательно в отдельной рабочей ветке/worktree; каждый этап заканчивать своими тестами и коммитом. Реализация и миграции этим документом **не выполняются**.
