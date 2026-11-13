# TrainBot Station Widget Implementation Plan

> **СТАТУС: ОТМЕНЁН / НЕ ИСПОЛЬЗОВАТЬ ДЛЯ РЕАЛИЗАЦИИ (2026-11-13).** Владелец принял решение вернуться к старому режиму поиска станций через текстовый ввод в чате Telegram и прежние inline-кнопки. Все шаги ниже являются историческим планом Widget; **не запускать их в Codex и не продолжать разработку станционного Widget**. Отказ от Widget не отменяет календарный Widget.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Встроить в существующий TrainBot один Telegram HTML Widget выбора станции отправления/назначения при создании и редактировании подписки «Отслеживание», сохранив календарь и старый текстовый сценарий.

**Architecture:** Использовать единственный существующий `widget_query` middleware/Telegram Bot API адаптер, старые `StSubscr.DepName`/`DestName`, `prm_sub_otslej()`, поиск `get_expressCode_async()` → Celery → РЖД и `MemoryStorage`. При `search` сразу отвечать `pending`, затем доставлять первую четвёрку через `editMessageWidgetData(chat_data)`; `page` возвращает срез FSM через `answerWidgetQuery`. Для несовместимого клиента остаются старые сообщения «Введите станцию отправления/назначения» без новой кнопки.

**Tech Stack:** Python, aiogram 3 (фактическую версию определить локально), asyncio, Celery, pytest/имеющийся тестовый стек, Telegram Bot API Widgets 10.4, HTML/CSS/QuickJS.

**Spec:** [Утверждённая архитектура, разделы 8–9](./station-widget-architecture-review-2026-11-12.md); [согласованные UX-требования](./station-widget-2026-11-12.md).

