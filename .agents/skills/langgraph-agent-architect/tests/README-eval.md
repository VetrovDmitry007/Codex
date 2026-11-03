# Запуск модельной оценки Skill

Runner `run_eval.py` выполняет 46 независимых Codex CLI сессий: 13 сценариев в CONTROL и TREATMENT, а также по пять независимых повторов для двух критических правил в каждой группе.

Требования: Codex CLI с действующей авторизацией в ChatGPT, Python 3 (только стандартная библиотека), доступ к модели `gpt-6-luna`. Для каждой сессии создаётся отдельный временный каталог с нейтральным именем. CONTROL физически не содержит проверяемого Skill; TREATMENT загружает его через `AGENTS.md`. Сессии запускаются с `--sandbox read-only`; пользовательская конфигурация игнорируется, а переменные привязки к текущему чату очищаются.

Среда-хост сохранила read-only GitHub MCP-инструменты даже после удаления переменной `CODEX_APP_TOOLS_PIPE_PATH`. Это не отключило сетевое чтение. Тестовые инструкции запрещали записи; просмотр JSONL-трасс не выявил write-вызовов. Этот факт следует учитывать при воспроизведении и сравнении условий.

Из корня клона:

```bash
python3 .agents/skills/langgraph-agent-architect/tests/run_eval.py --run-label baseline
```

Runner не выставляет оценки автоматически. Итоговые PASS/FAIL/BLOCKED определяются по фактическим ответам в `results/` и критериям `scenarios.md`. Сводные оценки первого цикла: [`scorecard.md`](scorecard.md), отчёт: [`eval-report.md`](eval-report.md).

Для выборочных независимых повторов используйте `--only`, `--variant` и `--repeat-case CASE=COUNT`. Например, команда ниже запускает пять отдельных treatment-сессий сценария S7 в каталоге второго цикла:

```bash
python3 .agents/skills/langgraph-agent-architect/tests/run_eval.py \
  --run-label refactor-2 \
  --only S07-main \
  --repeat-case S07-main=5 \
  --variant treatment
```

Для нескольких сценариев повторите `--repeat-case` для каждого имени. Сценарии, не перечисленные в параметре повторов, запускаются один раз. Отчёт второго цикла и его оценки находятся в [`eval-report-2.md`](eval-report-2.md) и [`scorecard-2.md`](scorecard-2.md).
