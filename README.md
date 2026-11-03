# Архив испытаний Skill `langgraph-agent-architect`

**Эта ветка предназначена для хранения истории разработки, отладки и поведенческих испытаний Skill `langgraph-agent-architect`.** Она не является рабочей веткой и не предназначена для слияния с `main` целиком.

В архиве сохранены тестовые сценарии, задания для Codex Desktop, раннер, отчёты, оценки, ответы LLM и трассы вызовов инструментов. Материалы позволяют восстановить причины ошибок и результаты исправлений, а также повторить проверки по методике `superpowers:writing-skills` (RED–GREEN–REFACTOR).

## Основные материалы

- [Skill в тестовой ветке](.agents/skills/langgraph-agent-architect/SKILL.md) — версия, прошедшая испытания.
- [Тестовые сценарии](.agents/skills/langgraph-agent-architect/tests/scenarios.md) — набор S1–S13.
- [Отчёт первого цикла](.agents/skills/langgraph-agent-architect/tests/eval-report.md) — первоначальная оценка и обнаруженные ошибки.
- [Отчёт второго цикла](.agents/skills/langgraph-agent-architect/tests/eval-report-2.md) — повторные проверки S7, S10 и регрессий.
- [Отчёт третьего цикла](.agents/skills/langgraph-agent-architect/tests/eval-report-3.md) — итоговая серия: **25/25 PASS** по S7, S8, S9, S10, S12.
- [Результаты и трассы](.agents/skills/langgraph-agent-architect/tests/results/) — артефакты независимых LLM-сессий.
- [Тестовый раннер](.agents/skills/langgraph-agent-architect/tests/run_eval.py) — воспроизведение проверок в Codex CLI.

## Рабочая версия

Актуальный Skill для использования находится в основной ветке:

[**`main/.agents/skills/langgraph-agent-architect/SKILL.md`**](https://github.com/VetrovDmitry007/Codex/blob/main/.agents/skills/langgraph-agent-architect/SKILL.md).

**Не переносите тестовые артефакты из этой ветки в `main`**: они сохранены исключительно для истории и воспроизводимости испытаний. При использовании архивных трасс учитывайте, что результаты получены в конкретной среде и не гарантируют аналогичное поведение всех моделей.