**Instruction:** [TrainBot rules](../../../instructions/trainbot-telegram-bot-rules.md), [Telegram Widgets Skill](../../../.agents/skills/telegram-aiogram-widgets/SKILL.md). Перед работой сверить [официальный Bot API](https://core.telegram.org/bots/api) и [Widgets](https://core.telegram.org/bots/widgets).

**Статус плана:** предложен к исполнению в **локальном репозитории исходников TrainBot**, а не в репозитории Codex со спецификациями. Настоящий документ не означает, что код написан или тесты пройдены. **Изменение исходников — только после отдельного поручения пользователя.**

## Global Constraints

- Не создавать новый middleware, Dispatcher, FSM-state, БД/Redis/cache, справочник кодов городов, отдельный поиск РЖД или универсальный Widget-framework.
- Сохранить календарь и текущий путь `widget_query`, `send_widget`, `answer_widget_query`; расширять их только минимально.
- Один Widget обслуживает «Откуда» и «Куда», создание и редактирование подписки «Отслеживание». **Другие сценарии подписок не менять без доказанной необходимости.**
- Четыре пользовательские команды: `search:<текст>`, `page:<номер>`, `confirm:<индекс>`, `cancel`. Пятая служебная: `ready`. Никакой версии/токена в `confirm`.
- Результат РЖД: исходный `list[str]` строк `name_code`, серверное разделение **по последнему** `_`; весь список только в FSM. На клиенте по 4 имени без expressCode; `page * 4 + position` для глобального индекса.
- `ready` подтверждает открытие Widget; пока нет `ready`, старый текстовый ввод может взять приоритет. После `ready` текстовые сообщения и старые inline callback не должны обходить Widget.
- На поиск — примерно 10 секунд с различением «0 результатов» и «ошибка/таймаут»; прежняя текстовая функция поиска не должна менять поведение.
- На время поиска остальные действия выбора блокируются, **× остаётся активной**. Из-за ограничения одного незавершённого `TelegramWidget.request` серверный `cancel` не гарантирован в коротком окне `BUSY` до `ready/pending`; не скрывать этот факт.
- При `confirm` менять только нужные `DepName/DepCode` или `DestName/DestCode`; при **реальной смене кода** очистить `TrainNumber/TimeDepart`; при `cancel` не менять подписку; никогда не делать `state.clear()` при завершении Widget.
- Подтверждение старой выдачи только индексом имеет известный остаточный риск в сценарии двух устройств; **не расширять** контракт на своё усмотрение.
- Ответ `TelegramWidget.request` до 64 байт UTF-8; `answerWidgetQuery` и `chat_data` до 1024 байт UTF-8; HTML до 32768 байт и zlib level 9 до 4096 байт; запрет NUL. Ответить на каждый `widget_query` в пределах 15 секунд; учитывать 5 запросов / 5 секунд.
- Не коммитить токены, cookie, пассажирские данные, `.env`, дампы БД. Не объявлять E2E проверенным без фактического теста в Telegram.

## Review Focus

Особенно проверить **до сдачи**, поскольку одних happy-path тестов недостаточно:
1. Отмена × во время `ready`, `pending`, медленного Celery и сбоя `editMessageWidgetData`: FSM и подписка не изменяются, старый результат не восстанавливается (Task 4, 5, 6).
2. Повторный/устаревший `widget_query`, другой `message_id`, два открытых Widget, устаревший legacy callback: менять станцию нельзя (Task 2, 5).
3. `[]`, failure Celery, timeout, 5/10 результатов, кириллические строки на границе 64/1024 байт, пропавший `MemoryStorage` (Task 3, 4, 5).
4. Не поддерживающий Widget клиент или отсутствие `ready`: старый текстовый ввод доступен; подтверждённый `ready` исключает параллельный чат (Task 2, 5, 6).
5. Регрессия старого календаря, обычного выбора станции и сохранения/редактирования подписки; узкая мобильная ширина (Task 1, 5, 6).

---

## Карта файлов локального проекта

Пути ниже установлены **по предоставленным снимкам исходников**; перед изменением Codex обязан сверить их с **актуальным локальным рабочим деревом TrainBot**. Если они отличаются, указать реальные пути в отчёте и не менять архитектуру.

| Файл | Назначение | Действие |
| --- | --- | --- |
| `bot.py` | Единый polling/перехват `widget_query` | Минимально подключить разбор станции, не менять `allowed_updates`, если он уже содержит `widget_query`. |
| `widgets/middleware.py` | `CalendarWidgetMiddleware`, существующая точка входа | Переиспользовать; при необходимости минимально адаптировать один callback/маршрутизацию. |
| `widgets/telegram_api.py` | `send_widget`, `answer_widget_query` через Bot session | Добавить только `editMessageWidgetData`, не отдельный API клиент. |
| `widgets/stations/__init__.py` | пакет Widget (если принята структура `widgets/calendar/`) | Создать только если нужно для Python import. |
| `widgets/stations/render.py` | Сборка одного HTML из шаблонов, параметров текущей станции и направления | Создать по образцу `widgets/calendar/render.py`. |
| `widgets/stations/stations.html` | Разметка | Создать. |
| `widgets/stations/stations.css` | Компактные стили | Создать. |
| `widgets/stations/stations.js` | Алфавит, список, пагинация, ready/search/page/confirm/cancel | Создать. |
| `handlers/subscrib.py` | FSM подписок, выбор станций и меню | Точечно добавить открытие и handler Widget, повторно использовать меню/поиск/черновик. |
| `core/util_bot.py` | `get_expressCode_async` | Минимальная совместимая обработка timeout/failure **только для Widget**, без изменения default поведения старого вызова. |
| `tests/widgets/test_station_render.py`, `tests/widgets/test_station_api.py`, `tests/handlers/test_station_widget.py`, `tests/handlers/test_station_widget_flow.py` | Проверки | Создать/адаптировать к имеющейся структуре тестов. |
| `tests/test_calendar_widget.py` | Регрессия календаря (если уже существует) | Использовать, а не создавать дубликат. |

Если исходники локально разделены иначе — не навязывать новый модуль `handlers/stations.py` или рефакторинг `subscrib.py` без необходимости.

## Task 1: Baseline, реальные контракты и тестовая инфраструктура

**Files:** Read `bot.py`, `handlers/subscrib.py`, `widgets/middleware.py`, `widgets/telegram_api.py`, `widgets/calendar/*`, `core/util_bot.py`, `tasks.py`, `core/rzd_track.py`; при необходимости Create `tests/widgets/test_station_api.py`.

**Interfaces:**
- Consumes: утверждённая архитектура 8–9.
- Produces: короткий локальный перечень проверенных сигнатур, версий зависимостей и baseline-тестов. `dp.update.outer_middleware(CalendarWidgetMiddleware(subscrib.handle_calendar_query))` — по снимку, не обещание нынешней версии.

- [ ] **Step 1:** Зафиксировать `git status`, текущую ветку, `python -m pip show aiogram`/локальный lockfile, зависимости тестов; использовать отдельную рабочую ветку/worktree, не смешивать посторонние изменения.
- [ ] **Step 2:** Установить реальные подписи `prm_sub_otslej(None, state, bot=..., chat_id=...)`, `handle_calendar_query(raw, bot, dp)`, `get_expressCode_async(city)`, `send_widget` и форматы исходного `list[str]`. Не использовать название функции/типа из плана, если такого нет в рабочем коде.
- [ ] **Step 3:** Запустить **существующие** тесты календаря и подписки выбранной командой проекта (если есть). Отметить baseline PASS/FAIL и причины; старые падения не маскировать.
- [ ] **Step 4:** Убедиться, что новый Widget подключается к **одному** существующему маршруту, `widget_query` присутствует в `allowed_updates`; проверить возможность native API в установленном aiogram прежде, чем добавлять raw `TelegramMethod`.
- [ ] **Step 5:** Commit только если добавлены тесты/настройки; иначе зафиксировать в отчёте отсутствие изменений. Ничего не коммитить в Codex-specs вместо локального TrainBot.

## Task 2: Транспорт Widget и изоляция календаря

**Files:** Modify `widgets/telegram_api.py`, `bot.py` и/или `widgets/middleware.py` **минимально**; Test `tests/widgets/test_station_api.py` и текущие тесты календаря.

**Interfaces:**
- Consumes: существующий `send_widget(bot, chat_id, html, reply_markup)` и `answer_widget_query(bot, query_id, data)`.
- Produces: `edit_message_widget_data(bot: Bot, *, chat_id: int, message_id: int, chat_data: str) -> None` (если нет нативного аналога в установленном aiogram); существующий маршрут `widget_query` различает календарь и станции по FSM + message ID.

- [ ] **Step 1:** Написать падающие тесты `test_edit_data_calls_bot_api_with_chat_and_message`, `test_edit_data_rejects_1025_utf8_bytes`, `test_calendar_query_still_routes_to_calendar`, `test_station_cancel_not_routed_to_calendar`, `test_unknown_widget_query_answered_once`.
- [ ] **Step 2:** Run `python -m pytest tests/widgets/test_station_api.py -q`; ожидается FAIL до реализации.
- [ ] **Step 3:** Добавить минимальную поддержку `editMessageWidgetData` с пределом 1024 UTF-8; разделить выбор обработчика в **уже существующей** входной точке на основании фактического активного Widget/FSM. `cancel` без привязки к сообщению не использовать как разделитель. Все запросы получают максимум один ответ.
- [ ] **Step 4:** Запустить новые тесты и baseline календаря; ожидается PASS без изменений календарного JS/HTML.
- [ ] **Step 5:** Commit `feat(trainbot): reuse widget transport for stations` с тестами.

## Task 3: HTML/QuickJS и локальная сборка виджета станций

**Files:** Create `widgets/stations/render.py`, `stations.html`, `stations.css`, `stations.js`, `__init__.py` при необходимости; Test `tests/widgets/test_station_render.py` + JS-контракт (тестовый способ из текущего проекта или статический smoke).

**Interfaces:**
- Consumes: `direction` (origin/destination) и текущее отображаемое имя станции; статус `ready`, `pending`, `ok`, `error` из Widget API.
- Produces: `render_station_widget(*, direction: str, selected_name: str | None) -> str` (предлагаемый интерфейс для `subscrib.py`); сообщения `ready`, `search:<текст>`, `page:<номер>`, `confirm:<индекс>`, `cancel`.

- [ ] **Step 1:** Написать падающие `test_render_origin_and_destination`, `test_render_shows_previous_station_or_not_selected`, `test_html_within_widget_limits`, `test_config_data_cannot_inject_script` и контрактные JS-тесты `test_search_only_on_button_press`, `test_busy_disables_all_except_cancel`, `test_results_limit_four`, `test_confirm_uses_global_index`.
- [ ] **Step 2:** Run `python -m pytest tests/widgets/test_station_render.py -q`; ожидается FAIL до создания renderer.
- [ ] **Step 3:** Собрать самодостаточный HTML **по образцу** `render_calendar`, инъекция JSON безопасна для JS/HTML. Первый экран: 4 города + «Другие станции», исходная станция; русский алфавит, подсветка, 4 результата, счётчик, ‹/›, «Подтвердить», ×. Популярный город запускает обычный `search`, не выбирает первый результат автоматически.
- [ ] **Step 4:** `ready` отправлять при первом появлении поддерживаемого Widget; `search` ждёт быстрый `pending`, затем получает ответ через `chatDataChanged`; `page` читает `JSON.parse(answer.result)`. Во время поиска остальные действия заблокированы, × сохраняет возможность касания. При новом поиске выделение сбросить; при `cancel` игнорировать поздние данные. Не использовать неподдерживаемые браузерные API/fetch.
- [ ] **Step 5:** Запустить тесты, проверить `len(html.encode('utf-8'))`, `len(zlib.compress(...,9))`, все запросы <=64 UTF-8 байт, а в худшем варианте 4 реальных имени помещаются в 1024 байта; ожидается PASS.
- [ ] **Step 6:** Commit `feat(trainbot): add station widget UI`.

## Task 4: Поиск РЖД, FSM-результаты и фоновая доставка

**Files:** Modify `core/util_bot.py` **только по необходимости**, `handlers/subscrib.py`; Test `tests/handlers/test_station_widget.py`.

**Interfaces:**
- Consumes: существующая `get_expressCode_async(city)` и Celery `ts_req_expressCode` с исходным `list[str]`.
- Produces: поиск, который для Widget выдаёт `pending` **до ожидания РЖД**, затем сохраняет полный список в FSM и доставляет первую страницу через `edit_message_widget_data`. Признак `station_search_busy` в **обычных данных FSM** допустим; дополнительных FSM-state/worker/хранилищ нет.

- [ ] **Step 1:** Написать падающие тесты: `test_search_ack_pending_without_waiting_for_celery`, `test_success_stores_raw_list_and_emits_first_four`, `test_page_uses_cached_fsm_without_celery`, `test_empty_results_not_error`, `test_celery_failure_vs_zero_results`, `test_timeout_at_ten_seconds_widget_only`, `test_cancel_during_search_prevents_late_write`, `test_new_widget_prevents_old_delivery`.
- [ ] **Step 2:** Run `python -m pytest tests/handlers/test_station_widget.py -q`; ожидается FAIL.
- [ ] **Step 3:** Реализовать быстрый `answerWidgetQuery({'status':'pending'})`, затем `asyncio`-задачу **в процессе бота**, вызывающую существующий поиск и ограниченную `asyncio.wait_for(..., 10)`. Для отличия Celery failure от `[]` расширять старую функцию только обратносуместимым opt-in интерфейсом, **не менять её обычный вызов и возвращаемое значение**. Не держать FSM lock на протяжении Celery. Учитывать, что отмена ожидания не прекращает Celery task.
- [ ] **Step 4:** После получения результата и **непосредственно перед** отправкой `chat_data` сверить владельца, `chat_id`, `message_id`, направление, активность Widget и незавершённость/неотменённость конкретной операции. Список `name_code` сохраняется без преобразований; клиент получает только имена и `total`. На ошибке нельзя подтверждать старый список.
- [ ] **Step 5:** Run тесты Task 4 и Task 2; ожидается PASS, поздние `search` не изменяют FSM. Ошибка Bot API обновления данных должна вести к безопасному состоянию без подтверждения устаревших результатов.
- [ ] **Step 6:** Commit `feat(trainbot): deliver station search results through widget data`.

## Task 5: Выбор, отмена, legacy fallback и меню подписки

**Files:** Modify `handlers/subscrib.py`; Test `tests/handlers/test_station_widget_flow.py` и существующие тесты подписок/календаря.

**Interfaces:**
- Consumes: `render_station_widget`, один `widget_query`, `stations` из FSM, текущие `StSubscr.DepName/DestName`, `prm_sub_otslej(None, state, bot=bot, chat_id=chat_id)`.
- Produces: точки открытия Widget для `DepName` и `DestName`, `ready`, `confirm:<индекс>`, `cancel` и прежний ввод при недоступности Widget.

- [ ] **Step 1:** Написать падающие тесты `test_origin_and_destination_use_same_widget`, `test_ready_marks_active_widget`, `test_text_before_ready_uses_legacy_flow`, `test_text_after_ready_does_not_change_station`, `test_stale_legacy_inline_callback_ignored`, `test_confirm_only_current_index_and_message`, `test_change_code_clears_train_and_time`, `test_same_code_keeps_train_and_time`, `test_cancel_keeps_subscription_and_returns_menu`, `test_send_widget_failure_uses_original_prompt`, `test_memory_storage_restart_rejects_old_widget`.
- [ ] **Step 2:** Run `python -m pytest tests/handlers/test_station_widget_flow.py -q`; ожидается FAIL.
- [ ] **Step 3:** В существующей ветке `select_sub_otsl` для `DepName`/`DestName` открывать Widget; на ошибке отправки — исходные «Введите станцию отправления»/«Введите станцию назначения» и старые текстовые хендлеры **без новой кнопки**. Поставить `await_ready`, после валидного `ready` — `active`; поздний `ready` устаревшего виджета игнорировать.
- [ ] **Step 4:** Проверить сервером каждый `confirm:<индекс>`: автор, приватный чат, текущее сообщение, FSM-состояние, не выполняется поиск, границы индекса, валидная строка с последним `_` и непустым expressCode. Применить **только** пару `DepName/DepCode` или `DestName/DestCode`; `TrainNumber`/`TimeDepart` очищать, только если код изменился. **Не добавлять версию в `confirm`**.
- [ ] **Step 5:** В `cancel` удалить только временные station-ключи, а не весь FSM; завершить состояние `set_state(None)`, вернуть прежнее `prm_sub_otslej()`. Заблокировать применение старых текстовых и inline callback результатов, если `ready` подтвердил активный Widget. Важное отличие: при `await_ready` текстовый сценарий имеет приоритет и выключает Widget.
- [ ] **Step 6:** Run тесты Task 5, старого выбора станции и календаря; ожидается PASS. Не касаться бизнес-сохранения БД.
- [ ] **Step 7:** Commit `feat(trainbot): integrate station widget into subscription FSM`.

## Task 6: Сквозная регрессия и ручная проверка в Telegram

**Files:** Existing tests; при необходимости Create `tests/handlers/test_station_widget_integration.py`; описание результатов — в отчёте/PR TrainBot, **без секретов**.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: воспроизводимые результаты автоматических тестов, реальный Telegram smoke, список ограничений и итоговый diff.

- [ ] **Step 1:** Добавить тесты `test_origin_edit_preserves_destination`, `test_destination_edit_preserves_origin`, `test_create_and_edit_subscription_do_not_save_database_early`, `test_no_duplicate_widget_query_answer`, `test_legacy_station_callback_rejected_while_active`, `test_search_queries_respect_utf8_bounds`. Выполнить RED, затем минимальную правку при провале, затем GREEN.
- [ ] **Step 2:** Run `python -m pytest -q` (либо документированную существующую команду TrainBot), затем текущие проверки style/lint проекта. Записать числа PASS/FAIL, ошибки, список пропущенных тестов; **не заявлять проверенным при FAIL**.
- [ ] **Step 3:** Проверить руками в Telegram на **поддерживаемом клиенте**: отправление/назначение, 4 популярных города, алфавит, 0/1/4/5/10 станций, переход страниц, подтверждение и возврат меню, отмена × при активном поиске, `ready`, таймаут, `BUSY`, `RATE_LIMITED`, слабая сеть и узкий экран. При недоступности реального Telegram **явно отметить NOT TESTED**, а не PASS.
- [ ] **Step 4:** Проверить fallback: ошибка `sendWidget`, текст до `ready`, обычный поиск и inline-выбор; после `ready` — отсутствие обхода через чат или старые inline-кнопки. Если невозможно получить неподдерживаемый клиент, отметить сценарий NOT TESTED.
- [ ] **Step 5:** Проверить `git diff` на отсутствие изменений `widgets/calendar/*`, новых storage, изменения платежей/броней, secrets, лишних библиотек. Сформировать короткий отчёт: изменённые файлы, тесты, незакрытые риски и ссылки на коммиты.
- [ ] **Step 6:** Commit только оставшихся проверенных тестов/исправлений. **Не выполнять merge/deploy в production без отдельного согласования**.

## Self-review / приёмка плана

- UX: первый экран, 4 города, русский алфавит, 4 на странице, ‹/›, выбор/подтверждение, × и ошибки — Task 3.
- Транспорт: `ready`, `pending`, `editMessageWidgetData/chatDataChanged`, `page`, общий middleware и существующий адаптер — Tasks 2–4.
- FSM: `Dep/Dest`, `TrainNumber/TimeDepart`, `cancel`, меню, устаревшие callbacks, старый ввод — Task 5.
- Интеграция, границы Telegram, перегрузки/сеть и календарная регрессия — Tasks 1, 4, 6.
- Принятые риски: окно `BUSY`, индекс без версии при двух устройствах и отсутствие стопроцентного детектора несовместимого клиента — **не скрывать в отчёте**.

**Рекомендуемый порядок:** отдельная ветка локального TrainBot → Task 1 (baseline) → Tasks 2–5 по TDD и отдельным небольшим коммитам → Task 6 (проверка, отчёт, запрос на merge). Если локальный код/установленный aiogram существенно отличается от приложенного снимка, **остановиться перед изменением архитектуры**, документировать различия и согласовать значимые отклонения с владельцем.

## Закрытие инициативы — 2026-11-13

**Решение владельца:** «Принято решение вернуться к старому режиму поиска станции. Данный диалог закрываем с соответствующей пометкой в документации» (смысл сообщения, 2026-11-13).

**Итоговое целевое поведение TrainBot:**
- При выборе **станции отправления или назначения** бот предлагает привычный ввод текста в чате («Введите станцию отправления» / «Введите станцию назначения»).
- Текст обрабатывается **ранее существовавшей функцией поиска РЖД**, станция выбирается через **прежние inline-кнопки** и сохраняется прежней логикой FSM/подписки.
- **Новый станционный Telegram Widget больше не используется** в целевом сценарии. Прекратить дальнейшие работы над его поиском, интерфейсом, алфавитом, `ready`, `chatDataChanged` и новой пагинацией.
- **Календарный Widget сохраняется**; отказ от выбора станции через Widget не распространяется на другие Widgets и их общий транспорт.
- Все ранние решения, документы и план оставлены как **архив проектирования**; утверждение архитектуры от 2026-11-12 **отозвано последующим решением** владельца. Исполнение ранее созданного плана для Codex прекращено.

**Разграничение документации и кода:** настоящая запись **не меняет и не откатывает рабочий код TrainBot**. По материалам обсуждения станционный Widget уже внедрялся; фактический возврат старого режима в локальном репозитории/развёртывании следует выполнить **отдельным поручением и проверкой**, если он ещё не выполнен. Не утверждать, что откат реализован или протестирован.

**Статус обсуждения:** закрыто; дальнейших вопросов и согласований по этому Widget в данной инициативе нет.
