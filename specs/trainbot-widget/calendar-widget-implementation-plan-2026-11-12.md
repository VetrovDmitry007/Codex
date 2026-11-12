# TrainBot Calendar Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить выбор даты календарём при создании и редактировании «Отслеживание», сохранив существующую FSM, меню, выбор поезда и сохранение подписки.

**Architecture:** Универсальный календарь собирается стандартным Python в самодостаточный HTML. Фиксированный адаптер Bot API использует существующий Bot/session; внешний middleware передаёт widget_query в обработчик подписки. Widget и ручной ввод используют одну функцию применения даты; asyncio.Lock на пользователя защищает проверку и погашение активного календаря.

**Tech Stack:** Python 3.11 (текущий Dockerfile), aiogram>=3,<4, существующие aiohttp/MemoryStorage, стандартные pathlib/json/zlib/datetime/zoneinfo/unittest. Новые зависимости не требуются.

**Spec:** [утверждённые требования](https://github.com/VetrovDmitry007/Codex/blob/main/specs/trainbot-widget/calendar-widget-2026-11-12.md), blob `994595e44247cc5c185e90aeeee32f570e394777`; [утверждённая архитектура](https://github.com/VetrovDmitry007/Codex/blob/main/specs/trainbot-widget/calendar-widget-architecture-2026-11-12.md), blob `6fdefec74e3e5c9303a93daa317fc29e1ba85226`. Исполнитель читает оба документа, включая последующие согласованные разделы 3.1–3.12: оставшиеся заголовки «не утверждено» и старые checkbox не отменяют итогового утверждения.

## Global Constraints

- «Первый этап — создание и редактирование подписки „Отслеживание“». Другие сценарии не изменять.
- «сегодня и следующие 90 дней включительно»; `Europe/Moscow`; значение `dt_depart` — `YYYY-MM-DD`, без времени.
- `widgets/calendar/config.py`, `calendar.html`, `calendar.css`, `calendar.js`; никаких Jinja2, сборщиков, новых зависимостей и runtime-LLM.
- Запросы: `date:YYYY-MM-DD`, `cancel`. Ответы: `{"status":"ok"}`, `{"status":"error","message":"..."}` через JSON-сериализацию.
- Кнопка «✏️ Ввести дату вручную» — обычная inline-кнопка под Widget.
- Не менять Router, состояния FSM, storage, схему БД, процесс сохранения, тарифы и бронирование. Не обновлять aiogram специально ради Widgets.
- Использовать существующие Bot/session/proxy, один polling, прежние allowed_updates плюс `widget_query`.
- При ошибке отправки/сборки — ручной ввод без повтора sendWidget. При неверном ручном вводе — прежний выход из состояния и меню.
- Этот документ — план, не разрешение исполнять его. Все команды и фрагменты ниже предназначены для отдельно согласованного этапа реализации.

## Review Focus

1. Почти одновременные подтверждения, отмена и ручной ввод: применить только первое актуальное действие, сохранить остальные поля (Task 4/5).
2. Сохранённая дата из MySQL как date, а не str: подтверждение того же дня не сбрасывает поезд (Task 1/3).
3. Дата невозможна или сообщение не текстовое: ошибка без исключения и без изменения подписки (Task 1/4).
4. Таймаут ответа/удаления после применения: не откатывать дату, не активировать старый календарь, не дублировать меню (Task 4/5).
5. Старый Telegram-клиент и узкий экран: доступен ручной ввод, кнопки читаемы, календарь не выходит за карточку (Task 6).

---

## Статус исследования и размещение

Исследование выполнено 2026-11-12. Runtime-код найден **локально в Z:/Python/Net/RZD_COM**, ветка `dev`, HEAD `6456ad3cf8a09dec0e2418698fdeb6f041d3fa9d`, а не предположен в репозитории Codex. Чужие untracked-файлы присутствуют; их не включать в будущие коммиты. Перед реализацией повторно проверить HEAD/состояние затрагиваемых файлов.

Документы и Widgets Skill прочитаны через GitHub в `VetrovDmitry007/Codex/main`. План размещается в `specs/trainbot-widget/` согласно §5 основной TrainBot-инструкции и утверждённой архитектуре; writing-plans разрешает переопределять default `docs/superpowers/plans/` пользовательским соглашением. Локальный issue tracker — `.scratch/calendar-widget/`, согласно `docs/agents/issue-tracker.md`; его spec — рабочая сводка утверждённых источников, не новая функциональная спецификация.

По позднему поручению использованы также to-spec/to-tickets. Пользователь согласовал границу тестирования и четыре тикета: 01 — общая дата/ручной ввод; 02 — подтверждение календарём по всем слоям; 03 — отмена/fallback/сбои; 04 — регрессии/клиенты. Зависимости: 01 → 02 → 03 → 04. Это согласование документации не разрешает реализацию.

### Подтверждённые точки интеграции

| Исходник | Наблюдение и использование |
| --- | --- |
| `bot.py:35–73` | Dispatcher(MemoryStorage), существующие include_routers, Bot с условным AiohttpSession(proxy), polling и finally session.close. Добавить только регистрацию middleware и allowed_updates. |
| `handlers/subscrib.py:20–37,137–145` | StSubscr.dt_depart и создание через state.clear(); сохранить. |
| `handlers/subscrib.py:172–225` | prm_sub_otslej(message, state), построение клавиатуры; вызывает delete_try(message), иногда sleep(2)/del_last_msg. WidgetQuery не содержит Message: потребуется минимально расширить способ отправки меню, без фиктивных Message. |
| `handlers/subscrib.py:229–289` | select_sub_otsl/ветка dt_depart открывает ввод; @router.message(StSubscr.dt_depart) проверяет и записывает дату. Это две основные изменяемые точки. |
| `handlers/subscrib.py:352–397,571–582` | set_NumTrain использует дату/станции из FSM; select_NumTrain сохраняет TrainNumber/TimeDepart. Не менять, проверить регрессионно. |
| `handlers/subscrib.py:585–637,746–799` | before_save_otslej требует номер; ch_subs загружает dc_prm; save_otslej выбирает update/insert по id_sub и очищает FSM. Не переписывать. |
| `core/util_bot.py:227–248,582–610` | ch_dt_depart проверяет формат и дату относительно локального времени, не ограничивает +90; get_prm_sub переносит id_sub, dt_dep, tm_dep. Общую util не менять: архитектура сохраняет ручную проверку. |
| `handlers/subscrib.py:987–1001` | del_last_msg/delete_try проглатывают ошибки удаления. Для нового Widget использовать удаление по bot/chat_id/message_id с безопасным логом класса ошибки; не переделывать старые helper. |

`requirements.txt` и `devop/Dockerfile_client` задают `aiogram>=3,<4`, точный релиз в зависимостях не зафиксирован. Пользователь указал среду `D:/Virtual_Env_2/RZD_COM_311/Scripts/python.exe`; в ней проверены **Python 3.11.6, aiogram 3.22.0, Pydantic 2.11.10**. Это версия указанной среды, не доказательство идентичности deployment. В `test/` обнаружены диагностические скрипты с реальными Telegram/БД/внешними вызовами; они не запускались. Готовой офлайн-системы unittest/pytest для этого сценария не найдено. GLOSSARY.md и docs/adr отсутствуют.

Офлайн-проба на этой среде (без файлов приложения/сети) успешно подтвердила: неизвестный widget_query доступен в model_extra и перехватывается outer middleware при feed_update, включая повторную привязку Update к Bot; get_context синхронно возвращает FSMContext; Bot.send_widget отсутствует; собственный TelegramMethod сериализуется через существующий AiohttpSession.build_form_data, а его синтетический API-ответ разбирается как Message с message_id=101, несмотря на неизвестное поле widget. Ответ answerWidgetQuery, полный polling-путь и поведение клиентов этой пробой не проверялись.

Первый импорт aiogram выявил унаследованную переменную SSLKEYLOGFILE, заставлявшую ssl открыть недоступный файл. Проба повторена успешно после удаления этой переменной **только из окружения проверочного процесса**, без изменения пользовательских настроек. При исполнении ниже в отдельной PowerShell-сессии задать `$trainbotPython = 'D:/Virtual_Env_2/RZD_COM_311/Scripts/python.exe'`; слово `python` во всех командах означает вызов **именно этого интерпретатора** (`& $trainbotPython ...`). Если SSLKEYLOGFILE всё ещё задана, убрать её только из тестового процесса/сессии. Не использовать системный Python и не устанавливать зависимости.

### Первоисточники и технические ограничения

Сверены [Telegram Widgets](https://core.telegram.org/bots/widgets), [sendWidget](https://core.telegram.org/bots/api#sendwidget), [WidgetQuery](https://core.telegram.org/bots/api#widgetquery), [answerWidgetQuery](https://core.telegram.org/bots/api#answerwidgetquery), [changelog](https://core.telegram.org/bots/api-changelog) и [aiogram](https://docs.aiogram.dev/en/latest/). Bot API 10.4 от 2026-11-09 содержит требуемые методы; явного противоречия выбранной архитектуре не найдено.

sendWidget возвращает Message, поддерживает html/allow_queries/reply_markup; WidgetQuery содержит id/from/chat/message_id/type/data. Принимаем type.type == `data` и собственное сообщение в private chat. Ответ Widget получает в строковом `result`, которую JS разбирает как JSON; answerWidgetQuery сам данные Widget не редактирует. HTML ≤32768 UTF-8 байт и ≤4096 после zlib level 9, без NUL; request 1–64 байта, answer.data ≤1024 байт. Не использовать shared/inline/network/input.

В [исходнике Dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html) feed_update оборачивает маршрутизацию outer middleware; [TelegramObject](https://github.com/aiogram/aiogram/blob/dev-3.x/aiogram/types/base.py) сохраняет extra, а [TelegramMethod](https://github.com/aiogram/aiogram/blob/dev-3.x/aiogram/methods/base.py) позволяет описать собственные методы. Обоснование по документации дополнено успешной ограниченной пробой на aiogram 3.22.0 выше. Перед интеграцией всё равно обязательны воспроизводимые тесты Task 2, включая passthrough/answer/polling; никаких условных native/adapter веток.

Два обнаруженных нюанса требуют минимальной локальной адаптации, не смены архитектуры: меню должно отправляться по bot/chat_id без создания фиктивного Message; существующий ch_dt_depart бросает ValueError для `2026-02-30` и TypeError для None — перехватить их только в ручном обработчике как неверный ввод. Сохранить его существующие правила допустимости: общий helper даты меняет данные, а не унифицирует валидаторы. Не вводить ограничение +90 для ручного пути без нового решения пользователя.

## Файлы и интерфейсы до декомпозиции

Все пути ниже — относительно runtime-корня TrainBot, не репозитория документов Codex.

| Файл | Назначение |
| --- | --- |
| Modify `handlers/subscrib.py` | Общая дата, открытие календаря, обработка запроса, ручной ввод, расширение отправки прежнего меню. Бизнес-логика остаётся здесь. |
| Modify `bot.py` | Подключение middleware и дополнение allowed_updates после регистрации существующих router. |
| Create `widgets/__init__.py`, `widgets/calendar/__init__.py` | Пакеты без побочных эффектов. |
| Create `widgets/telegram_api.py` | Два собственных TelegramMethod и обёртки через Bot. |
| Create `widgets/middleware.py` | Только извлечение widget_query и делегирование callback; passthrough остальных Update. |
| Create `widgets/calendar/config.py` | `DAYS_AHEAD = 90`, `TIMEZONE = "Europe/Moscow"`. |
| Create `widgets/calendar/render.py` | Московская дата/диапазон, строгая валидация ISO, подготовка начального выбора, сборка/ограничения HTML. |
| Create `widgets/calendar/calendar.html`, `.css`, `.js` | Карточка и локальная логика календаря; без полей подписки. |
| Create `test/calendar_widget/__init__.py`, `support.py`, `test_manual.py`, `test_transport.py`, `test_render.py`, `test_flow.py`, `test_fallback.py`, `test_regression.py` | Офлайн unittest; реальный Dispatcher/FSM, подменённые внешние границы. |
| Create `docs/testing/calendar-widget.md` | Воспроизводимые команды, версии среды и незаполненная до проверки матрица клиентов. |

Не создавать таблицы, migrations, новый storage, callback Router, отдельный polling, универсальный FSM-manager, очередь, rate limiter или retry-слой. В новом модуле middleware нет импорта handlers; callback передаётся при подключении из bot.py. subscrib.py импортирует только widgets, поэтому циклических импортов bot/handlers/widgets нет.

Служебные поля FSM: `calendar_message_id: int | None`, `calendar_user_id: int | None`, `calendar_chat_id: int | None`. Очистка — удалить только эти ключи через get_data/set_data внутри lock; не state.clear(). Не хранить Message/Lock в FSM и не передавать эти поля в БД. last_msg принадлежит существующему ручному пути.

Основная граница тестирования согласована: `Dispatcher.feed_update()` с настоящим `Update.model_validate(..., context={"bot": bot})`, MemoryStorage и fake Bot BaseSession. Проверяем видимые ответы/исходящие Telegram-методы и FSM, не приватные вызовы helper. Чистую сборку HTML и формирование API дополнительно проверяем узкими тестами там, где они дают более точный диагноз. JS/UI проверяем локально и затем в Telegram, не выдаём grep HTML за исполняемый UI-тест.

## Task 1: Общая дата и сохранение ручного сценария (тикет 01)

**Files:** Modify `handlers/subscrib.py:275–289`; Create `test/calendar_widget/__init__.py`, `support.py`, `test_manual.py`.

**Interfaces:**
- Consumes: FSMContext, util_bot.ch_dt_depart(str)->bool, существующий Message и prm_sub_otslej.
- Produces: `async apply_departure_date(state: FSMContext, new_date: str) -> None` в subscrib.py. Вход уже проверен; сравнить ISO нового дня со старым str/date/datetime, при изменении одним update_data записать dt_depart и пустые строки TrainNumber/TimeDepart. При совпадении записать каноническую строку dt_depart, сохранив поезд/время. Не менять state, меню, last_msg и остальные поля.
- Test support: `Harness` предоставляет async `feed_message(text: str | None) -> None`, `seed(data: dict, state: str | None) -> None`, `data() -> dict`, `state: FSMContext`, `outgoing: list[TelegramMethod]`, `menu_count: int` (вычисляется по исходящему прежнему меню); это только тестовый API. Использовать unittest.IsolatedAsyncioTestCase, AsyncMock и fake BaseSession, без новых библиотек. Перед импортом реальных handlers изолировать config, DB и тяжёлые соседние сервисы через patch.dict(sys.modules); не читать секреты и не выполнять их инициализацию. Сами subscrib, Router/FSM/Update остаются настоящими.

- [ ] **Step 1: Написать тесты внешнего поведения ручного ввода.** Сфиксировать время валидатора на 2026-11-12; сохранить существующий вызов util_bot и лог успешного ввода через fake DB.

```python
async def test_manual_changed_date(self):
    await self.h.seed({"dt_depart": "2026-11-20", "TrainNumber": "030У",
                       "TimeDepart": "10:00", "id_sub": 7, "DepCode": "2000000"}, "StSubscr:dt_depart")
    await self.h.feed_message("2026-11-21")
    data = await self.h.data()
    self.assertEqual((data["dt_depart"], data["TrainNumber"], data["TimeDepart"]),
                     ("2026-11-21", "", ""))
    self.assertEqual((data["id_sub"], data["DepCode"]), (7, "2000000"))
    self.assertIsNone(await self.h.state.get_state())
    self.assertEqual(self.h.menu_count, 1)
```

В отдельных test_manual_same_date_keeps_train/date_object_same_day, test_manual_invalid_keeps_draft и test_manual_nontext_keeps_draft проверить соответственно сохранение поезда; ввод `bad`, `2026-02-30`, None → предупреждение, state None, ровно одно меню, прежние дата/поезд/время. test_manual_existing_validator_policy: дата дальше 90 дней не получает нового Widget-ограничения.

- [ ] **Step 2: Запустить RED.** В подготовленной среде TrainBot из корня: `python -m unittest discover -s test/calendar_widget -p test_manual.py -v`. Ожидать assertion failure на отсутствии сброса поезда или исключениях валидации, не ошибку внешнего подключения. Если нет доступной среды aiogram — остановить исполнение до её предоставления, ничего не устанавливать по этому плану.
- [ ] **Step 3: Реализовать apply_departure_date по Interfaces.** Без импорта календаря в общий util_bot; нормализация старого date/datetime выполняется перед сравнением, новое значение уже ISO.
- [ ] **Step 4: Заменить запись dt_depart в существующем ручном обработчике вызовом helper.** util_bot.ch_dt_depart оставить; TypeError/ValueError трактовать как False. Сохранить существующие тексты, логирование, set_state(None) и возврат в меню. Не переименовывать все одноимённые legacy-функции.
- [ ] **Step 5: Запустить GREEN.** Та же команда; все тесты PASS/OK, без сетевых запросов.
- [ ] **Step 6: Коммит.** `git add handlers/subscrib.py test/calendar_widget`; `git commit -m "refactor: share tracking departure date application"`.

## Task 2: Проверенный путь Widget API и сырого Update (часть тикета 02)

**Files:** Create `widgets/__init__.py`, `widgets/telegram_api.py`, `widgets/middleware.py`, `test/calendar_widget/test_transport.py`; Modify test support.

**Interfaces:**
- Consumes: существующие Bot, Dispatcher, BaseSession, TelegramMethod, Message, InlineKeyboardMarkup.
- Produces в telegram_api.py: собственные `SendWidget(TelegramMethod[Message])` (`__api_method__="sendWidget"`, `__returning__=Message`, поля chat_id:int/html:str/allow_queries:bool=True/reply_markup:InlineKeyboardMarkup); `AnswerWidgetQuery(TelegramMethod[bool])` (`__api_method__="answerWidgetQuery"`, `__returning__=bool`, widget_query_id:str/data:str).
- Produces: `async send_widget(bot: Bot, *, chat_id: int, html: str, reply_markup: InlineKeyboardMarkup) -> Message`; `async answer_widget_query(bot: Bot, *, query_id: str, data: str) -> None`. Используют `await bot(custom_method, request_timeout=5)`; не создают сессий и не форматируют URL с токеном. data JSON формирует вызывающая сторона, адаптер проверяет ≤1024 UTF-8 байт.
- Produces в middleware.py: `CalendarWidgetMiddleware(on_query: Callable[[dict[str, Any], Bot, Dispatcher], Awaitable[None]])`; async __call__ получает raw из `(event.model_extra or {}).get("widget_query")`. Для наличия ключа обрабатывает событие и возвращает None без дальнейшего router; для остальных — `await handler(event, data)`. Передаёт bot/dispatcher из data, не рассчитывает на автоматически заполненный state для неизвестного события.

- [ ] **Step 1: Зафиксировать безопасно только версии runtime.** В используемой TrainBot среде выполнить `python -c "import sys, aiogram, pydantic; print(sys.version.split()[0], aiogram.__version__, pydantic.__version__)"`; записать в docs/testing на Task 6. Не запускать bot.main/polling. Это compatibility gate, не обновление зависимостей.
- [ ] **Step 2: Написать test_unknown_update_reaches_outer_middleware.** Raw fixture: update_id=1, widget_query={id:"q1", from:{id:42,is_bot:false,first_name:"Test"}, chat:{id:42,type:"private"}, message_id:101, chat_instance:"test", type:{type:"data"}, data:"date:2026-11-20"}. Через Update.model_validate и feed_update проверить: raw целиком дошёл до callback, callback вызван один раз, стандартный router не вызван. Повторить с Update без mounted bot (roundtrip feed_update не теряет extra).
- [ ] **Step 3: Написать test_other_updates_passthrough.** Обычные message/callback_query через тот же middleware вызывают прежние обработчики по одному разу; raw Widget не требует event.event_type до перехвата. При несовместимости реального aiogram остановить интеграцию и предложить минимальную адаптацию extraction для его модели; не менять polling/Router архитектуру молча.
- [ ] **Step 4: Написать test_widget_methods_use_existing_session.** Fake session видит методы sendWidget/answerWidgetQuery, allow_queries=True, inline markup и точный JSON; возвращённый Message даёт message_id=101, ответ True разобран. Отдельно вызвать существующий AiohttpSession.build_form_data/check_response офлайн: сериализуются html/markup, неизвестное widget-поле ответа не мешает Message. Проверить ошибку API/таймаут не скрываются, answer.data >1024 отклоняется до отправки; ни новая ClientSession, ни native bot.send_widget не вызываются.
- [ ] **Step 5: Запустить RED.** `python -m unittest discover -s test/calendar_widget -p test_transport.py -v`; FAIL из-за отсутствующих новых модулей/методов, не aiogram как зависимости.
- [ ] **Step 6: Реализовать два метода/обёртки по Interfaces.** Транспорт использует текущий механизм ошибок aiogram; без скрытых retries.
- [ ] **Step 7: Реализовать CalendarWidgetMiddleware по Interfaces.** Только обнаружение/делегирование; subscription validation отсутствует здесь.
- [ ] **Step 8: Запустить GREEN и compatibility gate.** Та же команда; OK на фактической версии TrainBot. До PASS не переходить к bot.py.
- [ ] **Step 9: Коммит.** `git add widgets/__init__.py widgets/telegram_api.py widgets/middleware.py test/calendar_widget`; `git commit -m "feat: add isolated Telegram widget transport"`.

## Task 3: Универсальная карточка календаря (часть тикета 02)

**Files:** Create `widgets/calendar/__init__.py`, `config.py`, `render.py`, `calendar.html`, `calendar.css`, `calendar.js`, `test/calendar_widget/test_render.py`.

**Interfaces:**
- Consumes: только текущую дату/параметры календаря, без FSM, TrainNumber/id_sub/станций.
- Produces в render.py: `moscow_today() -> date`; `date_bounds(today: date) -> tuple[date, date]` читает DAYS_AHEAD; `validate_date(value: str, *, today: date) -> str` возвращает строгий канонический ISO либо ValueError; `render_calendar(*, today: date, selected_date: str | date | datetime | None) -> str` возвращает HTML либо ValueError при некорректной сборке/размере. Невалидный selected_date — отсутствие выбора, не ошибка сборки.
- HTML получает ровно minDate/maxDate/selectedDate из JSON в `const calendarConfig = ...`; null для отсутствующего выбора. Плейсхолдеры `__CALENDAR_CSS__`, `__CALENDAR_JS__`, `__CALENDAR_CONFIG__` заменяются однократно через str.replace, не format на JS/CSS со скобками. json.dumps(..., ensure_ascii=True), экранирование `<` как `\u003c` для script-контекста. Path(__file__).parent, encoding UTF-8, без зависимости от cwd.

- [ ] **Step 1: Написать тест границ.** Для today=date(2026,11,12) ожидать (`2026-11-12`,`2027-02-10`); validate_date принимает обе границы, отклоняет `2026-11-11`,`2027-02-11`,`2026-02-30`,`2026-2-01`. Изменение config.DAYS_AHEAD на 7 даёт верхнюю `2026-11-19`; использовать mock clock, не системную дату.
- [ ] **Step 2: Написать test_initial_selection и test_html_limits.** selected None/прошлая/за горизонтом → null и текущий месяц; допустимая `2027-01-20`/date(2027,1,20) → выбран день и его месяц. HTML содержит встроенные CSS/JS, правильный JSON, не содержит внешних src/href, необработанных плейсхолдеров и NUL. Для готового HTML проверить len(encode)<=32768 и len(zlib.compress(...,9))<=4096; отдельные oversized/NUL fixtures вызывают ValueError.
- [ ] **Step 3: Запустить RED.** `python -m unittest discover -s test/calendar_widget -p test_render.py -v`; ожидается отсутствие нового renderer.
- [ ] **Step 4: Реализовать config и функции render.py по Interfaces.** Moscow через ZoneInfo(TIMEZONE); если zoneinfo недоступен в runtime — не ставить tzdata скрытно, зафиксировать limitation и использовать имеющийся tz runtime; при невозможности сборки действует fallback. Сервер при подтверждении повторно вычисляет bounds, без отдельного сценария полуночи.
- [ ] **Step 5: Реализовать HTML/CSS.** Белая скруглённая карточка, заголовок «Выбор даты отправления», стрелки месяцев, сетка дней, синий выбранный день, строка даты, «Подтвердить», «Отмена», встроенная область ошибки. Width не фиксировать; карточка помещается в узком bubble. Не подменять отсутствующий исходный UI-образец заявлением о pixel-perfect совпадении.
- [ ] **Step 6: Реализовать JS.** Локальные месяцы/выбор, disabled за границами; без запросов при навигации. Даты считать по календарным компонентам/UTC, не через local timezone устройства. confirm disabled при null, при допустимом selected сразу enabled; подтверждение отправляет `date:`+ISO, отмена `cancel`. Перед запросом блокировать обе кнопки. Разбирать JSON.parse(answer.result); ok → завершённое состояние ожидания удаления, error → показать message; rejection BUSY/TIMEOUT/FAILED → «Не удалось подтвердить действие» и разблокировка допустимого выбора. Никаких таймеров синхронизации состояния или дополнительных запросов.
- [ ] **Step 7: Запустить GREEN.** Та же unittest-команда → OK; записать реальные измеренные размеры готового HTML, не оценку. Исполняемая проверка JS/клиентов будет в Task 6.
- [ ] **Step 8: Коммит.** `git add widgets/calendar test/calendar_widget/test_render.py`; `git commit -m "feat: add reusable calendar widget template"`.

## Task 4: Подтверждение календарём по полному пути (завершает тикет 02)

**Files:** Modify `handlers/subscrib.py:172–236`, `bot.py:35–73`, test support; Create `test/calendar_widget/test_flow.py`.

**Interfaces:**
- Consumes: Tasks 1–3; синхронный `dp.fsm.get_context(bot=bot,chat_id=...,user_id=...)`, затем await методов FSM.
- Produces в subscrib.py: `async open_departure_calendar(callback: types.CallbackQuery, state: FSMContext) -> None`; `async handle_calendar_query(raw: dict[str, Any], bot: Bot, dp: Dispatcher) -> None`; общий `_calendar_locks: dict[int, asyncio.Lock]` на пользователя, без внешних хранилищ.
- Минимальное расширение меню: `async prm_sub_otslej(message: types.Message | None, state: FSMContext, *, bot: Bot | None = None, chat_id: int | None = None) -> None`. Старые вызовы неизменны; при message=None отправлять ту же клавиатуру через bot.send_message(chat_id,...), не delete_try(None). Для Widget-пути очистить устаревший last_msg после его удаления, чтобы не задерживать меню на sleep(2). Не создавать фиктивный Message и не хранить исходный Message в FSM.
- В test support дополнить feed_callback(action,val,message_id), feed_query(data,query_id="q1",message_id=101,user_id=42,chat_id=42), counters методов/session и clock. В документации интерфейса fixture это keyword-аргументы, значения идентификаторов синтетические.

- [ ] **Step 1: Написать test_confirm_creates_date и test_confirm_edit_same_or_changed_date через Dispatcher.** Нажатие существующей кнопки даты отправляет sendWidget с ручной inline-кнопкой (её рабочий обработчик в Task 5), state StSubscr.dt_depart и active message 101; до подтверждения данные не меняются. date:2026-11-20 → ISO в FSM, state None, active keys отсутствуют, один answer с status ok, один deleteMessage(42,101), одно прежнее меню. При редактировании одинаковая дата сохраняет поезд/время/id_sub; другая дата очищает поезд/время, сохраняя id_sub и станции.
- [ ] **Step 2: Написать таблицу отказов test_invalid_or_stale_query.** Неверная/несуществующая/вне bounds дата, неизвестная команда, type.type != data, чужой пользователь/чат, mismatch message_id, state None/другой state, нет active id после рестарта → один error answer, нет изменения подписки и нет меню/удаления. Неверная дата оставляет активный Widget. Не логировать полное raw.
- [ ] **Step 3: Написать test_concurrent_confirm_applies_once.** asyncio.gather двух feed_query для одного активного сообщения; ждать оба. Ровно одно применение/удаление/меню, ответы ok и error, поезд сброшен один раз. Повторная доставка после завершения тоже не порождает меню. Другой пользователь не блокируется этим lock.
- [ ] **Step 4: Запустить RED.** `python -m unittest discover -s test/calendar_widget -p test_flow.py -v`; FAIL на отсутствующем Widget-пути.
- [ ] **Step 5: Расширить prm_sub_otslej по Interfaces.** Сохранить подписи/порядок/CallbackData существующих кнопок. Проверить старую и новую отправку на идентичный текст/markup.
- [ ] **Step 6: Реализовать открытие календаря.** В исходной ветке dt_depart делегировать open_departure_calendar. Под тем же user-lock погасить предыдущую activity, сохранить бизнес-поля, собрать/sendWidget, после успеха записать message/user/chat и state; старый Widget не получает новую активность. Не назначать активный id при неопределённой отправке. Полный fallback добавляется следующей задачей; этот коммит отдельно не выкатывать.
- [ ] **Step 7: Реализовать подтверждение handle_calendar_query.** Проверить private/from/chat/type/message, получить настоящий FSMContext; под user-lock заново прочитать state/data, проверить владельца/активность, validate_date(moscow_today()), применить Task 1 и удалить только active keys, set_state(None). Чтобы не ждать IO под lock, завершить защищённую секцию до answer/delete/menu. Если lock занят, ждать максимум 2 секунды; при таймауте — один error answer, никаких изменений. Это ограничение ожидания для окна 15 секунд, не новый слой защиты.
- [ ] **Step 8: Реализовать единственную точку ответа и cleanup.** На один доставленный query — одна попытка answerWidgetQuery с request_timeout=5; отказ без chat-сообщений. При успехе: сначала изменение FSM/погашение, затем answer, delete, menu. Ошибка answer не откатывает применённое; в finally выполнить успешный cleanup без второго answer. При ошибке delete всё равно показать меню; при ошибке меню сохранить данные/не активировать Widget, залогировать тип ошибки без retry. До применения исключение → error, бизнес-поля прежние. В обработке нет БД/поиска поездов до answer; вся нетривиальная IO после него. Измерить ответ <15 секунд в fake-сценариях занятости/ошибок; реальную доставку гарантировать невозможно.
- [ ] **Step 9: Подключить middleware и polling.** В bot.py после include_routers зарегистрировать CalendarWidgetMiddleware(subscrib.handle_calendar_query) через dp.update.outer_middleware(...); в main сохранить прежний Bot/proxy/finally и передать `allowed_updates=list(dict.fromkeys([*dp.resolve_used_update_types(), "widget_query"]))`. Не импортировать bot.py из handlers.
- [ ] **Step 10: Запустить GREEN.** Команда test_flow → OK; также `python -m unittest discover -s test/calendar_widget -p 'test_*.py' -v` → OK. Проверить регистрацию bot.py через подменённые зависимости, не запускать main.
- [ ] **Step 11: Коммит.** `git add bot.py handlers/subscrib.py test/calendar_widget`; `git commit -m "feat: confirm tracking dates through calendar widgets"`.

## Task 5: Отмена, ручной fallback и сбои (тикет 03)

**Files:** Modify `handlers/subscrib.py` (новые календарные функции/исходный ручной обработчик), `widgets/calendar/calendar.js` при выявленных сбоях; Create `test/calendar_widget/test_fallback.py`.

**Interfaces:**
- Consumes: active keys, тот же lock, query answer/cleanup из Task 4, существующий ручной handler из Task 1.
- Produces: `async start_manual_departure(message: types.Message, state: FSMContext) -> None` — прежнее приглашение, last_msg, StSubscr.dt_depart; `async select_calendar_manual(callback: types.CallbackQuery, callback_data: MyCallback, state: FSMContext) -> None` — новый callback только с action `sub_otsl_calendar_manual`, val `open`. Это отдельный обработчик кнопки, не новый текстовый обработчик.
- При переходе вручную обязательно проверить state/владельца/chat/message под тем же lock; погасить календарь, удалить сообщение, вызвать start_manual_departure. После неуспешного sendWidget вызывать тот же start_manual_departure без требования active id.

- [ ] **Step 1: Написать test_cancel_keeps_existing_draft.** query cancel при активном Widget → data бизнес-полей полностью равен прежнему (включая старую недопустимую дату), state None, active keys удалены, ok answer/delete/menu ровно по одному. Вторая отмена/подтверждение → только error.
- [ ] **Step 2: Написать test_manual_button_uses_existing_handler.** inline callback соответствующего сообщения → календарь погашен/удалён, приглашение и StSubscr.dt_depart; последующий текст идёт через прежний router.message. Старый/чужой callback не выключает новый календарь; answerCallbackQuery завершает spinner, без лишнего меню.
- [ ] **Step 3: Написать test_send_failure_falls_back_once.** Сборка oversized, отклонение API и timeout sendWidget → одна попытка отправки (при ошибке сборки ноль), нет active id, дата/поезд/время/id_sub/станции прежние, ровно одно текстовое приглашение. При ошибке и приглашения — не объявлять успешный переход, state None, поля прежние, безопасный log; никаких retries.
- [ ] **Step 4: Написать test_cleanup_failures_do_not_reapply и test_manual_widget_race.** answer timeout/delete error/menu error после успешного применения не восстанавливают календарь/дату; повторный query не создаёт меню. Под asyncio.gather чередовать cancel/confirm/manual callback и текст/confirm; только первый актуальный путь меняет дату, остальные не вмешиваются. В текстовом обработчике после lock заново проверить state: raw_state фильтра мог устареть, когда callback уже завершил FSM.
- [ ] **Step 5: Запустить RED.** `python -m unittest discover -s test/calendar_widget -p test_fallback.py -v`; FAIL на отсутствующей cancel/manual ветке.
- [ ] **Step 6: Добавить cancel в handle_calendar_query.** Та же авторизация/lock, без apply_departure_date, снять activity/set_state(None); переиспользовать одну точку answer/cleanup/меню. При недопустимой дате календарь оставить активным.
- [ ] **Step 7: Добавить start_manual_departure и callback по Interfaces.** Сохранить точный текст существующего приглашения. При открытии календаря подставить MyCallback(action='sub_otsl_calendar_manual',val='open') в inline-кнопку; callback action не пересекается с booking/otslej_15.
- [ ] **Step 8: Подключить fallback к ошибке сборки/sendWidget.** Погасить только служебную activity, отправить приглашение; устанавливать StSubscr.dt_depart и last_msg после успешной отправки приглашения. При ошибке приглашения установить state None и безопасно залогировать сбой, бизнес-данные не трогать. Не делать никаких повторов отправки.
- [ ] **Step 9: Защитить существующий текстовый handler тем же user-lock.** После захвата повторно проверить StSubscr.dt_depart, при активном календаре погасить его и завершить очистку после ответа; если state уже завершён другим действием, не применять текст и не создавать второе меню. Это ограниченная сериализация одного сценария, без глобального изменения FSM isolation. Сохранить неверный ввод/предупреждение/меню из Task 1.
- [ ] **Step 10: Запустить GREEN.** test_fallback, затем весь `test/calendar_widget` → OK. Убедиться, что технические поля удалены перед save_otslej, данные других подписок не меняются.
- [ ] **Step 11: Коммит.** `git add handlers/subscrib.py widgets/calendar/calendar.js test/calendar_widget`; `git commit -m "feat: finish calendar cancellation and manual fallback"`.

## Task 6: Совместимость и приёмка (тикет 04)

**Files:** Create `test/calendar_widget/test_regression.py`, `docs/testing/calendar-widget.md`; Modify только конкретные новые файлы/точки интеграции при обнаруженной регрессии, с отдельным RED/GREEN для исправления.

**Interfaces:**
- Consumes: полный путь Tasks 1–5; настоящие subscribe handlers и callback значения, fake DB/поиск поездов/session.
- Produces: воспроизводимый набор офлайн-регрессий и документ результатов, где отдельно указаны локальные тесты и реальные Telegram-клиенты. Этап не выполняется при составлении плана.

- [ ] **Step 1: Написать test_existing_tracking_workflows.** Через feed_update проверить создание без id_sub/редактирование с id_sub=7; apply новой даты сбрасывает поезд, before_save возвращает в параметры без сохранения до выбора нового поезда; set_NumTrain получает новую dt_depart/те же станции, select_NumTrain записывает новый номер/время. После выбора save_otslej вызывает прежний insert либо update ровно один раз и state.clear. Fake DB не принимает calendar_* поля.
- [ ] **Step 2: Написать test_noncalendar_routes_unchanged.** Message/callback booking/otslej_15/grand_servs без widget_query достигают прежнего router, не получают Widget-ответов; исходные state/filter значения и набор resolved update types сохранены. Проверить разрешённый polling список: прежние типы включены, widget_query ровно один раз, один polling, прежнее закрытие Bot-session. Для сохранения подписок прогнать ранее использованные callback кнопок, не их фиктивные имитации.
- [ ] **Step 3: Запустить RED/GREEN для регрессий.** `python -m unittest discover -s test/calendar_widget -p test_regression.py -v`. При PASS с первого раза зафиксировать это честно — не ломать рабочий код ради RED. При реальном FAIL исправить только выявленный дефект и повторить узкий тест, затем полный suite.
- [ ] **Step 4: Проверить JS исполняемо в имеющемся браузере без установки инструментария.** Открыть сформированный HTML во временном preview с маленьким тестовым TelegramWidget.request stub (не включать stub в отправляемый HTML). Просмотреть новый/предвыбранный/недопустимый selected; навигацию через декабрь/январь и февраль; disabled дней/bounds/confirm; отсутствие запросов до подтверждения; точные date:/cancel; pending/error/rejection/unblock. Отметить результат каждого кейса. Если доступен уже установленный JS/browser test runner, автоматизировать эти же assertions без добавления зависимости; иначе записать ручную процедуру/фактические результаты.
- [ ] **Step 5: Выполнить офлайн-проверки в подтверждённой среде.** `python -m unittest discover -s test/calendar_widget -p 'test_*.py' -v`; `python -m compileall -q widgets test/calendar_widget handlers/subscrib.py bot.py`; `git diff --check`. Ожидается OK/exit 0. Записать Python/aiogram/pydantic, размеры HTML и список проверок в docs/testing. Не запускать `unittest discover -s test` целиком.
- [ ] **Step 6: Провести Telegram-приёмку только на согласованном тестовом боте/чате.** Новая/редактируемая подписка: допустимая дата сразу выбрана, недопустимая старая — null, одинаковая сохраняет поезд, новая сбрасывает; отмена сохраняет старое; fallback/ручной неверный ввод; двойной клик, старый Widget после рестарта; реальные confirm/cancel ответы и удаление. Проверить Android/iOS/Desktop доступных версий, узкий экран и тёмную тему; отдельно клиент без поддержки Widget и доступность inline-кнопки. При недоступном клиенте отметить NOT RUN, не PASS. Не проводить платёж/бронь/production-сохранение ради проверки.
- [ ] **Step 7: Зафиксировать ограничения приёмки.** Оригинальное согласованное изображение в GitHub не приложено; проверить все текстовые UI-требования, точное визуальное совпадение отложить до наличия образца. Если старый клиент реально скрывает inline-кнопку вместе с Widget, зафиксировать объективное противоречие и предложить минимальное изменение: отдельное обычное сообщение с той же ручной кнопкой; не менять утверждённый UI без согласования.
- [ ] **Step 8: Коммит проверок.** `git add test/calendar_widget/test_regression.py docs/testing/calendar-widget.md`; `git commit -m "test: verify calendar and existing tracking workflows"`. При наличии исправлений перечислить их файлы отдельно, не git add -A.

## Самопроверка плана (проведена при подготовке)

- Покрытие требований §2.1–19: универсальность/диапазон/UI/начальный выбор — Task 3; FSM/подтверждение/сброс поезда/меню — Tasks 1,4; отмена/удаление/fallback/ошибочный ввод — Task 5; совместимость и клиенты — Task 6.
- Покрытие архитектуры §3.1–3.12: адаптер/middleware — Task 2, подключение — Task 4; общая дата — Task 1; привязка/повторы/lock — Tasks 4,5; сборка/запросы — Task 3; ответы и ошибки — Tasks 4,5.
- Signatures и поля согласованы между задачами; widgets не импортирует subscriptions; не предлагаются фиктивные Telegram Message. Меню использует расширенный обратно совместимый интерфейс. Офлайн-проба подтверждает только перечисленные контракты aiogram 3.22.0; полный runtime-suite и Telegram E2E ещё не выполнялись.
- Пять Review Focus привязаны к именованным тестам/процедурам. Assertions проверяют пользовательский результат, а не количество приватных вызовов.
- План задаёт решения, команды RED/GREEN и границы файлов, не содержит реализации функции календаря. Точный runtime compatibility остаётся обязательным gate, не выдан за PASS.

## Передача плана

Планирование завершено; код приложения, файлы тестов и зависимости не изменялись, бот не запускался. Выполнена только описанная ограниченная офлайн-проба совместимости aiogram с синтетическими данными. Проверки Task 1–6 — будущие действия, а не результаты текущей сессии. Перед реализацией пользователь отдельно проверяет план, утверждает объём и затрагиваемые runtime-файлы.

Рекомендация для последующего исполнения — **Native** через superpowers:executing-plans: шесть задач тесно связаны одной FSM и общей подписочной логикой; сохранение контекста уменьшит ошибки интерфейсов. Альтернатива — **Subagent-driven**: отдельные implementer/reviewer на задачу, затем обзор всей ветки; больше независимых проверок и контекстов. Выбор метода и разрешение программировать сейчас не запрашиваются как уже полученные: их нужно дать отдельно. После выдачи документов остановиться.
