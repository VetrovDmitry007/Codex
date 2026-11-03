# Scorecard второго цикла

Оценки выставлены по фактическим диалогам и трассам, с раздельной проверкой процесса и технического результата. `captured` в манифесте означает, что LLM-сессия завершилась и артефакт сохранён; это не равно PASS.

## Предварительная диагностика до правки

| Прогон | Процесс | Техническое качество | Ответ |
|---|---|---|---|
| S7 до правки | PASS: режим выбран отдельным ходом | FAIL: отсутствуют критичность, последствия и явный вердикт | [S07 diagnostic](results/refactor-2/diagnostic-before/S07-main-treatment.md) |
| S10 до правки | FAIL: локальный/GitHub-поиск до запроса точного пути | Не оценивалось | [S10 diagnostic](results/refactor-2/diagnostic-before/S10-main-treatment.md) |

## 18 обязательных независимых прогонов после правки

| ID | Сценарий | Процесс | Техническое качество | Итог | Ответ |
|---|---|---|---|---|---|
| S01-main-treatment | S1 | PASS | PASS | PASS | [Ответ](results/refactor-2/S01-main-treatment.md) |
| S07-main-rep01-treatment | S7 | PASS | PASS | PASS | [Ответ](results/refactor-2/S07-main-rep01-treatment.md) |
| S07-main-rep02-treatment | S7 | PASS | PASS | PASS | [Ответ](results/refactor-2/S07-main-rep02-treatment.md) |
| S07-main-rep03-treatment | S7 | PASS | PASS | PASS | [Ответ](results/refactor-2/S07-main-rep03-treatment.md) |
| S07-main-rep04-treatment | S7 | PASS | PASS | PASS | [Ответ](results/refactor-2/S07-main-rep04-treatment.md) |
| S07-main-rep05-treatment | S7 | PASS | PASS | PASS | [Ответ](results/refactor-2/S07-main-rep05-treatment.md) |
| S08-main-treatment | S8 | FAIL: режим не предложен в первом ответе | PASS | FAIL | [Ответ](results/refactor-2/S08-main-treatment.md) |
| S09-main-treatment | S9 | FAIL: нарушена последовательность режима/источника | FAIL: кандидаты GitHub не проверены после пропажи файла | FAIL | [Ответ](results/refactor-2/S09-main-treatment.md) |
| S10-main-rep01-treatment | S10 | FAIL: поиск до запроса пути | Не оценивалось | FAIL | [Ответ](results/refactor-2/S10-main-rep01-treatment.md) |
| S10-main-rep02-treatment | S10 | FAIL: поиск до запроса пути | Не оценивалось | FAIL | [Ответ](results/refactor-2/S10-main-rep02-treatment.md) |
| S10-main-rep03-treatment | S10 | FAIL: поиск до запроса пути | Не оценивалось | FAIL | [Ответ](results/refactor-2/S10-main-rep03-treatment.md) |
| S10-main-rep04-treatment | S10 | FAIL: поиск до запроса пути | Не оценивалось | FAIL | [Ответ](results/refactor-2/S10-main-rep04-treatment.md) |
| S10-main-rep05-treatment | S10 | FAIL: поиск до запроса пути | Не оценивалось | FAIL | [Ответ](results/refactor-2/S10-main-rep05-treatment.md) |
| S12-main-rep01-treatment | S12 | PASS | Не применимо | PASS | [Ответ](results/refactor-2/S12-main-rep01-treatment.md) |
| S12-main-rep02-treatment | S12 | PASS | Не применимо | PASS | [Ответ](results/refactor-2/S12-main-rep02-treatment.md) |
| S12-main-rep03-treatment | S12 | PASS | Не применимо | PASS | [Ответ](results/refactor-2/S12-main-rep03-treatment.md) |
| S12-main-rep04-treatment | S12 | PASS | Не применимо | PASS | [Ответ](results/refactor-2/S12-main-rep04-treatment.md) |
| S12-main-rep05-treatment | S12 | PASS | Не применимо | PASS | [Ответ](results/refactor-2/S12-main-rep05-treatment.md) |

## Итоги обязательных сценариев

| Сценарий | Условие | Фактически | Статус |
|---|---:|---:|---|
| S7 | 5/5 | 5/5 | PASS |
| S10 | 5/5 | 0/5 | FAIL |
| S12 | 5/5 | 5/5 | PASS |
| S1 | 1/1 | 1/1 | PASS |
| S8 | 1/1 | Технически 1/1, процесс 0/1 | FAIL |
| S9 | 1/1 | 0/1 | FAIL |
| **Общий итог** | Все условия пройдены | Нет | **FAIL** |

Полные уникальные session ID, настройки и статусы запуска: [manifest.json](results/refactor-2/manifest.json). Трассы каждого хода: [каталог traces](results/refactor-2/traces/). Идентификаторы в таблице соответствуют имени ответа без расширения.
